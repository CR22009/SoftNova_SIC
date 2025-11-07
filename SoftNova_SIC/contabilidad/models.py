from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from django.db.models import Sum, Q # Importar Q

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
    
    # --- NUEVO CAMPO PARA SOFT DELETE ---
    esta_activa = models.BooleanField(
        default=True,
        help_text="Indica si la cuenta está activa. Las cuentas inactivas no se pueden usar en nuevos asientos."
    )

    class Meta:
        ordering = ['codigo']
        verbose_name = "Cuenta Contable"
        verbose_name_plural = "Catálogo de Cuentas"

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"

    def get_saldo_total(self):
        """
        Calcula el saldo neto total (histórico) de esta cuenta.
        Se usa para verificar si se puede eliminar.
        """
        if not self.es_imputable:
            # Las cuentas de grupo no tienen saldo propio
            return Decimal('0.00')

        agregado = self.movimiento_set.aggregate(
            total_debe=Sum('debe'),
            total_haber=Sum('haber')
        )
        total_debe = agregado.get('total_debe') or Decimal('0.00')
        total_haber = agregado.get('total_haber') or Decimal('0.00')
        
        if self.naturaleza == self.NaturalezaCuenta.DEUDORA:
            return total_debe - total_haber
        else:
            return total_haber - total_debe

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

    # --- NUEVOS CAMPOS PARA EL CIERRE ---
    asiento_cierre = models.ForeignKey(
        'AsientoDiario',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='periodo_cerrado_por',
        help_text="Asiento de Cierre (Resultados) de este período."
    )
    asiento_apertura_siguiente = models.ForeignKey(
        'AsientoDiario',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='periodo_abierto_por',
        help_text="Asiento de Apertura (Balance) creado para el *siguiente* período."
    )
    # --- FIN DE NUEVOS CAMPOS ---

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
    
    # --- NUEVO CAMPO PARA CIERRE/APERTURA ---
    es_asiento_automatico = models.BooleanField(
        default=False,
        help_text="Indica si es un asiento de Cierre o Apertura generado por el sistema."
    )
    # --- FIN DE NUEVO CAMPO ---

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
        if hasattr(self, 'periodo') and self.periodo.estado == PeriodoContable.EstadoPeriodo.CERRADO:
            # Permitir asientos automáticos incluso si el período se está cerrando
            if not self.es_asiento_automatico:
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
        # No validamos si es un asiento automático (para evitar problemas en el cierre)
        if not self.es_asiento_automatico:
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
        # Y que estén ACTIVAS (esta es la clave del soft delete)
        limit_choices_to={'es_imputable': True, 'esta_activa': True}
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
            
        # 3. Validar que la cuenta esté activa
        if not self.cuenta.esta_activa:
            raise ValidationError(f"La cuenta '{self.cuenta.nombre}' está inactiva y no puede recibir nuevos movimientos.")

 #COSTEO


# --- Nuevos Modelos Basados en tus Imágenes ---

## 💰 Modelo para Salario MOD Anual (Imagen 3)
# Este modelo almacena el salario base y calcula automáticamente el MOD Unitario
# para un período contable específico.

