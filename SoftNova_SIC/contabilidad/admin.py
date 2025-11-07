from django.contrib import admin
from .models import Cuenta, PeriodoContable, AsientoDiario, Movimiento,SalarioEstimadoMODAnual,CosteoProyecto,CostoIndirectoAnual
from decimal import Decimal

# --- Admin de Cuenta (Existente) ---
@admin.register(Cuenta)
class CuentaAdmin(admin.ModelAdmin):
    list_display = (
        'codigo', 
        'nombre', 
        'tipo_cuenta', 
        'naturaleza', 
        'padre', 
        'es_imputable'
    )
    list_editable = ('es_imputable',)
    list_filter = ('tipo_cuenta', 'naturaleza', 'es_imputable')
    search_fields = ('codigo', 'nombre')
    autocomplete_fields = ('padre',)
    fieldsets = (
        (None, {
            'fields': ('nombre', 'codigo', 'padre')
        }),
        ('Clasificación Contable', {
            'fields': ('tipo_cuenta', 'naturaleza', 'es_imputable')
        }),
    )

# --- Admin de Períodos Contables ---
@admin.register(PeriodoContable)
class PeriodoContableAdmin(admin.ModelAdmin):
    """
    Admin para que el 'Admin' del sistema gestione los períodos.
    """
    list_display = ('nombre', 'fecha_inicio', 'fecha_fin', 'estado', 'asiento_cierre', 'asiento_apertura_siguiente')
    list_filter = ('estado',)
    # --- CAMBIO: list_editable se quita para forzar el uso de la vista personalizada ---
    # list_editable = ('estado',) 
    search_fields = ('nombre',)
    
    # --- NUEVO: Hacemos los campos de estado y asientos solo de lectura ---
    readonly_fields = ('estado', 'asiento_cierre', 'asiento_apertura_siguiente')
    
    # Solo el superusuario (Admin) debe poder gestionar períodos
    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        # Permitimos añadir desde el admin por si acaso, aunque la vista lo manejará
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        # Cambiar SÍ, pero los campos clave son readonly
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        # No deberíamos permitir borrar períodos con asientos
        return request.user.is_superuser


# --- Admin de Asientos y Movimientos ---

class MovimientoInline(admin.TabularInline):
    """
    Permite agregar movimientos (líneas de débito/crédito)
    directamente DENTRO del formulario del Asiento Diario.
    """
    model = Movimiento
    extra = 2 # Muestra 2 líneas en blanco por defecto
    autocomplete_fields = ('cuenta',) # Usa autocompletar para buscar cuentas
    
    # Campos a mostrar en la línea
    fields = ('cuenta', 'debe', 'haber')
    
    # --- NUEVO: Hacer que los asientos automáticos no se puedan editar ---
    def get_readonly_fields(self, request, obj=None):
        if obj and obj.es_asiento_automatico:
            return ('cuenta', 'debe', 'haber')
        return ()

