from datetime import date

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import BusquedaForm, RegistroForm, ReservaForm
from .models import ESTADOS_BLOQUEANTES, Habitacion, Notificacion, Reserva
from .services import crear_paquete, crear_reserva

es_recepcion = user_passes_test(lambda u: u.is_active and u.is_staff, login_url="login")


class LoginSeguroView(LoginView):
    """Login con bloqueo temporal tras 5 intentos fallidos (mitiga fuerza bruta)."""
    template_name = "registro/login.html"
    MAX_INTENTOS = 5
    BLOQUEO_SEG = 300

    def _clave(self):
        usuario = self.request.POST.get("username", "").strip().lower()
        return f"login_fallos:{self.request.META.get('REMOTE_ADDR', '')}:{usuario}"

    def post(self, request, *args, **kwargs):
        if cache.get(self._clave(), 0) >= self.MAX_INTENTOS:
            form = self.get_form()
            form.add_error(None, "Demasiados intentos fallidos. Espera 5 minutos e inténtalo de nuevo.")
            return super().form_invalid(form)
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        cache.set(self._clave(), cache.get(self._clave(), 0) + 1, self.BLOQUEO_SEG)
        return super().form_invalid(form)

    def form_valid(self, form):
        cache.delete(self._clave())
        return super().form_valid(form)


def inicio(request):
    form = BusquedaForm(request.GET or None)
    habitaciones, paquetes, buscado, noches, qs = None, [], False, 0, ""
    if request.GET and form.is_valid():
        d = form.cleaned_data
        noches = (d["salida"] - d["ingreso"]).days
        personas_buscadas = d["personas"]
        tipo_solicitado = d["tipo"] or None

        habitaciones = list(Habitacion.objects.disponibles(d["ingreso"], d["salida"], personas_buscadas, tipo_solicitado))
        for h in habitaciones:
            h.total = h.precio_noche * noches

        if not habitaciones and not tipo_solicitado and personas_buscadas > 4:
            libres_en_fechas = list(Habitacion.objects.disponibles(d["ingreso"], d["salida"], personas=1, tipo=None))
            for i in range(len(libres_en_fechas)):
                for j in range(i + 1, len(libres_en_fechas)):
                    h1 = libres_en_fechas[i]
                    h2 = libres_en_fechas[j]
                    if (h1.capacidad + h2.capacidad) >= personas_buscadas:
                        class PaqueteCombinado:
                            pass
                        p = PaqueteCombinado()
                        p.habitacion_1 = h1
                        p.habitacion_2 = h2
                        p.capacidad_total = h1.capacidad + h2.capacidad
                        p.total = (h1.precio_noche + h2.precio_noche) * noches
                        paquetes.append(p)

        buscado = True
        qs = f"ingreso={d['ingreso']:%Y-%m-%d}&salida={d['salida']:%Y-%m-%d}&personas={d['personas']}"
    elif not request.GET:
        habitaciones = Habitacion.objects.exclude(estado="MANTENCION").order_by("precio_noche")
        
    return render(request, "hotel/inicio.html", {
        "form": form, 
        "habitaciones": habitaciones, 
        "paquetes": paquetes,
        "buscado": buscado, 
        "noches": noches, 
        "qs": qs
    })


def registro(request):
    if request.user.is_authenticated:
        return redirect("inicio")
    form = RegistroForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "¡Cuenta creada! Ya puedes reservar.")
        return redirect("inicio")
    return render(request, "hotel/registro.html", {"form": form})


@login_required
def reservar(request, pk):
    habitacion = get_object_or_404(Habitacion, pk=pk)
    hab2_pk = request.GET.get('hab2', '')
    habitacion_2 = get_object_or_404(Habitacion, pk=int(hab2_pk)) if hab2_pk.isdigit() else None
    
    huesped = getattr(request.user, "huesped", None)
    if huesped is None:
        messages.error(request, "Tu usuario no tiene ficha de huésped. Usa una cuenta de cliente.")
        return redirect("inicio")
        
    initial = {
        'ingreso': request.GET.get('ingreso') or request.POST.get('ingreso'),
        'salida': request.GET.get('salida') or request.POST.get('salida'),
        'personas': request.GET.get('personas') or request.POST.get('personas')
    }
    initial = {k: v for k, v in initial.items() if v}

    form = ReservaForm(request.POST or None, initial=initial)
    total = None
    precio_por_noche = habitacion.precio_noche + (habitacion_2.precio_noche if habitacion_2 else 0)

    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            with transaction.atomic():
                if habitacion_2:
                    reserva_1, _ = crear_paquete(habitacion, habitacion_2, huesped, d["ingreso"], d["salida"], d["personas"])
                else:
                    reserva_1 = crear_reserva(habitacion, huesped, d["ingreso"], d["salida"], d["personas"])
        except ValidationError as e:
            form.add_error(None, e)
        else:
            msg = "¡Paquete de reservas creado con éxito!" if habitacion_2 else f"Reserva #{reserva_1.pk} creada."
            messages.success(request, f"{msg} Queda pendiente de confirmación por recepción.")
            return redirect("mis_reservas")
            
    if form.is_valid():
        d = form.cleaned_data
        noches = (d["salida"] - d["ingreso"]).days
        total = noches * precio_por_noche
        
    return render(request, "hotel/reservar.html", {
        "form": form, 
        "habitacion": habitacion, 
        "habitacion_2": habitacion_2,
        "total": total
    })


