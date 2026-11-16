from django.core.management.base import BaseCommand

from hotelApp.models import Habitacion

DATOS = [
    ("101", "SIMPLE", 1, 35000, "Cama de 1 plaza, escritorio y vista al jardín."),
    ("102", "SIMPLE", 1, 35000, "Ideal para viajes de trabajo, con Wi-Fi de alta velocidad."),
    ("201", "DOBLE", 2, 52000, "Dos camas individuales, baño privado y calefacción."),
    ("202", "DOBLE", 2, 52000, "Luminosa, con balcón hacia el río Calle-Calle."),
    ("203", "MATRIMONIAL", 2, 62000, "Cama king, tina de hidromasaje y desayuno incluido."),
    ("301", "FAMILIAR", 4, 85000, "Dos ambientes, cuatro camas y kitchenette."),
    ("302", "FAMILIAR", 5, 98000, "Amplia habitación para toda la familia con terraza."),
    ("401", "SUITE", 3, 135000, "Suite con living, vista panorámica al río y jacuzzi."),
]


class Command(BaseCommand):
    help = "Carga habitaciones de ejemplo"

    def handle(self, *args, **opts):
        for num, tipo, cap, precio, desc in DATOS:
            Habitacion.objects.get_or_create(numero=num, defaults=dict(
                tipo=tipo, capacidad=cap, precio_noche=precio, descripcion=desc))
        self.stdout.write(self.style.SUCCESS(f"{Habitacion.objects.count()} habitaciones en el sistema."))
