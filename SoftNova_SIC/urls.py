from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView # Importar RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Incluye todas las URLs de la app 'contabilidad'
    # bajo el prefijo 'contabilidad/'
    path('contabilidad/', include('contabilidad.urls')),
    
    # Redirección de la raíz (http://.../)
    # AHORA apunta a nuestra vista de login
    path('', RedirectView.as_view(url='/contabilidad/login/', permanent=True)),
]

# --- Manejador de Error 404 ---
# (Solo funciona si DEBUG = False)
handler404 = 'contabilidad.views.custom_404_view'