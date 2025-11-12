from django.utils.timezone import now
from calendar import monthrange
from datetime import date
from django.urls import reverse, reverse_lazy
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction, models
from django.db.models import Sum, Q # Importar Q
from django.contrib import messages
# --- Imports para Login ---
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm
# --- Fin Imports Login ---
from .models import AsientoDiario, PeriodoContable, Cuenta, Movimiento
# --- MODIFICADO: Importar el nuevo PeriodoForm y CuentaForm ---
from .forms import AsientoDiarioForm, MovimientoFormSet, PeriodoForm, CuentaForm
from decimal import Decimal
from datetime import date, timedelta
from calendar import monthrange

# --- ========================================= ---
# ---     AUTENTICACIÓN Y ROLES (Sin cambios)   ---
# --- ========================================= ---
def login_view(request):
    # ... (Sin cambios) ...
    if request.user.is_authenticated:
        return redirect('contabilidad:dashboard')
    
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            
            if user is not None:
                login(request, user)
                messages.success(request, f"Bienvenido de nuevo, {user.first_name or user.username}.")
                return redirect('contabilidad:dashboard')
            else:
                messages.error(request, "Usuario o contraseña incorrectos. Inténtalo de nuevo.")
        else:
            messages.error(request, "Usuario o contraseña incorrectos. Inténtalo de nuevo.")
    else:
        form = AuthenticationForm()
        
    return render(request, 'contabilidad/login.html', {'form': form})

def logout_view(request):
    # ... (Sin cambios) ...
    logout(request)
    messages.info(request, "Has cerrado sesión exitosamente.")
    return redirect('contabilidad:login')

def es_grupo_administrador(user):
    # ... (Sin cambios) ...
    return user.groups.filter(name='Administrador').exists()

def check_acceso_admin(user):
    # ... (Sin cambios) ...
    if not user.is_authenticated:
        return False
    return user.is_superuser or es_grupo_administrador(user)

def es_grupo_contador(user):
    # ... (Sin cambios) ...
    return user.groups.filter(name='Contador').exists()

def es_grupo_informatico(user):
    # ... (Sin cambios) ...
    return user.groups.filter(name='Informático').exists()

def check_acceso_contable(user):
    # ... (Sin cambios) ...
    return user.is_authenticated and (es_grupo_administrador(user) or es_grupo_contador(user))

def check_acceso_costeo(user):
    # ... (Sin cambios) ...
    return user.is_authenticated and (es_grupo_administrador(user) or es_grupo_informatico(user))


# --- ========================================= ---
# ---     Dashboard (Sin cambios)               ---
# --- ========================================= ---
def dashboard(request):
    # ... (Sin cambios) ...
    ultimos_asientos = AsientoDiario.objects.prefetch_related(
        'movimientos__cuenta'
    ).order_by('-fecha', '-numero_partida')

    periodo_abierto = PeriodoContable.objects.filter(estado=PeriodoContable.EstadoPeriodo.ABIERTO).first()
    context = {
        'ultimos_asientos': ultimos_asientos,
        'periodo_abierto': periodo_abierto,
    }
    return render(request, 'contabilidad/dashboard.html', context)

# --- ========================================= ---
# ---     FASE 1 - Registro (Sin cambios)       ---
# --- ========================================= ---

@login_required
@user_passes_test(check_acceso_contable)
@transaction.atomic
def registrar_asiento(request):
    # ... (Sin cambios) ...
    asiento_id = request.POST.get('asiento_id') 
    if asiento_id:
        asiento_obj = get_object_or_404(AsientoDiario, pk=asiento_id)
        if asiento_obj.es_asiento_automatico:
            messages.error(request, "Error: Los asientos automáticos (Cierre/Apertura) no pueden ser modificados.")
            return redirect('contabilidad:dashboard')

    if request.method == 'POST':
        asiento_form = AsientoDiarioForm(request.POST)
        movimiento_formset = MovimientoFormSet(request.POST, prefix='movimientos')

        if asiento_form.is_valid() and movimiento_formset.is_valid():
            total_debe = Decimal('0.00')
            total_haber = Decimal('0.00')
            
            movimientos_validos = 0
            for form in movimiento_formset.cleaned_data:
                if not form.get('DELETE', False) and form.get('cuenta'):
                    total_debe += form.get('debe', Decimal('0.00'))
                    total_haber += form.get('haber', Decimal('0.00'))
                    movimientos_validos += 1
            
            if movimientos_validos == 0:
                messages.error(request, 'Error: El asiento está vacío. Debe añadir al menos un movimiento.')
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
                    messages.error(request, f'Error al guardar el asiento: {e}')
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


# --- ========================================= ---
# ---     FASE 2 - Reportes (Sin cambios)       ---
# --- ========================================= ---

