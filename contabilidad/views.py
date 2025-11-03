from django.utils.timezone import now
from calendar import monthrange
from datetime import date
from django.urls import reverse
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
# --- MODIFICADO: Importar el nuevo PeriodoForm ---
from .forms import AsientoDiarioForm, MovimientoFormSet, PeriodoForm
from decimal import Decimal
from datetime import date, timedelta
from calendar import monthrange

# --- ========================================= ---
# ---     AUTENTICACIÓN Y ROLES (NUEVO)         ---
# --- ========================================= ---

def login_view(request):
    """
    Maneja el inicio de sesión personalizado.
    """
    # Si el usuario ya está autenticado, redirigir al dashboard
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
                # Redirigir al dashboard después de un login exitoso
                return redirect('contabilidad:dashboard')
            else:
                messages.error(request, "Usuario o contraseña incorrectos. Inténtalo de nuevo.")
        else:
            messages.error(request, "Usuario o contraseña incorrectos. Inténtalo de nuevo.")
    else:
        form = AuthenticationForm()
        
    # Renderizar la plantilla de login personalizada
    # (La crearemos en el siguiente paso)
    return render(request, 'contabilidad/login.html', {'form': form})

def logout_view(request):
    """
    Cierra la sesión del usuario.
    """
    logout(request)
    messages.info(request, "Has cerrado sesión exitosamente.")
    # Redirigir a la página de login
    return redirect('contabilidad:login')


# --- Verificación de Roles (NUEVO) ---
def es_grupo_administrador(user):
    """Verifica si el usuario pertenece al grupo 'Administrador'."""
    return user.groups.filter(name='Administrador').exists()

def check_acceso_admin(user):
    """Verifica si el usuario tiene rol de Administrador o es Superuser."""
    if not user.is_authenticated:
        return False
    return user.is_superuser or es_grupo_administrador(user)

def es_grupo_contador(user):
    """Verifica si el usuario pertenece al grupo 'Contador'."""
    return user.groups.filter(name='Contador').exists()

def es_grupo_informatico(user):
    """Verifica si el usuario pertenece al grupo 'Informático'."""
    return user.groups.filter(name='Informático').exists()

# Comprobador para vistas contables (Acceso para Admin Y Contador)
def check_acceso_contable(user):
    """Verifica si el usuario tiene rol de Administrador o Contador."""
    return user.is_authenticated and (es_grupo_administrador(user) or es_grupo_contador(user))

# Comprobador para vistas de costeo (Acceso para Admin E Informático)
def check_acceso_costeo(user):
    """Verifica si el usuario tiene rol de Administrador o Informático."""
    # (Lo usaremos cuando implementemos el módulo de costeo)
    return user.is_authenticated and (es_grupo_administrador(user) or es_grupo_informatico(user))


# --- ========================================= ---
# ---     Dashboard (Sin cambios, solo @login_required) ---
# --- ========================================= ---
@login_required
def dashboard(request):
    """Página principal del sistema."""
    ultimos_asientos = AsientoDiario.objects.order_by('-fecha', '-numero_partida')[:5]
    periodo_abierto = PeriodoContable.objects.filter(estado=PeriodoContable.EstadoPeriodo.ABIERTO).first()
    context = {
        'ultimos_asientos': ultimos_asientos,
        'periodo_abierto': periodo_abierto,
    }
    return render(request, 'contabilidad/dashboard.html', context)

# --- ========================================= ---
# ---     FASE 1 - Registro de Transacciones    ---
# --- ========================================= ---

@login_required
@user_passes_test(check_acceso_contable) # <-- DECORADOR ACTUALIZADO
@transaction.atomic
def registrar_asiento(request):
    """Maneja el formulario de registro de asientos diarios con formsets."""
    
    # --- Validar que no sea un asiento automático ---
    # (Esta lógica aún no está implementada para edición, pero la validación es buena)
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
            
            # Validar que no esté vacío
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
                    # Guardar Asiento
                    asiento = asiento_form.save(commit=False)
                    asiento.creado_por = request.user
                    # La lógica de 'save()' en models.py asignará el numero_partida
                    asiento.save() 
                    
                    # Guardar Movimientos
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
# ---     FASE 2 - Vistas de Reportes           ---
# --- ========================================= ---

