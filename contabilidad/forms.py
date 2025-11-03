from django import forms
from django.db import models
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory
from .models import AsientoDiario, Movimiento, PeriodoContable, Cuenta
from django.core.exceptions import ValidationError

class AsientoDiarioForm(forms.ModelForm):
    """
    Formulario para el "encabezado" del asiento (fecha, período, descripción).
    """
    
    # Sobrescribimos el campo 'periodo' para filtrar solo los abiertos
    periodo = forms.ModelChoiceField(
        queryset=PeriodoContable.objects.filter(estado=PeriodoContable.EstadoPeriodo.ABIERTO),
        label="Período Contable",
        widget=forms.Select(attrs={'class': 'block w-full mt-1 rounded-md border-gray-300 shadow-sm focus:border-sic-primary focus:ring-sic-primary'})
    )

    class Meta:
        model = AsientoDiario
        fields = ['fecha', 'periodo', 'descripcion']
        widgets = {
            'fecha': forms.DateInput(
                attrs={
                    'type': 'date', # Widget de calendario HTML5
                    'class': 'block w-full mt-1 rounded-md border-gray-300 shadow-sm focus:border-sic-primary focus:ring-sic-primary'
                }
            ),
            'descripcion': forms.Textarea(
                attrs={
                    'rows': 3,
                    'class': 'block w-full mt-1 rounded-md border-gray-300 shadow-sm focus:border-sic-primary focus:ring-sic-primary'
                }
            ),
        }

# --- Formset para los Movimientos (Líneas de la partida) ---

