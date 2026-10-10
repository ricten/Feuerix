"""Verwaltung > Datensicherung: Einstellungen, Sicherung per Knopf, Verbindungstest und Download der lokalen
Sicherungsdateien. Nur fuer Superadministratoren - eine Sicherung enthaelt die Daten aller Vereine."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import datensicherung
from .forms import SicherungForm
from .models import Systemeinstellung


def _nur_superuser(request):
    if not request.user.is_superuser:
        raise PermissionDenied


@login_required
def datensicherung_einstellungen(request):
    _nur_superuser(request)
    se = Systemeinstellung.laden()
    form = SicherungForm(request.POST or None, instance=se)
    dateien = datensicherung.dateien_auflisten()
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Einstellungen gespeichert."))
        return redirect("datensicherung")
    return render(request, "core/datensicherung.html", {
        "titel": _("Datensicherung"), "form": form, "se": se, "dateien": dateien,
        "db_dateien": [d for d in dateien if d[0].startswith("db-")],
        "media_dateien": [d for d in dateien if d[0].startswith("media-")],
        "wiederherstellung": datensicherung.letzte_wiederherstellung(),
        "ziel_arten": dict(Systemeinstellung.ZIEL_ARTEN)})


@login_required
@require_POST
def datensicherung_jetzt(request):
    _nur_superuser(request)
    from .tasks import datensicherung_task
    datensicherung_task.delay()
    messages.info(request, _("Die Sicherung läuft im Hintergrund. Das Ergebnis erscheint unter „Letzte Sicherung“ "
                             "(Seite ggf. neu laden)."))
    return redirect("datensicherung")


@login_required
@require_POST
def datensicherung_test(request):
    _nur_superuser(request)
    se = Systemeinstellung.laden()
    try:
        meldung = datensicherung.verbindung_testen(se)
        se.sicherung_letzter_test = str(meldung)[:300]
        messages.success(request, meldung)
    except ValidationError as e:
        se.sicherung_letzter_test = ("Fehler: " + " ".join(e.messages))[:300]
        messages.error(request, _("Verbindung fehlgeschlagen: %(fehler)s") % {"fehler": " ".join(e.messages)})
    except Exception as e:
        se.sicherung_letzter_test = f"Fehler: {e}"[:300]
        messages.error(request, _("Verbindung fehlgeschlagen: %(fehler)s") % {"fehler": e})
    se.save()
    return redirect("datensicherung")


@login_required
def datensicherung_download(request, name):
    _nur_superuser(request)
    pfad = datensicherung.datei_pfad(name)
    if pfad is None:
        raise Http404
    return FileResponse(open(pfad, "rb"), as_attachment=True, filename=pfad.name)


BESTAETIGUNG = "WIEDERHERSTELLEN"


@login_required
@require_POST
def datensicherung_wiederherstellen(request):
    """Spielt eine lokale Sicherung ein. Doppelt abgesichert (aktuelles Passwort + Bestaetigungswort), da der
    aktuelle Datenbestand dabei ersetzt wird; die eigentliche Arbeit macht der Worker."""
    _nur_superuser(request)
    db_name = request.POST.get("db", "")
    media_name = request.POST.get("media", "")
    if request.POST.get("bestaetigung", "").strip() != BESTAETIGUNG:
        messages.error(request, _("Bitte zur Bestätigung %(wort)s eintippen.") % {"wort": BESTAETIGUNG})
    elif not request.user.check_password(request.POST.get("passwort", "")):
        messages.error(request, _("Das Passwort stimmt nicht."))
    elif not db_name.startswith("db-") or datensicherung.datei_pfad(db_name) is None:
        messages.error(request, _("Bitte eine vorhandene Datenbank-Sicherung auswählen."))
    elif media_name and (not media_name.startswith("media-") or datensicherung.datei_pfad(media_name) is None):
        messages.error(request, _("Die gewählte Medien-Sicherung gibt es nicht."))
    elif datensicherung.wartung_aktiv():
        messages.error(request, _("Es läuft bereits eine Wiederherstellung."))
    else:
        from .tasks import wiederherstellung_task
        wiederherstellung_task.delay(db_name, media_name, request.user.get_username())
        messages.warning(request, _("Die Wiederherstellung wurde gestartet. Die Anwendung ist in den nächsten "
                                    "Minuten im Wartungsmodus und lädt sich danach neu; evtl. ist eine neue "
                                    "Anmeldung nötig. Das Ergebnis steht danach unter „Datensicherung“."))
    return redirect("datensicherung")


@login_required
@require_POST
def datensicherung_hochladen(request):
    """Legt hochgeladene Sicherungsdateien (z. B. vom NAS oder aus einem Download) im Sicherungsordner ab, damit
    sie wiederhergestellt werden koennen - etwa auf einem frisch installierten Server."""
    _nur_superuser(request)
    dateien = request.FILES.getlist("dateien")
    if not dateien:
        messages.error(request, _("Bitte mindestens eine Datei auswählen."))
    for datei in dateien:
        try:
            messages.success(request, _("Hochgeladen: %(name)s") % {"name": datensicherung.sicherung_speichern(datei)})
        except ValidationError as e:
            messages.error(request, f"{datei.name}: {' '.join(e.messages)}")
    return redirect("datensicherung")
