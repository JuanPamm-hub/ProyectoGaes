from django.urls import path
from . import views

urlpatterns = [
    path('', views.inicio, name='inicio'),
    path("iniciar-sesion/", views.iniciar_sesion_cliente, name="iniciar_sesion"),
]