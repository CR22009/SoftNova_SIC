from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.contrib import messages
from .models import AsientoDiario, PeriodoContable
from .forms import AsientoDiarioForm, MovimientoFormSet

# --- Verificación de Roles ---
def es_contador_o_admin(user):
    """
    Verifica si el usuario es staff (Contador) o superuser (Admin).
    """
    return user.is_staff or user.is_superuser

# --- Dashboard (Página de Inicio) ---
@login_required
def dashboard(request):
    """
    Muestra la página principal después de iniciar sesión.
    """
    # Futuro: Agregar estadísticas aquí (ej. últimos asientos, saldos)
    ultimos_asientos = AsientoDiario.objects.order_by('-fecha', '-numero_partida')[:5]
    periodo_abierto = PeriodoContable.objects.filter(estado=PeriodoContable.EstadoPeriodo.ABIERTO).first()

    context = {
        'ultimos_asientos': ultimos_asientos,
        'periodo_abierto': periodo_abierto,
    }
    return render(request, 'contabilidad/dashboard.html', context)


# --- Vista de Registro de Asientos ---
@login_required
@user_passes_test(es_contador_o_admin, login_url='/admin/login/') # Protege la vista
@transaction.atomic # Asegura que todo el asiento se guarde, o nada
def registrar_asiento(request):
    """
    Maneja la creación de un nuevo Asiento Diario con sus Movimientos.
    """
    
    if request.method == 'POST':
        # Si el formulario es enviado (POST)
        asiento_form = AsientoDiarioForm(request.POST)
        movimiento_formset = MovimientoFormSet(request.POST, prefix='movimientos')

        if asiento_form.is_valid() and movimiento_formset.is_valid():
            
            # --- Validación de Partida Doble ---
            total_debe = 0
            total_haber = 0
            for form in movimiento_formset.cleaned_data:
                if not form.get('DELETE', False) and form.get('cuenta'):
                    total_debe += form.get('debe', 0)
                    total_haber += form.get('haber', 0)
            
            if total_debe == 0 and total_haber == 0:
                messages.error(request, 'Error: El asiento está vacío (total 0.00).')
            elif total_debe != total_haber:
                messages.error(request, f'Error: El asiento está descuadrado. (Debe: ${total_debe}, Haber: ${total_haber})')
            else:
                # --- Guardado Atómico ---
                try:
                    # 1. Guardar el Asiento (encabezado)
                    asiento = asiento_form.save(commit=False)
                    asiento.creado_por = request.user
                    # (El número_partida se asigna en el .save() de models.py)
                    asiento.save() 

                    # 2. Vincular y guardar los Movimientos
                    movimiento_formset.instance = asiento
                    movimiento_formset.save()

                    messages.success(request, f'Asiento N° {asiento.numero_partida} (Período: {asiento.periodo.nombre}) guardado exitosamente.')
                    
                    # Redirigir a un nuevo formulario vacío
                    return redirect('contabilidad:registrar_asiento')

                except Exception as e:
                    # Captura validaciones del modelo (ej. fecha fuera de período)
                    messages.error(request, f'Error al guardar: {e}')
        
        else:
            # Si hay errores en los formularios
            messages.error(request, 'Error: Revisa los campos marcados en rojo.')

    else:
        # Si es la primera visita (GET)
        asiento_form = AsientoDiarioForm()
        movimiento_formset = MovimientoFormSet(prefix='movimientos')

    context = {
        'asiento_form': asiento_form,
        'movimiento_formset': movimiento_formset,
    }
    return render(request, 'contabilidad/registro_asiento.html', context)
# Create your views here.
