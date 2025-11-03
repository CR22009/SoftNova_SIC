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
    # Sobrescribimos 'cuenta' para filtrar solo las imputables
    cuenta = forms.ModelChoiceField(
        queryset=Cuenta.objects.filter(es_imputable=True).order_by('codigo'),
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


# --- NUEVO: Formulario para crear Períodos Personalizados ---

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

        if fecha_inicio and fecha_fin:
            # Validación 1: Fin no puede ser antes que Inicio
            if fecha_fin < fecha_inicio:
                raise ValidationError("La fecha de fin no puede ser anterior a la fecha de inicio.")

            # Validación 2: No permitir solapamiento con períodos existentes
            # Comprobar si algún período existente se solapa con este nuevo rango
            periodos_solapados = PeriodoContable.objects.filter(
                models.Q(fecha_inicio__lte=fecha_fin) & models.Q(fecha_fin__gte=fecha_inicio)
            ).exists()
            
            if periodos_solapados:
                raise ValidationError("Las fechas de este período se solapan con un período ya existente.")
        
        return cleaned_data
    
    
 

