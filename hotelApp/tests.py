from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import Habitacion, Huesped, Reserva, validar_rut
from .services import crear_reserva

HOY = date.today()
d = lambda n: HOY + timedelta(days=n)


class BaseTest(TestCase):
    def setUp(self):
        self.hab = Habitacion.objects.create(numero="101", tipo="DOBLE", capacidad=2, precio_noche=40000)
        self.user = User.objects.create_user("cliente", password="Clave12345!")
        self.huesped = Huesped.objects.create(usuario=self.user, nombre_completo="Ana Pérez",
                                              rut="12345678-5", correo="a@a.cl", telefono="+56912345678")


class DisponibilidadTests(BaseTest):
    def test_calcula_monto(self):
        r = crear_reserva(self.hab, self.huesped, d(1), d(4), 2)
        self.assertEqual(r.monto_total, 120000)

    def test_rechaza_cruce_de_fechas(self):
        crear_reserva(self.hab, self.huesped, d(1), d(5), 2)
        with self.assertRaises(ValidationError):
            crear_reserva(self.hab, self.huesped, d(3), d(6), 2)

    def test_permite_fechas_contiguas(self):
        crear_reserva(self.hab, self.huesped, d(1), d(3), 2)
        crear_reserva(self.hab, self.huesped, d(3), d(5), 2)  # sale uno, entra otro el mismo día

    def test_cancelada_libera_calendario(self):
        r = crear_reserva(self.hab, self.huesped, d(1), d(5), 2)
        self.assertEqual(Habitacion.objects.disponibles(d(2), d(3)).count(), 0)
        r.cancelar()
        self.assertEqual(Habitacion.objects.disponibles(d(2), d(3)).count(), 1)

    def test_excluye_capacidad_y_mantencion(self):
        self.assertEqual(Habitacion.objects.disponibles(d(1), d(2), personas=3).count(), 0)
        self.hab.estado = "MANTENCION"; self.hab.save()
        self.assertEqual(Habitacion.objects.disponibles(d(1), d(2)).count(), 0)

    def test_rechaza_fechas_invertidas(self):
        with self.assertRaises(ValidationError):
            crear_reserva(self.hab, self.huesped, d(5), d(2), 1)


class CicloDeVidaTests(BaseTest):
    def test_flujo_completo(self):
        r = crear_reserva(self.hab, self.huesped, HOY, d(2), 2)
        self.assertEqual(r.estado, "PENDIENTE")
        with self.assertRaises(ValidationError):
            r.check_in()  # no se puede sin confirmar
        r.confirmar(); r.check_in()
        self.hab.refresh_from_db()
        self.assertEqual((r.estado, self.hab.estado), ("ACTIVA", "OCUPADA"))
        r.check_out(); self.hab.refresh_from_db()
        self.assertEqual((r.estado, self.hab.estado), ("FINALIZADA", "LIMPIEZA"))

    def test_no_checkin_antes_de_fecha(self):
        r = crear_reserva(self.hab, self.huesped, d(3), d(5), 2); r.confirmar()
        with self.assertRaises(ValidationError):
            r.check_in()


class VistasYSeguridadTests(BaseTest):
    def test_inicio_y_busqueda(self):
        self.assertEqual(self.client.get(reverse("inicio")).status_code, 200)
        r = self.client.get(reverse("inicio"), {"ingreso": d(1), "salida": d(3), "personas": 2})
        self.assertContains(r, "Habitaciones disponibles")

    def test_reservar_exige_login(self):
        r = self.client.get(reverse("reservar", args=[self.hab.pk]))
        self.assertEqual(r.status_code, 302)

    def test_cliente_no_entra_al_panel(self):
        self.client.login(username="cliente", password="Clave12345!")
        self.assertEqual(self.client.get(reverse("panel")).status_code, 302)

    def test_recepcion_entra_al_panel(self):
        User.objects.create_user("recep", password="Clave12345!", is_staff=True)
        self.client.login(username="recep", password="Clave12345!")
        self.assertEqual(self.client.get(reverse("panel")).status_code, 200)

    def test_cliente_no_cancela_reserva_ajena(self):
        r = crear_reserva(self.hab, self.huesped, d(1), d(2), 1)
        User.objects.create_user("otro", password="Clave12345!")
        self.client.login(username="otro", password="Clave12345!")
        self.assertEqual(self.client.post(reverse("cancelar_reserva", args=[r.pk])).status_code, 404)

    def test_registro_crea_huesped(self):
        r = self.client.post(reverse("registro"), {
            "username": "nuevo", "password1": "ClaveSegura#2026", "password2": "ClaveSegura#2026",
            "nombre_completo": "Luis Soto", "rut": "11.111.111-1", "correo": "l@l.cl", "telefono": "+56987654321", "acepta_datos": "on"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Huesped.objects.filter(rut="11111111-1").exists())

    def test_rut_invalido(self):
        with self.assertRaises(ValidationError):
            validar_rut("12345678-9")


# ---------- Pruebas agregadas (combos, roles, login, consentimiento, teléfono) ----------
from django.core.cache import cache
from django.core.management import call_command

from .models import validar_telefono
from .services import crear_paquete, repartir_personas


class PaqueteCombinadoTests(BaseTest):
    def setUp(self):
        super().setUp()
        self.familiar = Habitacion.objects.create(numero="301", tipo="FAMILIAR", capacidad=4, precio_noche=85000)
        self.simple = Habitacion.objects.create(numero="102", tipo="SIMPLE", capacidad=1, precio_noche=35000)

    def test_reparte_primero_en_la_mayor_capacidad(self):
        (h1, p1), (h2, p2) = repartir_personas(5, self.simple, self.familiar)
        self.assertEqual((h1, p1, h2, p2), (self.familiar, 4, self.simple, 1))

    def test_paquete_de_5_personas_se_crea_completo(self):
        r1, r2 = crear_paquete(self.familiar, self.simple, self.huesped, d(1), d(3), 5)
        self.assertEqual(r1.paquete, r2.paquete)
        self.assertEqual(r1.personas + r2.personas, 5)

    def test_paquete_es_todo_o_nada(self):
        crear_reserva(self.simple, self.huesped, d(1), d(3), 1)  # la simple ya está ocupada
        with self.assertRaises(ValidationError):
            crear_paquete(self.familiar, self.simple, self.huesped, d(1), d(3), 5)
        self.assertEqual(Reserva.objects.filter(habitacion=self.familiar).count(), 0)

    def test_grupo_mayor_a_la_capacidad_total_se_rechaza(self):
        with self.assertRaises(ValidationError):
            crear_paquete(self.familiar, self.simple, self.huesped, d(1), d(3), 6)

    def test_cancelar_una_cancela_el_paquete(self):
        r1, r2 = crear_paquete(self.familiar, self.simple, self.huesped, d(1), d(3), 5)
        r1.cancelar(); r2.refresh_from_db()
        self.assertEqual(r2.estado, "CANCELADA")

    def test_reserva_del_combo_desde_la_vista(self):
        self.client.login(username="cliente", password="Clave12345!")
        url = reverse("reservar", args=[self.familiar.pk]) + f"?hab2={self.simple.pk}"
        r = self.client.post(url, {"ingreso": d(1), "salida": d(3), "personas": 5})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Reserva.objects.filter(huesped=self.huesped).count(), 2)


