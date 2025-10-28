from django import forms
from django.forms import inlineformset_factory
from .models import AsientoDiario, Movimiento, PeriodoContable, Cuenta

class AsientoDiarioForm(forms.ModelForm):
    """
    Formulario para el "encabezado" del asiento (fecha, período, descripción).
    """
    
    # Sobrescribimos el campo 'periodo' para filtrar solo los abiertos
    periodo = forms.ModelChoiceField(
        queryset=PeriodoContable.objects.filter(estado=PeriodoContable.EstadoPeriodo.ABIERTO),
        label="Período Contable",
        widget=forms.Select(attrs={'class': 'block w-full mt-1 rounded-md border-gray-300 shadow-sm focus:border-sic-teal focus:ring-sic-teal'})
    )

    class Meta:
        model = AsientoDiario
        fields = ['fecha', 'periodo', 'descripcion']
        widgets = {
            'fecha': forms.DateInput(
                attrs={
                    'type': 'date', # Widget de calendario HTML5
                    'class': 'block w-full mt-1 rounded-md border-gray-300 shadow-sm focus:border-sic-teal focus:ring-sic-teal'
                }
            ),
            'descripcion': forms.Textarea(
                attrs={
                    'rows': 3,
                    'class': 'block w-full mt-1 rounded-md border-gray-300 shadow-sm focus:border-sic-teal focus:ring-sic-teal'
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
        widget=forms.Select(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm focus:border-sic-teal focus:ring-sic-teal'})
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