@login_required
@user_passes_test(check_acceso_contable) 
def mayor_seleccion(request):
    # ... (Sin cambios) ...
    periodos = PeriodoContable.objects.all().order_by('-fecha_inicio')
    periodo_seleccionado = None
    cuentas = None
    periodo_id = request.GET.get('periodo_id')

    if periodo_id:
        try:
            periodo_seleccionado = PeriodoContable.objects.get(pk=periodo_id)
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
@user_passes_test(check_acceso_contable) 
def libro_mayor_detalle(request, periodo_id, cuenta_id):
    # ... (Sin cambios) ...
    periodo = get_object_or_404(PeriodoContable, pk=periodo_id)
    cuenta = get_object_or_404(Cuenta, pk=cuenta_id)
    
    movimientos = Movimiento.objects.filter(
        asiento__periodo=periodo,
        cuenta=cuenta
    ).order_by('asiento__fecha', 'asiento__numero_partida', 'pk')
    
    movimientos_debe = movimientos.filter(debe__gt=0)
    movimientos_haber = movimientos.filter(haber__gt=0)
    
    totales = movimientos.aggregate(
        total_debe=models.Sum('debe'),
        total_haber=models.Sum('haber')
    )
    total_debe = totales.get('total_debe') or Decimal('0.00')
    total_haber = totales.get('total_haber') or Decimal('0.00')
    
    saldo = Decimal('0.00')
    if cuenta.naturaleza == Cuenta.NaturalezaCuenta.DEUDORA:
        saldo = total_debe - total_haber
    else:
        saldo = total_haber - total_debe
        
    context = {
        'periodo': periodo,
        'cuenta': cuenta,
        'movimientos_debe': movimientos_debe,
        'movimientos_haber': movimientos_haber,
        'total_debe': total_debe,
        'total_haber': total_haber,
        'saldo': saldo,
        'saldo_abs': abs(saldo),
    }
    return render(request, 'contabilidad/libro_mayor_detalle.html', context)

@login_required
@user_passes_test(check_acceso_contable) 
def balanza_comprobacion(request, periodo_id):
    # ... (Sin cambios) ...
    periodo = get_object_or_404(PeriodoContable, pk=periodo_id)
    cuentas = Cuenta.objects.filter(es_imputable=True).order_by('codigo')
    
    resultados = []
    total_saldo_deudor = Decimal('0.00')
    total_saldo_acreedor = Decimal('0.00')
    
    for cuenta in cuentas:
        totales = Movimiento.objects.filter(asiento__periodo=periodo, cuenta=cuenta).aggregate(
            total_debe=models.Sum('debe'),
            total_haber=models.Sum('haber')
        )
        total_debe = totales.get('total_debe') or Decimal('0.00')
        total_haber = totales.get('total_haber') or Decimal('0.00')
        
        if total_debe > 0 or total_haber > 0:
            saldo_deudor = Decimal('0.00')
            saldo_acreedor = Decimal('0.00')
            
            if cuenta.naturaleza == Cuenta.NaturalezaCuenta.DEUDORA:
                saldo = total_debe - total_haber
                if saldo > 0: saldo_deudor = saldo
                else: saldo_acreedor = -saldo 
            else: 
                saldo = total_haber - total_debe
                if saldo > 0: saldo_acreedor = saldo
                else: saldo_deudor = -saldo 
                
            resultados.append({
                'codigo': cuenta.codigo,
                'nombre': cuenta.nombre,
                'saldo_deudor': saldo_deudor,
                'saldo_acreedor': saldo_acreedor,
                'esta_activa': cuenta.esta_activa
            })
            total_saldo_deudor += saldo_deudor
            total_saldo_acreedor += saldo_acreedor
            
    diferencia = total_saldo_deudor - total_saldo_acreedor
    esta_cuadrado = diferencia.quantize(Decimal('0.01')) == Decimal('0.00')
    
    context = {
        'periodo': periodo,
        'resultados': resultados,
        'total_saldo_deudor': total_saldo_deudor,
        'total_saldo_acreedor': total_saldo_acreedor,
        'diferencia': diferencia,
        'esta_cuadrado': esta_cuadrado
    }
    return render(request, 'contabilidad/balanza_comprobacion.html', context)


# --- ========================================= ---
# ---     FASE 3 - Estados Financieros          ---
# --- (Sin cambios, ya están correctos)         ---
# --- ========================================= ---

def _calcular_saldos_cuentas_por_tipo(periodo, tipo_cuenta, excluir_automaticos=False):
    # ... (Sin cambios) ...
    cuentas = Cuenta.objects.filter(tipo_cuenta=tipo_cuenta, es_imputable=True).order_by('codigo')
    lista_saldos = []
    total_general_tipo = Decimal('0.00')

    for c in cuentas:
        movimientos_query = Movimiento.objects.filter(asiento__periodo=periodo, cuenta=c)
        
        if excluir_automaticos:
            movimientos_query = movimientos_query.exclude(asiento__es_asiento_automatico=True)
            
        agregado = movimientos_query.aggregate(
            total_debe=models.Sum('debe'),
            total_haber=models.Sum('haber')
        )
        total_debe = agregado.get('total_debe') or Decimal('0.00')
        total_haber = agregado.get('total_haber') or Decimal('0.00')
        
        saldo = Decimal('0.00')
        if total_debe > 0 or total_haber > 0: 
            if c.naturaleza == Cuenta.NaturalezaCuenta.DEUDORA:
                saldo = total_debe - total_haber
            else:
                saldo = total_haber - total_debe
        
        if saldo != Decimal('0.00'):
            lista_saldos.append({'cuenta': c, 'saldo': saldo})
            total_general_tipo += saldo
    
    return lista_saldos, total_general_tipo

