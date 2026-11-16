from datetime import date

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone

from .models import Habitacion, Huesped, normalizar_rut, validar_rut, validar_telefono


class FechasForm(forms.Form):
    ingreso = forms.DateField(label="Llegada", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    salida = forms.DateField(label="Salida", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    personas = forms.IntegerField(label="Personas", min_value=1, max_value=10, initial=2)

    def clean(self):
        data = super().clean()
        ingreso, salida = data.get("ingreso"), data.get("salida")
        if ingreso and salida:
            if ingreso < date.today():
                raise forms.ValidationError("La fecha de llegada no puede ser pasada.")
            if salida <= ingreso:
                raise forms.ValidationError("La salida debe ser posterior a la llegada.")
            if (salida - ingreso).days > 30:
                raise forms.ValidationError("La estadía máxima es de 30 noches.")
        return data


class BusquedaForm(FechasForm):
    tipo = forms.ChoiceField(label="Tipo", required=False, choices=[("", "Todos")] + Habitacion.TIPOS)


class ReservaForm(FechasForm):
    pass


class RegistroForm(UserCreationForm):
    nombre_completo = forms.CharField(max_length=120)
    rut = forms.CharField(max_length=12, validators=[validar_rut], help_text="Ej: 12.345.678-5")
    correo = forms.EmailField()
    telefono = forms.CharField(max_length=16, validators=[validar_telefono])
    acepta_datos = forms.BooleanField(
        label="Autorizo el tratamiento de mis datos personales para gestionar mis reservas (Ley 19.628).",
        error_messages={"required": "Debes aceptar el tratamiento de datos para registrarte."})

    class Meta:
        model = User
        fields = ("username",)

    def clean_rut(self):
        rut = normalizar_rut(self.cleaned_data["rut"])
        if Huesped.objects.filter(rut=rut).exists():
            raise forms.ValidationError("Este RUT ya está registrado.")
        return rut

    def clean_correo(self):
        correo = self.cleaned_data["correo"].lower()
        if User.objects.filter(email__iexact=correo).exists():
            raise forms.ValidationError("Este correo ya está registrado.")
        return correo

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["correo"]
        user.first_name = self.cleaned_data["nombre_completo"].split()[0]
        user.save()
        Huesped.objects.create(usuario=user, nombre_completo=self.cleaned_data["nombre_completo"],
                               rut=self.cleaned_data["rut"], correo=user.email,
                               telefono=self.cleaned_data["telefono"], consentimiento=timezone.now())
        return user
