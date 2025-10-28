from django.urls import path
from . import views

app_name = 'contabilidad'  # Namespace para las URLs

urlpatterns = [
    # Ej. http://.../contabilidad/
    path('', views.dashboard, name='dashboard'),
    
    # Ej. http://.../contabilidad/registro/
    path('registro/', views.registrar_asiento, name='registrar_asiento'),
    
    # --- Aquí añadiremos las URLs para Mayor, Balanza, etc. ---
]