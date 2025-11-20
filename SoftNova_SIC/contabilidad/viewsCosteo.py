# costeo/viewsCosteo.py
from django.shortcuts import render, redirect
from django.contrib import messages
from .models import SalarioEstimadoMODAnual, CostoIndirectoAnual, CosteoProyecto
from .forms import SalarioFormSet, CifFormSet, CosteoProyectoForm
import json 
from django.db.models import Sum
from decimal import Decimal

def costeo(request):
    """
    Vista de "Pantalla Únca" estilo Excel.
    Maneja 3 formsets/formularios en una sola página.
    """
    
    # --- 1. Lógica de GET (Inicialización por defecto) ---
    salario_formset = SalarioFormSet(
        prefix='salarios',
        queryset=SalarioEstimadoMODAnual.objects.all().order_by('periodo__nombre')
    )
    
    cif_formset = CifFormSet(
        prefix='cif',
        queryset=CostoIndirectoAnual.objects.all().order_by('periodo__nombre')
    )
    
    costeo_form_nuevo = CosteoProyectoForm(prefix='costeo')

    
    # --- 2. Lógica de POST (Guardado) ---
    if request.method == 'POST':
        
        # 1. ¿Se está guardando la tabla de SALARIOS?
        if 'submit_salarios' in request.POST:
            salario_formset = SalarioFormSet(request.POST, prefix='salarios')
            if salario_formset.is_valid():
                salario_formset.save()
                messages.success(request, 'Tabla de Salarios guardada correctamente.')
                return redirect('contabilidad:costeo') # <-- CORREGIDO
            else:
                messages.error(request, 'Error al guardar Salarios. Revisa los campos.')

        # 2. ¿Se está guardando la tabla de CIF?
        elif 'submit_cif' in request.POST:
            cif_formset = CifFormSet(request.POST, prefix='cif')
            if cif_formset.is_valid():
                cif_formset.save()
                messages.success(request, 'Tabla de CIF guardada correctamente.')
                return redirect('contabilidad:costeo') # <-- CORREGIDO
            else:
                messages.error(request, 'Error al guardar CIF. Revisa los campos.')
        
        # 3. ¿Se está guardando un NUEVO PROYECTO de Costeo?
        elif 'submit_costeo' in request.POST:
            # Re-inicializamos los otros forms vacíos
            salario_formset = SalarioFormSet(prefix='salarios', queryset=SalarioEstimadoMODAnual.objects.all().order_by('periodo__nombre'))
            cif_formset = CifFormSet(prefix='cif', queryset=CostoIndirectoAnual.objects.all().order_by('periodo__nombre'))
            
            # Llenamos el form de costeo con los datos del POST
            costeo_form_nuevo = CosteoProyectoForm(request.POST, prefix='costeo')
            
            if costeo_form_nuevo.is_valid():
                try:
                    costeo_form_nuevo.save()
                    messages.success(request, 'Nuevo proyecto de costeo agregado correctamente.')
                    return redirect('contabilidad:costeo') # <-- CORREGIDO
                except Exception as e:
                    messages.error(request, f'Error al guardar el costeo: {e}')
            else:
                messages.error(request, 'Error al agregar el costeo. Revisa los campos.')

    
    # --- 3. Contexto y Renderizado ---
    
    # Lista de costeos ya existentes
    lista_costeos_existentes = CosteoProyecto.objects.all().order_by('-idCosteo')

    # Obtenemos los salarios para que JS pueda hacer cálculos en vivo.
    salarios_qs = SalarioEstimadoMODAnual.objects.all()
    
    # Mapa para el cálculo visual de CIF (Salario Total)
    salarios_map = {
        salario.periodo.id: float(salario.salario)
        for salario in salarios_qs
        if salario.salario is not None and salario.salario > 0
    }
    salarios_json = json.dumps(salarios_map)
    
    # Mapa para el cálculo visual de Costeo (MOD Unitario)
    mod_unitario_map = {
        salario.periodo.id: float(salario.mod_unitario)
        for salario in salarios_qs
        if salario.mod_unitario is not None and salario.mod_unitario > 0
    }
    mod_unitario_json = json.dumps(mod_unitario_map)
    
    
    # Mapa para el cálculo visual de Costeo (Factor Suma / 12)
    factores_agregados = CostoIndirectoAnual.objects.values(
        'periodo_id'
    ).annotate(
        suma_bruta=Sum('factor')
    ).order_by('periodo_id')

    factor_suma_map = {
        item['periodo_id']: float( (item['suma_bruta'] or Decimal(0)) / Decimal(12) )
        for item in factores_agregados
        if item['suma_bruta'] is not None
    }
    factor_suma_json = json.dumps(factor_suma_map)
    
    
    context = {
        'salario_formset': salario_formset, 
        'cif_formset': cif_formset,
        'costeo_form_nuevo': costeo_form_nuevo,
        'lista_costeos_existentes': lista_costeos_existentes,
        'salarios_json': salarios_json,
        'mod_unitario_json': mod_unitario_json, 
        'factor_suma_json': factor_suma_json,
    }
    
    # Renderiza la plantilla
    return render(request, 'contabilidad/costeo.html', context)