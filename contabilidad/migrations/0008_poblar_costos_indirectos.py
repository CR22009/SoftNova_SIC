# Archivo: contabilidad/migrations/000X_poblar_costos_indirectos_anuales.py

from django.db import migrations
from decimal import Decimal
from datetime import date # <--- 1. IMPORTADO

# --- DATOS A INSERTAR ---
# (Ajustados a los campos de tu modelo CostoIndirectoAnual)
COSTOS_DATA = [
    # (nombre, categoria_str, costo_anual_estimado)
    ('Alquiler o Renta de Oficinas', 'Costo General de Produccion', 18000.00),
    ('Depreciacion y Amortizacion', 'Costos Generales de Produccion', 15000.00),
    ('Mantenimiento Tecnico General', 'Costos Generales de Produccion', 3000.00),
    ('Poliza de Seguros', 'Costos Generales de Produccion', 1000.00),
    ('Costos de Garantia y Post Venta', 'Costos Postventa', 10000.00),
    ('Servicios Basicos', 'Mano de Obra Indirecta', 6000.00),
    ('Sueldos del Personal Indirecto', 'Materiales y Suministros Indirectos', 292212.03),
    ('Costo de Servidores y Cloud Computing', 'Materiales y Suministros Indirectos', 20000.00),
    ('Licencias y Herramientas Comunes', 'Materiales y Suministros Indirectos', 4999.94),
    ('Suministro de Oficina y Limpieza', 'Materiales y Suministros Indirectos', 1999.92),
]

# --- MAPEO DE CATEGORÍAS ---
# Mapea el texto de tu SQL a los 'choices' de tu modelo
CATEGORIA_MAP = {
    'Costo General de Produccion': 'PRODUCCION',
    'Costos Generales de Produccion': 'PRODUCCION', 
    'Costos Postventa': 'POSTVENTA',
    'Mano de Obra Indirecta': 'MANO_OBRA_IND',
    'Materiales y Suministros Indirectos': 'MATERIALES_SUM',
}

def poblar_costos_indirectos(apps, schema_editor):
    """
    Función 'up': Inserta los costos indirectos anuales para 'Periodo1'.
    Si 'Periodo1' no existe, lo crea automáticamente.
    """
    # Obtenemos los modelos históricos
    CostoIndirectoAnual = apps.get_model('contabilidad', 'CostoIndirectoAnual')
    PeriodoContable = apps.get_model('contabilidad', 'PeriodoContable')
    SalarioEstimadoMODAnual = apps.get_model('contabilidad', 'SalarioEstimadoMODAnual')

    # --- 2. CAMBIO DE 'get' A 'get_or_create' ---
    # Intenta obtener 'Periodo1'. Si no existe, lo crea usando 'defaults'.
    periodo_1, creado = PeriodoContable.objects.get_or_create(
        nombre='Periodo 1',
        defaults={
            'fecha_inicio': date(2025, 11, 1), 
            'fecha_fin': date(2025, 11, 30),
        }
    )
    
    # Si 'creado' es True, imprimirá un mensaje en la consola
    if creado:
        print(" -> Se creó el PeriodoContable 'Periodo1'.")
        
    salario_obj, salario_creado = SalarioEstimadoMODAnual.objects.get_or_create(
        periodo=periodo_1,
        defaults={
            'descripcion': 'Salario MOD (Default Migración)',
            'salario': Decimal('750.00')
        }
    )
    if salario_creado:
        print(f" -> Creado Salario MOD para 'Periodo 1' con valor {salario_obj.salario}.")
    else:
        print(f" -> Salario MOD para 'Periodo 1' ya existía (Valor: {salario_obj.salario}).")

    # Preparamos los objetos para bulk_create
    costos_para_crear = []
    for nombre, categoria_str, costo_estimado in COSTOS_DATA:
        valor_categoria = CATEGORIA_MAP.get(categoria_str)
        
        if not valor_categoria:
            raise ValueError(f"La categoría '{categoria_str}' no tiene un mapeo definido.")

        costos_para_crear.append(
            CostoIndirectoAnual(
                periodo=periodo_1,
                nombre=nombre,
                categoria=valor_categoria,
                costo_anual_estimado=Decimal(costo_estimado)
            )
        )
    
    CostoIndirectoAnual.objects.bulk_create(costos_para_crear)


def deshacer_poblar_costos(apps, schema_editor):
    """
    Función 'down': Borra los datos que insertamos si revertimos la migración.
    NOTA: Esto NO borrará el 'Periodo1', incluso si esta migración lo creó.
    Es más seguro dejar el período que arriesgarse a borrar datos.
    """
    CostoIndirectoAnual = apps.get_model('contabilidad', 'CostoIndirectoAnual')
    PeriodoContable = apps.get_model('contabilidad', 'PeriodoContable')
    SalarioEstimadoMODAnual = apps.get_model('contabilidad', 'SalarioEstimadoMODAnual')

    try:
        periodo_1 = PeriodoContable.objects.get(nombre='Periodo1')
    except PeriodoContable.DoesNotExist:
        return

    nombres_costos = [item[0] for item in COSTOS_DATA]
    
    CostoIndirectoAnual.objects.filter(
        periodo=periodo_1,
        nombre__in=nombres_costos
    ).delete()
    
    SalarioEstimadoMODAnual.objects.filter(periodo=periodo_1).delete()


class Migration(migrations.Migration):

    dependencies = [
        # Asegúrate que la migración anterior esté aquí
        ('contabilidad', '0007_salarioestimadomodanual_costeoproyecto_and_more'), 
    ]

    operations = [
        migrations.RunPython(poblar_costos_indirectos, deshacer_poblar_costos),
    ]