def _get_utilidad_del_ejercicio(periodo):
    # ... (Sin cambios) ...
    _, total_ingresos = _calcular_saldos_cuentas_por_tipo(periodo, Cuenta.TipoCuenta.INGRESO, excluir_automaticos=True)
    _, total_costos = _calcular_saldos_cuentas_por_tipo(periodo, Cuenta.TipoCuenta.COSTO, excluir_automaticos=True)
    _, total_gastos = _calcular_saldos_cuentas_por_tipo(periodo, Cuenta.TipoCuenta.GASTO, excluir_automaticos=True)
    
    utilidad = total_ingresos - (total_costos + total_gastos)
    return utilidad

def _get_saldo_a_fecha(cuenta, fecha):
    # ... (Sin cambios) ...
    if not fecha:
        return Decimal('0.00')
        
    agregado = Movimiento.objects.filter(
        asiento__fecha__lte=fecha, 
        cuenta=cuenta
    ).aggregate(
        total_debe=models.Sum('debe'),
        total_haber=models.Sum('haber')
    )
    total_debe = agregado.get('total_debe') or Decimal('0.00')
    total_haber = agregado.get('total_haber') or Decimal('0.00')
    
    if cuenta.naturaleza == Cuenta.NaturalezaCuenta.DEUDORA:
         return total_debe - total_haber
    else:
         return total_haber - total_debe

def _calcular_detalle_cuenta_patrimonio(cuenta, periodo, periodo_anterior):
    # ... (Sin cambios) ...
    if cuenta.codigo == '34': 
         saldo_inicial = Decimal('0.00')
    else:
        fecha_saldo_inicial = periodo_anterior.fecha_fin if periodo_anterior else None
        saldo_inicial = _get_saldo_a_fecha(cuenta, fecha_saldo_inicial)

    agregado_mov = Movimiento.objects.filter(
        asiento__periodo=periodo,
        cuenta=cuenta,
        asiento__es_asiento_automatico=False 
    ).aggregate(
        total_debe=models.Sum('debe'),
        total_haber=models.Sum('haber')
    )
    mov_debe = agregado_mov.get('total_debe') or Decimal('0.00') 
    mov_haber = agregado_mov.get('total_haber') or Decimal('0.00')
    
    movimientos = mov_haber - mov_debe
    
    saldo_final = saldo_inicial + movimientos
    
    return {
        'saldo_inicial': saldo_inicial.quantize(Decimal('0.01')),
        'movimientos': movimientos.quantize(Decimal('0.01')),
        'saldo_final': saldo_final.quantize(Decimal('0.01'))
    }

def _get_saldo_cuentas(cuentas_ids, periodo):
    # ... (Sin cambios) ...
    if not periodo:
        return Decimal('0.00')
    
    agregado = Movimiento.objects.filter(
        asiento__fecha__lte=periodo.fecha_fin,
        cuenta_id__in=cuentas_ids
    ).aggregate(
        total_debe=models.Sum('debe'),
        total_haber=models.Sum('haber')
    )
    total_debe = agregado.get('total_debe') or Decimal('0.00')
    total_haber = agregado.get('total_haber') or Decimal('0.00')
    
    saldo = total_debe - total_haber
    return saldo

@login_required
@user_passes_test(check_acceso_contable) 
def estado_resultados(request, periodo_id):
    # ... (Sin cambios) ...
    periodo = get_object_or_404(PeriodoContable, pk=periodo_id)
    
    lista_ingresos, total_ingresos = _calcular_saldos_cuentas_por_tipo(periodo, Cuenta.TipoCuenta.INGRESO, excluir_automaticos=True)
    lista_costos, total_costos = _calcular_saldos_cuentas_por_tipo(periodo, Cuenta.TipoCuenta.COSTO, excluir_automaticos=True)
    lista_gastos, total_gastos = _calcular_saldos_cuentas_por_tipo(periodo, Cuenta.TipoCuenta.GASTO, excluir_automaticos=True)
    
    utilidad_bruta = total_ingresos - total_costos
    utilidad_neta = utilidad_bruta - total_gastos 

    context = {
        'periodo': periodo,
        'lista_ingresos': lista_ingresos,
        'total_ingresos': total_ingresos,
        'lista_costos': lista_costos,
        'total_costos': total_costos,
        'lista_gastos': lista_gastos,
        'total_gastos': total_gastos,
        'utilidad_bruta': utilidad_bruta,
        'utilidad_neta': utilidad_neta,
    }
    return render(request, 'contabilidad/estado_resultados.html', context)

@login_required
@user_passes_test(check_acceso_contable) 
def hub_estado_resultados(request):
    if request.method == 'POST':
        periodo_id = request.POST.get('periodo_id')
        if periodo_id:
            try:
                periodo = PeriodoContable.objects.get(pk=periodo_id)
                return redirect('contabilidad:estado_resultados', periodo_id=periodo.id)
            except PeriodoContable.DoesNotExist:
                messages.error(request, "Período no válido.")
        else:
            messages.error(request, "Debe seleccionar un período.")
    
    periodos = PeriodoContable.objects.filter(
        estado=PeriodoContable.EstadoPeriodo.CERRADO
    ).order_by('-fecha_inicio')
    
    context = {
        'periodos': periodos
    }
    return render(request, 'contabilidad/hub_estado_resultados.html', context)

