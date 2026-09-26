from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core.crud import abschnitt, knopf
from apps.core.util import geld

from . import services
from .models import Spende, Zuwendungsbestaetigung
from .pdf import zuwendungsbestaetigung_pdf


def _pruefen(request, aktion):
    if request.verein is None or not request.rechte.darf("spenden", aktion):
        raise PermissionDenied


def bescheid_warnungen(v):
    w = []
    if not (v.finanzamt and v.steuernummer and v.bescheid_datum):
        w.append("Vereinsdaten unvollständig (Finanzamt, Steuernummer, Datum des Bescheids) – bitte unter "
                 "Verwaltung › Verein ergänzen, bevor Bestätigungen ausgestellt werden.")
    elif (date.today() - v.bescheid_datum).days > 3 * 365:
        w.append("Der Gemeinnützigkeitsbescheid ist älter als 3 Jahre – bitte prüfen, ob er für Zuwendungsbestätigungen "
                 "noch ausreicht.")
    if not v.beguenstigte_zwecke:
        w.append("Begünstigte Zwecke sind nicht hinterlegt.")
    return w


def spende_kontext(request, s):
    aktionen = []
    if s.bestaetigung_id is None and request.rechte.darf("spenden", "add"):
        aktionen.append(knopf("Einzelbestätigung erstellen", reverse("spende_einzelbestaetigung", args=[s.pk]),
                              post=True, stil="primary"))
    if s.bestaetigung_id:
        aktionen.append(knopf(f"Zur Bestätigung {s.bestaetigung}", reverse("zuwendungsbestaetigung_detail",
                                                                            args=[s.bestaetigung_id])))
    return {"aktionen": aktionen}


def spenden_listen_aktionen(request):
    if request.rechte.darf("spenden", "add"):
        return [knopf("Sammelbestätigungen erstellen", reverse("quittung_sammel"), stil="primary")]
    return []


@login_required
@require_POST
def spende_einzelbestaetigung(request, pk):
    _pruefen(request, "add")
    s = get_object_or_404(Spende, pk=pk, verein=request.verein, bestaetigung__isnull=True)
    b = services.einzelbestaetigung(request.verein, s)
    messages.success(request, "Entwurf erstellt. Bitte prüfen und ausstellen.")
    return redirect("zuwendungsbestaetigung_detail", pk=b.pk)


@login_required
def quittung_sammel(request):
    _pruefen(request, "add")
    try:
        jahr = int(request.GET.get("jahr") or request.POST.get("jahr") or date.today().year - 1)
    except ValueError:
        jahr = date.today().year - 1
    if request.method == "POST":
        erstellt = services.sammelbestaetigungen(request.verein, jahr)
        messages.success(request, f"{len(erstellt)} Sammelbestätigungen als Entwurf erstellt.")
        return redirect(reverse("zuwendungsbestaetigung_list") + "?status=entwurf")
    gruppen = services.offene_gruppen(request.verein, jahr)
    zeilen = [(g[0].name_des_spenders, len(g), geld(sum(s.betrag for s in g))) for g in gruppen]
    return render(request, "donations/quittung_sammel.html", {"titel": "Sammelbestätigungen", "jahr": jahr,
                                                              "zeilen": zeilen})


def bestaetigung_kontext(request, b):
    aktionen, rt = [knopf("PDF", reverse("zuwendungsbestaetigung_pdf", args=[b.pk]), stil="primary")], request.rechte
    if rt.darf("spenden", "change"):
        if b.status == "entwurf":
            aktionen.append(knopf("Ausstellen (Nummer vergeben, fixieren)",
                                  reverse("zuwendungsbestaetigung_ausstellen", args=[b.pk]), post=True, stil="success",
                                  bestaetigung="Bestätigung ausstellen? Sie ist danach nicht mehr änderbar."))
        if b.status == "ausgestellt":
            aktionen.append(knopf("Stornieren", reverse("zuwendungsbestaetigung_stornieren", args=[b.pk]), post=True,
                                  stil="outline-danger", bestaetigung="Bestätigung stornieren? Die Spenden werden wieder freigegeben."))
    return {"aktionen": aktionen, "hinweise": bescheid_warnungen(request.verein) if b.status == "entwurf" else [],
            "abschnitte": [abschnitt(request, "Enthaltene Spenden", b.spenden.all(), ("datum", "art", "betrag"))]}


@login_required
def bestaetigung_pdf(request, pk):
    _pruefen(request, "view")
    b = get_object_or_404(Zuwendungsbestaetigung, pk=pk, verein=request.verein)
    r = HttpResponse(zuwendungsbestaetigung_pdf(b), content_type="application/pdf")
    r["Content-Disposition"] = f'inline; filename="{b.nummer or "entwurf"}.pdf"'
    return r


@login_required
@require_POST
def bestaetigung_ausstellen(request, pk):
    _pruefen(request, "change")
    b = get_object_or_404(Zuwendungsbestaetigung, pk=pk, verein=request.verein)
    if b.status == "entwurf":
        b.ausstellen()
        try:
            from apps.paperless import auto
            auto.fertiges_dokument("zuwendung", b.pk, b.verein)
        except Exception:
            pass
        messages.success(request, f"Bestätigung {b.nummer} ausgestellt.")
    return redirect("zuwendungsbestaetigung_detail", pk=b.pk)


@login_required
@require_POST
def bestaetigung_stornieren(request, pk):
    _pruefen(request, "change")
    b = get_object_or_404(Zuwendungsbestaetigung, pk=pk, verein=request.verein)
    if b.status == "ausgestellt":
        b.status = "storniert"
        b.save()
        for s in b.spenden.all():
            s.bestaetigung = None
            s.save(update_fields=["bestaetigung", "geaendert"])
        messages.success(request, "Storniert.")
    return redirect("zuwendungsbestaetigung_detail", pk=b.pk)
