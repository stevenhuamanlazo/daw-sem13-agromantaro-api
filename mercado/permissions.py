"""
Permisos reutilizables. Las vistas los referencian por clase; no se escriben
condiciones de rol dentro de métodos de vista (Guía, Paso 1).
"""
from rest_framework import permissions


def _es_productor(user):
    # La relación inversa OneToOne lanza RelatedObjectDoesNotExist (AttributeError) si no existe.
    return user.is_authenticated and hasattr(user, "productor")


class SoloLecturaOStaff(permissions.BasePermission):
    """Cualquiera lee; solo el personal administrativo crea/edita/borra."""

    def has_permission(self, request, view):
        return request.method in permissions.SAFE_METHODS or bool(
            request.user and request.user.is_staff
        )


class ProductorDuenoOStaff(permissions.BasePermission):
    """
    Lectura pública. Escritura: staff o un usuario con perfil de productor.
    A nivel de objeto, un productor solo modifica SUS productos.
    """

    message = "Debes ser un productor registrado (o personal administrativo) para modificar el catálogo."

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user.is_staff or _es_productor(request.user))

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user.is_staff or obj.productor.usuario_id == request.user.id)


class AutorOStaff(permissions.BasePermission):
    """Para reseñas: solo su autor (o staff) puede eliminarlas."""

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user.is_staff or obj.autor_id == request.user.id)