@login_required
@user_passes_test(check_acceso_contable) 
def balance_general(request, periodo_id):
    # ... (Sin cambios) ...
    periodo = get_object_or_404(PeriodoContable, pk=periodo_id)
    
    lista_activos, total_activos = _calcular_saldos_cuentas_por_tipo(periodo, Cuenta.TipoCuenta.ACTIVO)
    lista_pasivos, total_pasivos = _calcular_saldos_cuentas_por_tipo(periodo, Cuenta.TipoCuenta.PASIVO)
    lista_patrimonio, total_patrimonio = _calcular_saldos_cuentas_por_tipo(periodo, Cuenta.TipoCuenta.PATRIMONIO)
    
    utilidad_ejercicio = _get_utilidad_del_ejercicio(periodo)
    
    total_patrimonio_final = total_patrimonio
    
    total_pasivo_patrimonio = total_pasivos + total_patrimonio_final
    
    diferencia = total_activos - total_pasivo_patrimonio
    esta_cuadrado = diferencia.quantize(Decimal('0.01')) == Decimal('0.00')

    context = {
        'periodo': periodo,
        'lista_activos': lista_activos,
        'total_activos': total_activos,
        'lista_pasivos': lista_pasivos,
        'total_pasivos': total_pasivos,
        'lista_patrimonio': lista_patrimonio,
        'total_patrimonio': total_patrimonio, 
        'utilidad_ejercicio': utilidad_ejercicio, 
        'total_patrimonio_final': total_patrimonio_final,
        'total_pasivo_patrimonio': total_pasivo_patrimonio,
        'diferencia': diferencia,
        'esta_cuadrado': esta_cuadrado,
    }
    return render(request, 'contabilidad/balance_general.html', context)

@login_required
@user_passes_test(check_acceso_contable) 
def hub_balance_general(request):
    # ... (Sin cambios) ...
    if request.method == 'POST':
        periodo_id = request.POST.get('periodo_id')
        if periodo_id:
            try:
                periodo = PeriodoContable.objects.get(pk=periodo_id)
                return redirect('contabilidad:balance_general', periodo_id=periodo.id)
            except PeriodoContable.DoesNotExist:
                messages.error(request, "Período no válido.")
        else:
            messages.error(request, "Debe seleccionar un período.")
    
    periodos = PeriodoContable.objects.filter(
        estado=PeriodoContable.EstadoPeriodo.CERRADO
    ).order_by('-fecha_inicio')

    context = {
        'periodos': periodos
    }
    return render(request, 'contabilidad/hub_balance_general.html', context)

@login_required
@user_passes_test(check_acceso_contable) 
def flujo_efectivo(request, periodo_id):
    """
    Muestra el reporte de Flujo de Efectivo (Método Directo Simplificado)
    analizando las contrapartidas de las cuentas de efectivo.
    """
    
    periodo = get_object_or_404(PeriodoContable, pk=periodo_id)
    
    cuentas_efectivo_ids = Cuenta.objects.filter(
        codigo__startswith='11', es_imputable=True
    ).values_list('id', flat=True)

    periodo_anterior = PeriodoContable.objects.filter(
        estado=PeriodoContable.EstadoPeriodo.CERRADO,
        fecha_fin__lt=periodo.fecha_inicio
    ).order_by('-fecha_fin').first()
    
    saldo_inicial_efectivo = _get_saldo_cuentas(cuentas_efectivo_ids, periodo_anterior)
    saldo_final_efectivo = _get_saldo_cuentas(cuentas_efectivo_ids, periodo)
    
    asientos_con_efectivo_ids = Movimiento.objects.filter(
        asiento__periodo=periodo,
        cuenta_id__in=cuentas_efectivo_ids
    ).values_list('asiento_id', flat=True).distinct()

    contrapartidas = Movimiento.objects.filter(
        asiento_id__in=asientos_con_efectivo_ids,
        asiento__periodo=periodo
    ).exclude(
        cuenta_id__in=cuentas_efectivo_ids
    ).values(
        'cuenta__codigo', 'cuenta__nombre'
    ).annotate(
        total_debe=Sum('debe'),
        total_haber=Sum('haber')
    ).order_by('cuenta__codigo')

    flujos_operacion = []
    total_operacion = Decimal('0.00')
    flujos_inversion = []
    total_inversion = Decimal('0.00')
    flujos_financiacion = []
    total_financiacion = Decimal('0.00')

    for item in contrapartidas:
        codigo = item['cuenta__codigo']
        nombre = item['cuenta__nombre']
        saldo_contrapartida = (item['total_debe'] or 0) - (item['total_haber'] or 0)
        flujo = -saldo_contrapartida
        
        flujo_item = {'nombre': nombre, 'monto': flujo}

        if (codigo.startswith('4') or codigo.startswith('5') or 
            codigo.startswith('12') or codigo.startswith('13') or 
            codigo.startswith('14') or codigo.startswith('21') or 
            codigo.startswith('22') or codigo.startswith('23') or 
            codigo.startswith('24')):
            flujos_operacion.append(flujo_item)
            total_operacion += flujo
        
        elif codigo.startswith('15') or codigo.startswith('16') or codigo.startswith('17'):
            flujos_inversion.append(flujo_item)
            total_inversion += flujo

        elif codigo.startswith('25') or codigo.startswith('3'):
            flujos_financiacion.append(flujo_item)
            total_financiacion += flujo
        
    total_flujo_neto = total_operacion + total_inversion + total_financiacion
    flujo_calculado = saldo_inicial_efectivo + total_flujo_neto
    
    esta_cuadrado = flujo_calculado.quantize(Decimal('0.01')) == saldo_final_efectivo.quantize(Decimal('0.01'))
    diferencia = saldo_final_efectivo - flujo_calculado

    context = {
        'periodo': periodo,
        'periodo_anterior': periodo_anterior,
        'saldo_inicial_efectivo': saldo_inicial_efectivo,
        'saldo_final_efectivo': saldo_final_efectivo,
        'flujos_operacion': flujos_operacion,
        'total_operacion': total_operacion,
        'flujos_inversion': flujos_inversion,
        'total_inversion': total_inversion,
        'flujos_financiacion': flujos_financiacion,
        'total_financiacion': total_financiacion,
        'total_flujo_neto': total_flujo_neto,
        'flujo_calculado': flujo_calculado,
        'esta_cuadrado': esta_cuadrado,
        'diferencia': diferencia,
    }
    return render(request, 'contabilidad/flujo_efectivo.html', context)


