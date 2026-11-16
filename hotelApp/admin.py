from django.contrib import admin
from .models import Habitacion, Huesped, Reserva

@admin.register(Habitacion)
class HabitacionAdmin(admin.ModelAdmin):
    list_display = ('numero', 'tipo', 'capacidad', 'precio_noche', 'estado')
    list_filter = ('tipo', 'estado')
    search_fields = ('numero',)

@admin.register(Huesped)
class HuespedAdmin(admin.ModelAdmin):
    list_display = ('nombre_completo', 'rut', 'correo', 'telefono', 'usuario')
    search_fields = ('nombre_completo', 'rut', 'correo')

@admin.register(Reserva)
class ReservaAdmin(admin.ModelAdmin):
    list_display = ('id', 'habitacion', 'huesped', 'fecha_ingreso', 'fecha_salida', 'estado', 'monto_total')
    list_filter = ('estado', 'fecha_ingreso')
    search_fields = ('huesped__nombre_completo', 'habitacion__numero')