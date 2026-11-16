from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from hotelApp.models import Habitacion, Huesped, Reserva
from hotelApp.services import crear_reserva

CLAVE = "Demo#2026"
HUESPEDES = [  # (usuario, nombre, RUT válido, correo, teléfono)
    ("cliente1", "Camila Rojas", "20123456-5", "camila@demo.cl", "+56 9 1234 5678"),
    ("cliente2", "Diego Muñoz", "19876543-0", "diego@demo.cl", "+56 9 8765 4321"),
    ("cliente3", "Fernanda Soto", "18765432-7", "fernanda@demo.cl", "+56 9 5555 1234"),
]


class Command(BaseCommand):
    help = "Deja datos de demostración listos para HOY (check-in, check-out, limpieza, pendiente)."

    def handle(self, *args, **opts):
        call_command("poblar_datos", verbosity=0)
        hoy = date.today()

        User.objects.filter(username="recepcion").delete()
        User.objects.create_user("recepcion", password=CLAVE, is_staff=True, first_name="Recepción")
        user_camila = User.objects.create_user(username='crojas', password='Demo#2026')
        Huesped.objects.create(
            usuario=user_camila,
            nombre_completo="Camila Rojas",
            rut="15.123.456-7",  # Asegúrate de que cumpla con el Módulo 11
            correo="camila.rojas@mail.com",
            telefono="+56 9 8765 4321"
        )
        user_diego = User.objects.create_user(username='dmunoz', password='Demo#2026')
        Huesped.objects.create(
            usuario=user_diego,
            nombre_completo="Diego Muñoz",
            rut="18.987.654-3",
            correo="diego.munoz@mail.com",
            telefono="+56 9 1234 5678"
        )
        
        huespedes = []
        for usuario, nombre, rut, correo, tel in HUESPEDES:
            u, _ = User.objects.get_or_create(username=usuario, defaults={"email": correo, "first_name": nombre.split()[0]})
            u.set_password(CLAVE); u.save()
            h, _ = Huesped.objects.get_or_create(rut=rut, defaults=dict(
                usuario=u, nombre_completo=nombre, correo=correo, telefono=tel, consentimiento=timezone.now()))
            huespedes.append(h)

        # Se rehacen solo las reservas de los huéspedes demo (no se toca el resto de los datos)
        Reserva.objects.filter(huesped__in=huespedes).delete()
        libres = list(Habitacion.objects.disponibles(hoy - timedelta(days=1), hoy + timedelta(days=4)))
        if len(libres) < 4:
            raise CommandError("Se necesitan al menos 4 habitaciones libres entre hoy y los próximos 4 días.")
        for h in libres[:4]:
            h.estado = "DISPONIBLE"; h.save(update_fields=["estado"])
        a, b, c, d = libres[:4]

        r = crear_reserva(a, huespedes[0], hoy, hoy + timedelta(days=2), 1); r.confirmar()          # para hacer CHECK-IN
        r = crear_reserva(b, huespedes[1], hoy - timedelta(days=1), hoy + timedelta(days=1), 1)     # para hacer CHECK-OUT
        r.confirmar(); r.check_in()
        crear_reserva(c, huespedes[2], hoy + timedelta(days=3), hoy + timedelta(days=5), 1)         # PENDIENTE: confirmar/cancelar
        d.estado = "LIMPIEZA"; d.save(update_fields=["estado"])                                      # muestra aviso 15:30

        self.stdout.write(self.style.SUCCESS("Datos demo listos."))
        self.stdout.write(f"  Recepción: recepcion / {CLAVE}")
        self.stdout.write(f"  Clientes:  cliente1, cliente2, cliente3 / {CLAVE}")
        self.stdout.write(f"  Check-in: reserva #{Reserva.objects.get(habitacion=a, huesped=huespedes[0]).pk} (hab. {a.numero}) | Check-out: hab. {b.numero} | Limpieza: hab. {d.numero}")