@login_required
@user_passes_test(check_acceso_contable) 
def hub_flujo_efectivo(request):
    # ... (Sin cambios) ...
    if request.method == 'POST':
        periodo_id = request.POST.get('periodo_id')
        if periodo_id:
            try:
                periodo = PeriodoContable.objects.get(pk=periodo_id)
                return redirect('contabilidad:flujo_efectivo', periodo_id=periodo.id)
            except PeriodoContable.DoesNotExist:
                messages.error(request, "Período no válido.")
        else:
            messages.error(request, "Debe seleccionar un período.")
    
    periodos = PeriodoContable.objects.filter(
        estado=PeriodoContable.EstadoPeriodo.CERRADO
    ).order_by('-fecha_inicio')

    context = {
        'periodos': periodos
    }
    return render(request, 'contabilidad/hub_flujo_efectivo.html', context)

@login_required
@user_passes_test(check_acceso_contable) 
def hub_estado_patrimonio(request):
    # ... (Sin cambios) ...
    if request.method == 'POST':
        periodo_id = request.POST.get('periodo_id')
        if periodo_id:
            try:
                periodo = PeriodoContable.objects.get(pk=periodo_id)
                return redirect('contabilidad:estado_patrimonio', periodo_id=periodo.id)
            except PeriodoContable.DoesNotExist:
                messages.error(request, "Período no válido.")
        else:
            messages.error(request, "Debe seleccionar un período.")
    
    periodos = PeriodoContable.objects.filter(
        estado=PeriodoContable.EstadoPeriodo.CERRADO
    ).order_by('-fecha_inicio')

    context = {
        'periodos': periodos
    }
    return render(request, 'contabilidad/hub_estado_patrimonio.html', context)

@login_required
@user_passes_test(check_acceso_contable)
def estado_patrimonio(request, periodo_id):
    # ... (Sin cambios) ...
    periodo = get_object_or_404(PeriodoContable, pk=periodo_id)
    
    periodo_anterior = PeriodoContable.objects.filter(
        estado=PeriodoContable.EstadoPeriodo.CERRADO,
        fecha_fin__lt=periodo.fecha_inicio
    ).order_by('-fecha_fin').first()

    try:
        cta_capital = Cuenta.objects.get(codigo='31')
        cta_reserva = Cuenta.objects.get(codigo='32')
        cta_resultados_acum = Cuenta.objects.get(codigo='33')
    except Cuenta.DoesNotExist as e:
        messages.error(request, f"Error crítico: Falta una cuenta de patrimonio (31, 32 o 33) en el catálogo. {e}")
        return redirect('contabilidad:hub_estado_patrimonio')

    reporte_capital = _calcular_detalle_cuenta_patrimonio(cta_capital, periodo, periodo_anterior)
    reporte_reserva = _calcular_detalle_cuenta_patrimonio(cta_reserva, periodo, periodo_anterior)
    reporte_resultados_acum = _calcular_detalle_cuenta_patrimonio(cta_resultados_acum, periodo, periodo_anterior)
    
    utilidad_neta_actual = _get_utilidad_del_ejercicio(periodo)
    reporte_utilidad = {
        'saldo_inicial': Decimal('0.00'),
        'movimientos': utilidad_neta_actual.quantize(Decimal('0.01')),
        'saldo_final': utilidad_neta_actual.quantize(Decimal('0.01'))
    }

    reporte = {
        'capital_social': reporte_capital,
        'reserva_legal': reporte_reserva,
        'resultados_acum': reporte_resultados_acum,
        'utilidad_ejercicio': reporte_utilidad,
    }
    
    total_saldo_inicial = (
        reporte_capital['saldo_inicial'] + 
        reporte_reserva['saldo_inicial'] + 
        reporte_resultados_acum['saldo_inicial'] +
        reporte_utilidad['saldo_inicial'] 
    )
    total_movimientos = (
        reporte_capital['movimientos'] + 
        reporte_reserva['movimientos'] + 
        reporte_resultados_acum['movimientos'] +
        reporte_utilidad['movimientos']
    )
    total_saldo_final = (
        reporte_capital['saldo_final'] + 
        reporte_reserva['saldo_final'] + 
        reporte_resultados_acum['saldo_final'] +
        reporte_utilidad['saldo_final']
    )
    
    totales = {
        'saldo_inicial': total_saldo_inicial,
        'movimientos': total_movimientos,
        'saldo_final': total_saldo_final,
    }

    context = {
        'periodo': periodo,
        'reporte': reporte, 
        'totales': totales, 
    }
    return render(request, 'contabilidad/estado_patrimonio.html', context)


# --- ========================================= ---
# ---     Vistas de Configuración (Sin cambios) ---
# --- ========================================= ---

