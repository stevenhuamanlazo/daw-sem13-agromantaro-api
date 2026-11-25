from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    # Login del navegable de DRF (útil para probar con sesión desde el navegador)
    path("api/auth/", include("rest_framework.urls")),
    path("api/", include("mercado.urls")),
]
