import re
from datetime import date

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

ESTADOS_BLOQUEANTES = ["PENDIENTE", "CONFIRMADA", "ACTIVA"]  # ocupan la habitación en el calendario


def validar_rut(valor):
    """Valida RUT chileno con módulo 11."""
    limpio = valor.replace(".", "").replace("-", "").upper()
    if len(limpio) < 8 or not limpio[:-1].isdigit():
        raise ValidationError("RUT inválido.")
    cuerpo, dv = limpio[:-1], limpio[-1]
    suma, mult = 0, 2
    for d in reversed(cuerpo):
        suma += int(d) * mult
        mult = 2 if mult == 7 else mult + 1
    r = 11 - suma % 11
    esperado = "0" if r == 11 else "K" if r == 10 else str(r)
    if dv != esperado:
        raise ValidationError("RUT inválido.")


def validar_telefono(valor):
    """Celular chileno: +56 9 XXXX XXXX (los espacios son opcionales)."""
    if not re.fullmatch(r"\+56 ?9 ?\d{4} ?\d{4}", valor.strip()):
        raise ValidationError("Teléfono inválido. Usa el formato +56 9 1234 5678.")


def normalizar_rut(valor):
    limpio = valor.replace(".", "").replace("-", "").upper()
    return f"{limpio[:-1]}-{limpio[-1]}"


class HabitacionQuerySet(models.QuerySet):
    def disponibles(self, ingreso, salida, personas=1, tipo=None):
        """Habitaciones libres en [ingreso, salida): sin cruces con reservas vigentes."""
        ocupadas = Reserva.objects.filter(
            estado__in=ESTADOS_BLOQUEANTES, fecha_ingreso__lt=salida, fecha_salida__gt=ingreso
        ).values("habitacion_id")
        qs = self.exclude(estado="MANTENCION").exclude(pk__in=ocupadas).filter(capacidad__gte=personas)
        if tipo:
            qs = qs.filter(tipo=tipo)
        return qs.order_by("precio_noche", "numero")


class Habitacion(models.Model):
    TIPOS = [("SIMPLE", "Simple"), ("DOBLE", "Doble"), ("MATRIMONIAL", "Matrimonial"),
             ("FAMILIAR", "Familiar"), ("SUITE", "Suite")]
    ESTADOS = [("DISPONIBLE", "Disponible"), ("OCUPADA", "Ocupada"),
               ("LIMPIEZA", "En limpieza"), ("MANTENCION", "En mantención")]
    ICONOS = {"SIMPLE": "bi-person", "DOBLE": "bi-people", "MATRIMONIAL": "bi-heart",
              "FAMILIAR": "bi-house-heart", "SUITE": "bi-gem"}

    numero = models.CharField(max_length=10, unique=True)
    tipo = models.CharField(max_length=15, choices=TIPOS)
    capacidad = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    precio_noche = models.PositiveIntegerField("precio por noche (CLP)", validators=[MinValueValidator(1)])
    descripcion = models.TextField(blank=True)
    estado = models.CharField(max_length=12, choices=ESTADOS, default="DISPONIBLE")

    objects = HabitacionQuerySet.as_manager()

    class Meta:
        ordering = ["numero"]
        verbose_name_plural = "habitaciones"

    def __str__(self):
        return f"Hab. {self.numero} ({self.get_tipo_display()})"

    @property
    def icono(self):
        return self.ICONOS.get(self.tipo, "bi-door-open")

    @property
    def mensaje_limpieza(self):
        if self.estado == "LIMPIEZA":
            return "Disponible a partir de las 15:30 hrs."
        return ""


