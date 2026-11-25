"""
Vistas delgadas: la lógica de negocio vive en los modelos (ciclo de vida del
pedido) y en los serializadores (validación). Todo el CRUD usa ViewSets; los
endpoints no estándar se declaran con @action (Guía, Paso 3).
"""
from django.db import transaction
from django.db.models import Avg, Count, Q
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAdminUser, IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response

from .filters import PedidoFilter, ProductoFilter
from .models import Categoria, ConflictoDeEstado, Pedido, Producto, Productor, Resena
from .pagination import PaginacionResenas
from .permissions import AutorOStaff, ProductorDuenoOStaff, SoloLecturaOStaff
from .serializers import (
    CategoriaSerializer,
    PedidoSerializer,
    ProductoSerializer,
    ProductorSerializer,
    ReponerStockSerializer,
    ResenaSerializer,
    ValidarCuponSerializer,
)


class ConflictoAPI(APIException):
    """HTTP 409: la operación choca con el estado actual del recurso."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "La operación no es válida para el estado actual del recurso."
    default_code = "conflicto_de_estado"


# --------------------------------------------------------------------------
# Productores y categorías
# --------------------------------------------------------------------------
class ProductorViewSet(viewsets.ModelViewSet):
    """Productores registrados. Lectura pública; alta/edición solo personal administrativo."""

    serializer_class = ProductorSerializer
    permission_classes = [SoloLecturaOStaff]   # endurece el default global (justificado)
    filterset_fields = ["region", "certificacion"]
    lookup_field = "slug"
    lookup_value_regex = r"[-\w]+"
    search_fields = ["nombre", "distrito"]
    ordering_fields = ["nombre", "creado", "total_productos"]
    ordering = ["nombre"]

    def get_queryset(self):
        qs = Productor.objects.annotate(
            total_productos=Count("productos", filter=Q(productos__estado=Producto.Estado.ACTIVO))
        )
        return qs if self.request.user.is_staff else qs.filter(activo=True)


class CategoriaViewSet(viewsets.ModelViewSet):
    serializer_class = CategoriaSerializer
    permission_classes = [SoloLecturaOStaff]
    queryset = Categoria.objects.select_related("padre").prefetch_related("hijos")
    lookup_field = "slug"
    lookup_value_regex = r"[-\w]+"
    search_fields = ["nombre"]
    ordering_fields = ["nombre"]
    pagination_class = None   # árbol pequeño y acotado: se entrega completo


# --------------------------------------------------------------------------
# Productos
# --------------------------------------------------------------------------
class ProductoViewSet(viewsets.ModelViewSet):
    """Catálogo de productos con calificación promedio calculada en base de datos."""

    serializer_class = ProductoSerializer
    permission_classes = [ProductorDuenoOStaff]
    filterset_class = ProductoFilter
    lookup_field = "slug"
    lookup_value_regex = r"[-\w]+"
    search_fields = ["nombre", "descripcion", "productor__nombre", "categoria__nombre"]
    ordering_fields = ["precio", "creado", "nombre", "stock", "fecha_cosecha", "calificacion_promedio"]
    ordering = ["-creado", "id"]

    def get_queryset(self):
        # select_related evita N+1; las anotaciones evitan contar/promediar en Python.
        qs = Producto.objects.select_related("productor", "categoria").annotate(
            calificacion_promedio=Avg("resenas__puntuacion"),
            num_resenas=Count("resenas", distinct=True),
        )
        user = self.request.user
        if user.is_staff:
            return qs
        visible = ~Q(estado=Producto.Estado.BORRADOR)   # los borradores no son públicos
        if user.is_authenticated:
            visible |= Q(productor__usuario=user)       # ...salvo para su propio productor
        return qs.filter(visible)

    @extend_schema(methods=["GET"], responses=ResenaSerializer(many=True))
    @extend_schema(methods=["POST"], request=ResenaSerializer, responses={201: ResenaSerializer})
    @action(
        detail=True, methods=["get", "post"], url_path="resenas", url_name="resenas",
        permission_classes=[IsAuthenticatedOrReadOnly], filter_backends=[],
        pagination_class=PaginacionResenas,
    )
    def resenas(self, request, slug=None):
        """GET lista las reseñas del producto; POST crea una (solo si recibiste el producto)."""
        producto = self.get_object()
        if request.method == "POST":
            ctx = {**self.get_serializer_context(), "producto": producto}
            serializer = ResenaSerializer(data=request.data, context=ctx)
            serializer.is_valid(raise_exception=True)
            serializer.save(producto=producto, autor=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        queryset = producto.resenas.select_related("autor", "producto")
        pagina = self.paginate_queryset(queryset)
        ctx = self.get_serializer_context()
        if pagina is not None:
            return self.get_paginated_response(ResenaSerializer(pagina, many=True, context=ctx).data)
        return Response(ResenaSerializer(queryset, many=True, context=ctx).data)

    @extend_schema(responses=ProductoSerializer(many=True))
    @action(detail=False, methods=["get"], filter_backends=[])
    def destacados(self, request):
        """Top 5 activos con al menos 2 reseñas, ordenados por calificación."""
        qs = (
            self.get_queryset()
            .filter(estado=Producto.Estado.ACTIVO, num_resenas__gte=2)
            .order_by("-calificacion_promedio", "-num_resenas")[:5]
        )
        return Response(ProductoSerializer(qs, many=True, context=self.get_serializer_context()).data)

    @extend_schema(request=ReponerStockSerializer, responses=ProductoSerializer)
    @action(detail=True, methods=["post"], url_path="reponer-stock", url_name="reponer-stock")
    def reponer_stock(self, request, slug=None):
        """Suma unidades al stock; si estaba agotado vuelve a 'activo'."""
        producto = self.get_object()
        entrada = ReponerStockSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        if producto.estado in (Producto.Estado.DESCONTINUADO, Producto.Estado.BORRADOR):
            raise ConflictoAPI(f"No se repone stock de un producto en estado '{producto.estado}'.")
        with transaction.atomic():
            bloqueado = Producto.objects.select_for_update().get(pk=producto.pk)
            bloqueado.stock += entrada.validated_data["cantidad"]
            if bloqueado.estado == Producto.Estado.AGOTADO:
                bloqueado.estado = Producto.Estado.ACTIVO
            bloqueado.save(update_fields=["stock", "estado", "actualizado"])
        producto = self.get_queryset().get(pk=producto.pk)
        return Response(ProductoSerializer(producto, context=self.get_serializer_context()).data)


class ResenaViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet
):
    """Consulta y moderación de reseñas. La creación ocurre en /productos/{slug}/resenas/."""

    serializer_class = ResenaSerializer
    permission_classes = [IsAuthenticatedOrReadOnly, AutorOStaff]
    queryset = Resena.objects.select_related("producto", "autor")
    filterset_fields = {"puntuacion": ["exact", "gte", "lte"], "producto__slug": ["exact"]}
    ordering_fields = ["creado", "puntuacion"]
    ordering = ["-creado"]
    pagination_class = PaginacionResenas


# --------------------------------------------------------------------------
# Pedidos
# --------------------------------------------------------------------------
class PedidoViewSet(
    mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Pedidos del cliente autenticado (el personal ve todos)."""

    serializer_class = PedidoSerializer
    permission_classes = [IsAuthenticated]   # los pedidos nunca son públicos
    filterset_class = PedidoFilter
    search_fields = ["ciudad", "items__producto__nombre"]
    ordering_fields = ["creado", "total"]
    ordering = ["-creado"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):   # generación de esquema OpenAPI
            return Pedido.objects.none()
        qs = Pedido.objects.select_related("cliente", "cupon").prefetch_related("items__producto")
        user = self.request.user
        return qs if user.is_staff else qs.filter(cliente=user)

    def _transicion(self, operacion):
        pedido = self.get_object()
        try:
            getattr(pedido, operacion)()
        except ConflictoDeEstado as exc:
            raise ConflictoAPI(str(exc))
        return Response(self.get_serializer(pedido).data)

    @extend_schema(request=None, responses={200: PedidoSerializer, 409: OpenApiResponse(description="Estado inválido")})
    @action(detail=True, methods=["post"])
    def pagar(self, request, pk=None):
        """Registra el pago (simulado) de un pedido pendiente."""
        return self._transicion("pagar")

    @extend_schema(request=None, responses={200: PedidoSerializer, 409: OpenApiResponse(description="Estado inválido")})
    @action(detail=True, methods=["post"])
    def cancelar(self, request, pk=None):
        """Cancela un pedido pendiente/pagado y devuelve el stock reservado."""
        return self._transicion("cancelar")

    @extend_schema(request=None, responses={200: PedidoSerializer, 409: OpenApiResponse(description="Estado inválido")})
    @action(detail=True, methods=["post"], permission_classes=[IsAdminUser])
    def avanzar(self, request, pk=None):
        """(Staff) pagado → enviado → entregado."""
        return self._transicion("avanzar")

    @extend_schema(request=ValidarCuponSerializer, responses={200: OpenApiResponse(description="Descuento calculado")})
    @action(detail=False, methods=["post"], url_path="validar-cupon", url_name="validar-cupon")
    def validar_cupon(self, request):
        """Previsualiza el descuento de un cupón sin crear el pedido."""
        entrada = ValidarCuponSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        cupon, subtotal = entrada.validated_data["cupon"], entrada.validated_data["subtotal"]
        descuento = cupon.descuento_para(subtotal)
        return Response(
            {"codigo": cupon.codigo, "porcentaje": cupon.porcentaje,
             "descuento": f"{descuento:.2f}", "subtotal_con_descuento": f"{subtotal - descuento:.2f}"}
        )
