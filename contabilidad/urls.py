from django.urls import path
from . import views

app_name = 'contabilidad'  # Namespace para las URLs

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # Fase 1: Registro
    path('asiento/nuevo/', views.registrar_asiento, name='registrar_asiento'),
    
    # Fase 2: Reportes (Mayor y Balanza)
    path('reportes/', views.mayor_seleccion, name='mayor_seleccion'),
    path('reportes/mayor/<int:periodo_id>/<int:cuenta_id>/', views.libro_mayor_detalle, name='libro_mayor_detalle'),
    path('reportes/balanza/<int:periodo_id>/', views.balanza_comprobacion, name='balanza_comprobacion'),

    # Fase 3: Estados Financieros
    path('reportes/estado-resultados/<int:periodo_id>/', views.estado_resultados, name='estado_resultados'),
    path('reportes/balance-general/<int:periodo_id>/', views.balance_general, name='balance_general'),

    # Configuración (Vistas Read-Only) ---
    path('configuracion/catalogo/', views.ver_catalogo, name='ver_catalogo'),
    path('configuracion/periodos/', views.ver_periodos, name='ver_periodos'),
]