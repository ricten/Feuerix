from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from . import zweifaktor
from .models import Systemeinstellung


def _ziel(request):
    ziel = request.POST.get("next") or request.GET.get("next") or ""
    ok = url_has_allowed_host_and_scheme(ziel, allowed_hosts={request.get_host()}, require_https=request.is_secure())
    return ziel if ok and ziel else "nach_login"


@login_required
@require_http_methods(["GET", "POST"])
def zf_pruefen(request):
    """Zweite Anmeldestufe: Code der Authenticator-App oder ein Wiederherstellungscode."""
    zf = zweifaktor.holen(request.user)
    if not zf.aktiv or request.session.get("zf_ok") is True:
        return redirect(_ziel(request))
    fehler = ""
    if request.method == "POST":
        ok, grund = zweifaktor.code_pruefen(zf, request.POST.get("code", ""))
        if ok:
            request.session["zf_ok"] = True
            return redirect(_ziel(request))
        fehler = (_("Zu viele Fehlversuche - bitte in %(min)s Minuten erneut versuchen.") % {"min": zweifaktor.SPERRZEIT_MIN}
                  if grund == "gesperrt" else _("Der Code ist falsch."))
    ziel = request.POST.get("next") or request.GET.get("next") or ""
    return render(request, "core/zf_pruefen.html", {"fehler": fehler, "next": ziel})


@login_required
@require_http_methods(["GET", "POST"])
def zf_einrichten(request):
    zf = zweifaktor.holen(request.user)
    if zf.aktiv:
        return redirect("zf_verwalten")
    if not zf.geheimnis:
        zf.geheimnis = zweifaktor.neues_geheimnis()
        zf.save(update_fields=["geheimnis"])
    fehler = ""
    if request.method == "POST":
        codes = zweifaktor.aktivieren(zf, request.POST.get("code", ""))
        if codes is not None:
            request.session["zf_ok"] = True
            messages.success(request, _("Die Zwei-Faktor-Anmeldung ist jetzt aktiv."))
            return render(request, "core/zf_codes.html", {"codes": codes})
        fehler = _("Der Code ist falsch - bitte erneut versuchen.")
    return render(request, "core/zf_einrichten.html", {
        "geheimnis": zf.geheimnis, "qr": zweifaktor.qr_svg_uri(zweifaktor.otpauth_uri(request.user, zf.geheimnis)),
        "fehler": fehler, "pflicht": zweifaktor.ist_pflicht(request.user)})


@login_required
@require_http_methods(["GET", "POST"])
def zf_verwalten(request):
    zf = zweifaktor.holen(request.user)
    if not zf.aktiv:
        return redirect("zf_einrichten")
    pflicht = zweifaktor.ist_pflicht(request.user)
    se = Systemeinstellung.laden()
    if request.method == "POST" and request.POST.get("aktion") == "pflicht_alle" and request.user.is_superuser:
        se.zweifaktor_fuer_alle = request.POST.get("fuer_alle") == "on"
        se.save()
        messages.success(request, _("Einstellung gespeichert."))
        return redirect("zf_verwalten")
    if request.method == "POST":
        if not request.user.check_password(request.POST.get("passwort", "")):
            messages.error(request, _("Das Passwort ist falsch."))
        elif request.POST.get("aktion") == "codes":
            return render(request, "core/zf_codes.html", {"codes": zweifaktor.wiederherstellungscodes_erzeugen(zf)})
        elif request.POST.get("aktion") == "aus":
            if pflicht:
                messages.error(request, _("Für Superadmins ist die Zwei-Faktor-Anmeldung verpflichtend."))
            else:
                zweifaktor.deaktivieren(zf)
                messages.success(request, _("Die Zwei-Faktor-Anmeldung wurde deaktiviert."))
                return redirect("zf_einrichten")
    return render(request, "core/zf_verwalten.html", {"pflicht": pflicht, "codes_rest": len(zf.wiederherstellungscodes),
        "fuer_alle": se.zweifaktor_fuer_alle})


@login_required
@require_http_methods(["GET", "POST"])
def lizenz_seite(request):
    """Lizenzstatus und Registrierung (nur Superadmins) - bleibt auch bei abgelaufener Probezeit erreichbar."""
    from django.core.exceptions import PermissionDenied
    from django.core.validators import validate_email
    from django.core.exceptions import ValidationError
    from . import lizenz
    if not request.user.is_superuser:
        raise PermissionDenied
    lz = lizenz.laden()
    fehler = ""
    if request.method == "POST" and lizenz.aktiv():
        email = request.POST.get("email", "").strip()
        try:
            validate_email(email)
            lz = lizenz.registrieren(email)
            messages.success(request, _("Die Installation wurde registriert. Vielen Dank!"))
            return redirect("lizenz")
        except ValidationError:
            fehler = _("Bitte eine gültige E-Mail-Adresse angeben.")
        except lizenz.LizenzFehler as e:
            fehler = str(e)
    elif request.method == "POST":
        fehler = _("Es ist kein Lizenzserver eingerichtet.")
    return render(request, "core/lizenz.html", {
        "lz": lz, "aktiv": lizenz.aktiv(), "registriert": lizenz.registriert(lz), "resttage": lizenz.tage_verbleibend(lz),
        "gesperrt": lizenz.gesperrt(lz), "fehler": fehler, "vereine": lizenz.nutzdaten()["vereine"],
        "server": lizenz.settings.LICENSE_SERVER_URL})
