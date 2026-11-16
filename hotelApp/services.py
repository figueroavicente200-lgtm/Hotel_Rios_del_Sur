from django.core.exceptions import ValidationError
from django.db import transaction
import uuid

from .models import Habitacion, Reserva


def crear_reserva(habitacion, huesped, ingreso, salida, personas, paquete=None):
    """Crea la reserva bloqueando la habitación para evitar reservas duplicadas por concurrencia."""
    with transaction.atomic():
        habitacion = Habitacion.objects.select_for_update().get(pk=habitacion.pk)
        if habitacion.estado == "MANTENCION":
            raise ValidationError("La habitación no está disponible.")
        reserva = Reserva(habitacion=habitacion, huesped=huesped, fecha_ingreso=ingreso,
                          fecha_salida=salida, personas=personas, paquete=paquete)
        reserva.full_clean()
        reserva.save()
    return reserva


def repartir_personas(total, hab_a, hab_b):
    """Reparte el grupo entre 2 habitaciones: llena primero la de mayor capacidad y deja >= 1 persona en la otra."""
    mayor, menor = sorted([hab_a, hab_b], key=lambda h: h.capacidad, reverse=True)
    if total < 2 or total > mayor.capacidad + menor.capacidad:
        raise ValidationError("El grupo no cabe en el paquete de habitaciones elegido.")
    en_menor = max(1, total - mayor.capacidad)
    return (mayor, total - en_menor), (menor, en_menor)


def crear_paquete(hab_a, hab_b, huesped, ingreso, salida, personas):
    """Reserva 2 habitaciones juntas (todo o nada) para un grupo grande."""
    if hab_a.pk == hab_b.pk:
        raise ValidationError("Debes elegir dos habitaciones distintas.")
    (h1, p1), (h2, p2) = repartir_personas(personas, hab_a, hab_b)
    codigo = uuid.uuid4()
    with transaction.atomic():
        r1 = crear_reserva(h1, huesped, ingreso, salida, p1, paquete=codigo)
        r2 = crear_reserva(h2, huesped, ingreso, salida, p2, paquete=codigo)
    return r1, r2
