from collections import OrderedDict

from rest_framework.pagination import LimitOffsetPagination, PageNumberPagination
from rest_framework.response import Response


class PaginacionEstandar(PageNumberPagination):
    """
    ?page=2&page_size=20 (máx. 50). Añade metadatos de navegación para que el
    cliente no tenga que calcular nada: HATEOAS básico también en la paginación.
    """

    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50

    def get_paginated_response(self, data):
        return Response(
            OrderedDict(
                [
                    ("count", self.page.paginator.count),
                    ("total_paginas", self.page.paginator.num_pages),
                    ("pagina_actual", self.page.number),
                    ("next", self.get_next_link()),
                    ("previous", self.get_previous_link()),
                    ("results", data),
                ]
            )
        )

    def get_paginated_response_schema(self, schema):
        return {
            "type": "object",
            "required": ["count", "results"],
            "properties": {
                "count": {"type": "integer", "example": 41},
                "total_paginas": {"type": "integer", "example": 5},
                "pagina_actual": {"type": "integer", "example": 1},
                "next": {"type": "string", "nullable": True, "format": "uri"},
                "previous": {"type": "string", "nullable": True, "format": "uri"},
                "results": schema,
            },
        }


class PaginacionResenas(LimitOffsetPagination):
    """?limit=5&offset=10 — adecuada para 'cargar más' en listas de comentarios."""

    default_limit = 5
    max_limit = 25
