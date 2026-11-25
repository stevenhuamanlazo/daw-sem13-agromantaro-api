"""
Carga un catálogo andino de demostración (productores, productos, cupones,
pedidos entregados y reseñas verificadas).

    python manage.py cargar_demo           # idempotente
    python manage.py cargar_demo --reset   # borra datos de dominio y recarga
"""
import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from mercado.models import (
    Categoria,
    Cupon,
    ItemPedido,
    Pedido,
    Producto,
    Productor,
    Resena,
)

User = get_user_model()

ARBOL_CATEGORIAS = {
    "Tubérculos y raíces": ["Papas nativas", "Maca y yacón", "Olluco y mashua"],
    "Granos andinos": ["Quinua", "Kiwicha y cañihua", "Tarwi y habas"],
    "Café y cacao": ["Café de altura", "Cacao fino de aroma"],
    "Lácteos y apicultura": ["Quesos andinos", "Miel y derivados"],
    "Frutas y hierbas": ["Frutas andinas", "Hierbas aromáticas"],
}

PRODUCTORES = [
    # nombre, región, distrito, certificación, usuario
    ("Asociación Mantaro Orgánico", "junin", "Concepción", "org_senasa", None),
    ("Familia Quispe Ccanto – Papas de Huasicancha", "junin", "Huasicancha", "pgs", "prod_quispe"),
    ("Cooperativa Cafetalera Pangoa", "junin", "Pangoa", "comercio_justo", "prod_pangoa"),
    ("Apícola Yanamarca", "junin", "Yanamarca", "ninguna", None),
    ("Comunidad Paccha Wasi", "huancavelica", "Acobamba", "pgs", None),
    ("Quesería Andina Yanacancha", "pasco", "Yanacancha", "ninguna", None),
]

# (idx productor, categoría, nombre, descripción, precio, unidad, stock, orgánico, estado, días desde cosecha)
PRODUCTOS = [
    (1, "Papas nativas", "Papa Huayro amarilla", "Papa nativa de pulpa firme, ideal para sancochar.", "6.50", "kg", 420, True, "activo", 12),
    (1, "Papas nativas", "Papa Peruanita multicolor", "Mezcla de variedades nativas de colores intensos.", "8.90", "kg", 260, True, "activo", 9),
    (1, "Papas nativas", "Papa Ccompis negra", "Variedad ancestral de piel oscura y sabor intenso.", "9.40", "kg", 0, True, "agotado", 30),
    (0, "Papas nativas", "Papa Canchán blanca", "Papa comercial de alta producción, lavada.", "3.20", "kg", 900, False, "activo", 6),
    (0, "Maca y yacón", "Maca gelatinizada en polvo", "Polvo de maca de Junín, bolsa de 500 g.", "28.00", "und", 150, True, "activo", 45),
    (0, "Maca y yacón", "Maca amarilla fresca", "Hipocótilo fresco recién cosechado.", "12.50", "kg", 80, True, "activo", 5),
    (4, "Maca y yacón", "Yacón fresco", "Raíz dulce rica en inulina.", "7.80", "kg", 130, True, "activo", 8),
    (4, "Olluco y mashua", "Olluco rosado", "Olluco de Acobamba para guisos andinos.", "5.60", "kg", 210, True, "activo", 10),
    (4, "Olluco y mashua", "Mashua amarilla", "Tubérculo picante tradicional.", "6.90", "kg", 95, True, "activo", 11),
    (0, "Quinua", "Quinua blanca lavada", "Quinua de grano grande, saponina eliminada.", "11.80", "kg", 600, True, "activo", 60),
    (0, "Quinua", "Quinua roja", "Variedad Pasankalla, ideal para ensaladas.", "13.40", "kg", 310, True, "activo", 60),
    (4, "Quinua", "Quinua negra Collana", "Grano negro de textura crocante.", "14.90", "kg", 140, True, "activo", 62),
    (4, "Kiwicha y cañihua", "Kiwicha pop", "Kiwicha reventada para desayunos.", "9.90", "kg", 180, True, "activo", 35),
    (4, "Kiwicha y cañihua", "Cañihua tostada", "Harina de cañihua tostada, rica en proteína.", "10.50", "kg", 120, True, "activo", 35),
    (1, "Tarwi y habas", "Tarwi desamargado", "Chocho listo para consumo, bolsa de 1 kg.", "8.20", "kg", 170, False, "activo", 20),
    (1, "Tarwi y habas", "Habas secas (mote)", "Habas secas seleccionadas.", "6.10", "kg", 0, False, "agotado", 70),
    (2, "Café de altura", "Café Pangoa grano tostado medio", "Café de altura, notas a cacao y panela.", "42.00", "kg", 220, True, "activo", 40),
    (2, "Café de altura", "Café Pangoa molido filtrado", "Molienda media para filtrado, 250 g.", "16.00", "und", 340, True, "activo", 40),
    (2, "Café de altura", "Café verde de exportación (lote)", "Café en grano verde, lote experimental.", "30.00", "kg", 500, True, "borrador", 50),
    (2, "Cacao fino de aroma", "Cacao en grano fermentado", "Cacao fino de aroma de la selva central.", "24.50", "kg", 160, True, "activo", 33),
    (2, "Cacao fino de aroma", "Chocolate 70% cacao", "Barra de chocolate oscuro, 100 g.", "9.50", "und", 400, True, "activo", 25),
    (3, "Miel y derivados", "Miel de eucalipto 500 ml", "Miel multifloral de la meseta del Mantaro.", "21.00", "lt", 110, False, "activo", 15),
    (3, "Miel y derivados", "Polen de abeja 250 g", "Polen deshidratado.", "18.00", "und", 75, False, "activo", 15),
    (3, "Miel y derivados", "Propóleo en tintura", "Tintura al 30 %, frasco de 30 ml.", "15.50", "und", 60, False, "descontinuado", 90),
    (5, "Quesos andinos", "Queso andino fresco", "Queso fresco de leche de vaca, pieza de 1 kg.", "26.00", "kg", 90, False, "activo", 3),
    (5, "Quesos andinos", "Queso paria madurado", "Queso madurado de textura firme.", "32.00", "kg", 45, False, "activo", 20),
    (5, "Quesos andinos", "Yogur natural 1 L", "Yogur sin azúcar añadida.", "9.80", "lt", 70, False, "activo", 2),
    (4, "Frutas andinas", "Lúcuma fresca", "Lúcuma madura, dulce y aromática.", "10.20", "kg", 100, True, "activo", 7),
    (0, "Frutas andinas", "Tumbo serrano", "Fruta ácida para refrescos y mermeladas.", "7.40", "kg", 85, True, "activo", 7),
    (4, "Hierbas aromáticas", "Muña seca", "Hierba andina digestiva, bolsa 100 g.", "5.00", "und", 200, True, "activo", 18),
    (0, "Hierbas aromáticas", "Huacatay en pasta", "Condimento clásico andino, frasco 200 g.", "8.50", "und", 140, False, "borrador", 4),
]