class PanelRecepcionTests(BaseTest):
    def setUp(self):
        super().setUp()
        User.objects.create_user("recep", password="Clave12345!", is_staff=True)

    def test_checkin_y_checkout_por_vista(self):
        r = crear_reserva(self.hab, self.huesped, HOY, d(2), 2); r.confirmar()
        self.client.login(username="recep", password="Clave12345!")
        self.client.post(reverse("accion_reserva", args=[r.pk, "checkin"]))
        r.refresh_from_db(); self.hab.refresh_from_db()
        self.assertEqual((r.estado, self.hab.estado), ("ACTIVA", "OCUPADA"))
        self.client.post(reverse("accion_reserva", args=[r.pk, "checkout"]))
        r.refresh_from_db(); self.hab.refresh_from_db()
        self.assertEqual((r.estado, self.hab.estado), ("FINALIZADA", "LIMPIEZA"))
        self.assertIn("15:30", self.hab.mensaje_limpieza)

    def test_cliente_no_puede_hacer_checkin(self):
        r = crear_reserva(self.hab, self.huesped, HOY, d(2), 2); r.confirmar()
        self.client.login(username="cliente", password="Clave12345!")
        self.client.post(reverse("accion_reserva", args=[r.pk, "checkin"]))
        r.refresh_from_db()
        self.assertEqual(r.estado, "CONFIRMADA")

    def test_get_no_ejecuta_acciones(self):
        r = crear_reserva(self.hab, self.huesped, HOY, d(2), 2)
        self.client.login(username="recep", password="Clave12345!")
        self.assertEqual(self.client.get(reverse("accion_reserva", args=[r.pk, "confirmar"])).status_code, 405)

    def test_cliente_cancela_su_propia_reserva(self):
        r = crear_reserva(self.hab, self.huesped, d(1), d(2), 1)
        self.client.login(username="cliente", password="Clave12345!")
        self.client.post(reverse("cancelar_reserva", args=[r.pk]))
        r.refresh_from_db()
        self.assertEqual(r.estado, "CANCELADA")


class SeguridadExtraTests(BaseTest):
    def setUp(self):
        super().setUp()
        cache.clear()

    def test_pagina_de_login_carga(self):
        self.assertEqual(self.client.get(reverse("login")).status_code, 200)

    def test_login_se_bloquea_tras_5_intentos(self):
        for _ in range(5):
            self.client.post(reverse("login"), {"username": "cliente", "password": "mala"})
        r = self.client.post(reverse("login"), {"username": "cliente", "password": "Clave12345!"})
        self.assertContains(r, "Demasiados intentos")

    def test_login_correcto_funciona(self):
        r = self.client.post(reverse("login"), {"username": "cliente", "password": "Clave12345!"})
        self.assertEqual(r.status_code, 302)

    def test_registro_exige_consentimiento(self):
        datos = {"username": "nuevo", "password1": "ClaveSegura#2026", "password2": "ClaveSegura#2026",
                 "nombre_completo": "Luis Soto", "rut": "11.111.111-1", "correo": "l@l.cl", "telefono": "+56 9 8765 4321"}
        self.assertEqual(self.client.post(reverse("registro"), datos).status_code, 200)  # sin casilla: no registra
        self.assertFalse(Huesped.objects.filter(rut="11111111-1").exists())
        datos["acepta_datos"] = "on"
        self.assertEqual(self.client.post(reverse("registro"), datos).status_code, 302)
        self.assertIsNotNone(Huesped.objects.get(rut="11111111-1").consentimiento)

    def test_telefono_chileno(self):
        validar_telefono("+56 9 1234 5678"); validar_telefono("+56912345678")
        for malo in ["12345678", "+56 2 1234 5678", "+56 9 123"]:
            with self.assertRaises(ValidationError):
                validar_telefono(malo)


class DemoTests(TestCase):
    def test_cargar_demo_permite_checkin_hoy(self):
        call_command("cargar_demo", verbosity=0)
        r = Reserva.objects.get(estado="CONFIRMADA")
        r.check_in()
        self.assertEqual(r.estado, "ACTIVA")