@login_required
@user_passes_test(check_acceso_contable) # <-- DECORADOR ACTUALIZADO
def mayor_seleccion(request):
    """Hub de selección para Libro Mayor y Balanza de Comprobación."""
    periodos = PeriodoContable.objects.all().order_by('-fecha_inicio')
    periodo_seleccionado = None
    cuentas = None # Cuentas con movimiento
    periodo_id = request.GET.get('periodo_id')

    if periodo_id:
        try:
            periodo_seleccionado = PeriodoContable.objects.get(pk=periodo_id)
            # Optimización: Solo mostrar cuentas que tuvieron movimiento en ese período
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
        'cuentas': cuentas, # Para el selector de Cuentas T
    }
    return render(request, 'contabilidad/mayor_seleccion.html', context)

@login_required
@user_passes_test(check_acceso_contable) # <-- DECORADOR ACTUALIZADO
def libro_mayor_detalle(request, periodo_id, cuenta_id):
    """Muestra el detalle de una Cuenta T para un período."""
    periodo = get_object_or_404(PeriodoContable, pk=periodo_id)
    cuenta = get_object_or_404(Cuenta, pk=cuenta_id)
    
    # Obtener todos los movimientos
    movimientos = Movimiento.objects.filter(
        asiento__periodo=periodo,
        cuenta=cuenta
    ).order_by('asiento__fecha', 'asiento__numero_partida', 'pk')
    
    # Separar para la vista de Cuenta T
    movimientos_debe = movimientos.filter(debe__gt=0)
    movimientos_haber = movimientos.filter(haber__gt=0)
    
    # Calcular totales y saldo
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
@user_passes_test(check_acceso_contable) # <-- DECORADOR ACTUALIZADO
def balanza_comprobacion(request, periodo_id):
    """Muestra la Balanza de Comprobación para un período."""
    periodo = get_object_or_404(PeriodoContable, pk=periodo_id)
    # Solo cuentas imputables
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
        
        # Solo incluir cuentas con movimiento
        if total_debe > 0 or total_haber > 0:
            saldo_deudor = Decimal('0.00')
            saldo_acreedor = Decimal('0.00')
            
            if cuenta.naturaleza == Cuenta.NaturalezaCuenta.DEUDORA:
                saldo = total_debe - total_haber
                if saldo > 0: saldo_deudor = saldo
                else: saldo_acreedor = -saldo 
            else: # Naturaleza Acreedora
                saldo = total_haber - total_debe
                if saldo > 0: saldo_acreedor = saldo
                else: saldo_deudor = -saldo 
                
            resultados.append({
                'codigo': cuenta.codigo,
                'nombre': cuenta.nombre,
                'saldo_deudor': saldo_deudor,
                'saldo_acreedor': saldo_acreedor,
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
# ---     FASE 3 - Estados Financieros (Refactorizados) ---
# --- ========================================= ---

# --- Funciones Auxiliares ---
def _calcular_saldos_cuentas_por_tipo(periodo, tipo_cuenta):
    """Calcula saldos de cuentas imputables para un tipo (ER, BG)."""
    cuentas = Cuenta.objects.filter(tipo_cuenta=tipo_cuenta, es_imputable=True).order_by('codigo')
    lista_saldos = []
    total_general_tipo = Decimal('0.00')

    for c in cuentas:
        agregado = Movimiento.objects.filter(asiento__periodo=periodo, cuenta=c).aggregate(
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
    """Calcula la Utilidad Neta (Ingresos - Costos - Gastos)."""
    _, total_ingresos = _calcular_saldos_cuentas_por_tipo(periodo, Cuenta.TipoCuenta.INGRESO)
    _, total_costos = _calcular_saldos_cuentas_por_tipo(periodo, Cuenta.TipoCuenta.COSTO)
    _, total_gastos = _calcular_saldos_cuentas_por_tipo(periodo, Cuenta.TipoCuenta.GASTO)
    
    utilidad = total_ingresos - (total_costos + total_gastos)
    return utilidad

# --- Helper para Flujo de Efectivo ---
def _get_saldo_cuentas(cuentas_ids, periodo):
    """
    Calcula el saldo acumulado de un conjunto de cuentas HASTA el final
    de un período dado (o 0 si el período es None).
    """
    if not periodo:
        return Decimal('0.00')
    
    # Movimientos hasta el final del período
    agregado = Movimiento.objects.filter(
        asiento__fecha__lte=periodo.fecha_fin, # Clave: HASTA esta fecha
        cuenta_id__in=cuentas_ids
    ).aggregate(
        total_debe=models.Sum('debe'),
        total_haber=models.Sum('haber')
    )
    total_debe = agregado.get('total_debe') or Decimal('0.00')
    total_haber = agregado.get('total_haber') or Decimal('0.00')
    
    # Asumimos que las cuentas de efectivo son DEUDORAS por naturaleza
    saldo = total_debe - total_haber
    return saldo

# --- Estado de Resultados ---
@login_required
@user_passes_test(check_acceso_contable) # <-- DECORADOR ACTUALIZADO
def estado_resultados(request, periodo_id):
    """Muestra el reporte de Estado de Resultados."""
    periodo = get_object_or_404(PeriodoContable, pk=periodo_id)
    
    lista_ingresos, total_ingresos = _calcular_saldos_cuentas_por_tipo(periodo, Cuenta.TipoCuenta.INGRESO)
    lista_costos, total_costos = _calcular_saldos_cuentas_por_tipo(periodo, Cuenta.TipoCuenta.COSTO)
    lista_gastos, total_gastos = _calcular_saldos_cuentas_por_tipo(periodo, Cuenta.TipoCuenta.GASTO)
    
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
@user_passes_test(check_acceso_contable) # <-- DECORADOR ACTUALIZADO
def hub_estado_resultados(request):
    """Hub de selección para Estado de Resultados."""
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
    
    periodos = PeriodoContable.objects.all().order_by('-fecha_inicio')
    context = {
        'periodos': periodos
    }
    return render(request, 'contabilidad/hub_estado_resultados.html', context)

# --- Balance General ---
@login_required
@user_passes_test(check_acceso_contable) # <-- DECORADOR ACTUALIZADO
def balance_general(request, periodo_id):
    """Muestra el reporte de Balance General."""
    periodo = get_object_or_404(PeriodoContable, pk=periodo_id)
    
    lista_activos, total_activos = _calcular_saldos_cuentas_por_tipo(periodo, Cuenta.TipoCuenta.ACTIVO)
    lista_pasivos, total_pasivos = _calcular_saldos_cuentas_por_tipo(periodo, Cuenta.TipoCuenta.PASIVO)
    lista_patrimonio, total_patrimonio = _calcular_saldos_cuentas_por_tipo(periodo, Cuenta.TipoCuenta.PATRIMONIO)
    utilidad_ejercicio = _get_utilidad_del_ejercicio(periodo)
    
    total_patrimonio_final = total_patrimonio + utilidad_ejercicio
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
@user_passes_test(check_acceso_contable) # <-- DECORADOR ACTUALIZADO
def hub_balance_general(request):
    """Hub de selección para Balance General."""
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
    
    periodos = PeriodoContable.objects.all().order_by('-fecha_inicio')
    context = {
        'periodos': periodos
    }
    return render(request, 'contabilidad/hub_balance_general.html', context)


# --- Flujo de Efectivo ---
@login_required
@user_passes_test(check_acceso_contable) # <-- DECORADOR ACTUALIZADO
def flujo_efectivo(request, periodo_id):
    """
    Muestra el reporte de Flujo de Efectivo (Método Directo Simplificado)
    analizando las contrapartidas de las cuentas de efectivo.
    """
    periodo = get_object_or_404(PeriodoContable, pk=periodo_id)
    
    # 1. Identificar cuentas de Efectivo (Caja y Bancos, código 11)
    cuentas_efectivo_ids = Cuenta.objects.filter(
        codigo__startswith='11', es_imputable=True
    ).values_list('id', flat=True)

    # 2. Calcular Saldo Inicial y Final de Efectivo
    periodo_anterior = PeriodoContable.objects.filter(
        fecha_fin__lt=periodo.fecha_inicio
    ).order_by('-fecha_fin').first()
    
    saldo_inicial_efectivo = _get_saldo_cuentas(cuentas_efectivo_ids, periodo_anterior)
    saldo_final_efectivo = _get_saldo_cuentas(cuentas_efectivo_ids, periodo)
    
    # 3. Encontrar asientos que movieron efectivo en este período
    asientos_con_efectivo_ids = Movimiento.objects.filter(
        asiento__periodo=periodo,
        cuenta_id__in=cuentas_efectivo_ids
    ).values_list('asiento_id', flat=True).distinct()

    # 4. Obtener TODAS las contrapartidas (no-efectivo) de esos asientos
    #    Agrupadas por cuenta para resumir.
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

    # 5. Clasificar contrapartidas
    flujos_operacion = []
    total_operacion = Decimal('0.00')
    flujos_inversion = []
    total_inversion = Decimal('0.00')
    flujos_financiacion = []
    total_financiacion = Decimal('0.00')

    for item in contrapartidas:
        codigo = item['cuenta__codigo']
        nombre = item['cuenta__nombre']
        # El saldo de la contrapartida (Debe - Haber)
        saldo_contrapartida = (item['total_debe'] or 0) - (item['total_haber'] or 0)
        # El flujo de efectivo es el INVERSO del saldo de la contrapartida
        flujo = -saldo_contrapartida
        
        flujo_item = {'nombre': nombre, 'monto': flujo}

        # Códigos de Operación (Ingresos '4', Costos '5', Gastos '52',
        # Cuentas x Cobrar '12', Cuentas x Pagar '21', '23', Impuestos '14', '22')
        if (codigo.startswith('4') or codigo.startswith('5') or 
            codigo.startswith('12') or codigo.startswith('13') or 
            codigo.startswith('14') or codigo.startswith('21') or 
            codigo.startswith('22') or codigo.startswith('23') or 
            codigo.startswith('24')):
            flujos_operacion.append(flujo_item)
            total_operacion += flujo
        
        # Códigos de Inversión (Activos Fijos '15', Intangibles '16')
        elif codigo.startswith('15') or codigo.startswith('16') or codigo.startswith('17'):
            flujos_inversion.append(flujo_item)
            total_inversion += flujo

        # Códigos de Financiación (Préstamos '25', Patrimonio '3')
        elif codigo.startswith('25') or codigo.startswith('3'):
            flujos_financiacion.append(flujo_item)
            total_financiacion += flujo
        
    # 6. Verificación final
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
        'flujo_calculado': flujo_calculado, # Saldo inicial + Flujo Neto
        'esta_cuadrado': esta_cuadrado,
        'diferencia': diferencia,
    }
    return render(request, 'contabilidad/flujo_efectivo.html', context)


@login_required
@user_passes_test(check_acceso_contable) # <-- DECORADOR ACTUALIZADO
def hub_flujo_efectivo(request):
    """
    Página de selección de período dedicada al Flujo de Efectivo.
    """
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
    
    periodos = PeriodoContable.objects.all().order_by('-fecha_inicio')
    context = {
        'periodos': periodos
    }
    return render(request, 'contabilidad/hub_flujo_efectivo.html', context)


# --- Estado de Patrimonio ---
@login_required
@user_passes_test(check_acceso_contable) # <-- DECORADOR ACTUALIZADO
def hub_estado_patrimonio(request):
    """Hub de selección para Estado de Cambios en el Patrimonio."""
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
    
    periodos = PeriodoContable.objects.all().order_by('-fecha_inicio')
    context = {
        'periodos': periodos
    }
    return render(request, 'contabilidad/hub_estado_patrimonio.html', context)

@login_required
@user_passes_test(check_acceso_contable) # <-- DECORADOR ACTUALIZADO
def estado_patrimonio(request, periodo_id):
    """
    Muestra el reporte de Estado de Cambios en el Patrimonio.
    (Versión simplificada consistente con otros reportes).
    """
    periodo = get_object_or_404(PeriodoContable, pk=periodo_id)
    
    # 1. Reutilizamos la lógica del Balance General
    # Esto nos da los saldos del período para Capital, Reservas, etc.
    lista_patrimonio, total_patrimonio_historico = _calcular_saldos_cuentas_por_tipo(periodo, Cuenta.TipoCuenta.PATRIMONIO)
    
    # 2. Reutilizamos la lógica del Estado de Resultados
    utilidad_ejercicio = _get_utilidad_del_ejercicio(periodo)
    
    # 3. Calculamos el total
    total_patrimonio_final = total_patrimonio_historico + utilidad_ejercicio

    context = {
        'periodo': periodo,
        'lista_patrimonio': lista_patrimonio, # Ej. [{'cuenta': <Cta 31>, 'saldo': 50000}, ...]
        'total_patrimonio_historico': total_patrimonio_historico,
        'utilidad_ejercicio': utilidad_ejercicio,
        'total_patrimonio_final': total_patrimonio_final,
    }
    return render(request, 'contabilidad/estado_patrimonio.html', context)

# --- ========================================= ---
# ---           Vistas de Configuración         ---
# --- ========================================= ---
@login_required
@user_passes_test(check_acceso_contable) # Sigue siendo accesible para ambos
def ver_catalogo(request):
    """Muestra el Catálogo de Cuentas (Solo Lectura)."""
    cuentas_principales = Cuenta.objects.filter(padre__isnull=True).order_by('codigo')
    context = {
        'cuentas_principales': cuentas_principales,
    }
    return render(request, 'contabilidad/catalogo_readonly.html', context)

# --- MODIFICADO: VISTA DE GESTIÓN DE PERÍODOS ---
@login_required
@user_passes_test(check_acceso_contable) # Accesible para Admin y Contador
@transaction.atomic # Usar transacción para la creación de período + apertura
def gestionar_periodos(request):
    """
    Vista personalizada para gestionar Períodos Contables.
    - Admin: Puede crear (con fechas personalizadas) y cerrar períodos.
    - Contador: Solo puede ver.
    """
    periodos = PeriodoContable.objects.all().order_by('-fecha_inicio')
    periodo_abierto = periodos.filter(estado=PeriodoContable.EstadoPeriodo.ABIERTO).first()
    
    # Inicializar form
    form = None
    
    # --- Lógica para CREAR un nuevo período (Solo Admin) ---
    if request.method == 'POST' and check_acceso_admin(request.user):
        
        # Validar que no haya un período abierto
        if periodo_abierto:
            messages.error(request, f"Ya existe un período abierto ({periodo_abierto.nombre}). Debe cerrarlo primero.")
            return redirect('contabilidad:gestionar_periodos')
            
        form = PeriodoForm(request.POST)
        if form.is_valid():
            try:
                # Guardar el formulario con las fechas personalizadas
                nuevo_periodo = form.save(commit=False)
                nuevo_periodo.estado = PeriodoContable.EstadoPeriodo.ABIERTO
                nuevo_periodo.save()
                messages.success(request, f"Período '{nuevo_periodo.nombre}' creado y abierto exitosamente.")
                
                # --- Lógica de Apertura ---
                # Buscar el período cerrado más reciente
                ultimo_periodo_cerrado = PeriodoContable.objects.filter(
                    estado=PeriodoContable.EstadoPeriodo.CERRADO,
                    fecha_fin__lt=nuevo_periodo.fecha_inicio
                ).order_by('-fecha_fin').first()

                if ultimo_periodo_cerrado:
                    # Si existe un período cerrado anterior, crear asiento de apertura
                    # --- MODIFICADO: Pasar el 'request' completo, no solo 'request.user' ---
                    _crear_asiento_apertura(nuevo_periodo, ultimo_periodo_cerrado, request)
                else:
                    messages.info(request, "Este es el primer período (o no hay período cerrado anterior), no se generó asiento de apertura.")
                
                return redirect('contabilidad:gestionar_periodos')
            
            except Exception as e:
                messages.error(request, f"Error al guardar el período: {e}")
                # Si falla, el form con errores se pasará al contexto más abajo
        
        else:
            # Si el formulario no es válido (ej. fechas solapadas),
            # se mostrarán los errores en el modal (ver plantilla).
            messages.error(request, "Error en el formulario. Revisa los datos ingresados.")
            # No redirigimos, dejamos que la vista GET renderice el formulario con errores

    # --- Lógica GET (Mostrar la página) ---
    
    # Calcular fechas sugeridas para el formulario
    ultimo_periodo = PeriodoContable.objects.order_by('-fecha_fin').first()
    if ultimo_periodo:
        fecha_inicio_sugerida = (ultimo_periodo.fecha_fin + timedelta(days=1))
    else:
        fecha_inicio_sugerida = date.today().replace(day=1)
        
    ultimo_dia_sugerido = monthrange(fecha_inicio_sugerida.year, fecha_inicio_sugerida.month)[1]
    fecha_fin_sugerida = fecha_inicio_sugerida.replace(day=ultimo_dia_sugerido)
    nombre_sugerido = fecha_inicio_sugerida.strftime('%B %Y').capitalize()

    # Si la solicitud fue POST y falló, 'form' ya tendrá los datos y errores.
    # Si es GET, creamos el formulario con las fechas sugeridas.
    if request.method != 'POST' or not form:
        form = PeriodoForm(initial={
            'nombre': nombre_sugerido,
            'fecha_inicio': fecha_inicio_sugerida,
            'fecha_fin': fecha_fin_sugerida
        })

    context = {
        'periodos': periodos,
        'periodo_abierto': periodo_abierto,
        'form_periodo': form # Pasamos el formulario al contexto
    }
    return render(request, 'contabilidad/gestionar_periodos.html', context)


@login_required
@user_passes_test(check_acceso_admin) # Solo el Admin puede CERRAR
@transaction.atomic
def cerrar_periodo(request, periodo_id):
    """
    Ejecuta la lógica contable para cerrar un período.
    SOLO genera el asiento de cierre. La apertura se
    maneja al crear el siguiente período.
    """
    if request.method != 'POST':
        return redirect('contabilidad:gestionar_periodos')

    periodo_a_cerrar = get_object_or_404(PeriodoContable, pk=periodo_id)
    if periodo_a_cerrar.estado == PeriodoContable.EstadoPeriodo.CERRADO:
        messages.error(request, "Este período ya está cerrado.")
        return redirect('contabilidad:gestionar_periodos')
        
    # CUENTAS CLAVE (basadas en tu catálogo PDF)
    try:
        cuenta_utilidad_ejercicio = Cuenta.objects.get(codigo='34') # Utilidad o Pérdida del Ejercicio
    except Cuenta.DoesNotExist:
        messages.error(request, "Error Crítico: No se encontró la cuenta '34' (Utilidad o Pérdida del Ejercicio) en el catálogo. Cierre cancelado.")
        return redirect('contabilidad:gestionar_periodos')
    
    # Validar que la cuenta '34' sea imputable
    if not cuenta_utilidad_ejercicio.es_imputable:
        messages.error(request, "Error Crítico: La cuenta '34' (Utilidad o Pérdida del Ejercicio) no está marcada como 'imputable' en el catálogo. Cierre cancelado.")
        return redirect('contabilidad:gestionar_periodos')


    # --- 1. CREAR ASIENTO DE CIERRE (RESULTADOS) ---
    utilidad_neta = _get_utilidad_del_ejercicio(periodo_a_cerrar)
    
    asiento_cierre = AsientoDiario.objects.create(
        periodo=periodo_a_cerrar,
        fecha=periodo_a_cerrar.fecha_fin,
        descripcion=f"Asiento de Cierre - {periodo_a_cerrar.nombre}",
        creado_por=request.user,
        es_asiento_automatico=True
    )
    
    movimientos_cierre = []
    
    # Cuentas de Resultado (Ingresos, Costos, Gastos)
    tipos_resultado = [Cuenta.TipoCuenta.INGRESO, Cuenta.TipoCuenta.COSTO, Cuenta.TipoCuenta.GASTO]
    cuentas_resultado = Cuenta.objects.filter(tipo_cuenta__in=tipos_resultado, es_imputable=True)

    for cuenta in cuentas_resultado:
        # Obtenemos el saldo individual real de la cuenta
        agregado = Movimiento.objects.filter(asiento__periodo=periodo_a_cerrar, cuenta=cuenta).aggregate(
            debe=Sum('debe'), haber=Sum('haber')
        )
        saldo_debe = (agregado['debe'] or 0)
        saldo_haber = (agregado['haber'] or 0)
        
        saldo = Decimal('0.00')
        if cuenta.naturaleza == Cuenta.NaturalezaCuenta.ACREEDORA:
             saldo = saldo_haber - saldo_debe # Saldo Acreedor (Ingresos)
        else:
             saldo = saldo_debe - saldo_haber # Saldo Deudor (Costos/Gastos)
        
        # Si hay saldo, creamos el movimiento contrario para saldarla
        if saldo != 0:
            if cuenta.naturaleza == Cuenta.NaturalezaCuenta.ACREEDORA: # Ingresos
                movimientos_cierre.append(Movimiento(asiento=asiento_cierre, cuenta=cuenta, debe=saldo, haber=0))
            else: # Costos y Gastos
                movimientos_cierre.append(Movimiento(asiento=asiento_cierre, cuenta=cuenta, debe=0, haber=saldo))

    # Movimiento contrapartida a Utilidad del Ejercicio ('34')
    if utilidad_neta > 0: # Ganancia (Acreedor)
        movimientos_cierre.append(Movimiento(asiento=asiento_cierre, cuenta=cuenta_utilidad_ejercicio, debe=0, haber=utilidad_neta))
    elif utilidad_neta < 0: # Pérdida (Deudor)
        movimientos_cierre.append(Movimiento(asiento=asiento_cierre, cuenta=cuenta_utilidad_ejercicio, debe=abs(utilidad_neta), haber=0))
    
    if movimientos_cierre:
        Movimiento.objects.bulk_create(movimientos_cierre)
    
    # --- 2. FINALIZAR Y GUARDAR ---
    periodo_a_cerrar.estado = PeriodoContable.EstadoPeriodo.CERRADO
    periodo_a_cerrar.asiento_cierre = asiento_cierre
    # Ya no creamos el asiento de apertura aquí
    # periodo_a_cerrar.asiento_apertura_siguiente = asiento_apertura
    periodo_a_cerrar.save()
    
    messages.success(request, f"Período '{periodo_a_cerrar.nombre}' cerrado exitosamente. Ya puede crear el siguiente período.")
    return redirect('contabilidad:gestionar_periodos')


# --- MODIFICADO: _crear_asiento_apertura ---
# Ahora acepta 'request' en lugar de 'admin_user'
def _crear_asiento_apertura(nuevo_periodo, periodo_anterior, request):
    """
    Función auxiliar interna.
    Crea el asiento de apertura para el nuevo_periodo, basándose
    en los saldos finales del periodo_anterior.
    """
    # Obtenemos el admin_user desde el request
    admin_user = request.user
    
    try:
        cuenta_utilidad_ejercicio = Cuenta.objects.get(codigo='34') # Utilidad o Pérdida del Ejercicio
        cuenta_resultados_acum = Cuenta.objects.get(codigo='33') # Resultados Acumulados
    except Cuenta.DoesNotExist:
        # --- MODIFICADO: Usar 'request' para el mensaje ---
        messages.error(request, "Error Crítico: No se encontraron las cuentas '34' o '33'. Asiento de apertura no se pudo generar.")
        return

    # 1. Obtener todas las cuentas de Balance (Activo, Pasivo, Patrimonio)
    tipos_balance = [Cuenta.TipoCuenta.ACTIVO, Cuenta.TipoCuenta.PASIVO, Cuenta.TipoCuenta.PATRIMONIO]
    cuentas_balance = Cuenta.objects.filter(tipo_cuenta__in=tipos_balance, es_imputable=True)

    movimientos_apertura = []
    total_debe_apertura = Decimal('0.00')
    total_haber_apertura = Decimal('0.00')

    # Variable para guardar el saldo de la cuenta '34'
    saldo_utilidad_ejercicio = Decimal('0.00')

    for cuenta in cuentas_balance:
        # Calcular saldo final del período anterior (incluyendo asiento de cierre)
        agregado = Movimiento.objects.filter(asiento__periodo=periodo_anterior, cuenta=cuenta).aggregate(
            debe=Sum('debe'), haber=Sum('haber')
        )
        saldo_debe = (agregado['debe'] or 0)
        saldo_haber = (agregado['haber'] or 0)
        
        saldo_final = Decimal('0.00')
        if cuenta.naturaleza == Cuenta.NaturalezaCuenta.DEUDORA:
             saldo_final = saldo_debe - saldo_haber
        else:
             saldo = saldo_haber - saldo_debe
        
        # --- Lógica de Traspaso de Utilidad ---
        if cuenta.codigo == cuenta_utilidad_ejercicio.codigo:
            # 1. Guardamos el saldo de la '34'
            saldo_utilidad_ejercicio = saldo_final
            # 2. No creamos movimiento de apertura para la '34', 
            #    ya que su saldo debe morir y pasar a la '33'.
            continue 
        
        # 3. Si la cuenta es 'Resultados Acumulados' (33), 
        #    le sumamos el saldo que traía la '34'.
        if cuenta.codigo == cuenta_resultados_acum.codigo:
            saldo_final += saldo_utilidad_ejercicio

        # --- Fin Lógica de Traspaso ---
            
        # Crear movimiento de apertura
        if saldo_final != 0:
            if saldo_final > 0: # Saldo normal según naturaleza
                if cuenta.naturaleza == Cuenta.NaturalezaCuenta.DEUDORA: # Activos
                    movimientos_apertura.append(Movimiento(cuenta=cuenta, debe=saldo_final, haber=0))
                    total_debe_apertura += saldo_final
                else: # Pasivos, Patrimonio
                    movimientos_apertura.append(Movimiento(cuenta=cuenta, debe=0, haber=saldo_final))
                    total_haber_apertura += saldo_final
            else: # Saldo Invertido (ej. Activo con saldo acreedor)
                if cuenta.naturaleza == Cuenta.NaturalezaCuenta.DEUDORA:
                    movimientos_apertura.append(Movimiento(cuenta=cuenta, debe=0, haber=abs(saldo_final)))
                    total_haber_apertura += abs(saldo_final)
                else: 
                    movimientos_apertura.append(Movimiento(cuenta=cuenta, debe=abs(saldo_final), haber=0))
                    total_debe_apertura += abs(saldo_final)

    if not movimientos_apertura:
        # --- MODIFICADO: Usar 'request' para el mensaje ---
        messages.warning(request, "No se generó asiento de apertura. No se encontraron saldos de balance en el período anterior.")
        return

    # 2. Crear el Asiento de Apertura
    asiento_apertura = AsientoDiario.objects.create(
        periodo=nuevo_periodo,
        fecha=nuevo_periodo.fecha_inicio,
        descripcion=f"Asiento de Apertura - Saldos de {periodo_anterior.nombre}",
        creado_por=admin_user,
        es_asiento_automatico=True
    )
    
    # Asignar el asiento a todos los movimientos
    for mov in movimientos_apertura:
        mov.asiento = asiento_apertura
    
    # 3. Guardar movimientos en bloque
    Movimiento.objects.bulk_create(movimientos_apertura)

    # 4. FINALIZAR Y GUARDAR
    periodo_anterior.asiento_apertura_siguiente = asiento_apertura
    periodo_anterior.save()
    
    # 5. Verificar si el asiento de apertura cuadró
    if total_debe_apertura.quantize(Decimal('0.01')) != total_haber_apertura.quantize(Decimal('0.01')):
        # --- MODIFICADO: Usar 'request' para el mensaje ---
        messages.error(request, f"¡Error Crítico! El Asiento de Apertura N° {asiento_apertura.numero_partida} está DESCUADRADO (Debe: {total_debe_apertura}, Haber: {total_haber_apertura}). Revise los saldos y asientos de cierre.")
    else:
        # --- MODIFICADO: Usar 'request' para el mensaje ---
        messages.success(request, f"Se generó el Asiento de Apertura N° {asiento_apertura.numero_partida} en el nuevo período.")


# --- ========================================= ---
# ---     Manejador de Error 404         ---
# --- ========================================= ---

def custom_404_view(request, exception):
    """
    Vista personalizada para manejar los errores 404 (Página no encontrada).
    """
    # Pasamos el 'request.user' al contexto para que el template
    # pueda decidir si muestra el botón de "Dashboard" o "Login".
    context = {'user': request.user}
    return render(request, '404.html', context, status=404)