class SalarioEstimadoMODAnual(models.Model):
    """
    Configuración del Salario Estimado de Mano de Obra Directa (MOD) Anual.
    Calcula y almacena el MOD Unitario (costo por hora).
    Basado en la Imagen 3 ('image_b25d61.png').
    """
    periodo = models.OneToOneField(
        PeriodoContable,
        on_delete=models.CASCADE,
        primary_key=True,
        help_text="Período contable al que aplica este salario."
    )
    descripcion = models.CharField(
        max_length=255, 
        default="SalarioEstimadoMODAnual"
    )
    salario = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        help_text="Salario Anual Estimado (Ej. 126,000.00)"
    )
    mod_unitario = models.DecimalField(
        max_digits=12, 
        decimal_places=4,
        editable=False,
        null=True, 
        blank=True,
        help_text="Costo por hora (MOD Unitario) calculado automáticamente."
    )

    def __str__(self):
        return f"{self.descripcion} ({self.periodo.nombre}) - ${self.salario}"

    def calcular_mod_unitario(self):
        """
        Calcula el MOD Unitario según tu fórmula:
        (((SalarioAnual / 14) / 12)) / ((44 * 52) / 12)
        """
        if self.salario is None or self.salario == 0:
            return Decimal(0)
        
        try:
            # Constantes de la fórmula
            DIVISOR_SALARIO = Decimal(14)
            MESES_ANIO = Decimal(12)
            HORAS_SEMANA = Decimal(44)
            SEMANAS_ANIO = Decimal(52)
            
            # Numerador: (((salrioAnualMOd/14)/12))
            numerador = (self.salario / DIVISOR_SALARIO) / MESES_ANIO
            
            # Denominador: ((44*52)/12)
            denominador = (HORAS_SEMANA * SEMANAS_ANIO) / MESES_ANIO
            
            if denominador == 0:
                return Decimal(0)

            # Cálculo final
            resultado = numerador / denominador
            return resultado.quantize(Decimal('0.0001')) # Redondea a 4 decimales
            
        except (TypeError, ZeroDivisionError):
            return Decimal(0)

    def save(self, *args, **kwargs):
        # Calcula el MOD unitario antes de guardar
        self.mod_unitario = self.calcular_mod_unitario()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Configuración Salario MOD Anual"
        verbose_name_plural = "Configuraciones Salario MOD Anual"


## 🧾 Modelo para CIF Específico (Imagen 2)
# Almacena cada línea de costo indirecto y calcula su factor individual
# en relación con el Salario MOD Anual del mismo período.

class CostoIndirectoAnual(models.Model):
    """
    Define un Costo Indirecto de Fabricación (CIF) Específico Anual.
    Calcula el 'Factor' basado en el Salario MOD Anual del período.
    Basado en la Imagen 2 ('image_b25d06.png').
    """
    
    class CategoriaChoices(models.TextChoices):
        PRODUCCION = 'PRODUCCION', 'Costo General de Produccion'
        POSTVENTA = 'POSTVENTA', 'Costos Prostventa'
        MANO_OBRA_IND = 'MANO_OBRA_IND', 'Mano de Obra Indirecta'
        MATERIALES_SUM = 'MATERIALES_SUM', 'Materiales y Suministros Indirectos'
        OTRO = 'OTRO', 'Otro'

    periodo = models.ForeignKey(
        PeriodoContable,
        on_delete=models.CASCADE,
        related_name="costos_indirectos",
        help_text="Período contable al que aplica este costo."
    )
    nombre = models.CharField(
        max_length=255,
        help_text="Nombre del CIF Específico (Ej. Alquiler o Renta de Oficinas)"
    )
    categoria = models.CharField(
        max_length=100,
        choices=CategoriaChoices.choices,
        default=CategoriaChoices.OTRO
    )
    costo_anual_estimado = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        help_text="Costo Anual Estimado para este ítem.",
       
        default=Decimal('0.00') # Asigna 0.00 por defecto
    )
    factor = models.DecimalField(
        max_digits=15, 
        decimal_places=10,
        editable=False,
        null=True, 
        blank=True,
        help_text="Factor calculado (Costo Anual / Salario MOD Anual)"
    )

    def __str__(self):
        return f"{self.nombre} ({self.periodo.nombre}) - ${self.costo_anual_estimado}"

    def calcular_factor(self):
        """
        Calcula el Factor dividiendo el costo anual entre 
        el Salario MOD Anual del mismo período.
        """
        try:
            # Busca la configuración de salario para el mismo período
            salario_config = SalarioEstimadoMODAnual.objects.get(periodo=self.periodo)
            
            if salario_config.salario and salario_config.salario > 0:
                resultado = self.costo_anual_estimado / salario_config.salario
                return resultado.quantize(Decimal('0.0000000001')) # Redondea a 10 decimales
            
        except SalarioEstimadoMODAnual.DoesNotExist:
            # No se puede calcular si no hay salario configurado
            pass
        except (TypeError, ZeroDivisionError):
            pass
            
        return Decimal(0)

    def save(self, *args, **kwargs):
        # Calcula el factor antes de guardar
        self.factor = self.calcular_factor()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Costo Indirecto Anual (CIF)"
        verbose_name_plural = "Costos Indirectos Anuales (CIF)"
        unique_together = ('periodo', 'nombre') # Evita duplicados en el mismo período


