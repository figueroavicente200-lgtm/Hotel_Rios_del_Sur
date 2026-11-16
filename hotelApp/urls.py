from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("registro/", views.registro, name="registro"),
    path("login/", views.LoginSeguroView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("reservar/<int:pk>/", views.reservar, name="reservar"),
    path("mis-reservas/", views.mis_reservas, name="mis_reservas"),
    path("mis-reservas/<int:pk>/cancelar/", views.cancelar_reserva, name="cancelar_reserva"),
    path("panel/", views.panel, name="panel"),
    path("panel/reserva/<int:pk>/<str:accion>/", views.accion_reserva, name="accion_reserva"),
    path("panel/habitacion/<int:pk>/estado/", views.estado_habitacion, name="estado_habitacion"),
]
