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
    v = services.verbindung_oder_none(request.verein)
    if v is None:
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


def _rechte_zuweisen(v, ver):
    """Rechte aus den Tags; ein Fehler dabei darf das Anlegen/Übertragen nicht scheitern lassen."""
    try:
        return services.versammlungsrechte_zuweisen(v, ver)
    except OpenSlidesFehler as e:
        return f"Rechte aus Tags konnten nicht vergeben werden: {e}."


@login_required
@require_POST
def veranstaltung_meeting(request, pk):
    _pruefen(request, "change")
    ver = get_object_or_404(Veranstaltung, pk=pk, verein=request.verein)
    try:
        v = _verbindung(request)
        if ver.openslides_meeting_id:
            n = services.tagesordnung_uebertragen(v, ver)
            rechte = _rechte_zuweisen(v, ver)
            messages.success(request, f"{n} neue Tagesordnungspunkte nach OpenSlides übertragen. {rechte}")
        else:
            mid, n = services.meeting_anlegen(v, ver)
            rechte = _rechte_zuweisen(v, ver)
            messages.success(request, f"Versammlung in OpenSlides angelegt (ID {mid}), {n} Tagesordnungspunkte "
                                      f"übertragen. {rechte} Weitere Teilnehmer bitte in OpenSlides hinzufügen.")
    except OpenSlidesFehler as e:
        messages.error(request, f"OpenSlides: {e}")
    return redirect("veranstaltung_detail", pk=ver.pk)


@login_required
@require_POST
def veranstaltung_wahlergebnisse(request, pk):
    _pruefen(request, "change")
    ver = get_object_or_404(Veranstaltung, pk=pk, verein=request.verein)
    try:
        v = _verbindung(request)
        n = services.wahlergebnisse_abrufen(v, ver) + services.anwesenheit_abrufen(v, ver)
        for hinweis in getattr(ver, "abruf_hinweise", []):
            messages.warning(request, f"OpenSlides: {hinweis}")
        if n:
            messages.success(request, _ergebnis_meldung(ver))
        else:
            messages.warning(request, "Keine abgeschlossenen Wahlen oder Abstimmungen und keine Anwesenden gefunden.")
    except OpenSlidesFehler as e:
        messages.error(request, f"OpenSlides: {e}")
    return redirect("veranstaltung_detail", pk=ver.pk)


def _ergebnis_meldung(ver):
    wahlen = ver.wahlergebnisse.filter(art="wahl").count()
    abstimmungen = ver.wahlergebnisse.filter(art="abstimmung").count()
    return (f"{wahlen} Wahlergebnis(se), {abstimmungen} Abstimmung(en) und {ver.anwesenheiten.count()} Anwesende "
            f"aus OpenSlides übernommen.")


def _abschnitte(ver):
    """(Platzhalter, Ueberschrift, Daten vorhanden) der Abschnitte, die der Knopf am Protokoll bei Bedarf anhaengt."""
    return (("{anwesenheit}", "Anwesenheitsliste (aus OpenSlides übernommen; Stimmberechtigung bitte prüfen)",
             ver.anwesenheiten.exists()),
            ("{abstimmungen}", "Abstimmungen (aus OpenSlides übernommen; ob angenommen, bitte ergänzen)",
             ver.wahlergebnisse.filter(art="abstimmung").exists()),
            ("{wahlergebnisse}", "Wahlergebnisse (aus OpenSlides übernommen; gewählte Person bitte ergänzen)",
             ver.wahlergebnisse.filter(art="wahl").exists()))


@login_required
@require_POST
def schriftstueck_abstimmungen(request, pk):
    """Am Protokoll: Anwesenheit, Wahlen und Abstimmungen frisch aus OpenSlides abrufen und - falls noch nicht im
    Text - als Abschnitte mit den Platzhaltern {anwesenheit}/{abstimmungen}/{wahlergebnisse} einfuegen. Die Platzhalter werden beim Erzeugen
    von PDF/Word jeweils mit dem aktuellen Stand gefuellt; ein erneuter Klick aktualisiert also die Daten, ohne
    den Text zu verdoppeln oder eigene Ergaenzungen zu ueberschreiben."""
    from apps.documents.models import Schriftstueck
    _pruefen(request, "change")
    if not request.rechte.darf("schriftverkehr", "change"):
        raise PermissionDenied
    s = get_object_or_404(Schriftstueck, pk=pk, verein=request.verein)
    ver = s.veranstaltung
    if s.art != "protokoll" or ver is None or not ver.openslides_meeting_id:
        messages.error(request, "Nur für Protokolle einer Veranstaltung, die mit einer OpenSlides-Versammlung "
                                "verknüpft ist.")
        return redirect("schriftstueck_detail", pk=s.pk)
    try:
        v = _verbindung(request)
        n = services.wahlergebnisse_abrufen(v, ver) + services.anwesenheit_abrufen(v, ver)
        for hinweis in getattr(ver, "abruf_hinweise", []):
            messages.warning(request, f"OpenSlides: {hinweis}")
    except OpenSlidesFehler as e:
        messages.error(request, f"OpenSlides: {e}")
        return redirect("schriftstueck_detail", pk=s.pk)
    if not n:
        messages.warning(request, "Keine abgeschlossenen Wahlen oder Abstimmungen und keine Anwesenden gefunden.")
        return redirect("schriftstueck_detail", pk=s.pk)
    neu = [f"{titel}:\n{platzhalter}" for platzhalter, titel, vorhanden in _abschnitte(ver)
           if vorhanden and platzhalter not in s.text]
    if neu:
        s.text = s.text.rstrip() + "\n\n" + "\n\n".join(neu) + "\n"
        s.save(update_fields=["text", "geaendert"])
    messages.success(request, _ergebnis_meldung(ver) + (" Abschnitte ins Protokoll eingefügt." if neu else
                                                         " Das Protokoll enthält die Platzhalter bereits und zeigt "
                                                         "jetzt den aktuellen Stand."))
    return redirect("schriftstueck_detail", pk=s.pk)