@login_required
@user_passes_test(check_acceso_contable) 
def gestionar_catalogo(request):
    # ... (Sin cambios) ...
    cuentas_principales = Cuenta.objects.filter(padre__isnull=True).order_by('codigo')
    context = {
        'cuentas_principales': cuentas_principales,
    }
    return render(request, 'contabilidad/gestionar_catalogo.html', context)

@login_required
@user_passes_test(check_acceso_admin) 
def crear_cuenta(request, padre_id=None):
    # ... (Sin cambios) ...
    cuenta_padre = None
    if padre_id:
        cuenta_padre = get_object_or_404(Cuenta, pk=padre_id, es_imputable=False, esta_activa=True)
    
    if request.method == 'POST':
        form = CuentaForm(request.POST)
        if form.is_valid():
            nueva_cuenta = form.save()
            messages.success(request, f"Cuenta '{nueva_cuenta.nombre}' creada exitosamente.")
            return redirect('contabilidad:gestionar_catalogo')
    else:
        form = CuentaForm(initial={'padre': cuenta_padre})
        
    context = {
        'form': form,
        'titulo': 'Crear Nueva Cuenta'
    }
    return render(request, 'contabilidad/cuenta_form.html', context)

@login_required
@user_passes_test(check_acceso_admin) 
def editar_cuenta(request, cuenta_id):
    # ... (Sin cambios) ...
    cuenta = get_object_or_404(Cuenta, pk=cuenta_id)
    
    if request.method == 'POST':
        form = CuentaForm(request.POST, instance=cuenta)
        if form.is_valid():
            cuenta_editada = form.save()
            messages.success(request, f"Cuenta '{cuenta_editada.nombre}' actualizada exitosamente.")
            return redirect('contabilidad:gestionar_catalogo')
    else:
        form = CuentaForm(instance=cuenta)
        
    context = {
        'form': form,
        'cuenta': cuenta,
        'titulo': f"Editando: {cuenta.nombre}"
    }
    return render(request, 'contabilidad/cuenta_form.html', context)

@login_required
@user_passes_test(check_acceso_admin) 
@transaction.atomic
def eliminar_cuenta(request, cuenta_id):
    # ... (Sin cambios) ...
    if request.method != 'POST':
        return redirect('contabilidad:gestionar_catalogo')
        
    cuenta = get_object_or_404(Cuenta, pk=cuenta_id)
    
    if cuenta.hijos.filter(esta_activa=True).exists():
        messages.error(request, f"Error: No se puede eliminar '{cuenta.nombre}' porque tiene sub-cuentas activas. Debe eliminar o reasignar las sub-cuentas primero.")
        return redirect('contabilidad:gestionar_catalogo')
        
    if cuenta.es_imputable:
        saldo = cuenta.get_saldo_total()
        if saldo != Decimal('0.00'):
            messages.error(request, f"Error: No se puede eliminar '{cuenta.nombre}' porque tiene un saldo de ${saldo}. Debe registrar una transacción para mover el saldo a otra cuenta.")
            return redirect('contabilidad:gestionar_catalogo')
            
    cuenta.esta_activa = False
    cuenta.save()
    messages.success(request, f"Cuenta '{cuenta.nombre}' eliminada (desactivada) exitosamente.")
    return redirect('contabilidad:gestionar_catalogo')


@login_required
@user_passes_test(check_acceso_contable) 
@transaction.atomic 
def gestionar_periodos(request):
    # ... (Sin cambios) ...
    periodos = PeriodoContable.objects.all().order_by('-fecha_inicio')
    periodo_abierto = periodos.filter(estado=PeriodoContable.EstadoPeriodo.ABIERTO).first()
    
    form = None
    
    if request.method == 'POST' and check_acceso_admin(request.user):
        
        if periodo_abierto:
            messages.error(request, f"Ya existe un período abierto ({periodo_abierto.nombre}). Debe cerrarlo primero.")
            return redirect('contabilidad:gestionar_periodos')
            
        form = PeriodoForm(request.POST)
        if form.is_valid():
            try:
                nuevo_periodo = form.save(commit=False)
                nuevo_periodo.estado = PeriodoContable.EstadoPeriodo.ABIERTO
                nuevo_periodo.save()
                messages.success(request, f"Período '{nuevo_periodo.nombre}' creado y abierto exitosamente.")
                
                ultimo_periodo_cerrado = PeriodoContable.objects.filter(
                    estado=PeriodoContable.EstadoPeriodo.CERRADO,
                    fecha_fin__lt=nuevo_periodo.fecha_inicio
                ).order_by('-fecha_fin').first()

                if ultimo_periodo_cerrado:
                    # Esta llamada ahora usará la función _crear_asiento_apertura CORREGIDA
                    _crear_asiento_apertura(nuevo_periodo, ultimo_periodo_cerrado, request)
                else:
                    messages.info(request, "Este es el primer período (o no hay período cerrado anterior), no se generó asiento de apertura.")
                
                return redirect('contabilidad:gestionar_periodos')
            
            except Exception as e:
                messages.error(request, f"Error al guardar el período: {e}")
        
        else:
            messages.error(request, "Error en el formulario. Revisa los datos ingresados.")

    fecha_inicio_sugerida = date.today()
    fecha_fin_sugerida = fecha_inicio_sugerida + timedelta(days=29) 
    nombre_sugerido = f"Período desde {fecha_inicio_sugerida.strftime('%d-%m-%Y')}"

    if request.method != 'POST' or not form:
        form = PeriodoForm(initial={
            'nombre': nombre_sugerido,
            'fecha_inicio': fecha_inicio_sugerida,
            'fecha_fin': fecha_fin_sugerida
        })

    context = {
        'periodos': periodos,
        'periodo_abierto': periodo_abierto,
        'form_periodo': form 
    }
    return render(request, 'contabilidad/gestionar_periodos.html', context)


