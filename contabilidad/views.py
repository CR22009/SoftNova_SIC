from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction, models
from django.contrib import messages
# Importamos todos los modelos y formularios
from .models import AsientoDiario, PeriodoContable, Cuenta, Movimiento
from .forms import AsientoDiarioForm, MovimientoFormSet
from decimal import Decimal

# --- Verificación de Roles (Existente) ---
def es_contador_o_admin(user):
    return user.is_staff or user.is_superuser

# --- Dashboard (Existente) ---
@login_required
def dashboard(request):
    ultimos_asientos = AsientoDiario.objects.order_by('-fecha', '-numero_partida')[:5]
    periodo_abierto = PeriodoContable.objects.filter(estado=PeriodoContable.EstadoPeriodo.ABIERTO).first()
    context = {
        'ultimos_asientos': ultimos_asientos,
        'periodo_abierto': periodo_abierto,
    }
    return render(request, 'contabilidad/dashboard.html', context)

# --- Registro de Asientos (Existente) ---
@login_required
@user_passes_test(es_contador_o_admin, login_url='/admin/login/')
@transaction.atomic
def registrar_asiento(request):
    if request.method == 'POST':
        asiento_form = AsientoDiarioForm(request.POST)
        movimiento_formset = MovimientoFormSet(request.POST, prefix='movimientos')

        if asiento_form.is_valid() and movimiento_formset.is_valid():
            total_debe = 0
            total_haber = 0
            for form in movimiento_formset.cleaned_data:
                if not form.get('DELETE', False) and form.get('cuenta'):
                    total_debe += form.get('debe', Decimal('0.00'))
                    total_haber += form.get('haber', Decimal('0.00'))
            
            if total_debe == 0 and total_haber == 0:
                messages.error(request, 'Error: El asiento está vacío (total 0.00).')
            elif total_debe != total_haber:
                messages.error(request, f'Error: El asiento está descuadrado. (Debe: ${total_debe}, Haber: ${total_haber})')
            else:
                try:
                    asiento = asiento_form.save(commit=False)
                    asiento.creado_por = request.user
                    asiento.save() 
                    movimiento_formset.instance = asiento
                    movimiento_formset.save()
                    messages.success(request, f'Asiento N° {asiento.numero_partida} (Período: {asiento.periodo.nombre}) guardado exitosamente.')
                    return redirect('contabilidad:registrar_asiento')
                except Exception as e:
                    messages.error(request, f'Error al guardar: {e}')
        
        else:
            messages.error(request, 'Error: Revisa los campos marcados en rojo.')

    else:
        asiento_form = AsientoDiarioForm()
        movimiento_formset = MovimientoFormSet(prefix='movimientos')

    context = {
        'asiento_form': asiento_form,
        'movimiento_formset': movimiento_formset,
    }
    return render(request, 'contabilidad/registro_asiento.html', context)


# --- NUEVO: FASE 2 - Vistas de Mayorización ---

@login_required
@user_passes_test(es_contador_o_admin, login_url='/admin/login/')
def mayor_seleccion(request):
    """
    Paso 1: Elige el período y luego la cuenta a mayorizar.
    """
    periodos = PeriodoContable.objects.all().order_by('-fecha_inicio')
    periodo_seleccionado = None
    cuentas = None
    
    periodo_id = request.GET.get('periodo_id')
    if periodo_id:
        try:
            periodo_seleccionado = PeriodoContable.objects.get(pk=periodo_id)
            # Obtenemos solo cuentas imputables que SÍ tuvieron movimiento en ese período
            cuentas_con_movimiento_ids = Movimiento.objects.filter(
                asiento__periodo=periodo_seleccionado
            ).values_list('cuenta__id', flat=True).distinct()
            
            cuentas = Cuenta.objects.filter(
                pk__in=cuentas_con_movimiento_ids
            ).order_by('codigo')
        except PeriodoContable.DoesNotExist:
            messages.error(request, "El período seleccionado no es válido.")

    context = {
        'periodos': periodos,
        'periodo_seleccionado': periodo_seleccionado,
        'cuentas': cuentas,
    }
    return render(request, 'contabilidad/mayor_seleccion.html', context)