class MovimientoForm(forms.ModelForm):
    """
    Formulario para una línea de movimiento individual.
    """
    # Sobrescribimos 'cuenta' para filtrar solo las imputables y activas
    cuenta = forms.ModelChoiceField(
        queryset=Cuenta.objects.filter(
            es_imputable=True, 
            esta_activa=True  # No mostrar cuentas "eliminadas"
        ).order_by('codigo'),
        widget=forms.Select(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm focus:border-sic-primary focus:ring-sic-primary'})
    )

    class Meta:
        model = Movimiento
        fields = ['cuenta', 'debe', 'haber']
        widgets = {
            'debe': forms.NumberInput(attrs={'class': 'debe-input w-full text-right rounded-md border-gray-300 shadow-sm', 'min': '0', 'step': '0.01', 'value': '0.00'}),
            'haber': forms.NumberInput(attrs={'class': 'haber-input w-full text-right rounded-md border-gray-300 shadow-sm', 'min': '0', 'step': '0.01', 'value': '0.00'}),
        }

# Usamos inlineformset_factory para vincular los Movimientos al AsientoDiario
MovimientoFormSet = inlineformset_factory(
    AsientoDiario,    # Modelo Padre
    Movimiento,       # Modelo Hijo
    form=MovimientoForm, # Formulario personalizado para la línea
    extra=2,          # Empezar con 2 líneas de movimiento vacías
    can_delete=True,  # Permitir eliminar líneas
    min_num=2,        # Requerir al menos 2 líneas para la partida doble
    validate_min=True,
)


# --- Formulario para crear Períodos Personalizados ---

class PeriodoForm(forms.ModelForm):
    """
    Formulario para que el Admin cree un nuevo período con fechas personalizadas.
    """
    class Meta:
        model = PeriodoContable
        fields = ['nombre', 'fecha_inicio', 'fecha_fin']
        widgets = {
            'nombre': forms.TextInput(
                attrs={
                    'class': 'block w-full mt-1 rounded-md border-gray-300 shadow-sm focus:border-sic-primary focus:ring-sic-primary',
                    'placeholder': 'Ej. Enero 2026'
                }
            ),
            'fecha_inicio': forms.DateInput(
                attrs={
                    'type': 'date',
                    'class': 'block w-full mt-1 rounded-md border-gray-300 shadow-sm focus:border-sic-primary focus:ring-sic-primary'
                }
            ),
            'fecha_fin': forms.DateInput(
                attrs={
                    'type': 'date',
                    'class': 'block w-full mt-1 rounded-md border-gray-300 shadow-sm focus:border-sic-primary focus:ring-sic-primary'
                }
            ),
        }

    def clean(self):
        """
        Validación personalizada para asegurar que las fechas sean lógicas.
        """
        cleaned_data = super().clean()
        fecha_inicio = cleaned_data.get("fecha_inicio")
        fecha_fin = cleaned_data.get("fecha_fin")

        # IDs para exclusión en modo edición
        instance_id = self.instance.pk if self.instance else None

        if fecha_inicio and fecha_fin:
            # Validación 1: Fin no puede ser antes que Inicio
            if fecha_fin < fecha_inicio:
                raise ValidationError("La fecha de fin no puede ser anterior a la fecha de inicio.")

            # Validación 2: No permitir solapamiento con períodos existentes
            # Comprobar si algún período existente se solapa con este nuevo rango
            query_solapamiento = models.Q(fecha_inicio__lte=fecha_fin) & models.Q(fecha_fin__gte=fecha_inicio)
            
            # Excluir el propio objeto si estamos editando
            periodos_solapados = PeriodoContable.objects.filter(query_solapamiento)
            if instance_id:
                periodos_solapados = periodos_solapados.exclude(pk=instance_id)
                
            if periodos_solapados.exists():
                raise ValidationError("Las fechas de este período se solapan con un período ya existente.")
        
        return cleaned_data
    

# --- Formulario para crear/editar Cuentas ---

class CuentaForm(forms.ModelForm):
    """
    Formulario para que el Admin cree o edite una cuenta del catálogo.
    """
    # Hacemos 'padre' opcional y filtramos
    padre = forms.ModelChoiceField(
        queryset=Cuenta.objects.filter(es_imputable=False, esta_activa=True).order_by('codigo'),
        required=False, 
        widget=forms.Select(attrs={'class': 'block w-full mt-1 rounded-md border-gray-300 shadow-sm focus:border-sic-primary focus:ring-sic-primary'})
    )

    class Meta:
        model = Cuenta
        fields = [
            'codigo', 
            'nombre', 
            'padre', 
            'tipo_cuenta', 
            'naturaleza', 
            'es_imputable'
        ]
        widgets = {
            'codigo': forms.TextInput(
                attrs={
                    'class': 'block w-full mt-1 rounded-md border-gray-300 shadow-sm focus:border-sic-primary focus:ring-sic-primary',
                    'placeholder': 'Ej: 111.01'
                }
            ),
            'nombre': forms.TextInput(
                attrs={
                    'class': 'block w-full mt-1 rounded-md border-gray-300 shadow-sm focus:border-sic-primary focus:ring-sic-primary',
                    'placeholder': 'Ej: Caja Chica'
                }
            ),
            'tipo_cuenta': forms.Select(
                attrs={'class': 'block w-full mt-1 rounded-md border-gray-300 shadow-sm focus:border-sic-primary focus:ring-sic-primary'}
            ),
            'naturaleza': forms.Select(
                attrs={'class': 'block w-full mt-1 rounded-md border-gray-300 shadow-sm focus:border-sic-primary focus:ring-sic-primary'}
            ),
            'es_imputable': forms.CheckboxInput(
                attrs={'class': 'h-4 w-4 text-sic-primary rounded border-gray-300 focus:ring-sic-primary'}
            ),
        }
        help_texts = {
            'padre': 'Seleccione la cuenta de grupo a la que pertenece.',
            'tipo_cuenta': 'Clasificación para reportes financieros.',
            'naturaleza': 'Indica si el saldo normal es Deudor o Acreedor.',
        }

    # --- INICIO DE MODIFICACIÓN ---
    def __init__(self, *args, **kwargs):
        """
        Sobrescribe el init para bloquear campos en modo 'Editar'.
        """
        super().__init__(*args, **kwargs)
        
        # Si 'self.instance.pk' existe, significa que estamos EDITANDO (no creando)
        if self.instance and self.instance.pk:
            # Deshabilitamos los campos que no se deben modificar
            self.fields['padre'].disabled = True
            self.fields['tipo_cuenta'].disabled = True
            self.fields['naturaleza'].disabled = True
            self.fields['es_imputable'].disabled = True

            # (Opcional) Añadir 'help_text' para explicar por qué están bloqueados
            self.fields['padre'].help_text = 'No se puede cambiar el padre de una cuenta existente.'
            self.fields['tipo_cuenta'].help_text = 'No se puede cambiar el tipo de una cuenta existente.'
            self.fields['naturaleza'].help_text = 'No se puede cambiar la naturaleza de una cuenta existente.'
    # --- FIN DE MODIFICACIÓN ---

    def clean_codigo(self):
        # Asegurarse de que el código sea único (ignorando el caso de editarse a sí mismo)
        codigo = self.cleaned_data.get('codigo')
        # 'self.instance' es la cuenta que se está editando (si existe)
        if self.instance.pk:
            if Cuenta.objects.filter(codigo=codigo).exclude(pk=self.instance.pk).exists():
                raise ValidationError("Ya existe otra cuenta con este código.")
        else:
            if Cuenta.objects.filter(codigo=codigo).exists():
                raise ValidationError("Ya existe una cuenta con este código.")
        return codigo

    def clean(self):
        cleaned_data = super().clean()
        es_imputable = cleaned_data.get('es_imputable')
        padre = cleaned_data.get('padre')

        # Si estamos creando (instance.pk no existe) aplicamos validación
        if not self.instance.pk:
            # Validación: Si es imputable, DEBE tener un padre.
            if es_imputable and not padre:
                raise ValidationError("Una cuenta imputable (de movimiento) debe pertenecer a una cuenta de grupo (cuenta padre).")
            
        return cleaned_data

