from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.text import slugify


def _slug_unico(modelo, base, pk=None):
    """Genera un slug único anexando -2, -3... si ya existe."""
    base = slugify(base)[:140] or "item"
    slug, n = base, 2
    existentes = modelo.objects.exclude(pk=pk) if pk else modelo.objects.all()
    while existentes.filter(slug=slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


class Productor(models.Model):
    """Asociación o familia productora que publica en el marketplace."""

    class Region(models.TextChoices):
        JUNIN = "junin", "Junín"
        HUANCAVELICA = "huancavelica", "Huancavelica"
        PASCO = "pasco", "Pasco"
        AYACUCHO = "ayacucho", "Ayacucho"

    class Certificacion(models.TextChoices):
        NINGUNA = "ninguna", "Sin certificación"
        ORGANICO_SENASA = "org_senasa", "Orgánico SENASA"
        PGS = "pgs", "Sistema Participativo de Garantía"
        COMERCIO_JUSTO = "comercio_justo", "Comercio Justo"

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="productor",
    )
    nombre = models.CharField(max_length=120)
    slug = models.SlugField(max_length=150, unique=True, blank=True)
    region = models.CharField(max_length=20, choices=Region.choices)
    distrito = models.CharField(max_length=80)
    certificacion = models.CharField(
        max_length=20, choices=Certificacion.choices, default=Certificacion.NINGUNA
    )
    activo = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name_plural = "productores"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _slug_unico(Productor, self.nombre, self.pk)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre


