"""Sicherheitsaktionen fuer Benutzerkonten (Verwaltung › Benutzer): Superadmins koennen die 2FA eines anderen Kontos
zuruecksetzen, ein neues Passwort setzen und ein gesperrtes Konto entsperren. Jede Aktion landet im Aenderungsprotokoll."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST

from django.utils.timezone import localtime

from . import audit, passwortabgleich, zweifaktor
from .crud import knopf
from .models import Zugang


def aktionen(request, zugang):
    """Knoepfe und Hinweise fuer die Detailseite eines Zugangs (nur fuer Superadmins und nie fuer das eigene Konto)."""
    if not request.user.is_superuser or zugang.user_id == request.user.pk:
        return [], []
    zf = zweifaktor.holen(zugang.user)
    knoepfe, hinweise = [], []
    if zf.gesperrt or not zugang.user.is_active or zf.fehlversuche:
        knoepfe.append(knopf(_("Konto entsperren"), reverse("benutzer_entsperren", args=[zugang.pk]), post=True,
                             stil="success", bestaetigung=_("Konto entsperren?")))
    if zf.gesperrt:
        hinweise.append(_("Das Konto ist wegen zu vieler falscher Passworteingaben gesperrt."))
    anfrage = zugang.user.zweifaktor_anfragen.filter(erledigt_am__isnull=True).first()
    if anfrage:
        hinweise.append(_("2FA-Rücksetzung angefragt am %(datum)s%(nachricht)s. Vor dem Zurücksetzen bitte sicherstellen, dass die Anfrage "
                          "wirklich von dieser Person kommt (z. B. Rückruf).") % {
            "datum": localtime(anfrage.erstellt).strftime("%d.%m.%Y %H:%M"),
            "nachricht": f" ({anfrage.nachricht})" if anfrage.nachricht else ""})
    if zf.aktiv:
        knoepfe.append(knopf(_("2FA zurücksetzen"), reverse("benutzer_zf_reset", args=[zugang.pk]), post=True,
                             stil="outline-danger",
                             bestaetigung=_("Zwei-Faktor-Anmeldung dieses Kontos zurücksetzen? Der Benutzer muss sie neu einrichten.")))
    knoepfe.append(knopf(_("Passwort neu setzen"), reverse("benutzer_passwort", args=[zugang.pk]), stil="outline-danger"))
    hinweise.append(_("Zwei-Faktor-Anmeldung: aktiv") if zf.aktiv else _("Zwei-Faktor-Anmeldung: nicht eingerichtet"))
    return knoepfe, hinweise


def _ziel(request, pk):
    if not request.user.is_superuser:
        raise PermissionDenied
    z = get_object_or_404(Zugang.objects.select_related("user"), pk=pk, verein=request.verein)
    if z.user_id == request.user.pk:
        raise PermissionDenied     # fuer das eigene Konto gibt es die eigenen Seiten (2FA, Passwort)
    return z


def _protokoll(request, z, text):
    audit._schreiben(z, "geaendert", {_("Sicherheit"): [None, text]})


@login_required
@require_POST
def benutzer_entsperren(request, pk):
    z = _ziel(request, pk)
    zweifaktor.entsperren(z.user)
    _protokoll(request, z, "Konto entsperrt")
    messages.success(request, _("Das Konto von %(name)s wurde entsperrt.") % {"name": z.user.get_username()})
    return redirect("zugang_detail", pk=z.pk)


@login_required
@require_POST
def benutzer_zf_reset(request, pk):
    z = _ziel(request, pk)
    zweifaktor.entsperren(z.user, zweifaktor_zuruecksetzen=True)
    _protokoll(request, z, "2FA zurückgesetzt")
    messages.success(request, _("Die Zwei-Faktor-Anmeldung von %(name)s wurde zurückgesetzt.")
                     % {"name": z.user.get_username()})
    return redirect("zugang_detail", pk=z.pk)


@login_required
@require_http_methods(["GET", "POST"])
def benutzer_passwort(request, pk):
    z = _ziel(request, pk)
    fehler = []
    if request.method == "POST":
        pw, pw2 = request.POST.get("passwort", ""), request.POST.get("passwort2", "")
        if pw != pw2:
            fehler.append(_("Die beiden Passwörter stimmen nicht überein."))
        else:
            try:
                validate_password(pw, z.user)
            except ValidationError as e:
                fehler.extend(e.messages)
        if not fehler:
            z.user.set_password(pw)
            z.user.save(update_fields=["password"])
            zweifaktor.entsperren(z.user)     # ein neues Passwort hebt auch eine Sperre wegen Fehlversuchen auf
            _protokoll(request, z, "Passwort neu gesetzt")
            messages.success(request, _("Das Passwort von %(name)s wurde neu gesetzt.") % {"name": z.user.get_username()})
            passwortabgleich.melden(request, passwortabgleich.abgleichen(z.user, pw))
            return redirect("zugang_detail", pk=z.pk)
    return render(request, "core/benutzer_passwort.html", {"zugang": z, "fehler": fehler})
