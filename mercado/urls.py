from django.urls import path
from rest_framework.routers import DefaultRouter

from . import seguridad, views

# DefaultRouter genera las rutas CRUD + @action y una raíz navegable (/api/)
# con hipervínculos a cada colección: punto de entrada HATEOAS de la API.
router = DefaultRouter()
router.register("productores", views.ProductorViewSet, basename="productor")
router.register("categorias", views.CategoriaViewSet, basename="categoria")
router.register("productos", views.ProductoViewSet, basename="producto")
router.register("resenas", views.ResenaViewSet, basename="resena")
router.register("pedidos", views.PedidoViewSet, basename="pedido")

urlpatterns = [
    path("csrf/", seguridad.CsrfView.as_view(), name="csrf"),
    path("sesion/", seguridad.SesionView.as_view(), name="sesion"),
] + router.urls
