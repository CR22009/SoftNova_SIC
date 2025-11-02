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
from .forms import AsientoDiarioForm, MovimientoFormSet
from decimal import Decimal

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
# ---     Vistas de Configuración (Read-Only) ---
# --- ========================================= ---

@login_required
@user_passes_test(check_acceso_contable) # <-- DECORADOR ACTUALIZADO
def ver_catalogo(request):
    """Muestra el Catálogo de Cuentas (Solo Lectura)."""
    cuentas_principales = Cuenta.objects.filter(padre__isnull=True).order_by('codigo')
    context = {
        'cuentas_principales': cuentas_principales,
    }
    return render(request, 'contabilidad/catalogo_readonly.html', context)

@login_required
@user_passes_test(check_acceso_contable) # <-- DECORADOR ACTUALIZADO
def ver_periodos(request):
    """Muestra los Períodos Contables (Solo Lectura)."""
    periodos = PeriodoContable.objects.all().order_by('-fecha_inicio')
    context = {
        'periodos': periodos,
    }
    return render(request, 'contabilidad/periodos_readonly.html', context)

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