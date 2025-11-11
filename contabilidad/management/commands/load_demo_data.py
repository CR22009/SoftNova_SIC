import decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth import get_user_model
from contabilidad.models import PeriodoContable, Cuenta, AsientoDiario, Movimiento
from decimal import Decimal
from datetime import date, timedelta
from calendar import monthrange

# Este es el nuevo "comando" que podrás ejecutar desde la terminal
# python manage.py load_demo_data

class Command(BaseCommand):
    help = 'Carga un conjunto ampliado de datos de prueba (apertura, ventas, gastos, cobros, pagos) en el primer período abierto.'

    # --- NUEVA FUNCIÓN AUXILIAR ---
    def _crear_asiento(self, periodo, fecha, descripcion, admin_user, movimientos_data, es_automatico=False):
        """
        Función auxiliar para crear un asiento y sus movimientos,
        validando que esté cuadrado.
        """
        # Validar que la fecha esté dentro del período
        if not (periodo.fecha_inicio <= fecha <= periodo.fecha_fin):
             self.stdout.write(self.style.ERROR(f"La fecha {fecha} está fuera del período '{periodo.nombre}'. Abortando asiento '{descripcion}'."))
             raise Exception(f"Fecha {fecha} fuera del rango del período {periodo.nombre}.")

        asiento = AsientoDiario.objects.create(
            periodo=periodo,
            fecha=fecha,
            descripcion=descripcion,
            creado_por=admin_user,
            es_asiento_automatico=es_automatico
        )
        
        movimientos_para_crear = []
        total_debe = Decimal('0.00')
        total_haber = Decimal('0.00')
        
        for cuenta, debe, haber in movimientos_data:
            movimientos_para_crear.append(
                Movimiento(asiento=asiento, cuenta=cuenta, debe=Decimal(debe), haber=Decimal(haber))
            )
            total_debe += Decimal(debe)
            total_haber += Decimal(haber)
        
        # Validar cuadre
        if total_debe.quantize(Decimal('0.01')) != total_haber.quantize(Decimal('0.01')):
            # Si falla, la transacción atómica hará un rollback
            self.stdout.write(self.style.ERROR(f"Asiento de prueba '{descripcion}' está descuadrado (Debe: {total_debe}, Haber: {total_haber}). Abortando."))
            raise Exception(f"Asiento de prueba '{descripcion}' descuadrado.")
            
        Movimiento.objects.bulk_create(movimientos_para_crear)
        # Usamos NOTICE para que resalte en la consola
        self.stdout.write(self.style.NOTICE(f" -> Asiento '{descripcion}' (P-{asiento.numero_partida}) creado exitosamente (Total: ${total_debe})."))
    # --- FIN DE FUNCIÓN AUXILIAR ---

    @transaction.atomic
    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS('--- Iniciando carga de DATOS DE PRUEBA AMPLIADOS ---'))

        # 1. Verificar si ya se cargaron los datos
        if AsientoDiario.objects.filter(descripcion="PARTIDA DE APERTURA (DATOS DE PRUEBA)").exists():
            self.stdout.write(self.style.WARNING('Los datos de prueba ya fueron cargados anteriormente. Abortando.'))
            return

        # 2. Encontrar un período abierto
        periodo_abierto = PeriodoContable.objects.filter(estado=PeriodoContable.EstadoPeriodo.ABIERTO).first()
        
        # Si no hay período abierto, crear uno
        if not periodo_abierto:
            self.stdout.write(self.style.WARNING('No se encontró período abierto. Creando período inicial...'))
            
            ultimo_periodo = PeriodoContable.objects.order_by('-fecha_fin').first()
            if ultimo_periodo:
                nueva_fecha_inicio = (ultimo_periodo.fecha_fin + timedelta(days=1))
            else:
                # Aseguramos que sea el primero de mes para que sea un mes completo
                nueva_fecha_inicio = date.today().replace(day=1)
            
            nuevo_mes = nueva_fecha_inicio.month
            nuevo_anio = nueva_fecha_inicio.year
            ultimo_dia = monthrange(nuevo_anio, nuevo_mes)[1]
            nueva_fecha_fin = date(nuevo_anio, nuevo_mes, ultimo_dia)
            nombre_periodo = f"{nueva_fecha_inicio.strftime('%B').capitalize()} {nuevo_anio}"

            # Validar si ya existe un período con ese nombre (por si acaso)
            if PeriodoContable.objects.filter(nombre=nombre_periodo).exists():
                 self.stdout.write(self.style.ERROR(f"Ya existe un período llamado '{nombre_periodo}'. Abortando."))
                 return

            periodo_abierto = PeriodoContable.objects.create(
                nombre=nombre_periodo,
                fecha_inicio=nueva_fecha_inicio,
                fecha_fin=nueva_fecha_fin,
                estado=PeriodoContable.EstadoPeriodo.ABIERTO
            )
            self.stdout.write(self.style.SUCCESS(f"Período '{periodo_abierto.nombre}' creado y abierto."))

        # 3. Obtener el usuario (Admin)
        User = get_user_model()
        admin_user = User.objects.filter(username='gerente.admin').first()
        if not admin_user:
            self.stdout.write(self.style.ERROR('Error: No se encontró el usuario admin "gerente.admin". ¿Ejecutaste la migración 0004?'))
            return
            
        # 4. Validar que el período tenga suficientes días para las transacciones
        fecha_base = periodo_abierto.fecha_inicio
        if (periodo_abierto.fecha_fin - fecha_base).days < 15:
             self.stdout.write(self.style.ERROR(f"El período de prueba '{periodo_abierto.nombre}' es muy corto. Se necesitan al menos 15 días para los datos de prueba. Abortando."))
             return

        try:
            # 5. Obtener las Cuentas de Prueba (AMPLIADO)
            self.stdout.write(self.style.NOTICE('Obteniendo cuentas del catálogo...'))
            banco = Cuenta.objects.get(codigo="113")
            equipo = Cuenta.objects.get(codigo="152")
            prestamo = Cuenta.objects.get(codigo="251")
            capital = Cuenta.objects.get(codigo="31")
            clientes = Cuenta.objects.get(codigo="121")
            ventas = Cuenta.objects.get(codigo="41")
            iva_debito = Cuenta.objects.get(codigo="221")
            
            # Cuentas nuevas
            alquiler = Cuenta.objects.get(codigo="523")
            iva_credito = Cuenta.objects.get(codigo="141")
            sueldos_gasto = Cuenta.objects.get(codigo="521")
            sueldos_pagar = Cuenta.objects.get(codigo="231")
            afp_pagar = Cuenta.objects.get(codigo="232")
            isss_pagar = Cuenta.objects.get(codigo="233")
            intereses_gasto = Cuenta.objects.get(codigo="531")
            self.stdout.write(self.style.SUCCESS('Cuentas obtenidas exitosamente.'))

            # --- 6. Crear Asientos de Prueba ---
            self.stdout.write(self.style.NOTICE('--- Creando Asientos de Prueba ---'))

            # Transacción 1: Apertura (Día 1)
            monto_banco = Decimal('50000.00')
            monto_equipo = Decimal('15000.00')
            monto_prestamo = Decimal('20000.00')
            monto_capital = (monto_banco + monto_equipo) - monto_prestamo # 45,000.00
            
            self._crear_asiento(
                periodo_abierto, fecha_base, "PARTIDA DE APERTURA (DATOS DE PRUEBA)", admin_user,
                [
                    (banco, monto_banco, 0),
                    (equipo, monto_equipo, 0),
                    (prestamo, 0, monto_prestamo),
                    (capital, 0, monto_capital),
                ],
                es_automatico=True
            )

            # Transacción 2: Venta de Software (Día 3)
            monto_venta_neta = Decimal('10000.00') # Venta más grande
            monto_iva_venta = (monto_venta_neta * Decimal('0.13')).quantize(Decimal('0.01'))
            monto_total_cliente = monto_venta_neta + monto_iva_venta
            
            self._crear_asiento(
                periodo_abierto, fecha_base + timedelta(days=2), "Venta de licencia de software a Cliente X (Crédito)", admin_user,
                [
                    (clientes, monto_total_cliente, 0),
                    (ventas, 0, monto_venta_neta),
                    (iva_debito, 0, monto_iva_venta),
                ]
            )

            # Transacción 3: Pago de Gasto (Alquiler) (Día 5)
            monto_alquiler = Decimal('500.00')
            monto_iva_alquiler = (monto_alquiler * Decimal('0.13')).quantize(Decimal('0.01'))
            monto_total_alquiler = monto_alquiler + monto_iva_alquiler
            
            self._crear_asiento(
                periodo_abierto, fecha_base + timedelta(days=4), "Pago de alquiler de oficina (Efectivo)", admin_user,
                [
                    (alquiler, monto_alquiler, 0),
                    (iva_credito, monto_iva_alquiler, 0),
                    (banco, 0, monto_total_alquiler),
                ]
            )

            # Transacción 4: Cobro a Cliente (Día 7)
            self._crear_asiento(
                periodo_abierto, fecha_base + timedelta(days=6), "Cobro de factura a Cliente X", admin_user,
                [
                    (banco, monto_total_cliente, 0),
                    (clientes, 0, monto_total_cliente),
                ]
            )

            # Transacción 5: Compra de Activo (Día 10)
            monto_laptop = Decimal('1000.00')
            monto_iva_laptop = (monto_laptop * Decimal('0.13')).quantize(Decimal('0.01'))
            monto_total_laptop = monto_laptop + monto_iva_laptop
            
            self._crear_asiento(
                periodo_abierto, fecha_base + timedelta(days=9), "Compra de laptop (Efectivo)", admin_user,
                [
                    (equipo, monto_laptop, 0),
                    (iva_credito, monto_iva_laptop, 0),
                    (banco, 0, monto_total_laptop),
                ]
            )

            # Transacción 6: Provisión de Salarios (Día 15)
            gasto_sueldos = Decimal('2000.00')
            # Usamos valores estándar de SV (simplificados)
            monto_afp = (gasto_sueldos * Decimal('0.0725')).quantize(Decimal('0.01'))
            monto_isss = (gasto_sueldos * Decimal('0.03')).quantize(Decimal('0.01'))
            liquido_pagar = gasto_sueldos - monto_afp - monto_isss
            
            self._crear_asiento(
                periodo_abierto, fecha_base + timedelta(days=14), "Provisión de planilla quincenal", admin_user,
                [
                    (sueldos_gasto, gasto_sueldos, 0),
                    (afp_pagar, 0, monto_afp),
                    (isss_pagar, 0, monto_isss),
                    (sueldos_pagar, 0, liquido_pagar),
                ]
            )

            # Transacción 7: Pago de Salarios (Día 15)
            self._crear_asiento(
                periodo_abierto, fecha_base + timedelta(days=14), "Pago de planilla quincenal", admin_user,
                [
                    (sueldos_pagar, liquido_pagar, 0),
                    (banco, 0, liquido_pagar),
                ]
            )

            # Transacción 8: Abono a Préstamo (Día 15)
            monto_interes = Decimal('200.00')
            monto_principal = Decimal('800.00')
            monto_total_pago = monto_interes + monto_principal
            
            self._crear_asiento(
                periodo_abierto, fecha_base + timedelta(days=14), "Pago de cuota de préstamo bancario", admin_user,
                [
                    (prestamo, monto_principal, 0),
                    (intereses_gasto, monto_interes, 0),
                    (banco, 0, monto_total_pago),
                ]
            )

            self.stdout.write(self.style.SUCCESS('\n--- ¡Datos de prueba ampliados cargados exitosamente! ---'))

        except Cuenta.DoesNotExist as e:
            self.stdout.write(self.style.ERROR(f"\nError: No se encontró una cuenta esencial en el catálogo ({e}). No se cargaron datos."))
            raise e # Detener la transacción atómica
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\nOcurrió un error inesperado: {e}"))
            raise e # Detener la transacción atómica