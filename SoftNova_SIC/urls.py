from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView # Importar RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Incluye todas las URLs de la app 'contabilidad'
    # bajo el prefijo 'contabilidad/'
    path('contabilidad/', include('contabilidad.urls')),
    
    # Redirección de la raíz (http://.../)
    # al dashboard de contabilidad
    path('', RedirectView.as_view(url='/contabilidad/', permanent=True)),
]