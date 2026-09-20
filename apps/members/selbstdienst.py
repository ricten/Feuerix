"""Selbstdatenpflege: Mitglieder pflegen ausgewaehlte eigene Daten selbst (kein Zugriff auf die Verwaltung)."""
import secrets

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.mail import EmailMessage
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import Mitglied

SELBSTDIENST_FELDER = ("strasse", "plz", "ort", "email", "telefon", "mobil", "kontoinhaber", "iban", "bic")
ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class SelbstdienstForm(forms.ModelForm):
    class Meta:
        model = Mitglied
        fields = SELBSTDIENST_FELDER

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs["class"] = "form-control"


def _passwort():
    return "".join(secrets.choice(ALPHABET) for _ in range(12))


def _protokoll(request, mitglied, text):
    from apps.core.models import AuditLog
    AuditLog.objects.create(verein=request.verein, user=request.user, user_name=request.user.get_username(),
                            ip=request.META.get("REMOTE_ADDR"), modell="Mitglied", objekt_id=str(mitglied.pk),
                            objekt_repr=str(mitglied), aktion="geaendert", grund=text[:200], aenderungen={})


def _zugangsdaten_mailen(request, mitglied, passwort):
    link = request.build_absolute_uri(reverse("login"))
    mail = EmailMessage(
        subject=f"{mitglied.verein.name}: Zugangsdaten für die Selbstdatenpflege",
        body=(f"Guten Tag {mitglied.name},\n\n"
              f"Sie können ab sofort einige Ihrer Daten (Adresse, Telefon, E-Mail, Bankverbindung) selbst "
              f"online pflegen: {link}\n\n"
              f"Benutzername: {mitglied.benutzer.username}\nPasswort: {passwort}\n\n"
              "Bitte ändern Sie das Passwort nach der ersten Anmeldung (oben rechts unter „Passwort“).\n\n"
              f"Mit freundlichen Grüßen\n{mitglied.verein.name}"),
        from_email=settings.DEFAULT_FROM_EMAIL, to=[mitglied.email])
    mail.send()


@login_required
def mein_konto(request):
    m = getattr(request.user, "mitglied_zugang", None)
    if m is None:
        raise Http404
    form = SelbstdienstForm(request.POST or None, instance=m)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Ihre Daten wurden gespeichert.")
        return redirect("mein_konto")
    return render(request, "core/formular.html", {
        "form": form, "titel": "Meine Daten", "abbrechen_url": reverse("mein_konto")})


@login_required
@require_POST
def zugang_einrichten(request, pk):
    if request.verein is None or not request.rechte.darf("selbstdienst", "change"):
        raise PermissionDenied
    m = get_object_or_404(Mitglied, pk=pk, verein=request.verein)
    if not m.email:
        messages.error(request, "Für die Selbstdatenpflege wird eine E-Mail-Adresse des Mitglieds benötigt.")
        return redirect("mitglied_detail", pk=m.pk)
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
    m.benutzer = benutzer
    m.selbstdienst_initialpasswort = passwort
    m.save(update_fields=["benutzer", "selbstdienst_initialpasswort", "geaendert"])
    _zugangsdaten_mailen(request, m, passwort)
    _protokoll(request, m, "Zugangsdaten für Selbstdatenpflege versendet")
    messages.success(request, f"Zugangsdaten an {m.email} gesendet.")
    return redirect("mitglied_detail", pk=m.pk)


@login_required
@require_POST
def zugang_sperren(request, pk):
    if request.verein is None or not request.rechte.darf("selbstdienst", "change"):
        raise PermissionDenied
    m = get_object_or_404(Mitglied, pk=pk, verein=request.verein)
    if m.benutzer_id and m.benutzer.is_active:
        m.benutzer.is_active = False
        m.benutzer.save(update_fields=["is_active"])
        _protokoll(request, m, "Zugang zur Selbstdatenpflege gesperrt")
        messages.success(request, "Zugang gesperrt.")
    return redirect("mitglied_detail", pk=m.pk)


@login_required
@require_POST
def startpasswort_loeschen(request, pk):
    if request.verein is None or not request.rechte.darf("selbstdienst", "change"):
        raise PermissionDenied
    m = get_object_or_404(Mitglied, pk=pk, verein=request.verein)
    m.selbstdienst_initialpasswort = ""
    m.save(update_fields=["selbstdienst_initialpasswort", "geaendert"])
    messages.success(request, "Gespeichertes Startpasswort gelöscht.")
    return redirect("mitglied_detail", pk=m.pk)
