from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal

# --- Modelo de Catálogo de Cuentas ---

class Cuenta(models.Model):
    """
    Representa una cuenta del Catálogo de Cuentas.
    El catálogo está estructurado como un árbol (jerarquía)
    usando el campo 'padre'.
    """

    # --- Tipos de Cuenta (Clasificación para Reportes) ---
    class TipoCuenta(models.TextChoices):
        ACTIVO = 'ACTIVO', 'Activo'
        PASIVO = 'PASIVO', 'Pasivo'
        PATRIMONIO = 'PATRIMONIO', 'Patrimonio'
        INGRESO = 'INGRESO', 'Ingreso'
        COSTO = 'COSTO', 'Costo'
        GASTO = 'GASTO', 'Gasto'
        CUENTA_DE_ORDEN = 'ORDEN', 'Cuenta de Orden'

    # --- Naturaleza de la Cuenta ---
    class NaturalezaCuenta(models.TextChoices):
        DEUDORA = 'DEUDORA', 'Deudora'
        ACREEDORA = 'ACREEDORA', 'Acreedora'

    codigo = models.CharField(
        max_length=20, 
        unique=True, 
        help_text="Código único de la cuenta (ej. 111, 121.01)"
    )
    nombre = models.CharField(
        max_length=255, 
        help_text="Nombre descriptivo de la cuenta (ej. Caja General)"
    )
    
    padre = models.ForeignKey(
        'self', 
        null=True, 
        blank=True, 
        on_delete=models.PROTECT, # Proteger para no borrar padres con hijos
        related_name='hijos',
        help_text="Cuenta padre a la que pertenece esta subcuenta"
    )

    tipo_cuenta = models.CharField(
        max_length=10,
        choices=TipoCuenta.choices,
        help_text="Clasificación principal para estados financieros"
    )

    naturaleza = models.CharField(
        max_length=10,
        choices=NaturalezaCuenta.choices,
        help_text="Naturaleza de la cuenta (Deudora o Acreedora)"
    )

    es_imputable = models.BooleanField(
        default=False,
        help_text="Indica si la cuenta puede recibir movimientos (transacciones)"
    )

    class Meta:
        ordering = ['codigo']
        verbose_name = "Cuenta Contable"
        verbose_name_plural = "Catálogo de Cuentas"

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"

# --- Modelo de Períodos Contables ---

class PeriodoContable(models.Model):
    """
    Define un período contable (ej. Enero 2024).
    Las transacciones solo pueden registrarse en períodos abiertos.
    """
    class EstadoPeriodo(models.TextChoices):
        ABIERTO = 'ABIERTO', 'Abierto'
        CERRADO = 'CERRADO', 'Cerrado'

    nombre = models.CharField(
        max_length=100, 
        unique=True,
        help_text="Nombre del período (ej. Enero 2024)"
    )
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    estado = models.CharField(
        max_length=10,
        choices=EstadoPeriodo.choices,
        default=EstadoPeriodo.ABIERTO
    )

    class Meta:
        ordering = ['-fecha_inicio']
        verbose_name = "Período Contable"
        verbose_name_plural = "Períodos Contables"

    def __str__(self):
        return f"{self.nombre} ({self.get_estado_display()})"

    def clean(self):
        # Validación para asegurar que las fechas sean lógicas
        if self.fecha_inicio and self.fecha_fin and self.fecha_inicio > self.fecha_fin:
            raise ValidationError("La fecha de inicio no puede ser posterior a la fecha de fin.")

# --- Modelo de Asiento Diario (Partida) ---

