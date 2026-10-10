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
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Einstellungen gespeichert."))
        return redirect("datensicherung")
    return render(request, "core/datensicherung.html", {
        "titel": _("Datensicherung"), "form": form, "se": se, "dateien": datensicherung.dateien_auflisten(),
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
