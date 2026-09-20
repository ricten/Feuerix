from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core.crud import knopf
from apps.core.util import geld
from apps.donations.models import Spende
from apps.members.models import Mitglied

from .models import Aufwandsentschaedigung, freibetrag_stand


def nach_speichern(request, obj, neu):
    if obj.ist_pauschale and obj.status in ("genehmigt", "ausgezahlt"):
        summe, grenze = freibetrag_stand(request.verein, obj.empfaenger, obj.datum.year)[obj.art]
        if summe > grenze:
            messages.warning(request, f"Achtung: Mit dieser Zahlung liegt die Summe {obj.datum.year} für "
                                      f"{obj.empfaenger.name} bei {geld(summe)} und überschreitet den Freibetrag von "
                                      f"{geld(grenze)}. Der übersteigende Betrag kann steuer- und "
                                      "sozialversicherungspflichtig sein.")
    if obj.ist_pauschale and not obj.freibetrag_erklaerung:
        messages.info(request, "Hinweis: Es liegt noch keine Erklärung des Empfängers zur Freibetragsnutzung vor.")


def aufwand_kontext(request, a):
    aktionen, hinweise = [], []
    rt = request.rechte
    if a.ist_pauschale:
        summe, grenze = freibetrag_stand(request.verein, a.empfaenger, a.datum.year)[a.art]
        hinweise.append(f"Stand {a.datum.year} für {a.empfaenger.name}: {geld(summe)} von {geld(grenze)} Freibetrag "
                        f"({a.get_art_display().split(' (')[0]}).")
    if rt.darf("aufwand", "change") and a.status == "beantragt":
        aktionen.append(knopf("Genehmigen", reverse("aufwand_status", args=[a.pk]), post=True, stil="success",
                              felder={"status": "genehmigt"}))
        aktionen.append(knopf("Ablehnen", reverse("aufwand_status", args=[a.pk]), post=True, stil="outline-danger",
                              felder={"status": "abgelehnt"}))
    if rt.darf("aufwand", "change") and a.status == "genehmigt":
        aktionen.append(knopf("Als ausgezahlt markieren", reverse("aufwand_status", args=[a.pk]), post=True,
                              stil="primary", felder={"status": "ausgezahlt"}))
    if (rt.darf("aufwand", "change") and rt.darf("spenden", "add") and a.status == "genehmigt"
            and a.art == "aufwandsersatz"):
        aktionen.append(knopf("Verzicht → Aufwandsspende", reverse("aufwand_verzicht", args=[a.pk]), post=True,
                              stil="outline-secondary",
                              bestaetigung="Empfänger verzichtet auf die Erstattung? Es wird eine Spende angelegt."))
    return {"aktionen": aktionen, "hinweise": hinweise}


def listen_aktionen(request):
    return [knopf("Jahresübersicht Freibeträge", reverse("aufwand_uebersicht"), stil="primary")]


@login_required
@require_POST
def aufwand_status(request, pk):
    if request.verein is None or not request.rechte.darf("aufwand", "change"):
        raise PermissionDenied
    a = get_object_or_404(Aufwandsentschaedigung, pk=pk, verein=request.verein)
    neu = request.POST.get("status")
    erlaubt = {"beantragt": ("genehmigt", "abgelehnt"), "genehmigt": ("ausgezahlt",)}
    if neu in erlaubt.get(a.status, ()):
        a.status = neu
        if neu == "genehmigt":
            a.genehmigt_von = request.user.get_username()
        if neu == "ausgezahlt":
            a.ausgezahlt_am = date.today()
        a.save()
        nach_speichern(request, a, False)
    return redirect("aufwandsentschaedigung_detail", pk=a.pk)


@login_required
@require_POST
def aufwand_verzicht(request, pk):
    if request.verein is None or not (request.rechte.darf("aufwand", "change") and request.rechte.darf("spenden", "add")):
        raise PermissionDenied
    a = get_object_or_404(Aufwandsentschaedigung, pk=pk, verein=request.verein, status="genehmigt",
                          art="aufwandsersatz")
    Spende.objects.create(verein=request.verein, spender=a.empfaenger, datum=date.today(), betrag=a.betrag,
                          art="aufwandsverzicht", zweck=a.taetigkeit[:200],
                          bemerkung="Verzicht auf genehmigten Aufwandsersatz")
    a.status = "verzichtet"
    a.save()
    messages.success(request, "Aufwandsspende angelegt – eine Spendenquittung kann nun erstellt werden.")
    return redirect("aufwandsentschaedigung_detail", pk=a.pk)


@login_required
def aufwand_uebersicht(request):
    if request.verein is None or not request.rechte.darf("aufwand", "view"):
        raise PermissionDenied
    try:
        jahr = int(request.GET.get("jahr", date.today().year))
    except ValueError:
        jahr = date.today().year
    v = request.verein
    zeilen = []
    ids = set(Aufwandsentschaedigung.objects.filter(verein=v, datum__year=jahr, status__in=["genehmigt", "ausgezahlt"])
              .values_list("empfaenger_id", flat=True))
    for m in Mitglied.objects.filter(pk__in=ids, verein=v):
        st = freibetrag_stand(v, m, jahr)
        ersatz = sum((a.betrag for a in Aufwandsentschaedigung.objects.filter(
            verein=v, empfaenger=m, datum__year=jahr, art="aufwandsersatz", status__in=["genehmigt", "ausgezahlt"])), 0)
        sonst = sum((a.betrag for a in Aufwandsentschaedigung.objects.filter(
            verein=v, empfaenger=m, datum__year=jahr, art="sonstige", status__in=["genehmigt", "ausgezahlt"])), 0)
        ea, ul = st["ehrenamtspauschale"], st["uebungsleiterpauschale"]
        warn = []
        if ea[0] > ea[1]:
            warn.append("Ehrenamtsfreibetrag überschritten")
        if ul[0] > ul[1]:
            warn.append("Übungsleiterfreibetrag überschritten")
        if sonst:
            warn.append("Sonstige Vergütung: steuerlich prüfen")
        zeilen.append({"mitglied": m, "ea": geld(ea[0]), "ul": geld(ul[0]), "ersatz": geld(ersatz),
                       "sonst": geld(sonst), "warn": "; ".join(warn)})
    return render(request, "allowances/uebersicht.html", {
        "titel": f"Freibeträge {jahr}", "jahr": jahr, "zeilen": zeilen,
        "grenzen": (geld(v.ehrenamts_freibetrag), geld(v.uebungsleiter_freibetrag))})
