from django.contrib import admin

from .models import Categoria, Producto, Productor, Resena


@admin.register(Productor)
class ProductorAdmin(admin.ModelAdmin):
    list_display = ("nombre", "region", "distrito", "certificacion", "activo")
    list_filter = ("region", "certificacion", "activo")
    search_fields = ("nombre", "distrito")


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "padre")
    search_fields = ("nombre",)


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "productor", "categoria", "precio", "stock", "estado")
    list_filter = ("estado", "es_organico", "categoria")
    search_fields = ("nombre", "productor__nombre")


@admin.register(Resena)
class ResenaAdmin(admin.ModelAdmin):
    list_display = ("producto", "autor", "puntuacion", "creado")


from .models import Cupon, ItemPedido, Pedido  # noqa: E402


class ItemPedidoInline(admin.TabularInline):
    model = ItemPedido
    extra = 0
    readonly_fields = ("precio_unitario",)


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "cliente", "estado", "total", "creado")
    list_filter = ("estado",)
    inlines = [ItemPedidoInline]


@admin.register(Cupon)
class CuponAdmin(admin.ModelAdmin):
    list_display = ("codigo", "porcentaje", "vigente_hasta", "usos_actuales", "usos_maximos", "activo")
