"""Verwaltung > Software-Update: Stand ansehen und ein Update anstossen. Nur fuer Superadministratoren (betrifft alle Vereine);
die eigentliche Arbeit macht der Server (siehe softwareupdate.py)."""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import softwareupdate
from .audit import kontext_var
from .models import AuditLog, Systemeinstellung


def _nur_superuser(request):
    if not request.user.is_superuser:
        raise PermissionDenied


def _aktuelle_version():
    try:
        return (settings.BASE_DIR / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _zustand(request):
    """Alles, was Seite und Statusabfrage anzeigen."""
    se = Systemeinstellung.laden()
    version = _aktuelle_version()
    neu = se.update_anzeigen(version)
    st = softwareupdate.status()
    return {"aktiv": softwareupdate.aktiv(), "bereit": softwareupdate.host_bereit(), "laeuft": softwareupdate.laeuft(),
            "haengt": softwareupdate.auftrag_haengt(), "version": version, "neue_version": neu or "", "status": st,
            "geprueft_am": se.update_geprueft_am}


@login_required
def softwareupdate_seite(request):
    _nur_superuser(request)
    z = _zustand(request)
    z.update({"titel": _("Software-Update"), "log": softwareupdate.log_ende(),
              "changelog_url": (f"{settings.PRODUCT_CHANGELOG_URL}#{z['neue_version'].replace('.', '')}"
                                if z["neue_version"] and settings.PRODUCT_CHANGELOG_URL else "")})
    return render(request, "core/softwareupdate.html", z)


@login_required
def softwareupdate_status(request):
    """JSON fuer die Fortschrittsanzeige (die Seite fragt waehrend des Updates regelmaessig ab)."""
    _nur_superuser(request)
    z = _zustand(request)
    st = z["status"]
    return JsonResponse({"laeuft": z["laeuft"], "zustand": st["zustand"], "schritt": st["schritt"], "meldung": st["meldung"],
                         "version": z["version"], "von": st["von"], "nach": st["nach"], "log": softwareupdate.log_ende()})


@login_required
@require_POST
def softwareupdate_starten(request):
    _nur_superuser(request)
    try:
        softwareupdate.anfordern(request.user.get_username())
    except softwareupdate.NichtMoeglich as e:
        messages.error(request, str(e))
        return redirect("softwareupdate")
    k = kontext_var.get() or {}
    version = _aktuelle_version()
    AuditLog.objects.create(
        user=request.user, user_name=request.user.get_username(), ip=k.get("ip"), modell=_("Software-Update"),
        objekt_id="", objekt_repr=version[:200], aktion="geaendert", aenderungen={},
        grund=_("Update angefordert (installiert: %(version)s)") % {"version": version})
    messages.warning(request, _("Das Update wurde angefordert. Feuerix wird dabei gesichert und neu gestartet und ist für einige "
                                "Minuten nicht erreichbar; diese Seite zeigt den Fortschritt und lädt sich danach neu."))
    return redirect("softwareupdate")
