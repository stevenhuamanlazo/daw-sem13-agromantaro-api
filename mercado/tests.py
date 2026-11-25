from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Cupon, Pedido, Producto

User = get_user_model()


class BaseAPITest(APITestCase):
    """Carga el catálogo demo y limpia la caché para reiniciar los contadores de throttling."""

    @classmethod
    def setUpTestData(cls):
        call_command("cargar_demo", stdout=StringIO())
        cls.lucia = User.objects.get(username="lucia")
        cls.marcos = User.objects.get(username="marcos")
        cls.quispe = User.objects.get(username="prod_quispe")
        cls.admin = User.objects.get(username="admin")

    def setUp(self):
        cache.clear()

    def url_producto(self, slug):
        return f"http://testserver/api/productos/{slug}/"


class CatalogoTests(BaseAPITest):
    def test_listado_publico_paginado_con_metadatos(self):
        r = self.client.get("/api/productos/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data["results"]), 10)
        for clave in ("count", "total_paginas", "pagina_actual", "next", "previous"):
            self.assertIn(clave, r.data)

    def test_page_size_tiene_tope_de_50(self):
        r = self.client.get("/api/productos/?page_size=500")
        self.assertLessEqual(len(r.data["results"]), 50)

    def test_borradores_no_son_publicos(self):
        r = self.client.get("/api/productos/?page_size=50")
        self.assertNotIn("borrador", {p["estado"] for p in r.data["results"]})

    def test_filtro_estado_y_precio(self):
        r = self.client.get("/api/productos/?estado=activo&precio_max=10&page_size=50")
        self.assertTrue(r.data["count"] > 0)
        for p in r.data["results"]:
            self.assertEqual(p["estado"], "activo")
            self.assertLessEqual(Decimal(p["precio"]), Decimal("10"))

    def test_filtro_por_arbol_de_categorias(self):
        r = self.client.get("/api/productos/?categoria_arbol=granos-andinos&page_size=50")
        self.assertTrue(r.data["count"] > 0)
        self.assertTrue(all("quinua" in p["categoria"] or "kiwicha" in p["categoria"]
                            or "tarwi" in p["categoria"] for p in r.data["results"]))

    def test_orden_por_precio_descendente(self):
        r = self.client.get("/api/productos/?ordering=-precio&page_size=50")
        precios = [Decimal(p["precio"]) for p in r.data["results"]]
        self.assertEqual(precios, sorted(precios, reverse=True))

    def test_busqueda_de_texto(self):
        r = self.client.get("/api/productos/?search=quinua")
        self.assertTrue(r.data["count"] >= 3)

    def test_enlaces_hateoas_dependen_del_estado(self):
        agotado = self.client.get("/api/productos/papa-ccompis-negra/").data
        activo = self.client.get("/api/productos/papa-huayro-amarilla/").data
        self.assertNotIn("comprar", agotado["_links"])
        self.assertIn("comprar", activo["_links"])


class ProductosEscrituraTests(BaseAPITest):
    def payload(self, **extra):
        base = {
            "nombre": "Papa Yungay mantequilla", "descripcion": "Lote de prueba.",
            "precio": "5.50", "unidad": "kg", "stock": 100, "estado": "activo",
            "es_organico": True, "fecha_cosecha": "2026-11-10",
            "productor": "http://testserver/api/productores/familia-quispe-ccanto-papas-de-huasicancha/",
            "categoria": "http://testserver/api/categorias/papas-nativas/",
        }
        base.update(extra)
        return base

    def test_anonimo_no_puede_crear(self):
        self.assertEqual(self.client.post("/api/productos/", self.payload()).status_code, 403)

    def test_cliente_sin_perfil_productor_no_puede_crear(self):
        self.client.force_authenticate(self.lucia)
        self.assertEqual(self.client.post("/api/productos/", self.payload()).status_code, 403)

    def test_productor_crea_en_su_perfil(self):
        self.client.force_authenticate(self.quispe)
        r = self.client.post("/api/productos/", self.payload(), format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["slug"], "papa-yungay-mantequilla")

    def test_productor_no_publica_en_perfil_ajeno(self):
        self.client.force_authenticate(self.quispe)
        r = self.client.post("/api/productos/", self.payload(
            productor="http://testserver/api/productores/asociacion-mantaro-organico/"), format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("productor", r.data)

    def test_activo_sin_stock_es_rechazado(self):
        self.client.force_authenticate(self.quispe)
        r = self.client.post("/api/productos/", self.payload(stock=0), format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("estado", r.data)

    def test_organico_exige_certificacion(self):
        self.client.force_authenticate(self.admin)
        r = self.client.post("/api/productos/", self.payload(
            productor="http://testserver/api/productores/apicola-yanamarca/"), format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("es_organico", r.data)

    def test_cosecha_futura_es_rechazada(self):
        self.client.force_authenticate(self.quispe)
        r = self.client.post("/api/productos/", self.payload(fecha_cosecha="2099-01-01"), format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("fecha_cosecha", r.data)

    def test_reponer_stock_reactiva_agotado(self):
        self.client.force_authenticate(self.quispe)
        r = self.client.post("/api/productos/papa-ccompis-negra/reponer-stock/", {"cantidad": 50})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual((r.data["estado"], r.data["stock"]), ("activo", 50))

    def test_productor_ajeno_no_repone_stock(self):
        self.client.force_authenticate(self.quispe)
        r = self.client.post("/api/productos/quinua-blanca-lavada/reponer-stock/", {"cantidad": 5})
        self.assertEqual(r.status_code, 403)


class PedidosTests(BaseAPITest):
    def crear(self, user, items, **extra):
        self.client.force_authenticate(user)
        datos = {"direccion_envio": "Av. Giráldez 120", "ciudad": "Huancayo", "items": items}
        datos.update(extra)
        return self.client.post("/api/pedidos/", datos, format="json")

    def item(self, slug, cantidad):
        return {"producto": self.url_producto(slug), "cantidad": cantidad}

    def test_pedido_calcula_totales_y_descuenta_stock(self):
        antes = Producto.objects.get(slug="papa-huayro-amarilla").stock
        r = self.crear(self.lucia, [self.item("papa-huayro-amarilla", 4)])
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["subtotal"], "26.00")
        self.assertEqual(r.data["costo_envio"], "12.00")   # < S/ 120 → paga envío
        self.assertEqual(r.data["total"], "38.00")
        self.assertEqual(Producto.objects.get(slug="papa-huayro-amarilla").stock, antes - 4)
        self.assertIn("pagar", r.data["_links"])

    def test_envio_gratis_desde_120_con_cupon(self):
        r = self.crear(self.lucia, [self.item("cafe-pangoa-grano-tostado-medio", 4)], cupon_codigo="mantaro20")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["subtotal"], "168.00")
        self.assertEqual(r.data["descuento"], "33.60")
        self.assertEqual(r.data["costo_envio"], "0.00")
        self.assertEqual(r.data["total"], "134.40")
        self.assertEqual(Cupon.objects.get(codigo="MANTARO20").usos_actuales, 1)

    def test_stock_insuficiente(self):
        r = self.crear(self.lucia, [self.item("queso-paria-madurado", 9999)])
        self.assertEqual(r.status_code, 400)
        self.assertIn("Stock insuficiente", str(r.data["items"]))

    def test_producto_agotado_no_se_vende(self):
        r = self.crear(self.lucia, [self.item("papa-ccompis-negra", 1)])
        self.assertEqual(r.status_code, 400)

    def test_items_repetidos_y_cupon_vencido(self):
        r = self.crear(self.lucia, [self.item("kiwicha-pop", 1), self.item("kiwicha-pop", 2)])
        self.assertEqual(r.status_code, 400)
        r = self.crear(self.lucia, [self.item("kiwicha-pop", 1)], cupon_codigo="VERANO15")
        self.assertIn("vigencia", str(r.data["cupon_codigo"]))

    def test_cancelar_devuelve_stock_y_no_se_puede_pagar_despues(self):
        antes = Producto.objects.get(slug="miel-de-eucalipto-500-ml").stock
        pedido = self.crear(self.lucia, [self.item("miel-de-eucalipto-500-ml", 3)]).data
        self.assertEqual(Producto.objects.get(slug="miel-de-eucalipto-500-ml").stock, antes - 3)
        r = self.client.post(f"/api/pedidos/{pedido['id']}/cancelar/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Producto.objects.get(slug="miel-de-eucalipto-500-ml").stock, antes)
        self.assertEqual(self.client.post(f"/api/pedidos/{pedido['id']}/pagar/").status_code, 409)

    def test_pagar_dos_veces_da_409_y_enlace_desaparece(self):
        pedido = self.crear(self.lucia, [self.item("yacon-fresco", 2)]).data
        r = self.client.post(f"/api/pedidos/{pedido['id']}/pagar/")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("pagar", r.data["_links"])
        self.assertEqual(self.client.post(f"/api/pedidos/{pedido['id']}/pagar/").status_code, 409)

    def test_aislamiento_entre_clientes_y_acceso_anonimo(self):
        pedido = self.crear(self.lucia, [self.item("yacon-fresco", 1)]).data
        self.client.force_authenticate(self.marcos)
        self.assertEqual(self.client.get(f"/api/pedidos/{pedido['id']}/").status_code, 404)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/pedidos/").status_code, 403)

    def test_solo_staff_avanza_pedidos(self):
        pedido = self.crear(self.lucia, [self.item("yacon-fresco", 1)]).data
        self.client.post(f"/api/pedidos/{pedido['id']}/pagar/")
        self.assertEqual(self.client.post(f"/api/pedidos/{pedido['id']}/avanzar/").status_code, 403)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(f"/api/pedidos/{pedido['id']}/avanzar/").data["estado"], "enviado")

    def test_validar_cupon_sin_crear_pedido(self):
        self.client.force_authenticate(self.lucia)
        antes = Pedido.objects.count()
        r = self.client.post("/api/pedidos/validar-cupon/", {"codigo": "andes10", "subtotal": "80.00"})
        self.assertEqual(r.data["descuento"], "8.00")
        self.assertEqual(Pedido.objects.count(), antes)


class ResenasTests(BaseAPITest):
    def test_resena_exige_pedido_entregado(self):
        self.client.force_authenticate(self.quispe)
        r = self.client.post("/api/productos/yacon-fresco/resenas/", {"puntuacion": 5})
        self.assertEqual(r.status_code, 400)
        self.assertIn("recibiste", str(r.data))

    def test_resena_valida_y_sin_duplicados(self):
        # Se entrega un pedido real de un producto aún no reseñado por Lucía.
        from .models import ItemPedido
        prod = Producto.objects.filter(estado="activo").exclude(resenas__autor=self.lucia).first()
        pedido = Pedido.objects.create(cliente=self.lucia, estado="entregado", direccion_envio="x", ciudad="y")
        ItemPedido.objects.create(pedido=pedido, producto=prod, cantidad=1, precio_unitario=prod.precio)
        self.client.force_authenticate(self.lucia)
        url = f"/api/productos/{prod.slug}/resenas/"
        r = self.client.post(url, {"puntuacion": 5, "comentario": "Muy bueno"})
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["autor"], "lucia")
        self.assertEqual(self.client.post(url, {"puntuacion": 4}).status_code, 400)

    def test_puntuacion_fuera_de_rango(self):
        self.client.force_authenticate(self.lucia)
        r = self.client.post("/api/productos/yacon-fresco/resenas/", {"puntuacion": 9})
        self.assertEqual(r.status_code, 400)
        self.assertIn("puntuacion", r.data)


class ThrottlingTests(BaseAPITest):
    def test_anonimo_recibe_429_tras_20_peticiones(self):
        codigos = [self.client.get("/api/categorias/").status_code for _ in range(22)]
        self.assertEqual(codigos[:20], [200] * 20)
        self.assertEqual(codigos[20], 429)
        r = self.client.get("/api/categorias/")
        self.assertIn("Retry-After", r.headers)

    def test_scope_pedidos_limita_a_10_por_minuto(self):
        self.client.force_authenticate(self.lucia)
        codigos = [self.client.post("/api/pedidos/validar-cupon/", {"codigo": "x", "subtotal": "1"}).status_code
                   for _ in range(2)]
        # validar-cupon no está en el scope estricto: solo aplica el cupo 'user'
        self.assertNotIn(429, codigos)
        malos = [self.client.post("/api/pedidos/", {"items": []}, format="json").status_code for _ in range(12)]
        self.assertEqual(malos[:10], [400] * 10)
        self.assertEqual(malos[10], 429)
