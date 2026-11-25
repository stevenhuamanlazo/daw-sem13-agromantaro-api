"""
Serializadores de la API.

Principios (Guía, Paso 2):
* ``fields`` siempre explícito: nunca se exponen ``password``, ``is_staff`` ni el
  ``usuario`` interno de un productor.
* La validación vive aquí (``validate_<campo>`` y ``validate``), no en las vistas.
* HATEOAS: cada recurso incluye ``url`` hipervinculada y un bloque ``_links``
  que cambia según el estado del recurso (p. ej. un pedido pagado ya no ofrece
  el enlace ``pagar``).
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.reverse import reverse

from .models import Categoria, Cupon, ItemPedido, Pedido, Producto, Productor, Resena


def _link(nombre_ruta, request, metodo="GET", **kwargs):
    return {"href": reverse(nombre_ruta, kwargs=kwargs or None, request=request), "method": metodo}


# --------------------------------------------------------------------------
# Productores y categorías
# --------------------------------------------------------------------------
class ProductorSerializer(serializers.HyperlinkedModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="productor-detail", lookup_field="slug")
    certificacion_display = serializers.CharField(source="get_certificacion_display", read_only=True)
    region_display = serializers.CharField(source="get_region_display", read_only=True)
    total_productos = serializers.SerializerMethodField(help_text="Productos activos publicados.")
    _links = serializers.SerializerMethodField()

    class Meta:
        model = Productor
        fields = (
            "url", "id", "slug", "nombre", "region", "region_display", "distrito",
            "certificacion", "certificacion_display", "activo", "total_productos", "_links",
        )
        read_only_fields = ("slug",)

    @extend_schema_field(OpenApiTypes.INT)
    def get_total_productos(self, obj):
        # Usa la anotación del queryset (1 sola consulta); si no existe, cuenta.
        valor = getattr(obj, "total_productos", None)
        return valor if valor is not None else obj.productos.filter(estado="activo").count()

    @extend_schema_field(serializers.DictField())
    def get__links(self, obj):
        req = self.context.get("request")
        catalogo = reverse("producto-list", request=req) + f"?productor={obj.slug}"
        return {
            "self": _link("productor-detail", req, slug=obj.slug),
            "productos": {"href": catalogo, "method": "GET"},
        }


class CategoriaSerializer(serializers.HyperlinkedModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="categoria-detail", lookup_field="slug")
    padre = serializers.HyperlinkedRelatedField(
        view_name="categoria-detail", lookup_field="slug",
        queryset=Categoria.objects.all(), allow_null=True, required=False,
    )
    hijos = serializers.HyperlinkedRelatedField(
        many=True, read_only=True, view_name="categoria-detail", lookup_field="slug"
    )
    _links = serializers.SerializerMethodField()

    class Meta:
        model = Categoria
        fields = ("url", "id", "slug", "nombre", "padre", "hijos", "_links")
        read_only_fields = ("slug",)

    @extend_schema_field(serializers.DictField())
    def get__links(self, obj):
        req = self.context.get("request")
        arbol = reverse("producto-list", request=req) + f"?categoria_arbol={obj.slug}"
        return {"self": _link("categoria-detail", req, slug=obj.slug),
                "productos": {"href": arbol, "method": "GET"}}


# --------------------------------------------------------------------------
# Productos
# --------------------------------------------------------------------------
class ProductoSerializer(serializers.HyperlinkedModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name="producto-detail", lookup_field="slug")
    productor = serializers.HyperlinkedRelatedField(
        view_name="productor-detail", lookup_field="slug",
        queryset=Productor.objects.filter(activo=True),
    )
    categoria = serializers.HyperlinkedRelatedField(
        view_name="categoria-detail", lookup_field="slug", queryset=Categoria.objects.all()
    )
    productor_nombre = serializers.ReadOnlyField(source="productor.nombre")
    categoria_nombre = serializers.ReadOnlyField(source="categoria.nombre")
    calificacion_promedio = serializers.SerializerMethodField()
    num_resenas = serializers.SerializerMethodField()
    disponible = serializers.BooleanField(read_only=True)
    _links = serializers.SerializerMethodField()

    class Meta:
        model = Producto
        fields = (
            "url", "id", "slug", "nombre", "descripcion", "precio", "unidad", "stock",
            "estado", "es_organico", "fecha_cosecha", "productor", "productor_nombre",
            "categoria", "categoria_nombre", "calificacion_promedio", "num_resenas",
            "disponible", "creado", "actualizado", "_links",
        )
        read_only_fields = ("slug", "creado", "actualizado")

    # -- Campos calculados --------------------------------------------------
    @extend_schema_field(OpenApiTypes.FLOAT)
    def get_calificacion_promedio(self, obj):
        valor = getattr(obj, "calificacion_promedio", None)
        return round(float(valor), 2) if valor is not None else None

    @extend_schema_field(OpenApiTypes.INT)
    def get_num_resenas(self, obj):
        valor = getattr(obj, "num_resenas", None)
        return valor if valor is not None else obj.resenas.count()

    @extend_schema_field(serializers.DictField())
    def get__links(self, obj):
        req = self.context.get("request")
        enlaces = {
            "self": _link("producto-detail", req, slug=obj.slug),
            "productor": _link("productor-detail", req, slug=obj.productor.slug),
            "categoria": _link("categoria-detail", req, slug=obj.categoria.slug),
            "resenas": _link("producto-resenas", req, slug=obj.slug),
        }
        if obj.disponible:  # solo se ofrece la acción de compra si el estado lo permite
            enlaces["comprar"] = _link("pedido-list", req, metodo="POST")
        return enlaces

    # -- Validación de campo ------------------------------------------------
    def validate_nombre(self, valor):
        valor = " ".join(valor.split())
        if len(valor) < 3:
            raise serializers.ValidationError("El nombre debe tener al menos 3 caracteres.")
        return valor

    def validate_precio(self, valor):
        if valor > Decimal("5000"):
            raise serializers.ValidationError("El precio unitario no puede superar S/ 5 000.")
        return valor

    # -- Validación cruzada (varios campos + contexto) ---------------------
    def validate(self, attrs):
        instancia = self.instance
        productor = attrs.get("productor") or (instancia.productor if instancia else None)
        estado = attrs.get("estado", instancia.estado if instancia else Producto.Estado.BORRADOR)
        stock = attrs.get("stock", instancia.stock if instancia else 0)
        organico = attrs.get("es_organico", instancia.es_organico if instancia else False)
        cosecha = attrs.get("fecha_cosecha", instancia.fecha_cosecha if instancia else None)
        errores = {}

        if estado == Producto.Estado.ACTIVO and stock == 0:
            errores["estado"] = "Un producto activo necesita stock > 0; use 'agotado' o reponga stock."
        if estado == Producto.Estado.AGOTADO and stock > 0:
            errores["stock"] = "Un producto 'agotado' no puede tener stock; use 'activo'."
        if cosecha and cosecha > timezone.localdate():
            errores["fecha_cosecha"] = "La fecha de cosecha no puede estar en el futuro."
        if organico and productor and productor.certificacion == Productor.Certificacion.NINGUNA:
            errores["es_organico"] = (
                "Solo productores con certificación (SENASA, PGS o Comercio Justo) "
                "pueden marcar un producto como orgánico."
            )

        request = self.context.get("request")
        if request and productor and not request.user.is_staff:
            if productor.usuario_id != request.user.id:
                errores["productor"] = "Solo puedes publicar bajo tu propio perfil de productor."

        if errores:
            raise serializers.ValidationError(errores)
        return attrs


class ReponerStockSerializer(serializers.Serializer):
    cantidad = serializers.IntegerField(min_value=1, max_value=10000)


# --------------------------------------------------------------------------
# Reseñas verificadas
# --------------------------------------------------------------------------
class ResenaSerializer(serializers.HyperlinkedModelSerializer):
    producto = serializers.HyperlinkedRelatedField(
        view_name="producto-detail", lookup_field="slug", read_only=True
    )
    producto_nombre = serializers.ReadOnlyField(source="producto.nombre")
    autor = serializers.ReadOnlyField(source="autor.username")

    class Meta:
        model = Resena
        fields = ("url", "id", "producto", "producto_nombre", "autor", "puntuacion", "comentario", "creado")
        read_only_fields = ("creado",)

    def validate(self, attrs):
        # Solo en creación: el producto llega por contexto desde /productos/{slug}/resenas/
        if self.instance is not None:
            return attrs
        producto = self.context["producto"]
        usuario = self.context["request"].user
        if Resena.objects.filter(producto=producto, autor=usuario).exists():
            raise serializers.ValidationError("Ya reseñaste este producto.")
        recibido = ItemPedido.objects.filter(
            pedido__cliente=usuario, pedido__estado=Pedido.Estado.ENTREGADO, producto=producto
        ).exists()
        if not recibido:
            raise serializers.ValidationError(
                "Solo puedes reseñar productos de pedidos que ya recibiste (estado 'entregado')."
            )
        return attrs