@login_required
def mis_reservas(request):
    huesped = getattr(request.user, "huesped", None)
    reservas = Reserva.objects.filter(huesped=huesped).select_related("habitacion") if huesped else []
    notificaciones = huesped.notificaciones.filter(leida=False) if huesped else []
    return render(request, "hotel/mis_reservas.html", {
        "reservas": reservas,
        "notificaciones": notificaciones
    })


@login_required
@require_POST
def cancelar_reserva(request, pk):
    reserva = get_object_or_404(Reserva, pk=pk, huesped__usuario=request.user)
    try:
        reserva.cancelar()
        messages.success(request, f"Reserva #{reserva.pk} cancelada.")
    except ValidationError as e:
        messages.error(request, e.messages[0])
    return redirect("mis_reservas")


@es_recepcion
def panel(request):
    filtro = request.GET.get("estado", "vigentes")
    reservas = Reserva.objects.select_related("habitacion", "huesped").order_by("fecha_ingreso")
    if filtro == "vigentes":
        reservas = reservas.filter(estado__in=ESTADOS_BLOQUEANTES)
    elif filtro != "todas":
        reservas = reservas.filter(estado=filtro)
    habitaciones = Habitacion.objects.all()
    stats = {
        "libres": habitaciones.filter(estado="DISPONIBLE").count(),
        "ocupadas": habitaciones.filter(estado="OCUPADA").count(),
        "pendientes": Reserva.objects.filter(estado="PENDIENTE").count(),
        "llegadas": Reserva.objects.filter(estado="CONFIRMADA", fecha_ingreso=date.today()).count(),
    }
    return render(request, "hotel/panel.html", {
        "reservas": reservas, "habitaciones": habitaciones, "stats": stats, "filtro": filtro,
        "filtros": [("vigentes", "Vigentes"), ("PENDIENTE", "Pendientes"), ("CONFIRMADA", "Confirmadas"),
                    ("ACTIVA", "En estadía"), ("FINALIZADA", "Finalizadas"), ("CANCELADA", "Canceladas"),
                    ("todas", "Todas")],
        "estados_hab": Habitacion.ESTADOS, "hoy": date.today(),
    })


@es_recepcion
@require_POST
def accion_reserva(request, pk, accion):
    reserva = get_object_or_404(Reserva.objects.select_related("habitacion", "huesped"), pk=pk)
    acciones = {"confirmar": reserva.confirmar, "rechazar": reserva.cancelar,
                "checkin": reserva.check_in, "checkout": reserva.check_out}
    if accion not in acciones:
        messages.error(request, "Acción no válida.")
        return redirect("panel")
    try:
        with transaction.atomic():
            acciones[accion]()
            
            # Generar mensaje automático para el cliente según la acción realizada
            mensajes_cliente = {
                "confirmar": f"¡Tu reserva #{reserva.pk} de la Habitación {reserva.habitacion.numero} ({reserva.fecha_ingreso:%d/%m/%Y}) ha sido CONFIRMADA por recepción!",
                "rechazar": f"Recepción ha CANCELADO tu reserva #{reserva.pk} de la Habitación {reserva.habitacion.numero} ({reserva.fecha_ingreso:%d/%m/%Y}).",
                "checkin": f"Se registró tu CHECK-IN en la Habitación {reserva.habitacion.numero}. ¡Bienvenido a Hotel Ríos del Sur!",
                "checkout": f"Se registró tu CHECK-OUT de la Habitación {reserva.habitacion.numero}. ¡Gracias por hospedarte con nosotros!"
            }
            Notificacion.objects.create(
                huesped=reserva.huesped,
                mensaje=mensajes_cliente[accion]
            )

        messages.success(request, f"Reserva #{reserva.pk}: {accion} realizado correctamente y cliente notificado.")
    except ValidationError as e:
        messages.error(request, e.messages[0])
    return redirect(request.POST.get("next") or "panel")


@es_recepcion
@require_POST
def estado_habitacion(request, pk):
    habitacion = get_object_or_404(Habitacion, pk=pk)
    nuevo = request.POST.get("estado")
    if nuevo in dict(Habitacion.ESTADOS):
        if nuevo == "DISPONIBLE" and habitacion.reservas.filter(estado="ACTIVA").exists():
            messages.error(request, "Hay un huésped alojado: haz el check-out primero.")
        else:
            habitacion.estado = nuevo
            habitacion.save(update_fields=["estado"])
            messages.success(request, f"{habitacion} ahora está «{habitacion.get_estado_display()}».")
    return redirect("panel")