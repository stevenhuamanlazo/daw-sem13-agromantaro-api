"""
Soporte CSRF/AJAX para clientes SPA que usan autenticación por sesión.

Flujo recomendado para el front-end:
  1. GET  /api/csrf/           -> fija la cookie 'csrftoken' y devuelve el token.
  2. POST /api/sesion/         -> login (cabecera X-CSRFToken obligatoria).
  3. GET  /api/csrf/ de nuevo  -> login rota el token; hay que renovarlo.
  4. Cualquier POST/PUT/PATCH/DELETE autenticado envía X-CSRFToken.
"""
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


def csrf_fallo(request, reason=""):
    """CSRF_FAILURE_VIEW: responde JSON (no HTML) para que el SPA pueda interpretarlo."""
    return JsonResponse(
        {"detail": "Verificación CSRF fallida: envía la cabecera X-CSRFToken.", "motivo": reason},
        status=403,
    )


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    """Entrega el token CSRF y garantiza que la cookie 'csrftoken' esté presente."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        responses=inline_serializer("CsrfToken", {"csrfToken": serializers.CharField()}),
        summary="Obtener token CSRF",
    )
    def get(self, request):
        return Response({"csrfToken": get_token(request)})


class CredencialesSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})


# IA: POST /api/sesion/ devolvía 403 "CSRF token missing" tras iniciar sesión, aunque el
# header se enviaba → Solución manual: login() rota el token CSRF (rotate_token), así que
# el cookie anterior queda inválido; el cliente debe volver a pedir GET /api/csrf/ y usar
# el nuevo valor. Además, el login no autenticado no pasa por SessionAuthentication (que
# es quien exige CSRF), por eso se protege la vista con csrf_protect de forma explícita.
@method_decorator(csrf_protect, name="dispatch")
class SesionView(APIView):
    """Sesión por cookie para SPAs (el resto de métodos exige CSRF vía SessionAuthentication)."""

    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Estado de la sesión",
        responses=inline_serializer(
            "EstadoSesion",
            {"autenticado": serializers.BooleanField(), "usuario": serializers.CharField(allow_null=True)},
        ),
    )
    def get(self, request):
        u = request.user
        return Response({"autenticado": u.is_authenticated, "usuario": u.username if u.is_authenticated else None})

    @extend_schema(
        summary="Iniciar sesión",
        request=CredencialesSerializer,
        responses={200: OpenApiResponse(description="Sesión iniciada"), 400: OpenApiResponse(description="Credenciales inválidas")},
    )
    def post(self, request):
        datos = CredencialesSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        usuario = authenticate(request, **datos.validated_data)
        if usuario is None:
            return Response({"detail": "Credenciales inválidas."}, status=status.HTTP_400_BAD_REQUEST)
        login(request, usuario)
        return Response({"autenticado": True, "usuario": usuario.username,
                         "aviso": "El token CSRF fue rotado: solicita GET /api/csrf/ otra vez."})

    @extend_schema(summary="Cerrar sesión", request=None, responses={204: None})
    def delete(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)