# Presentaciones por saco de 5 kg para productos vendidos por kg (genera volumen de catálogo).
VARIANTES_5KG = [
    "Papa Huayro amarilla", "Papa Canchán blanca", "Quinua blanca lavada", "Quinua roja",
    "Olluco rosado", "Kiwicha pop", "Yacón fresco", "Tarwi desamargado", "Cañihua tostada",
    "Maca amarilla fresca", "Lúcuma fresca", "Tumbo serrano",
]


class Command(BaseCommand):
    help = "Carga datos de demostración de AgroMantaro Market."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Borra los datos de dominio antes de cargar.")

    @transaction.atomic
    def handle(self, *args, **opts):
        if opts["reset"]:
            for modelo in (ItemPedido, Pedido, Resena, Cupon, Producto, Productor, Categoria):
                modelo.objects.all().delete()

        rnd = random.Random(2026)  # datos deterministas para poder reproducir capturas
        hoy = timezone.localdate()

        # Usuarios --------------------------------------------------------
        admin, creado = User.objects.get_or_create(
            username="admin", defaults={"email": "admin@agromantaro.pe", "is_staff": True, "is_superuser": True}
        )
        if creado:
            admin.set_password("Admin12345!")
            admin.save()
        usuarios = {"admin": admin}
        for username in ("lucia", "marcos", "prod_quispe", "prod_pangoa"):
            u, creado = User.objects.get_or_create(username=username, defaults={"email": f"{username}@example.com"})
            if creado:
                u.set_password("Cliente123!" if not username.startswith("prod_") else "Productor123!")
                u.save()
            usuarios[username] = u

        # Categorías --------------------------------------------------------
        categorias = {}
        for padre_nombre, hijas in ARBOL_CATEGORIAS.items():
            padre, _ = Categoria.objects.get_or_create(nombre=padre_nombre, padre=None)
            categorias[padre_nombre] = padre
            for h in hijas:
                categorias[h], _ = Categoria.objects.get_or_create(nombre=h, padre=padre)

        # Productores -------------------------------------------------------
        productores = []
        for nombre, region, distrito, cert, user in PRODUCTORES:
            p, _ = Productor.objects.get_or_create(
                nombre=nombre,
                defaults={
                    "region": region,
                    "distrito": distrito,
                    "certificacion": cert,
                    "usuario": usuarios.get(user) if user else None,
                },
            )
            productores.append(p)

        # Productos ---------------------------------------------------------
        productos = {}
        for idx, cat, nombre, desc, precio, unidad, stock, organico, estado, dias in PRODUCTOS:
            prod, _ = Producto.objects.get_or_create(
                nombre=nombre,
                productor=productores[idx],
                defaults={
                    "categoria": categorias[cat],
                    "descripcion": desc,
                    "precio": Decimal(precio),
                    "unidad": unidad,
                    "stock": stock,
                    "es_organico": organico and productores[idx].certificacion != "ninguna",
                    "estado": estado,
                    "fecha_cosecha": hoy - timedelta(days=dias),
                },
            )
            productos[nombre] = prod
        for nombre in VARIANTES_5KG:
            base = productos[nombre]
            Producto.objects.get_or_create(
                nombre=f"{nombre} – saco 5 kg",
                productor=base.productor,
                defaults={
                    "categoria": base.categoria,
                    "descripcion": f"{base.descripcion} Presentación familiar de 5 kg.",
                    "precio": (base.precio * Decimal("4.6")).quantize(Decimal("0.01")),
                    "unidad": "und",
                    "stock": max(base.stock // 6, 5) if base.stock else 0,
                    "es_organico": base.es_organico,
                    "estado": base.estado if base.stock else "agotado",
                    "fecha_cosecha": base.fecha_cosecha,
                },
            )

        # Cupones -----------------------------------------------------------
        Cupon.objects.get_or_create(
            codigo="ANDES10",
            defaults={"porcentaje": 10, "vigente_desde": hoy - timedelta(days=30),
                      "vigente_hasta": hoy + timedelta(days=90), "usos_maximos": 500},
        )
        Cupon.objects.get_or_create(
            codigo="MANTARO20",
            defaults={"porcentaje": 20, "monto_minimo": Decimal("100.00"),
                      "vigente_desde": hoy - timedelta(days=10),
                      "vigente_hasta": hoy + timedelta(days=45), "usos_maximos": 50},
        )
        Cupon.objects.get_or_create(
            codigo="VERANO15",
            defaults={"porcentaje": 15, "vigente_desde": hoy - timedelta(days=200),
                      "vigente_hasta": hoy - timedelta(days=20)},
        )

        # Pedidos entregados + reseñas verificadas -------------------------
        if not Pedido.objects.exists():
            activos = list(
                Producto.objects.filter(estado="activo", stock__gt=0).order_by("id")[:14]
            )
            comentarios = [
                "Llegó fresco y bien empacado.", "Excelente sabor, repetiré la compra.",
                "Buena calidad, aunque tardó un poco el envío.", "Muy buen producto de la zona.",
                "Calidad superior, se nota que es orgánico.", "Cumple lo prometido.",
            ]
            for cliente in (usuarios["lucia"], usuarios["marcos"]):
                for lote in range(3):
                    elegidos = rnd.sample(activos, 3)
                    pedido = Pedido.objects.create(
                        cliente=cliente, estado="entregado",
                        direccion_envio="Jr. Real 450", ciudad="Huancayo",
                    )
                    subtotal = Decimal("0.00")
                    for pr in elegidos:
                        cant = rnd.randint(1, 3)
                        ItemPedido.objects.create(
                            pedido=pedido, producto=pr, cantidad=cant, precio_unitario=pr.precio
                        )
                        subtotal += pr.precio * cant
                        Resena.objects.get_or_create(
                            producto=pr, autor=cliente,
                            defaults={"puntuacion": rnd.choice([3, 4, 4, 5, 5]),
                                      "comentario": rnd.choice(comentarios)},
                        )
                    envio = Decimal("0.00") if subtotal >= Pedido.ENVIO_GRATIS_DESDE else Pedido.COSTO_ENVIO
                    pedido.subtotal, pedido.costo_envio = subtotal, envio
                    pedido.total = subtotal + envio
                    pedido.save()

        self.stdout.write(self.style.SUCCESS(
            f"Demo lista: {Productor.objects.count()} productores, {Producto.objects.count()} productos, "
            f"{Pedido.objects.count()} pedidos, {Resena.objects.count()} reseñas."
        ))
