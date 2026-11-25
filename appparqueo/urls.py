from django.urls import path
from . import views

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("registrarse/", views.registrarse_cliente, name="registrarse"),
    path("iniciar-sesion/", views.iniciar_sesion_cliente, name="iniciar_sesion"),
    path("cerrar-sesion/", views.cerrar_sesion_cliente, name="cerrar_sesion"),
    path("buscar-parqueadero/", views.buscar_parqueadero, name="buscar_parqueadero"),
    path("mis-vehiculos/", views.mis_vehiculos, name="mis_vehiculos"),
    path("mis-vehiculos/<int:vehiculo_id>/editar/", views.editar_vehiculo, name="editar_vehiculo"),
    path("mis-vehiculos/<int:vehiculo_id>/eliminar/", views.eliminar_vehiculo, name="eliminar_vehiculo"),
    path("mis-reservas/", views.mis_reservas, name="mis_reservas"),
    path("mis-reservas/<int:reserva_id>/eliminar/", views.eliminar_reserva, name="eliminar_reserva"),
    path("mis-reservas/<int:reserva_id>/factura/", views.descargar_factura_reserva, name="descargar_factura_reserva"),
    path("mi-perfil/", views.mi_perfil, name="mi_perfil"),
    path("mi-perfil/eliminar/", views.eliminar_cuenta_cliente, name="eliminar_cuenta_cliente"),

    # Personal (Admin y Empleado)
    path("personal/iniciar-sesion/", views.login_staff, name="login_staff"),
    path("personal/cerrar-sesion/", views.cerrar_sesion_staff, name="cerrar_sesion_staff"),
    path("personal/panel/", views.panel_admin, name="panel_admin"),
    path("personal/espacio/crear/", views.crear_espacio_staff, name="crear_espacio_staff"),
    path("personal/espacio/<int:espacio_id>/estado/", views.cambiar_estado_espacio, name="cambiar_estado_espacio"),
    path("personal/reserva/<int:reserva_id>/accion/", views.accion_reserva_staff, name="accion_reserva_staff"),

    # Empleados (Admin)
    path("personal/empleado/crear/", views.crear_empleado_staff, name="crear_empleado_staff"),
    path("personal/empleado/<int:empleado_id>/editar/", views.editar_empleado_staff, name="editar_empleado_staff"),
    path("personal/empleado/<int:empleado_id>/eliminar/", views.eliminar_empleado_staff, name="eliminar_empleado_staff"),
    path("personal/empleado/<int:empleado_id>/toggle/", views.toggle_empleado_staff, name="toggle_empleado_staff"),

    # Tarifas (Admin)
    path("personal/tarifa/crear/", views.crear_tarifa_staff, name="crear_tarifa_staff"),
    path("personal/tarifa/<int:tarifa_id>/editar/", views.editar_tarifa_staff, name="editar_tarifa_staff"),
    path("personal/tarifa/<int:tarifa_id>/eliminar/", views.eliminar_tarifa_staff, name="eliminar_tarifa_staff"),
]