@login_required
@user_passes_test(es_contador_o_admin, login_url='/admin/login/')
def libro_mayor_detalle(request, periodo_id, cuenta_id):
    """
    Paso 2: Muestra la Cuenta T para la cuenta y período seleccionados.
    """
    periodo = get_object_or_404(PeriodoContable, pk=periodo_id)
    cuenta = get_object_or_404(Cuenta, pk=cuenta_id)
    
    # Obtener todos los movimientos de esta cuenta en este período
    movimientos = Movimiento.objects.filter(
        asiento__periodo=periodo,
        cuenta=cuenta
    ).order_by('asiento__fecha', 'asiento__numero_partida')
    
    # Separar en debe y haber para la Cuenta T
    movimientos_debe = movimientos.filter(debe__gt=0)
    movimientos_haber = movimientos.filter(haber__gt=0)
    
    # Calcular totales
    totales = movimientos.aggregate(
        total_debe=models.Sum('debe'),
        total_haber=models.Sum('haber')
    )
    total_debe = totales.get('total_debe') or Decimal('0.00')
    total_haber = totales.get('total_haber') or Decimal('0.00')
    
    # Calcular saldo final
    saldo = Decimal('0.00')
    if cuenta.naturaleza == Cuenta.NaturalezaCuenta.DEUDORA:
        saldo = total_debe - total_haber
    else: # Naturaleza ACREEDORA
        saldo = total_haber - total_debe

    context = {
        'periodo': periodo,
        'cuenta': cuenta,
        'movimientos_debe': movimientos_debe,
        'movimientos_haber': movimientos_haber,
        'total_debe': total_debe,
        'total_haber': total_haber,
        'saldo': saldo,
    }
    return render(request, 'contabilidad/libro_mayor_detalle.html', context)


@login_required
@user_passes_test(es_contador_o_admin, login_url='/admin/login/')
def balanza_comprobacion(request, periodo_id):
    """
    Muestra el Balance de Comprobación (por saldos) para un período.
    """
    periodo = get_object_or_404(PeriodoContable, pk=periodo_id)
    
    # Usaremos solo cuentas imputables
    cuentas = Cuenta.objects.filter(es_imputable=True).order_by('codigo')
    
    resultados = []
    total_saldo_deudor = Decimal('0.00')
    total_saldo_acreedor = Decimal('0.00')

    for cuenta in cuentas:
        # Calcular el saldo de CADA cuenta
        movs = Movimiento.objects.filter(asiento__periodo=periodo, cuenta=cuenta)
        
        totales = movs.aggregate(
            total_debe=models.Sum('debe'),
            total_haber=models.Sum('haber')
        )
        total_debe = totales.get('total_debe') or Decimal('0.00')
        total_haber = totales.get('total_haber') or Decimal('0.00')
        
        # Solo añadir si hubo movimiento
        if total_debe > 0 or total_haber > 0:
            saldo_deudor = Decimal('0.00')
            saldo_acreedor = Decimal('0.00')
            
            # Aplicar naturaleza para determinar saldo
            if cuenta.naturaleza == Cuenta.NaturalezaCuenta.DEUDORA:
                saldo = total_debe - total_haber
                if saldo > 0:
                    saldo_deudor = saldo
                else:
                    saldo_acreedor = -saldo # Saldo "rojo" o acreedor
            else: # ACREEDORA
                saldo = total_haber - total_debe
                if saldo > 0:
                    saldo_acreedor = saldo
                else:
                    saldo_deudor = -saldo # Saldo "rojo" o deudor

            resultados.append({
                'codigo': cuenta.codigo,
                'nombre': cuenta.nombre,
                'saldo_deudor': saldo_deudor,
                'saldo_acreedor': saldo_acreedor,
            })
            
            total_saldo_deudor += saldo_deudor
            total_saldo_acreedor += saldo_acreedor

    # Verificamos si la balanza cuadra
    diferencia = total_saldo_deudor - total_saldo_acreedor

    context = {
        'periodo': periodo,
        'resultados': resultados,
        'total_saldo_deudor': total_saldo_deudor,
        'total_saldo_acreedor': total_saldo_acreedor,
        'diferencia': diferencia,
        'esta_cuadrado': diferencia.quantize(Decimal('0.01')) == Decimal('0.00')
    }
    return render(request, 'contabilidad/balanza_comprobacion.html', context)
