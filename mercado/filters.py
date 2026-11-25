"""
FilterSets de django-filter. Todo se traduce a SQL (QuerySet lazy): nunca se
filtra en memoria con list() (Guía, Paso 4).
"""
import django_filters as df
from django.db.models import Q

from .models import Categoria, Pedido, Producto, Productor


class ProductoFilter(df.FilterSet):
    # Ej.: /api/productos/?estado=activo&es_organico=true&precio_max=15&ordering=-creado
    categoria = df.CharFilter(field_name="categoria__slug", help_text="Slug exacto de la categoría.")
    categoria_arbol = df.CharFilter(
        method="filtrar_arbol", help_text="Slug de una categoría: incluye todas sus subcategorías."
    )
    productor = df.CharFilter(field_name="productor__slug")
    region = df.ChoiceFilter(field_name="productor__region", choices=Productor.Region.choices)
    precio_min = df.NumberFilter(field_name="precio", lookup_expr="gte")
    precio_max = df.NumberFilter(field_name="precio", lookup_expr="lte")
    cosechado_desde = df.DateFilter(field_name="fecha_cosecha", lookup_expr="gte")
    en_stock = df.BooleanFilter(method="filtrar_en_stock", help_text="true = activos con stock > 0.")
    calificacion_min = df.NumberFilter(field_name="calificacion_promedio", lookup_expr="gte")

    class Meta:
        model = Producto
        fields = ["estado", "es_organico", "unidad"]

    def filtrar_arbol(self, queryset, nombre, valor):
        categoria = Categoria.objects.filter(slug=valor).first()
        if categoria is None:
            return queryset.none()
        return queryset.filter(categoria_id__in=categoria.ids_descendientes())

    def filtrar_en_stock(self, queryset, nombre, valor):
        con_stock = Q(estado=Producto.Estado.ACTIVO, stock__gt=0)
        return queryset.filter(con_stock) if valor else queryset.exclude(con_stock)


class PedidoFilter(df.FilterSet):
    desde = df.DateFilter(field_name="creado", lookup_expr="date__gte")
    hasta = df.DateFilter(field_name="creado", lookup_expr="date__lte")
    total_min = df.NumberFilter(field_name="total", lookup_expr="gte")
    con_cupon = df.BooleanFilter(field_name="cupon", lookup_expr="isnull", exclude=True)

    class Meta:
        model = Pedido
        fields = ["estado", "ciudad"]
