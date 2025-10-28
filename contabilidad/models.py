from django.db import models
from django.contrib.auth.models import User

# --- Modelos del Módulo de Contabilidad ---

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

# --- Aquí irán los demás modelos (AsientoDiario, Movimiento, etc.) en el futuro ---