## 📋 Modelo para Costeo de Proyecto (Imagen 1)
# Este es el modelo principal que consume la configuración.
# El usuario ingresa las 'Horas de Esfuerzo' y el 'CIF'.
# El modelo calcula el 'Total' automáticamente.

class CosteoProyecto(models.Model):
    """
    Registro de costeo para un proyecto específico.
    Utiliza los valores configurados de MOD Unitario y Factores.
    Basado en la Imagen 1 ('image_b25dbc.png').
    """
    idCosteo = models.AutoField(primary_key=True)
    periodo = models.ForeignKey(
        PeriodoContable,
        on_delete=models.PROTECT, # Proteger para no borrar costeos si se borra un período
        help_text="Período de configuración que usará este costeo."
    )
    descripcion_proyecto = models.TextField(
        blank=True, 
        null=True
    )
    
    # --- Campos de Entrada (Input) ---
    horas_esfuerzo = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Horas de esfuerzo ingresadas para el proyecto (Ej. 320)"
    )
    cif = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        help_text="Costo Indirecto de Fabricación asignado (Ej. 309.87)"
    )

    # --- Campos Calculados (Automáticos) ---
    mod_unitario = models.DecimalField(
        max_digits=12, 
        decimal_places=4,
        editable=False,
        help_text="Costo MOD por hora (obtenido de la config. del período)"
    )
    factor_suma = models.DecimalField(
        max_digits=15, 
        decimal_places=10,
        editable=False,
        # --- MODIFICACIÓN 1: Actualizar el help_text ---
        help_text="Suma de factores CIF del período / 12"
    )
    mod_total = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        editable=False,
        help_text="MOD Unitario * Horas de Esfuerzo"
    )
    total = models.DecimalField(
        max_digits=14, 
        decimal_places=2,
        editable=False,
        help_text="Costo total del proyecto (MOD Total + CIF)"
    )

    def __str__(self):
        return f"Costeo {self.idCosteo}: {self.descripcion_proyecto[:50]}... ({self.periodo.nombre})"

    def recalcular_costeo(self):
        """
        Obtiene los valores de configuración del período y calcula los totales.
        """
        try:
            # 1. Obtener el MOD Unitario de la configuración del período
            salario_config = SalarioEstimadoMODAnual.objects.get(periodo=self.periodo)
            self.mod_unitario = salario_config.mod_unitario or Decimal(0)
            
            # --- MODIFICACIÓN 2: Actualizar el cálculo de factor_suma ---
            # 2. Obtener la Suma de Factores (FactorSuma) y dividirla entre 12
            agregado = CostoIndirectoAnual.objects.filter(
                periodo=self.periodo
            ).aggregate(
                suma_factores=Sum('factor')
            )
            suma_bruta = agregado['suma_factores'] or Decimal(0)
            
            # Dividimos la suma bruta entre 12
            self.factor_suma = (suma_bruta / Decimal(12)).quantize(Decimal('0.0000000001')) 
            # --- Fin de la Modificación 2 ---

            # 3. Calcular MOD Total (MOD Unitario * Horas de Esfuerzo)
            self.mod_total = (self.mod_unitario * self.horas_esfuerzo).quantize(Decimal('0.01'))
            
            # 4. Calcular Total (MOD Total + CIF)
            #    (Según tu fórmula: "total es la suma de modunitario por mano de esfuerzo mas los cif")
            self.total = (self.mod_total + self.cif).quantize(Decimal('0.01'))

        except SalarioEstimadoMODAnual.DoesNotExist:
            # ... (resto del método sin cambios)
            raise ValidationError(
                f"No existe configuración de 'SalarioEstimadoMODAnual' para el período '{self.periodo}'. "
                f"Por favor, configure primero el salario para este período."
            )
        except TypeError:
             raise ValidationError("Error en el tipo de datos. Asegúrese de que 'horas_esfuerzo' y 'cif' sean números.")


    def save(self, *args, **kwargs):
        # ... (sin cambios)
        self.recalcular_costeo()
        super().save(*args, **kwargs)

    class Meta:
        # ... (sin cambios)
        verbose_name = "Costeo de Proyecto"
        verbose_name_plural = "Costeos de Proyectos"
        ordering = ['-periodo', '-idCosteo']
    """
    Registro de costeo para un proyecto específico.
    Utiliza los valores configurados de MOD Unitario y Factores.
    Basado en la Imagen 1 ('image_b25dbc.png').
    """
    idCosteo = models.AutoField(primary_key=True)
    periodo = models.ForeignKey(
        PeriodoContable,
        on_delete=models.PROTECT, # Proteger para no borrar costeos si se borra un período
        help_text="Período de configuración que usará este costeo."
    )
    descripcion_proyecto = models.TextField(
        blank=True, 
        null=True
    )
    
    # --- Campos de Entrada (Input) ---
    horas_esfuerzo = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Horas de esfuerzo ingresadas para el proyecto (Ej. 320)"
    )
    cif = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        help_text="Costo Indirecto de Fabricación asignado (Ej. 309.87)"
    )

    # --- Campos Calculados (Automáticos) ---
    mod_unitario = models.DecimalField(
        max_digits=12, 
        decimal_places=4,
        editable=False,
        help_text="Costo MOD por hora (obtenido de la config. del período)"
    )
    factor_suma = models.DecimalField(
        max_digits=15, 
        decimal_places=10,
        editable=False,
        help_text="Suma de todos los factores CIF del período"
    )
    mod_total = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        editable=False,
        help_text="MOD Unitario * Horas de Esfuerzo"
    )
    total = models.DecimalField(
        max_digits=14, 
        decimal_places=2,
        editable=False,
        help_text="Costo total del proyecto (MOD Total + CIF)"
    )

    def __str__(self):
        return f"Costeo {self.idCosteo}: {self.descripcion_proyecto[:50]}... ({self.periodo.nombre})"

    def recalcular_costeo(self):
        """
        Obtiene los valores de configuración del período y calcula los totales.
        """
        try:
            # 1. Obtener el MOD Unitario de la configuración del período
            salario_config = SalarioEstimadoMODAnual.objects.get(periodo=self.periodo)
            self.mod_unitario = salario_config.mod_unitario or Decimal(0)
            
            # 2. Obtener la Suma de Factores (FactorSuma)
            agregado = CostoIndirectoAnual.objects.filter(
                periodo=self.periodo
            ).aggregate(
                suma_factores=Sum('factor')
            )
            self.factor_suma = agregado['suma_factores'] or Decimal(0)

            # 3. Calcular MOD Total (MOD Unitario * Horas de Esfuerzo)
            self.mod_total = (self.mod_unitario * self.horas_esfuerzo).quantize(Decimal('0.01'))
            
            # 4. Calcular Total (MOD Total + CIF)
            #    (Según tu fórmula: "total es la suma de modunitario por mano de esfuerzo mas los cif")
            self.total = (self.mod_total + self.cif).quantize(Decimal('0.01'))

        except SalarioEstimadoMODAnual.DoesNotExist:
            # No se puede calcular si el período no tiene salario configurado
            raise ValidationError(
                f"No existe configuración de 'SalarioEstimadoMODAnual' para el período '{self.periodo}'. "
                f"Por favor, configure primero el salario para este período."
            )
        except TypeError:
             raise ValidationError("Error en el tipo de datos. Asegúrese de que 'horas_esfuerzo' y 'cif' sean números.")


    def save(self, *args, **kwargs):
        # Ejecuta todos los cálculos antes de guardar el objeto
        self.recalcular_costeo()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Costeo de Proyecto"
        verbose_name_plural = "Costeos de Proyectos"
        ordering = ['-periodo', '-idCosteo']
