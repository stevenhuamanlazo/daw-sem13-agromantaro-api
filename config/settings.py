"""
Configuración del proyecto AgroMantaro Market API.

Toda la política de la API (autenticación, permisos, paginación, filtros,
throttling, esquema OpenAPI) vive AQUÍ de forma global. Las vistas solo
sobrescriben cuando hay una razón de negocio documentada.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------------
# Núcleo Django
# --------------------------------------------------------------------------
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY", "dev-only-cambiar-en-produccion-agromantaro-2026"
)
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get(
    "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver"
).split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Terceros
    "rest_framework",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    "drf_spectacular_sidecar",  # Swagger UI / Redoc servidos localmente (sin CDN)
    # Apps propias
    "mercado",
]

MIDDLEWARE = [
    # CorsMiddleware debe ir lo más arriba posible, antes de CommonMiddleware
    # y de cualquier middleware que pueda generar respuestas.
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-pe"
TIME_ZONE = "America/Lima"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------
# Django REST Framework – política global de la API
# --------------------------------------------------------------------------
REST_FRAMEWORK = {
    # Stateless para clientes máquina (Basic) + sesión para SPA/AJAX (con CSRF).
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    # Lectura pública, escritura solo autenticada. Las vistas solo endurecen.
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    # Paginación por defecto (se reemplaza por una clase propia en la etapa 4).
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 10,
    # Filtrado / búsqueda / orden delegados a la base de datos (QuerySets lazy).
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    # Throttling global contra scraping y abuso.
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "20/min",
        "user": "120/min",
    },
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# --------------------------------------------------------------------------
# CORS – orígenes explícitos, nunca "*" (la API usa cookies de sesión)
# --------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",   # Vite / SPA en desarrollo
    "http://127.0.0.1:5173",
    "http://localhost:3000",   # React CRA / Next.js
]
CORS_URLS_REGEX = r"^/api/.*$"   # solo la API es accesible cross-origin
CORS_ALLOW_CREDENTIALS = True    # necesario para enviar la cookie de sesión

# --------------------------------------------------------------------------
# OpenAPI / Swagger (drf-spectacular)
# --------------------------------------------------------------------------
SPECTACULAR_SETTINGS = {
    "TITLE": "AgroMantaro Market API",
    "DESCRIPTION": (
        "Marketplace agroecológico del Valle del Mantaro: productores, catálogo "
        "por lotes, pedidos con cupones y reseñas verificadas."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "REDOC_DIST": "SIDECAR",
    "COMPONENT_SPLIT_REQUEST": True,
}
