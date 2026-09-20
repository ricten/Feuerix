from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core import audit
from apps.events.models import Veranstaltung
from apps.members.models import Mitglied

from . import services
from .client import OpenSlidesFehler
from .forms import VerbindungForm
from .models import OpenSlidesVerbindung


def _pruefen(request, aktion):
    if request.verein is None or not request.rechte.darf("openslides", aktion):
        raise PermissionDenied


def _verbindung(request):
    v = OpenSlidesVerbindung.objects.filter(verein=request.verein).first()
    if v is None or not v.url or not v.benutzername or not v.passwort:
        raise OpenSlidesFehler("Die OpenSlides-Anbindung ist noch nicht vollständig eingerichtet.")
    return v


@login_required
def einstellungen(request):
    _pruefen(request, "view")
    inst = OpenSlidesVerbindung.objects.filter(verein=request.verein).first() or OpenSlidesVerbindung(verein=request.verein)
    kann = request.rechte.darf("openslides", "change")
    form = VerbindungForm(request.POST or None, instance=inst, verein=request.verein)
    if request.method == "POST":
        if not kann:
            raise PermissionDenied
        if form.is_valid():
            audit.kontext_setzen(grund=form.cleaned_data.get("aenderungsgrund"))
            form.instance.verein = request.verein
            form.save()
            messages.success(request, "Einstellungen gespeichert.")
            return redirect("openslides_einstellungen")
    ohne_pw = Mitglied.objects.filter(verein=request.verein, openslides_user_id__isnull=False).count()
    return render(request, "openslides/einstellungen.html", {
        "titel": "OpenSlides-Anbindung", "form": form, "inst": inst if inst.pk else None, "kann": kann,
        "verknuepft": ohne_pw, "mit_pw": Mitglied.objects.filter(
            verein=request.verein, openslides_user_id__isnull=False).exclude(openslides_initialpasswort="").count()})


@login_required
@require_POST
def test(request):
    _pruefen(request, "change")
    try:
        v = _verbindung(request)
        v.letzter_test = services.verbindung_testen(v)
        messages.success(request, "Verbindung erfolgreich: Anmeldung an OpenSlides funktioniert.")
    except OpenSlidesFehler as e:
        v = OpenSlidesVerbindung.objects.filter(verein=request.verein).first()
        if v:
            v.letzter_test = f"Fehler: {e}"[:300]
        messages.error(request, f"Verbindung fehlgeschlagen: {e}")
    if v:
        v.save(update_fields=["letzter_test", "geaendert"])
    return redirect("openslides_einstellungen")


@login_required
@require_POST
def abgleich(request):
    _pruefen(request, "change")
    try:
        v = _verbindung(request)
    except OpenSlidesFehler as e:
        messages.error(request, str(e))
        return redirect("openslides_einstellungen")
    from .tasks import abgleich_task
    abgleich_task.delay(v.pk)
    messages.success(request, "Der Abgleich läuft im Hintergrund. Das Ergebnis erscheint auf dieser Seite (ggf. neu laden).")
    return redirect("openslides_einstellungen")


@login_required
@require_POST
def passwoerter_loeschen(request):
    _pruefen(request, "change")
    n = Mitglied.objects.filter(verein=request.verein).exclude(openslides_initialpasswort="").update(
        openslides_initialpasswort="")
    messages.success(request, f"{n} gespeicherte Startpasswörter gelöscht.")
    return redirect("openslides_einstellungen")


@login_required
@require_POST
def veranstaltung_meeting(request, pk):
    _pruefen(request, "change")
    ver = get_object_or_404(Veranstaltung, pk=pk, verein=request.verein)
    try:
        v = _verbindung(request)
        if ver.openslides_meeting_id:
            n = services.tagesordnung_uebertragen(v, ver)
            messages.success(request, f"{n} neue Tagesordnungspunkte nach OpenSlides übertragen.")
        else:
            mid, n = services.meeting_anlegen(v, ver)
            messages.success(request, f"Versammlung in OpenSlides angelegt (ID {mid}), {n} Tagesordnungspunkte übertragen. "
                                      "Teilnehmer bitte in OpenSlides der Versammlung hinzufügen.")
    except OpenSlidesFehler as e:
        messages.error(request, f"OpenSlides: {e}")
    return redirect("veranstaltung_detail", pk=ver.pk)