class Huesped(models.Model):
    usuario = models.OneToOneField(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="huesped")
    nombre_completo = models.CharField(max_length=120)
    rut = models.CharField(max_length=12, unique=True, validators=[validar_rut])
    correo = models.EmailField()
    telefono = models.CharField(max_length=16, validators=[validar_telefono])
    consentimiento = models.DateTimeField("consentimiento de datos", null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "huéspedes"
        ordering = ["nombre_completo"]

    def __str__(self):
        return f"{self.nombre_completo} ({self.rut})"


class Reserva(models.Model):
    ESTADOS = [("PENDIENTE", "Pendiente"), ("CONFIRMADA", "Confirmada"), ("ACTIVA", "Activa (check-in)"),
               ("FINALIZADA", "Finalizada"), ("CANCELADA", "Cancelada")]

    habitacion = models.ForeignKey(Habitacion, on_delete=models.PROTECT, related_name="reservas")
    huesped = models.ForeignKey(Huesped, on_delete=models.PROTECT, related_name="reservas")
    fecha_ingreso = models.DateField()
    fecha_salida = models.DateField()
    personas = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    estado = models.CharField(max_length=12, choices=ESTADOS, default="PENDIENTE")
    monto_total = models.PositiveIntegerField(default=0)
    paquete = models.UUIDField(null=True, blank=True, editable=False, db_index=True)  # une las 2 reservas de un combo
    creada = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creada"]
        indexes = [models.Index(fields=["habitacion", "fecha_ingreso", "fecha_salida"])]

    def __str__(self):
        return f"Reserva #{self.pk} - {self.habitacion} - {self.fecha_ingreso}→{self.fecha_salida}"

    @property
    def noches(self):
        return (self.fecha_salida - self.fecha_ingreso).days

    def clean(self):
        if not (self.fecha_ingreso and self.fecha_salida and self.habitacion_id):
            return
        if self.fecha_salida <= self.fecha_ingreso:
            raise ValidationError("La fecha de salida debe ser posterior a la de ingreso.")
        if self.personas > self.habitacion.capacidad:
            raise ValidationError(f"La habitación admite máximo {self.habitacion.capacidad} personas.")
        if self.estado in ESTADOS_BLOQUEANTES:
            cruces = Reserva.objects.filter(
                habitacion_id=self.habitacion_id, estado__in=ESTADOS_BLOQUEANTES,
                fecha_ingreso__lt=self.fecha_salida, fecha_salida__gt=self.fecha_ingreso,
            ).exclude(pk=self.pk)
            if cruces.exists():
                raise ValidationError("La habitación ya está reservada en esas fechas.")

    def save(self, *args, **kwargs):
        if self._state.adding:
            self.monto_total = self.noches * self.habitacion.precio_noche
        super().save(*args, **kwargs)

    # --- Transiciones del diagrama de estados ---
    def _exigir(self, desde, accion):
        if self.estado not in desde:
            raise ValidationError(f"No se puede {accion} una reserva en estado «{self.get_estado_display()}».")

    def confirmar(self):
        self._exigir(["PENDIENTE"], "confirmar")
        self.estado = "CONFIRMADA"
        self.save(update_fields=["estado"])

    def cancelar(self):
        self._exigir(["PENDIENTE", "CONFIRMADA"], "cancelar")
        self.estado = "CANCELADA"  # libera el calendario de inmediato
        self.save(update_fields=["estado"])
        if self.paquete:  # si es un combo, se cancela completo
            for otra in Reserva.objects.filter(paquete=self.paquete, estado__in=["PENDIENTE", "CONFIRMADA"]).exclude(pk=self.pk):
                otra.estado = "CANCELADA"
                otra.save(update_fields=["estado"])

    def check_in(self):
        self._exigir(["CONFIRMADA"], "hacer check-in de")
        if self.fecha_ingreso > date.today():
            raise ValidationError("Aún no llega la fecha de ingreso.")
        if self.habitacion.estado != "DISPONIBLE":
            raise ValidationError(f"La habitación está «{self.habitacion.get_estado_display()}».")
        self.estado = "ACTIVA"
        self.save(update_fields=["estado"])
        self.habitacion.estado = "OCUPADA"
        self.habitacion.save(update_fields=["estado"])

    def check_out(self):
        self._exigir(["ACTIVA"], "hacer check-out de")
        self.estado = "FINALIZADA"
        self.save(update_fields=["estado"])
        self.habitacion.estado = "LIMPIEZA"
        self.habitacion.save(update_fields=["estado"])


class Notificacion(models.Model):
    huesped = models.ForeignKey(Huesped, on_delete=models.CASCADE, related_name='notificaciones')
    mensaje = models.CharField(max_length=255)
    leida = models.BooleanField(default=False)
    creada = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-creada']

    def __str__(self):
        return f"Aviso para {self.huesped.nombre_completo}: {self.mensaje}"