class AsientoDiario(models.Model):
    """
    Representa una partida o asiento contable en el libro diario.
    Contiene múltiples movimientos (partida doble).
    """
    periodo = models.ForeignKey(
        PeriodoContable,
        on_delete=models.PROTECT, # No permitir borrar períodos con asientos
        related_name="asientos"
    )
    numero_partida = models.PositiveIntegerField(
        editable=False,
        help_text="Número de partida correlativo dentro del período"
    )
    fecha = models.DateField(
        default=timezone.now,
        help_text="Fecha de la transacción"
    )
    descripcion = models.TextField(
        blank=True,
        help_text="Descripción del asiento (concepto, glosa)"
    )
    creado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="asientos_creados"
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['periodo', 'numero_partida']
        # Asegura que el número de partida sea único POR PERÍODO
        unique_together = ('periodo', 'numero_partida')
        verbose_name = "Asiento Diario"
        verbose_name_plural = "Libro Diario"

    def __str__(self):
        return f"Partida {self.numero_partida} ({self.fecha}) - {self.descripcion[:30]}..."

    def clean(self):
        """
        Validaciones personalizadas antes de guardar.
        """
        # 1. Validar que el período esté abierto
        # (Se comprueba en el 'save' para asegurar que el periodo existe,
        # pero también es bueno tenerlo aquí para validación de formularios)
        if hasattr(self, 'periodo') and self.periodo.estado == PeriodoContable.EstadoPeriodo.CERRADO:
            raise ValidationError(f"El período '{self.periodo.nombre}' está cerrado. No se pueden registrar transacciones.")
        
        # 2. Validar que la fecha del asiento esté dentro del rango del período
        if hasattr(self, 'periodo') and self.fecha:
            if not (self.periodo.fecha_inicio <= self.fecha <= self.periodo.fecha_fin):
                raise ValidationError(
                    f"La fecha {self.fecha} está fuera del rango del período "
                    f"({self.periodo.fecha_inicio} al {self.periodo.fecha_fin})."
                )

    def save(self, *args, **kwargs):
        """
        Sobrescribe el método save para asignar el número_partida correlativo
        y ejecutar validaciones finales.
        """
        
        # Validar período y fecha antes de asignar número
        self.clean()
        
        # Asignar número de partida solo al crear un nuevo asiento
        if not self.pk and self.periodo:
            # 1. Obtener el último número de partida para ESTE período
            ultimo_asiento = AsientoDiario.objects.filter(periodo=self.periodo).order_by('-numero_partida').first()
            
            if ultimo_asiento:
                self.numero_partida = ultimo_asiento.numero_partida + 1
            else:
                # Es el primer asiento del período
                self.numero_partida = 1
        
        super().save(*args, **kwargs)

    # Propiedades para verificar la partida doble (útil en vistas y admin)
    @property
    def total_debe(self):
        # 'movimientos' es el related_name del ForeignKey en el modelo Movimiento
        return self.movimientos.aggregate(total=models.Sum('debe'))['total'] or Decimal('0.00')

    @property
    def total_haber(self):
        return self.movimientos.aggregate(total=models.Sum('haber'))['total'] or Decimal('0.00')

    @property
    def esta_cuadrado(self):
        return self.total_debe == self.total_haber

# --- Modelo de Movimiento (Línea de Asiento) ---

class Movimiento(models.Model):
    """
    Representa una línea individual (débito o crédito) dentro
    de un AsientoDiario.
    """
    asiento = models.ForeignKey(
        AsientoDiario,
        on_delete=models.CASCADE,
        related_name="movimientos",
        help_text="Asiento al que pertenece este movimiento"
    )
    cuenta = models.ForeignKey(
        Cuenta,
        on_delete=models.PROTECT, # No borrar cuentas con movimientos
        help_text="Cuenta contable afectada",
        # Optimización: Solo mostrar cuentas que pueden recibir transacciones
        limit_choices_to={'es_imputable': True}
    )
    debe = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0
    )
    haber = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0
    )

    class Meta:
        ordering = ['pk'] # Ordenar por creación
        verbose_name = "Movimiento"
        verbose_name_plural = "Movimientos"

    def __str__(self):
        return f"{self.cuenta.codigo} | Debe: {self.debe} | Haber: {self.haber}"

    def clean(self):
        # 1. Validar que no se ingrese debe y haber al mismo tiempo
        if self.debe > 0 and self.haber > 0:
            raise ValidationError("Un movimiento no puede tener Débito y Haber al mismo tiempo.")
        
        # 2. Validar que la cuenta sea imputable (aunque limit_choices_to ayuda)
        if not self.cuenta.es_imputable:
            raise ValidationError(f"La cuenta '{self.cuenta.nombre}' no es imputable. No puede recibir movimientos.")