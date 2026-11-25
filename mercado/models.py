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
