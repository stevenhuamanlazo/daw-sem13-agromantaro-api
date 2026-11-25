from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

urlpatterns = [
    path("admin/", admin.site.urls),
    # Contrato OpenAPI 3 generado automáticamente (no se edita a mano) + visores.
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    # Login del navegable de DRF (útil para probar con sesión desde el navegador)
    path("api/auth/", include("rest_framework.urls")),
    path("api/", include("mercado.urls")),
]
