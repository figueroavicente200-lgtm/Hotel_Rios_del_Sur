from django.contrib import admin
from .models import Habitacion, Huesped, Notificacion, Reserva


@admin.register(Habitacion)
class HabitacionAdmin(admin.ModelAdmin):
    list_display = ('numero', 'tipo', 'capacidad', 'precio_noche', 'estado')
    list_filter = ('tipo', 'estado')
    search_fields = ('numero',)


@admin.register(Huesped)
class HuespedAdmin(admin.ModelAdmin):
    list_display = ('nombre_completo', 'rut', 'correo', 'telefono', 'usuario', 'consentimiento')
    readonly_fields = ('consentimiento', 'creado')
    search_fields = ('nombre_completo', 'rut', 'correo')


@admin.register(Reserva)
class ReservaAdmin(admin.ModelAdmin):
    list_display = ('id', 'habitacion', 'huesped', 'fecha_ingreso', 'fecha_salida', 'estado', 'monto_total')
    list_filter = ('estado', 'fecha_ingreso')
    search_fields = ('huesped__nombre_completo', 'habitacion__numero')

    def save_model(self, request, obj, form, change):
        if change and 'estado' in form.changed_data:
            Notificacion.objects.create(
                huesped=obj.huesped,
                mensaje=f"Administración actualizó el estado de tu reserva #{obj.pk} (Hab. {obj.habitacion.numero}) a: {obj.get_estado_display()}."
            )
        super().save_model(request, obj, form, change)


@admin.register(Notificacion)
class NotificacionAdmin(admin.ModelAdmin):
    list_display = ('huesped', 'mensaje', 'leida', 'creada')
    list_filter = ('leida', 'creada')