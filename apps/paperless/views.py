from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.documents.models import Ablagedokument

from .client import PaperlessFehler
from .forms import VerbindungForm
from .models import PaperlessVerbindung


def _pruefen(request, aktion):
    if request.verein is None or not request.rechte.darf("paperless", aktion):
        raise PermissionDenied


def _verbindung(request):
    v = PaperlessVerbindung.objects.filter(verein=request.verein).first()
    if v is None or not v.aktiv or not v.url or not v.api_token:
        raise PaperlessFehler("Die Paperless-Anbindung ist noch nicht eingerichtet oder nicht aktiv.")
    return v


@login_required
def einstellungen(request):
    _pruefen(request, "view")
    inst = PaperlessVerbindung.objects.filter(verein=request.verein).first() or PaperlessVerbindung(verein=request.verein)
    kann = request.rechte.darf("paperless", "change")
    form = VerbindungForm(request.POST or None, instance=inst, verein=request.verein)
    if request.method == "POST":
        if not kann:
            raise PermissionDenied
        if form.is_valid():
            form.instance.verein = request.verein
            form.save()
            messages.success(request, "Einstellungen gespeichert.")
            return redirect("paperless_einstellungen")
    return render(request, "paperless/einstellungen.html", {
        "titel": "Paperless-Anbindung", "form": form, "inst": inst if inst.pk else None, "kann": kann})


@login_required
@require_POST
def test(request):
    _pruefen(request, "change")
    from . import services
    v = PaperlessVerbindung.objects.filter(verein=request.verein).first()
    if v is None:
        messages.error(request, "Bitte zuerst Adresse und API-Token speichern.")
        return redirect("paperless_einstellungen")
    try:
        services.verbindung_testen(v)
        messages.success(request, "Verbindung erfolgreich: Paperless ist erreichbar.")
    except PaperlessFehler as e:
        v.letzter_test = f"Fehler: {e}"[:300]
        v.save(update_fields=["letzter_test", "geaendert"])
        messages.error(request, f"Verbindung fehlgeschlagen: {e}")
    return redirect("paperless_einstellungen")


@login_required
@require_POST
def dokument_senden(request, pk):
    _pruefen_ablage(request)
    d = get_object_or_404(Ablagedokument, pk=pk, verein=request.verein)
    try:
        v = _verbindung(request)
    except PaperlessFehler as e:
        messages.error(request, str(e))
        return redirect("ablagedokument_detail", pk=d.pk)
    if not d.datei:
        messages.error(request, "Dieses Dokument hat keine Datei.")
        return redirect("ablagedokument_detail", pk=d.pk)
    from .tasks import senden_task
    senden_task.delay(v.pk, d.pk, request.POST.get("erneut") == "1")
    messages.success(request, "Wird an Paperless gesendet – Ergebnis erscheint in Kürze auf dieser Seite "
                              "(ggf. neu laden).")
    return redirect("ablagedokument_detail", pk=d.pk)


def _pruefen_ablage(request):
    if request.verein is None or not request.rechte.darf("ablage", "change"):
        raise PermissionDenied


@login_required
def sammelversand(request):
    _pruefen_ablage(request)
    qs = Ablagedokument.objects.filter(verein=request.verein).exclude(datei="").order_by("-datum", "-id")
    if request.method == "POST":
        try:
            v = _verbindung(request)
        except PaperlessFehler as e:
            messages.error(request, str(e))
            return redirect("ablage_paperless_sammelversand")
        ids = [int(pk) for pk in request.POST.getlist("dokumente") if pk.isdigit()]
        ids = list(qs.filter(pk__in=ids).values_list("pk", flat=True))
        if not ids:
            messages.error(request, "Bitte mindestens ein Dokument auswählen.")
            return redirect("ablage_paperless_sammelversand")
        from .tasks import sammel_senden_task
        sammel_senden_task.delay(v.pk, ids, request.POST.get("erneut") == "1")
        messages.success(request, f"{len(ids)} Dokument(e) werden an Paperless gesendet – Ergebnis erscheint "
                                  "in Kürze in der Ablage (ggf. neu laden).")
        return redirect("ablage_paperless_sammelversand")
    return render(request, "paperless/sammelversand.html", {"titel": "Sammelversand an Paperless", "dokumente": qs})