@login_required
@user_passes_test(check_acceso_admin) 
@transaction.atomic
def cerrar_periodo(request, periodo_id):
    # ... (Sin cambios) ...
    if request.method != 'POST':
        return redirect('contabilidad:gestionar_periodos')

    periodo_a_cerrar = get_object_or_404(PeriodoContable, pk=periodo_id)
    if periodo_a_cerrar.estado == PeriodoContable.EstadoPeriodo.CERRADO:
        messages.error(request, "Este período ya está cerrado.")
        return redirect('contabilidad:gestionar_periodos')
        
    try:
        cuenta_utilidad_ejercicio = Cuenta.objects.get(codigo='34') 
    except Cuenta.DoesNotExist:
        messages.error(request, "Error Crítico: No se encontró la cuenta '34' (Utilidad o Pérdida del Ejercicio) en el catálogo. Cierre cancelado.")
        return redirect('contabilidad:gestionar_periodos')
    
    if not cuenta_utilidad_ejercicio.es_imputable:
        messages.error(request, "Error Crítico: La cuenta '34' (Utilidad o Pérdida del Ejercicio) no está marcada como 'imputable' en el catálogo. Cierre cancelado.")
        return redirect('contabilidad:gestionar_periodos')

    utilidad_neta = _get_utilidad_del_ejercicio(periodo_a_cerrar)
    
    asiento_cierre = AsientoDiario.objects.create(
        periodo=periodo_a_cerrar,
        fecha=periodo_a_cerrar.fecha_fin,
        descripcion=f"Asiento de Cierre - {periodo_a_cerrar.nombre}",
        creado_por=request.user,
        es_asiento_automatico=True
    )
    
    movimientos_cierre = []
    
    tipos_resultado = [Cuenta.TipoCuenta.INGRESO, Cuenta.TipoCuenta.COSTO, Cuenta.TipoCuenta.GASTO]
    cuentas_resultado = Cuenta.objects.filter(tipo_cuenta__in=tipos_resultado, es_imputable=True)

    for cuenta in cuentas_resultado:
        agregado = Movimiento.objects.filter(
            asiento__periodo=periodo_a_cerrar, 
            cuenta=cuenta,
            asiento__es_asiento_automatico=False
        ).aggregate(
            debe=Sum('debe'), haber=Sum('haber')
        )
        saldo_debe = (agregado['debe'] or 0)
        saldo_haber = (agregado['haber'] or 0)
        
        saldo = Decimal('0.00')
        if cuenta.naturaleza == Cuenta.NaturalezaCuenta.ACREEDORA:
             saldo = saldo_haber - saldo_debe 
        else:
             saldo = saldo_debe - saldo_haber
        
        if saldo != 0:
            if cuenta.naturaleza == Cuenta.NaturalezaCuenta.ACREEDORA: 
                movimientos_cierre.append(Movimiento(asiento=asiento_cierre, cuenta=cuenta, debe=saldo, haber=0))
            else: 
                movimientos_cierre.append(Movimiento(asiento=asiento_cierre, cuenta=cuenta, debe=0, haber=saldo))

    if utilidad_neta > 0: 
        movimientos_cierre.append(Movimiento(asiento=asiento_cierre, cuenta=cuenta_utilidad_ejercicio, debe=0, haber=utilidad_neta))
    elif utilidad_neta < 0: 
        movimientos_cierre.append(Movimiento(asiento=asiento_cierre, cuenta=cuenta_utilidad_ejercicio, debe=abs(utilidad_neta), haber=0))
    
    if movimientos_cierre:
        Movimiento.objects.bulk_create(movimientos_cierre)
    
    periodo_a_cerrar.estado = PeriodoContable.EstadoPeriodo.CERRADO
    periodo_a_cerrar.asiento_cierre = asiento_cierre
    periodo_a_cerrar.save()
    
    messages.success(request, f"Período '{periodo_a_cerrar.nombre}' cerrado exitosamente. Ya puede crear el siguiente período.")
    return redirect('contabilidad:gestionar_periodos')


