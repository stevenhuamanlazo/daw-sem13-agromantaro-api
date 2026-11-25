"""CORS, CSRF y documentación OpenAPI (Guía, Paso 5)."""
from rest_framework.test import APIClient

from .tests import BaseAPITest

ORIGEN_OK = "http://localhost:5173"
ORIGEN_MALO = "http://sitio-malicioso.example"


class CorsTests(BaseAPITest):
    def test_origen_permitido_recibe_cabeceras_cors_con_credenciales(self):
        r = self.client.get("/api/productos/", HTTP_ORIGIN=ORIGEN_OK)
        self.assertEqual(r.headers["Access-Control-Allow-Origin"], ORIGEN_OK)
        self.assertEqual(r.headers["Access-Control-Allow-Credentials"], "true")

    def test_origen_no_permitido_no_recibe_cabeceras(self):
        r = self.client.get("/api/productos/", HTTP_ORIGIN=ORIGEN_MALO)
        self.assertNotIn("Access-Control-Allow-Origin", r.headers)

    def test_preflight_options_anuncia_metodos_y_x_csrftoken(self):
        r = self.client.options(
            "/api/pedidos/", HTTP_ORIGIN=ORIGEN_OK,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type,x-csrftoken",
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("POST", r.headers["Access-Control-Allow-Methods"])
        self.assertIn("x-csrftoken", r.headers["Access-Control-Allow-Headers"])

    def test_cors_solo_aplica_bajo_api(self):
        r = self.client.get("/admin/login/", HTTP_ORIGIN=ORIGEN_OK)
        self.assertNotIn("Access-Control-Allow-Origin", r.headers)


class CsrfTests(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.spa = APIClient(enforce_csrf_checks=True)   # se comporta como un navegador real

    def token(self):
        return self.spa.get("/api/csrf/").json()["csrfToken"]

    def test_endpoint_csrf_fija_cookie(self):
        self.token()
        self.assertIn("csrftoken", self.spa.cookies)

    def test_login_sin_token_es_403_json(self):
        r = self.spa.post("/api/sesion/", {"username": "lucia", "password": "Cliente123!"}, format="json")
        self.assertEqual(r.status_code, 403)
        self.assertIn("X-CSRFToken", r.json()["detail"])

    def test_flujo_completo_login_y_pedido_con_sesion(self):
        t = self.token()
        r = self.spa.post("/api/sesion/", {"username": "lucia", "password": "Cliente123!"},
                          format="json", HTTP_X_CSRFTOKEN=t)
        self.assertEqual(r.status_code, 200, r.content)
        pedido = {"direccion_envio": "Jr. Real 450", "ciudad": "Huancayo",
                  "items": [{"producto": "http://testserver/api/productos/yacon-fresco/", "cantidad": 1}]}
        # Con sesión activa, sin cabecera -> CSRF rechaza la escritura
        sin = self.spa.post("/api/pedidos/", pedido, format="json")
        self.assertEqual(sin.status_code, 403)
        # Con el token renovado tras el login -> 201
        con = self.spa.post("/api/pedidos/", pedido, format="json", HTTP_X_CSRFTOKEN=self.token())
        self.assertEqual(con.status_code, 201, con.content)

    def test_credenciales_invalidas(self):
        r = self.spa.post("/api/sesion/", {"username": "lucia", "password": "mal"},
                          format="json", HTTP_X_CSRFTOKEN=self.token())
        self.assertEqual(r.status_code, 400)

    def test_lecturas_publicas_no_requieren_csrf(self):
        self.assertEqual(self.spa.get("/api/productos/").status_code, 200)


class DocumentacionTests(BaseAPITest):
    def test_esquema_openapi_3_con_rutas_clave(self):
        r = self.client.get("/api/schema/?format=json")
        self.assertEqual(r.status_code, 200)
        esquema = r.json()
        self.assertTrue(esquema["openapi"].startswith("3."))
        for ruta in ("/api/productos/", "/api/productos/{slug}/resenas/", "/api/pedidos/{id}/pagar/", "/api/csrf/"):
            self.assertIn(ruta, esquema["paths"])

    def test_swagger_y_redoc_se_sirven_localmente(self):
        for url in ("/api/docs/", "/api/redoc/"):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200)
            self.assertNotIn(b"cdn.jsdelivr.net", r.content)
