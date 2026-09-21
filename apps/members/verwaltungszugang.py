"""Verwaltungszugang (Zugang + Rolle) direkt aus dem Mitglied heraus einrichten - ohne Umweg über
Verwaltung > Benutzer. Nutzt ein vorhandenes Selbstdienst-Konto (Mitglied.benutzer) weiter, falls eins existiert."""
import secrets

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.mail import EmailMessage
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.core.models import Rolle, Zugang

from .models import Mitglied

ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _passwort():
    return "".join(secrets.choice(ALPHABET) for _ in range(12))


class VerwaltungszugangForm(forms.Form):
    rolle = forms.ModelChoiceField(label="Rolle", queryset=Rolle.objects.none())

    def __init__(self, *args, verein=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["rolle"].queryset = Rolle.objects.filter(verein=verein)
        self.fields["rolle"].widget.attrs["class"] = "form-select"


def _zugangsdaten_mailen(request, mitglied, benutzer, rolle, passwort):
    link = request.build_absolute_uri(reverse("login"))
    mail = EmailMessage(
        subject=f"{mitglied.verein.name}: Zugang zur Vereinsverwaltung",
        body=(f"Guten Tag {mitglied.name},\n\n"
              f"Sie haben ab sofort Zugang zur Vereinsverwaltung mit der Rolle „{rolle.name}“: {link}\n\n"
              f"Benutzername: {benutzer.username}\nPasswort: {passwort}\n\n"
              "Bitte ändern Sie das Passwort nach der ersten Anmeldung (oben rechts unter „Passwort“).\n\n"
              f"Mit freundlichen Grüßen\n{mitglied.verein.name}"),
        from_email=settings.DEFAULT_FROM_EMAIL, to=[mitglied.email])
    mail.send()


@login_required
def verwaltungszugang_einrichten(request, pk):
    if request.verein is None or not request.rechte.darf("verwaltung", "add"):
        raise PermissionDenied
    m = get_object_or_404(Mitglied, pk=pk, verein=request.verein)
    if m.benutzer_id and Zugang.objects.filter(verein=request.verein, user_id=m.benutzer_id).exists():
        messages.error(request, "Für dieses Mitglied besteht bereits ein Verwaltungszugang.")
        return redirect("mitglied_detail", pk=m.pk)
    if not m.email:
        messages.error(request, "Für einen Verwaltungszugang wird eine E-Mail-Adresse des Mitglieds benötigt.")
        return redirect("mitglied_detail", pk=m.pk)

    form = VerwaltungszugangForm(request.POST or None, verein=request.verein)
    if request.method == "POST" and form.is_valid():
        User = get_user_model()
        passwort = _passwort()
        if m.benutzer_id:
            benutzer = m.benutzer
            benutzer.is_active = True
        else:
            if User.objects.filter(username=m.email).exists():
                messages.error(request, "Diese E-Mail-Adresse ist bereits einem Benutzerkonto zugeordnet.")
                return redirect("mitglied_detail", pk=m.pk)
            benutzer = User(username=m.email, email=m.email, first_name=m.vorname, last_name=m.nachname)
        benutzer.set_password(passwort)
        benutzer.save()
        if not m.benutzer_id:
            m.benutzer = benutzer
            m.save(update_fields=["benutzer", "geaendert"])
        rolle = form.cleaned_data["rolle"]
        Zugang.objects.create(verein=request.verein, user=benutzer, rolle=rolle)
        _zugangsdaten_mailen(request, m, benutzer, rolle, passwort)
        messages.success(request, f"Verwaltungszugang eingerichtet, Zugangsdaten an {m.email} gesendet.")
        return redirect("mitglied_detail", pk=m.pk)

    return render(request, "core/formular.html", {
        "form": form, "titel": f"Verwaltungszugang für {m.name} einrichten",
        "abbrechen_url": reverse("mitglied_detail", args=[m.pk])})