# --- 
# --- INICIO DE MODIFICACIÓN: Función _crear_asiento_apertura REESCRITA
# --- 
def _crear_asiento_apertura(nuevo_periodo, periodo_anterior, request):
    """
    Función auxiliar interna.
    Crea el asiento de apertura para el nuevo_periodo, basándose
    en los saldos finales del periodo_anterior.
    
    LÓGICA CORREGIDA: Calcula el traspaso de '34' a '33'
    explícitamente para evitar errores de orden.
    """
    admin_user = request.user
    
    try:
        cuenta_utilidad_ejercicio = Cuenta.objects.get(codigo='34') # Utilidad o Pérdida del Ejercicio
        cuenta_resultados_acum = Cuenta.objects.get(codigo='33') # Resultados Acumulados
    except Cuenta.DoesNotExist:
        messages.error(request, "Error Crítico: No se encontraron las cuentas '34' o '33'. Asiento de apertura no se pudo generar.")
        return

    # --- INICIO DE LÓGICA CORREGIDA ---
    
    # 1. Obtener saldos clave ANTES del loop
    #    Usamos _get_saldo_a_fecha, que lee el saldo final total (incl. cierre)
    fecha_fin_anterior = periodo_anterior.fecha_fin
    saldo_utilidad_ejercicio = _get_saldo_a_fecha(cuenta_utilidad_ejercicio, fecha_fin_anterior)
    saldo_acumulado_inicial = _get_saldo_a_fecha(cuenta_resultados_acum, fecha_fin_anterior)

    tipos_balance = [Cuenta.TipoCuenta.ACTIVO, Cuenta.TipoCuenta.PASIVO, Cuenta.TipoCuenta.PATRIMONIO]
    cuentas_balance = Cuenta.objects.filter(tipo_cuenta__in=tipos_balance, es_imputable=True)

    movimientos_apertura = []
    total_debe_apertura = Decimal('0.00')
    total_haber_apertura = Decimal('0.00')

    # 2. Loop principal: procesar TODAS las cuentas EXCEPTO las de traspaso (33 y 34)
    for cuenta in cuentas_balance:
        # Omitir las cuentas que trataremos manualmente
        if cuenta.codigo == cuenta_utilidad_ejercicio.codigo or cuenta.codigo == cuenta_resultados_acum.codigo:
            continue
        
        # Calcular saldo final del período anterior
        saldo_final = _get_saldo_a_fecha(cuenta, fecha_fin_anterior)
            
        if saldo_final != 0:
            if not cuenta.esta_activa and cuenta.codigo != cuenta_resultados_acum.codigo:
                messages.warning(request, f"Se omitió el saldo de {saldo_final} de la cuenta inactiva '{cuenta.nombre}' en el asiento de apertura.")
                continue

            if saldo_final > 0: # Saldo normal según naturaleza
                if cuenta.naturaleza == Cuenta.NaturalezaCuenta.DEUDORA: # Activos
                    movimientos_apertura.append(Movimiento(cuenta=cuenta, debe=saldo_final, haber=0))
                    total_debe_apertura += saldo_final
                else: # Pasivos, Patrimonio (ej. 31, 32)
                    movimientos_apertura.append(Movimiento(cuenta=cuenta, debe=0, haber=saldo_final))
                    total_haber_apertura += saldo_final
            else: # Saldo Invertido (ej. Activo con saldo acreedor)
                if cuenta.naturaleza == Cuenta.NaturalezaCuenta.DEUDORA:
                    movimientos_apertura.append(Movimiento(cuenta=cuenta, debe=0, haber=abs(saldo_final)))
                    total_haber_apertura += abs(saldo_final)
                else: 
                    movimientos_apertura.append(Movimiento(cuenta=cuenta, debe=abs(saldo_final), haber=0))
                    total_debe_apertura += abs(saldo_final)
    
    # 3. Traspaso Manual: Mover el saldo de '34' a '33'
    saldo_final_acumulado = saldo_acumulado_inicial + saldo_utilidad_ejercicio
    
    if saldo_final_acumulado != 0:
        if saldo_final_acumulado > 0: # Saldo Acreedor (normal)
            movimientos_apertura.append(Movimiento(cuenta=cuenta_resultados_acum, debe=0, haber=saldo_final_acumulado))
            total_haber_apertura += saldo_final_acumulado
        else: # Saldo Deudor (pérdidas acumuladas)
            movimientos_apertura.append(Movimiento(cuenta=cuenta_resultados_acum, debe=abs(saldo_final_acumulado), haber=0))
            total_debe_apertura += abs(saldo_final_acumulado)

    # --- FIN DE LÓGICA CORREGIDA ---

    if not movimientos_apertura:
        messages.warning(request, "No se generó asiento de apertura. No se encontraron saldos de balance en el período anterior.")
        return

    # 4. Crear el Asiento de Apertura
    asiento_apertura = AsientoDiario.objects.create(
        periodo=nuevo_periodo,
        fecha=nuevo_periodo.fecha_inicio,
        descripcion=f"Asiento de Apertura - Saldos de {periodo_anterior.nombre}",
        creado_por=admin_user,
        es_asiento_automatico=True
    )
    
    for mov in movimientos_apertura:
        mov.asiento = asiento_apertura
    
    Movimiento.objects.bulk_create(movimientos_apertura)

    periodo_anterior.asiento_apertura_siguiente = asiento_apertura
    periodo_anterior.save()
    
    if total_debe_apertura.quantize(Decimal('0.01')) != total_haber_apertura.quantize(Decimal('0.01')):
        messages.error(request, f"¡Error Crítico! El Asiento de Apertura N° {asiento_apertura.numero_partida} está DESCUADRADO (Debe: {total_debe_apertura}, Haber: {total_haber_apertura}). Revise los saldos y asientos de cierre.")
    else:
        messages.success(request, f"Se generó el Asiento de Apertura N° {asiento_apertura.numero_partida} en el nuevo período.")
# --- 
# --- FIN DE MODIFICACIÓN: Función _crear_asiento_apertura REESCRITA
# --- 


# --- ========================================= ---
# ---     Manejador de Error 404 (Sin cambios)  ---
# --- ========================================= ---

def custom_404_view(request, exception):
    # ... (Sin cambios) ...
    context = {'user': request.user}
    return render(request, '404.html', context, status=404)