from django import template
from django.contrib.auth.models import Group 

register = template.Library() 

@register.filter(name='has_group') 
def has_group(user, group_name):
    """
    Verifica si un usuario (autenticado) pertenece a un grupo específico.
    Uso en plantilla: {% if user|has_group:"Administrador" %}
    """
    # Comprobar si el usuario está autenticado antes de consultar
    if user.is_authenticated:
        return user.groups.filter(name=group_name).exists()
    return False