class Categoria(models.Model):
    """Categoría jerárquica (p. ej. Tubérculos → Papas nativas)."""

    nombre = models.CharField(max_length=80)
    slug = models.SlugField(max_length=100, unique=True, blank=True)
    padre = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="hijos"
    )

    class Meta:
        ordering = ["nombre"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _slug_unico(Categoria, self.nombre, self.pk)
        super().save(*args, **kwargs)

    def ids_descendientes(self):
        """IDs de esta categoría y de todas sus hijas (recorrido en anchura)."""
        ids, frontera = [self.pk], [self.pk]
        while frontera:
            frontera = list(
                Categoria.objects.filter(padre_id__in=frontera).values_list("pk", flat=True)
            )
            ids.extend(frontera)
        return ids

    def __str__(self):
        return self.nombre


class Producto(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = "borrador", "Borrador"
        ACTIVO = "activo", "Activo"
        AGOTADO = "agotado", "Agotado"
        DESCONTINUADO = "descontinuado", "Descontinuado"

    class Unidad(models.TextChoices):
        KG = "kg", "Kilogramo"
        UND = "und", "Unidad"
        LT = "lt", "Litro"
        SACO = "saco", "Saco de 50 kg"

    productor = models.ForeignKey(Productor, on_delete=models.PROTECT, related_name="productos")
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name="productos")
    nombre = models.CharField(max_length=140)
    slug = models.SlugField(max_length=160, unique=True, blank=True)
    descripcion = models.TextField(blank=True)
    precio = models.DecimalField(
        max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    unidad = models.CharField(max_length=10, choices=Unidad.choices, default=Unidad.KG)
    stock = models.PositiveIntegerField(default=0)
    estado = models.CharField(max_length=15, choices=Estado.choices, default=Estado.BORRADOR)
    es_organico = models.BooleanField(default=False)
    fecha_cosecha = models.DateField(null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-creado", "id"]
        indexes = [
            # Consultas más frecuentes del catálogo: estado + categoría y rangos de precio.
            models.Index(fields=["estado", "categoria"], name="prod_estado_cat_idx"),
            models.Index(fields=["precio"], name="prod_precio_idx"),
            models.Index(fields=["-creado"], name="prod_creado_idx"),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _slug_unico(Producto, self.nombre, self.pk)
        super().save(*args, **kwargs)

    @property
    def disponible(self):
        return self.estado == self.Estado.ACTIVO and self.stock > 0

    def __str__(self):
        return f"{self.nombre} ({self.productor})"


class Resena(models.Model):
    """Reseña verificada: solo quien recibió el producto puede opinar."""

    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name="resenas")
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="resenas"
    )
    puntuacion = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comentario = models.TextField(blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado"]
        constraints = [
            models.UniqueConstraint(fields=["producto", "autor"], name="una_resena_por_producto")
        ]

    def __str__(self):
        return f"{self.autor} → {self.producto} ({self.puntuacion}★)"


# --------------------------------------------------------------------------
# Comercio: cupones y pedidos
# --------------------------------------------------------------------------
class ConflictoDeEstado(Exception):
    """Transición de estado no permitida (la API la traduce a HTTP 409)."""


class Cupon(models.Model):
    codigo = models.CharField(max_length=30, unique=True)
    porcentaje = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(60)]
    )
    monto_minimo = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    vigente_desde = models.DateField()
    vigente_hasta = models.DateField()
    usos_maximos = models.PositiveIntegerField(default=100)
    usos_actuales = models.PositiveIntegerField(default=0)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "cupones"

    def save(self, *args, **kwargs):
        self.codigo = self.codigo.strip().upper()
        super().save(*args, **kwargs)

    def motivo_invalido(self, subtotal, hoy):
        """Devuelve None si el cupón es aplicable o el motivo del rechazo."""
        if not self.activo:
            return "El cupón está desactivado."
        if not (self.vigente_desde <= hoy <= self.vigente_hasta):
            return "El cupón está fuera de su fecha de vigencia."
        if self.usos_actuales >= self.usos_maximos:
            return "El cupón alcanzó su límite de usos."
        if subtotal < self.monto_minimo:
            return f"El cupón requiere una compra mínima de S/ {self.monto_minimo}."
        return None

    def descuento_para(self, subtotal):
        return (subtotal * self.porcentaje / Decimal("100")).quantize(Decimal("0.01"))

    def __str__(self):
        return f"{self.codigo} (-{self.porcentaje}%)"


class Pedido(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente de pago"
        PAGADO = "pagado", "Pagado"
        ENVIADO = "enviado", "Enviado"
        ENTREGADO = "entregado", "Entregado"
        CANCELADO = "cancelado", "Cancelado"

    ENVIO_GRATIS_DESDE = Decimal("120.00")
    COSTO_ENVIO = Decimal("12.00")

    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pedidos"
    )
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PENDIENTE)
    direccion_envio = models.CharField(max_length=200)
    ciudad = models.CharField(max_length=80)
    cupon = models.ForeignKey(Cupon, null=True, blank=True, on_delete=models.PROTECT)
    subtotal = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("0.00"))
    descuento = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("0.00"))
    costo_envio = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("0.00"))
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-creado"]
        indexes = [models.Index(fields=["cliente", "estado", "-creado"], name="ped_cli_est_idx")]

    @property
    def codigo(self):
        return f"AGM-{self.creado:%Y%m}-{self.pk:05d}"

    # -- Ciclo de vida -----------------------------------------------------
    def puede_pagar(self):
        return self.estado == self.Estado.PENDIENTE

    def puede_cancelar(self):
        return self.estado in (self.Estado.PENDIENTE, self.Estado.PAGADO)

    def pagar(self):
        if not self.puede_pagar():
            raise ConflictoDeEstado(f"No se puede pagar un pedido en estado '{self.estado}'.")
        self.estado = self.Estado.PAGADO
        self.save(update_fields=["estado", "actualizado"])

    def avanzar(self):
        siguiente = {
            self.Estado.PAGADO: self.Estado.ENVIADO,
            self.Estado.ENVIADO: self.Estado.ENTREGADO,
        }.get(self.estado)
        if siguiente is None:
            raise ConflictoDeEstado(f"El pedido en estado '{self.estado}' no puede avanzar.")
        self.estado = siguiente
        self.save(update_fields=["estado", "actualizado"])

    def cancelar(self):
        """Cancela y devuelve el stock reservado por cada ítem."""
        if not self.puede_cancelar():
            raise ConflictoDeEstado(f"No se puede cancelar un pedido en estado '{self.estado}'.")
        from django.db import transaction

        with transaction.atomic():
            for item in self.items.select_related("producto"):
                producto = item.producto
                producto.stock += item.cantidad
                if producto.estado == Producto.Estado.AGOTADO:
                    producto.estado = Producto.Estado.ACTIVO
                producto.save(update_fields=["stock", "estado", "actualizado"])
            self.estado = self.Estado.CANCELADO
            self.save(update_fields=["estado", "actualizado"])

    def __str__(self):
        return self.codigo


class ItemPedido(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="items")
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name="items_pedido")
    cantidad = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    # Precio congelado al momento de la compra (el catálogo puede cambiar luego).
    precio_unitario = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["pedido", "producto"], name="un_item_por_producto")
        ]

    @property
    def subtotal(self):
        return self.precio_unitario * self.cantidad
