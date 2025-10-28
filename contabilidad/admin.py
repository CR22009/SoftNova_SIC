from django.contrib import admin
from .models import Cuenta, PeriodoContable, AsientoDiario, Movimiento
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
    list_display = ('nombre', 'fecha_inicio', 'fecha_fin', 'estado')
    list_filter = ('estado',)
    # Permite al Admin cambiar el estado (Abrir/Cerrar) desde la lista
    list_editable = ('estado',)
    search_fields = ('nombre',)
    
    # Solo el superusuario (Admin) debe poder gestionar períodos
    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
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

@admin.register(AsientoDiario)
class AsientoDiarioAdmin(admin.ModelAdmin):
    """
    Admin para que el 'Contador' gestione los asientos diarios.
    """
    
    # --- Configuración del formulario de edición ---
    inlines = [MovimientoInline] # ¡La magia! Incrusta los movimientos
    fields = ('periodo', 'fecha', 'descripcion', ('numero_partida', 'creado_por', 'creado_en'))
    autocomplete_fields = ('periodo',)
    
    # Campos que no se pueden editar manualmente
    readonly_fields = ('numero_partida', 'creado_por', 'creado_en')

    # --- Configuración de la lista de asientos ---
    list_display = (
        'fecha', 
        'periodo',
        'numero_partida', 
        'descripcion_corta', 
        'total_debe', 
        'total_haber',
        'estado_partida' # Columna personalizada
    )
    list_filter = ('periodo', 'fecha', 'creado_por')
    search_fields = ('numero_partida', 'descripcion')
    date_hierarchy = 'fecha'

    # --- Métodos personalizados para la lista ---
    
    @admin.display(description='Descripción')
    def descripcion_corta(self, obj):
        return (obj.descripcion[:40] + '...') if len(obj.descripcion) > 40 else obj.descripcion

    @admin.display(description='Estado', ordering='total_debe') # Permite ordenar por aquí
    def estado_partida(self, obj):
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
        elif asiento.total_debe == 0:
            self.message_user(
                request, 
                f"Advertencia: La Partida N° {asiento.numero_partida} está VACÍA (total 0.00).",
                level='WARNING'
            )

