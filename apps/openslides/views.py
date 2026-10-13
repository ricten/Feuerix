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
from django.utils.translation import gettext


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
    if not request.user.is_superuser:        # Administrator-Zugang und Passwort-Abgleich nur fuer Superadmins
        for f in VerbindungForm.NUR_SUPERADMIN:
            form.fields.pop(f, None)
    if request.method == "POST":
        if not kann:
            raise PermissionDenied
        if form.is_valid():
            audit.kontext_setzen(grund=form.cleaned_data.get("aenderungsgrund"))
            form.instance.verein = request.verein
            form.save()
            messages.success(request, gettext("Einstellungen gespeichert."))
            return redirect("openslides_einstellungen")
    ohne_pw = Mitglied.objects.filter(verein=request.verein, openslides_user_id__isnull=False).count()
    return render(request, "openslides/einstellungen.html", {
        "titel": gettext("OpenSlides-Anbindung"), "form": form, "inst": inst if inst.pk else None, "kann": kann,
        "verknuepft": ohne_pw, "mit_pw": Mitglied.objects.filter(
            verein=request.verein, openslides_user_id__isnull=False).exclude(openslides_initialpasswort="").count()})


@login_required
@require_POST
def admin_anzeigen(request):
    from apps.core import zugangsdaten
    _pruefen(request, "view")
    v = OpenSlidesVerbindung.objects.filter(verein=request.verein).first()
    return zugangsdaten.anzeigen(request, v, gettext("OpenSlides-Administrator"), "openslides_einstellungen")


@login_required
@require_POST
def test(request):
    _pruefen(request, "change")
    try:
        v = _verbindung(request)
        v.letzter_test = services.verbindung_testen(v)
        messages.success(request, gettext("Verbindung erfolgreich: Anmeldung an OpenSlides funktioniert."))
    except OpenSlidesFehler as e:
        v = OpenSlidesVerbindung.objects.filter(verein=request.verein).first()
        if v:
            v.letzter_test = f"Fehler: {e}"[:300]
        messages.error(request, gettext("Verbindung fehlgeschlagen: %(e)s") % {"e": e})
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
    messages.success(request, gettext("Der Abgleich läuft im Hintergrund. Das Ergebnis erscheint auf dieser Seite (ggf. neu laden)."))
    return redirect("openslides_einstellungen")


@login_required
@require_POST
def passwoerter_loeschen(request):
    _pruefen(request, "change")
    n = Mitglied.objects.filter(verein=request.verein).exclude(openslides_initialpasswort="").update(
        openslides_initialpasswort="")
    messages.success(request, gettext("%(n)s gespeicherte Startpasswörter gelöscht.") % {"n": n})
    return redirect("openslides_einstellungen")


def _rechte_zuweisen(v, ver):
    """Rechte aus den Tags; ein Fehler dabei darf das Anlegen/Übertragen nicht scheitern lassen."""
    try:
        return services.versammlungsrechte_zuweisen(v, ver)
    except OpenSlidesFehler as e:
        return gettext("Rechte aus Tags konnten nicht vergeben werden: %(fehler)s.") % {"fehler": e}


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
            messages.success(request, gettext("%(n)s neue Tagesordnungspunkte nach OpenSlides übertragen. %(rechte)s") % {"n": n, "rechte": rechte})
        else:
            mid, n = services.meeting_anlegen(v, ver)
            rechte = _rechte_zuweisen(v, ver)
            messages.success(request, gettext("Versammlung in OpenSlides angelegt (ID %(mid)s), %(n)s Tagesordnungspunkte übertragen. %(rechte)s Weitere Teilnehmer bitte in OpenSlides hinzufügen.") % {"mid": mid, "n": n, "rechte": rechte})
    except OpenSlidesFehler as e:
        messages.error(request, gettext("OpenSlides: %(e)s") % {"e": e})
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
            messages.warning(request, gettext("OpenSlides: %(hinweis)s") % {"hinweis": hinweis})
        if n:
            messages.success(request, _ergebnis_meldung(ver))
        else:
            messages.warning(request, gettext("Keine abgeschlossenen Wahlen oder Abstimmungen und keine Anwesenden gefunden."))
    except OpenSlidesFehler as e:
        messages.error(request, gettext("OpenSlides: %(e)s") % {"e": e})
    return redirect("veranstaltung_detail", pk=ver.pk)


def _ergebnis_meldung(ver):
    wahlen = ver.wahlergebnisse.filter(art="wahl").count()
    abstimmungen = ver.wahlergebnisse.filter(art="abstimmung").count()
    return gettext("%(wahlen)s Wahlergebnis(se), %(abstimmungen)s Abstimmung(en) und %(anwesende)s Anwesende aus OpenSlides übernommen.") % {
        "wahlen": wahlen, "abstimmungen": abstimmungen, "anwesende": ver.anwesenheiten.count()}


@login_required
@require_POST
def schriftstueck_abstimmungen(request, pk):
    """Am Protokoll: Anwesenheit, Wahlen und Abstimmungen frisch aus OpenSlides abrufen. Sie werden beim Erzeugen von
    PDF/Word automatisch als Anlagen angehaengt (Teilnehmerliste, Abstimmungen, Wahlen - je eine eigene Seite, siehe
    apps.documents.anlagen); der Protokolltext selbst wird nicht veraendert. Ein erneuter Klick aktualisiert die
    Daten."""
    from apps.documents.models import Schriftstueck
    _pruefen(request, "change")
    if not request.rechte.darf("schriftverkehr", "change"):
        raise PermissionDenied
    s = get_object_or_404(Schriftstueck, pk=pk, verein=request.verein)
    ver = s.veranstaltung
    if s.art != "protokoll" or ver is None or not ver.openslides_meeting_id:
        messages.error(request, gettext("Nur für Protokolle einer Veranstaltung, die mit einer OpenSlides-Versammlung verknüpft ist."))
        return redirect("schriftstueck_detail", pk=s.pk)
    try:
        v = _verbindung(request)
        n = services.wahlergebnisse_abrufen(v, ver) + services.anwesenheit_abrufen(v, ver)
        for hinweis in getattr(ver, "abruf_hinweise", []):
            messages.warning(request, gettext("OpenSlides: %(hinweis)s") % {"hinweis": hinweis})
    except OpenSlidesFehler as e:
        messages.error(request, gettext("OpenSlides: %(e)s") % {"e": e})
        return redirect("schriftstueck_detail", pk=s.pk)
    if not n:
        messages.warning(request, gettext("Keine abgeschlossenen Wahlen oder Abstimmungen und keine Anwesenden gefunden."))
        return redirect("schriftstueck_detail", pk=s.pk)
    from apps.documents.anlagen import anlagen
    titel = ", ".join(a["titel"] for a in anlagen(ver))
    messages.success(request, gettext("%(ergebnis_meldung)s Dem Protokoll werden angehängt: %(titel)s.") % {"ergebnis_meldung": _ergebnis_meldung(ver), "titel": titel})
    return redirect("schriftstueck_detail", pk=s.pk)
