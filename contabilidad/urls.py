from django.urls import path
from . import views

app_name = 'contabilidad'  # Namespace para las URLs

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    
    path('registro/', views.registrar_asiento, name='registrar_asiento'),
    
    path('mayor/', views.mayor_seleccion, name='mayor_seleccion'),
    
    # Página que muestra la Cuenta T (detalle)
    # Ej: /contabilidad/mayor/1/5/ (Período 1, Cuenta 5)
    path('mayor/<int:periodo_id>/<int:cuenta_id>/', 
         views.libro_mayor_detalle, 
         name='libro_mayor_detalle'),
         
    # Página que muestra el Balance de Comprobación
    # Ej: /contabilidad/balanza/1/ (Período 1)
    path('balanza/<int:periodo_id>/', 
         views.balanza_comprobacion, 
         name='balanza_comprobacion'),
]