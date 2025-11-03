from django.urls import path
from . import views

app_name = 'contabilidad'  # Namespace para las URLs

urlpatterns = [
    # --- Autenticación (NUEVO) ---
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # Registro
    path('asiento/nuevo/', views.registrar_asiento, name='registrar_asiento'),
    
    # Mayor y Balance de Comprobación
    path('reportes/', views.mayor_seleccion, name='mayor_seleccion'),
    path('reportes/mayor/<int:periodo_id>/<int:cuenta_id>/', views.libro_mayor_detalle, name='libro_mayor_detalle'),
    path('reportes/balanza/<int:periodo_id>/', views.balanza_comprobacion, name='balanza_comprobacion'),

   # --- Estado de Resultados ---
    path('estado-resultados/', views.hub_estado_resultados, name='hub_estado_resultados'), 
    path('reportes/estado-resultados/<int:periodo_id>/', views.estado_resultados, name='estado_resultados'), 
    
    # --- Balance General ---
    path('balance-general/', views.hub_balance_general, name='hub_balance_general'), 
    path('reportes/balance-general/<int:periodo_id>/', views.balance_general, name='balance_general'),
    
    #--- Flujo de Efectivo ---
    path('flujo-efectivo/', views.hub_flujo_efectivo, name='hub_flujo_efectivo'),
    path('reportes/flujo-efectivo/<int:periodo_id>/', views.flujo_efectivo, name='flujo_efectivo'),
    
    #--- Estado de Patrimonio ---
    path('estado-patrimonio/', views.hub_estado_patrimonio, name='hub_estado_patrimonio'),
    path('reportes/estado-patrimonio/<int:periodo_id>/', views.estado_patrimonio, name='estado_patrimonio'),

    # Configuración (Vistas Read-Only) ---
    path('configuracion/catalogo/', views.ver_catalogo, name='ver_catalogo'),
    
    # --- MODIFICADO: Nueva vista de Gestión de Períodos ---
    path('configuracion/periodos/', views.gestionar_periodos, name='gestionar_periodos'),
    
    # --- NUEVA RUTA: Acción de Cerrar Período ---
    path('configuracion/periodos/cerrar/<int:periodo_id>/', views.cerrar_periodo, name='cerrar_periodo'),
]

