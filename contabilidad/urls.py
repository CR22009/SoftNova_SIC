from django.urls import path
from . import views

app_name = 'contabilidad'  # Namespace para las URLs

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # Registro
    path('asiento/nuevo/', views.registrar_asiento, name='registrar_asiento'),
    
    # Mayor y Balance de Comprobación
    path('reportes/', views.mayor_seleccion, name='mayor_seleccion'),
    path('reportes/mayor/<int:periodo_id>/<int:cuenta_id>/', views.libro_mayor_detalle, name='libro_mayor_detalle'),
    path('reportes/balanza/<int:periodo_id>/', views.balanza_comprobacion, name='balanza_comprobacion'),

   # --- Estado de Resultados ---
    path('estado-resultados/', views.hub_estado_resultados, name='hub_estado_resultados'), # NUEVO: Hub de selección
    path('reportes/estado-resultados/<int:periodo_id>/', views.estado_resultados, name='estado_resultados'), # Página del reporte
    
    # --- Balance General ---
    path('reportes/balance-general/<int:periodo_id>/', views.balance_general, name='balance_general'),

    # Configuración (Vistas Read-Only) ---
    path('configuracion/catalogo/', views.ver_catalogo, name='ver_catalogo'),
    path('configuracion/periodos/', views.ver_periodos, name='ver_periodos'),
]