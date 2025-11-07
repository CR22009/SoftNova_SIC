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
    help = 'Carga datos de prueba (asiento de apertura y una venta) en el primer período abierto que encuentre.'

    @transaction.atomic
    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.NOTICE('Iniciando carga de datos de prueba...'))

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
                nueva_fecha_inicio = date.today().replace(day=1)
            
            nuevo_mes = nueva_fecha_inicio.month
            nuevo_anio = nueva_fecha_inicio.year
            ultimo_dia = monthrange(nuevo_anio, nuevo_mes)[1]
            nueva_fecha_fin = date(nuevo_anio, nuevo_mes, ultimo_dia)
            nombre_periodo = f"{nueva_fecha_inicio.strftime('%B').capitalize()} {nuevo_anio}"

            periodo_abierto = PeriodoContable.objects.create(
                nombre=nombre_periodo,
                fecha_inicio=nueva_fecha_inicio,
                fecha_fin=nueva_fecha_fin,
                estado=PeriodoContable.EstadoPeriodo.ABIERTO
            )
            self.stdout.write(self.style.SUCCESS(f"Período '{periodo_abierto.nombre}' creado y abierto."))

        # 3. Obtener el usuario (Admin)
        # Usamos uno de los usuarios que crea la migración 0004
        User = get_user_model()
        admin_user = User.objects.filter(username='gerente.admin').first()
        if not admin_user:
            self.stdout.write(self.style.ERROR('Error: No se encontró el usuario admin "gerente.admin". ¿Ejecutaste la migración 0004?'))
            return
            
        fecha_asiento = periodo_abierto.fecha_inicio

        try:
            # 4. Obtener las Cuentas de Prueba
            banco = Cuenta.objects.get(codigo="113")
            equipo = Cuenta.objects.get(codigo="152")
            prestamo = Cuenta.objects.get(codigo="251")
            capital = Cuenta.objects.get(codigo="31")
            clientes = Cuenta.objects.get(codigo="121")
            ventas = Cuenta.objects.get(codigo="41")
            iva_debito = Cuenta.objects.get(codigo="221")

            # 5. Definir montos del Asiento de Apertura
            monto_banco = Decimal('50000.00')
            monto_equipo = Decimal('15000.00')
            monto_prestamo = Decimal('20000.00')
            monto_capital = (monto_banco + monto_equipo) - monto_prestamo # 45,000.00
            
            # --- 6. Crear Asiento de Apertura ---
            self.stdout.write(self.style.NOTICE(f'Creando Asiento de Apertura en período {periodo_abierto.nombre}...'))
            asiento_apertura = AsientoDiario.objects.create(
                periodo=periodo_abierto,
                fecha=fecha_asiento,
                descripcion="PARTIDA DE APERTURA (DATOS DE PRUEBA)",
                creado_por=admin_user,
                es_asiento_automatico=True
            )
            Movimiento.objects.create(asiento=asiento_apertura, cuenta=banco, debe=monto_banco, haber=0)
            Movimiento.objects.create(asiento=asiento_apertura, cuenta=equipo, debe=monto_equipo, haber=0)
            Movimiento.objects.create(asiento=asiento_apertura, cuenta=prestamo, debe=0, haber=monto_prestamo)
            Movimiento.objects.create(asiento=asiento_apertura, cuenta=capital, debe=0, haber=monto_capital)
            self.stdout.write(self.style.SUCCESS('Asiento de Apertura creado.'))

            # --- 7. Crear Asiento de Venta de Ejemplo ---
            monto_venta_neta = Decimal('1000.00')
            monto_iva = (monto_venta_neta * Decimal('0.13')).quantize(Decimal('0.01'))
            monto_total_cliente = monto_venta_neta + monto_iva
            fecha_venta = fecha_asiento + timedelta(days=2)
            
            self.stdout.write(self.style.NOTICE('Creando Asiento de Venta de ejemplo...'))
            asiento_venta = AsientoDiario.objects.create(
                periodo=periodo_abierto,
                fecha=fecha_venta,
                descripcion="Venta de licencia de software a Cliente X (DATOS DE PRUEBA)",
                creado_por=admin_user
            )
            Movimiento.objects.create(asiento=asiento_venta, cuenta=clientes, debe=monto_total_cliente, haber=0)
            Movimiento.objects.create(asiento=asiento_venta, cuenta=ventas, debe=0, haber=monto_venta_neta)
            Movimiento.objects.create(asiento=asiento_venta, cuenta=iva_debito, debe=0, haber=monto_iva)
            self.stdout.write(self.style.SUCCESS('Asiento de Venta creado.'))

            self.stdout.write(self.style.SUCCESS('\n¡Datos de prueba cargados exitosamente!'))

        except Cuenta.DoesNotExist as e:
            self.stdout.write(self.style.ERROR(f"\nError: No se encontró una cuenta esencial en el catálogo ({e}). No se cargaron datos."))
            raise e # Detener la transacción atómica
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\nOcurrió un error inesperado: {e}"))
            raise e # Detener la transacción atómica