@admin.register(AsientoDiario)
class AsientoDiarioAdmin(admin.ModelAdmin):
    """
    Admin para que el 'Contador' gestione los asientos diarios.
    """
    
    # --- Configuración del formulario de edición ---
    inlines = [MovimientoInline] # ¡La magia! Incrusta los movimientos
    fields = ('periodo', 'fecha', 'descripcion', ('numero_partida', 'creado_por', 'creado_en', 'es_asiento_automatico'))
    autocomplete_fields = ('periodo',)
    
    # Campos que no se pueden editar manualmente
    readonly_fields = ('numero_partida', 'creado_por', 'creado_en', 'es_asiento_automatico')

    # --- Configuración de la lista de asientos ---
    list_display = (
        'fecha', 
        'periodo',
        'numero_partida', 
        'descripcion_corta', 
        'total_debe', 
        'total_haber',
        'estado_partida', # Columna personalizada
        'es_asiento_automatico', # Nuevo
    )
    list_filter = ('periodo', 'fecha', 'creado_por', 'es_asiento_automatico') # Nuevo
    search_fields = ('numero_partida', 'descripcion')
    date_hierarchy = 'fecha'

    # --- Métodos personalizados para la lista ---
    
    @admin.display(description='Descripción')
    def descripcion_corta(self, obj):
        return (obj.descripcion[:40] + '...') if len(obj.descripcion) > 40 else obj.descripcion

    @admin.display(description='Estado', ordering='total_debe') # Permite ordenar por aquí
    def estado_partida(self, obj):
        if obj.es_asiento_automatico:
            return "🤖 Automático"
        if obj.esta_cuadrado and obj.total_debe > 0:
            return "✅ Cuadrado"
        elif obj.total_debe == 0 and obj.total_haber == 0:
            return "❌ Vacío"
        else:
            return "⚠️ Descuadrado"

    def get_queryset(self, request):
        # Optimización: Prefetch (precargar) movimientos para calcular totales
        return super().get_queryset(request).prefetch_related('movimientos')

    def save_model(self, request, obj, form, change):
        """
        Al guardar desde el admin, asigna el usuario actual.
        """
        if not obj.pk: # Solo al crear
            obj.creado_por = request.user
        super().save_model(request, obj, form, change)
        
    def save_formset(self, request, form, formset, change):
        """
        Validación de partida doble después de guardar los movimientos.
        """
        super().save_formset(request, form, formset, change)
        # 'instance' es el AsientoDiario que se acaba de guardar
        asiento = form.instance
        
        # Forzar una recarga de los totales (ya que se guardaron los inlines)
        asiento.refresh_from_db() 
        
        if not asiento.esta_cuadrado:
            # Informar al usuario que la partida está descuadrada
            self.message_user(
                request, 
                f"Advertencia: La Partida N° {asiento.numero_partida} está DESCUADRADA. "
                f"(Debe: {asiento.total_debe}, Haber: {asiento.total_haber})",
                level='WARNING'
            )
        elif asiento.total_debe == 0 and not asiento.es_asiento_automatico: # Permitir asientos automáticos vacíos si es necesario
            self.message_user(
                request, 
                f"Advertencia: La Partida N° {asiento.numero_partida} está VACÍA (total 0.00).",
                level='WARNING'
            )
            
    # --- NUEVO: Proteger asientos automáticos ---
    def get_readonly_fields(self, request, obj=None):
        # Si el asiento es automático, hacerlo todo de solo lectura
        if obj and obj.es_asiento_automatico:
            return ('periodo', 'fecha', 'descripcion', 'numero_partida', 'creado_por', 'creado_en', 'es_asiento_automatico')
        return self.readonly_fields

    def has_delete_permission(self, request, obj=None):
        # No permitir borrar asientos automáticos
        if obj and obj.es_asiento_automatico:
            return False
        return super().has_delete_permission(request, obj)

# --- (INICIO) CÓDIGO AGREGADO PARA COSTEO ---

@admin.register(SalarioEstimadoMODAnual)
class SalarioEstimadoMODAnualAdmin(admin.ModelAdmin):
    """
    Admin para configurar el Salario MOD base de un período.
    """
    list_display = ('periodo', 'descripcion', 'salario', 'mod_unitario')
    # Protege el campo 'mod_unitario' que se calcula solo
    readonly_fields = ('mod_unitario',)
    search_fields = ('descripcion', 'periodo__nombre')
    list_filter = ('periodo',)

@admin.register(CostoIndirectoAnual)
class CostoIndirectoAnualAdmin(admin.ModelAdmin):
    """
    Admin para registrar las líneas de CIF de un período.
    """
    list_display = ('nombre', 'periodo', 'categoria', 'costo_anual_estimado', 'factor')
    list_filter = ('periodo', 'categoria')
    search_fields = ('nombre', 'periodo__nombre')
    autocomplete_fields = ('periodo',)
    
    # Protege el campo 'factor' que se calcula solo
    readonly_fields = ('factor',)

@admin.register(CosteoProyecto)
class CosteoProyectoAdmin(admin.ModelAdmin):
    """
    Admin para registrar y calcular el costeo de un proyecto.
    """
    list_display = ('idCosteo', 'descripcion_proyecto_corta', 'periodo', 'horas_esfuerzo', 'cif', 'mod_total', 'total')
    list_filter = ('periodo',)
    search_fields = ('descripcion_proyecto', 'idCosteo', 'periodo__nombre')
    autocomplete_fields = ('periodo',)
    
    # Protege todos los campos calculados automáticamente
    readonly_fields = ('mod_unitario', 'factor_suma', 'mod_total', 'total')

    # Función auxiliar para acortar la descripción en la lista
    @admin.display(description='Descripción Proyecto')
    def descripcion_proyecto_corta(self, obj):
        if obj.descripcion_proyecto:
            return (obj.descripcion_proyecto[:40] + '...') if len(obj.descripcion_proyecto) > 40 else obj.descripcion_proyecto
        return '-' # Muestra un guion si no hay descripción

# --- (FIN) CÓDIGO AGREG
