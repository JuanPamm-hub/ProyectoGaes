from django.contrib import admin

from .models import (
    Cliente,
    Vehiculo,
    Administrador,
    Parqueadero,
    Espacio,
    Empleado,
    Reserva,
    Tarifa,
    Pago,
    Factura,
    
)


# Registro simple
admin.site.register(Cliente)
admin.site.register(Vehiculo)
admin.site.register(Administrador)
admin.site.register(Parqueadero)
admin.site.register(Espacio)
admin.site.register(Empleado)
admin.site.register(Reserva)
admin.site.register(Tarifa)
admin.site.register(Pago)
admin.site.register(Factura)


# Personalización del panel
admin.site.site_header = "Administración de Parkly"
admin.site.site_title = "Parkly"
admin.site.index_title = "Gestión del parqueadero"