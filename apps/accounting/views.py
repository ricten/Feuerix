import os
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from apps.core.crud import pdf_vorschau, knopf
from apps.core.util import geld
from apps.documents.services import ablegen

from . import erechnung, services
from .excel import kassenbericht_xlsx
from .models import Buchung, Kassenbericht, Konto
from .pdf import kassenbericht_pdf
from .services import _kat, berichtsdaten
from django.utils.translation import gettext, gettext_lazy


def _pruefen(request, aktion):
    if request.verein is None or not request.rechte.darf("kassenbuch", aktion):
        raise PermissionDenied


def buchung_listen_aktionen(request):
    a = []
    if request.rechte.darf("kassenbuch", "add"):
        a.append(knopf(gettext_lazy("Aus Zahlungen/Spenden/Veranstaltungen übernehmen"), reverse("buchungen_uebernehmen"), stil="outline-primary"))
        a.append(knopf(gettext_lazy("E-Rechnung importieren"), reverse("erechnung_importieren"), stil="outline-primary"))
    return a


def buchung_kontext(request, b):
    aktionen, hinweise = [], []
    if b.beleg:
        if b.ablage_id:
            hinweise.append(gettext("Beleg in Ablage gespeichert: %(ablage)s") % {"ablage": b.ablage})
        elif request.rechte.darf("kassenbuch", "change"):
            aktionen.append(knopf(gettext_lazy("Beleg in Ablage übernehmen"), reverse("buchung_beleg_ablegen", args=[b.pk]),
                                  post=True))
    return {"aktionen": aktionen, "hinweise": hinweise}


def _auto_uebergeben(dokument):
    from apps.paperless import auto
    try:
        auto.ablage_fertig(dokument)
    except Exception:  # Paperless-Probleme duerfen das Ablegen nie verhindern
        pass


@login_required
@require_POST
def buchung_beleg_ablegen(request, pk):
    _pruefen(request, "change")
    b = get_object_or_404(Buchung, pk=pk, verein=request.verein)
    if not b.beleg:
        messages.error(request, gettext("Diese Buchung hat keinen Beleg."))
        return redirect("buchung_detail", pk=b.pk)
    if b.ablage_id:
        messages.info(request, gettext("Der Beleg wurde bereits in der Ablage abgelegt."))
        return redirect("buchung_detail", pk=b.pk)
    b.beleg.open("rb")
    try:
        inhalt = b.beleg.read()
    finally:
        b.beleg.close()
    dateiname = os.path.basename(b.beleg.name)
    doc = ablegen(request.verein, f"Beleg {b.belegnummer or b.pk}", "beleg", dateiname, inhalt, datum=b.datum,
                 veranstaltung=b.veranstaltung, beschreibung=b.text[:300])
    b.ablage = doc
    b.save(update_fields=["ablage", "geaendert"])
    _auto_uebergeben(doc)
    messages.success(request, gettext("Beleg in der Ablage abgelegt."))
    return redirect("buchung_detail", pk=b.pk)


@login_required
def erechnung_importieren(request):
    _pruefen(request, "add")
    if request.method == "POST":
        datei = request.FILES.get("datei")
        if not datei:
            messages.error(request, gettext("Bitte eine Datei auswählen."))
            return redirect("erechnung_importieren")
        inhalt = datei.read()
        datei.seek(0)
        angaben = erechnung.parse_rechnung(erechnung.xml_aus_datei(datei.name, inhalt))
        konto = Konto.objects.filter(verein=request.verein, typ="bank", aktiv=True).first() \
            or Konto.objects.filter(verein=request.verein, aktiv=True).first()
        if konto is None:
            messages.error(request, gettext("Bitte zuerst unter Kasse › Konten mindestens ein Konto anlegen."))
            return redirect("erechnung_importieren")
        kategorie = _kat(request.verein, "Sonstige Ausgaben", "ausgabe")
        b = Buchung(verein=request.verein, typ="ausgabe", konto=konto, kategorie=kategorie)
        b.beleg = datei
        if angaben:
            b.datum = angaben["datum"] or date.today()
            b.betrag = angaben["betrag"] or Decimal("0.01")
            teile = [f"E-Rechnung {angaben['nummer']}" if angaben["nummer"] else "E-Rechnung", angaben["verkaeufer"]]
            b.text = " – ".join(t for t in teile if t)[:250]
            messages.success(request, gettext("%(format)s eingelesen – bitte Angaben prüfen, Kategorie/Konto kontrollieren und speichern.") % {"format": angaben['format']})
        else:
            b.datum = date.today()
            b.betrag = Decimal("0.01")
            b.text = f"E-Rechnung {datei.name}"[:250]
            messages.warning(request, gettext("Datei enthält keine lesbare E-Rechnung (XRechnung/ZUGFeRD) – Beleg wurde trotzdem angehängt, bitte Angaben manuell eintragen."))
        b.save()
        return redirect("buchung_edit", pk=b.pk)
    return render(request, "accounting/erechnung_importieren.html", {"titel": gettext("E-Rechnung importieren")})


@login_required
def buchungen_uebernehmen(request):
    _pruefen(request, "add")
    heute = date.today()
    von, bis = date(heute.year, 1, 1), heute
    if request.method == "POST":
        try:
            von = date.fromisoformat(request.POST["von"])
            bis = date.fromisoformat(request.POST["bis"])
        except (KeyError, ValueError):
            messages.error(request, gettext("Bitte gültige Daten angeben."))
            return redirect("buchungen_uebernehmen")
        z = services.uebernehmen(request.verein, von, bis)
        gesamt = z["zahlung"] + z["spende"] + z["aufwand"] + z["kosten"]
        messages.success(request, gettext("%(gesamt)s Buchungen übernommen (Zahlungen %(zahlung)s, Spenden %(spende)s, Aufwandsentschädigungen %(aufwand)s, Veranstaltungen %(kosten)s).") % {"gesamt": gesamt, "zahlung": z['zahlung'], "spende": z['spende'], "aufwand": z['aufwand'], "kosten": z['kosten']})
        if z["gesperrt"]:
            messages.warning(request, gettext("%(gesperrt)s Buchungen liegen in abgeschlossenen Zeiträumen und wurden nicht gebucht.") % {"gesperrt": z['gesperrt']})
        if z["vor_eroeffnung"]:
            messages.warning(request, gettext("%(vor_eroeffnung)s Buchungen liegen vor der Kontoeröffnung und wurden nicht gebucht.") % {"vor_eroeffnung": z['vor_eroeffnung']})
        return redirect("buchung_list")
    return render(request, "accounting/uebernehmen.html", {"titel": gettext("Buchungen übernehmen"), "von": von, "bis": bis})


# ---------------------------------------------------------------- Kassenbericht
def _zeile(*zellen):
    return {"url": None, "zellen": list(zellen)}


def kassenbericht_kontext(request, b):
    d = berichtsdaten(b)
    rt = request.rechte
    aktionen = [knopf("PDF", reverse("kassenbericht_pdf", args=[b.pk]), stil="primary"),
                knopf("Excel", reverse("kassenbericht_xlsx", args=[b.pk]))]
    if rt.darf("kassenbuch", "change") and b.status == "entwurf":
        aktionen.append(knopf(gettext_lazy("Abschließen (sperrt den Zeitraum, PDF in Ablage)"), reverse("kassenbericht_abschliessen", args=[b.pk]),
                              post=True, stil="success",
                              bestaetigung=gettext("Kassenbericht abschließen? Buchungen im Zeitraum sind danach nicht mehr änderbar.")))
    if rt.darf("kassenbuch", "delete") and b.status == "abgeschlossen":
        aktionen.append(knopf(gettext_lazy("Wieder öffnen"), reverse("kassenbericht_oeffnen", args=[b.pk]), post=True, stil="outline-danger",
                              bestaetigung=gettext("Kassenbericht wieder öffnen? Der Zeitraum wird für Buchungen entsperrt.")))
    hinweise = [gettext("Anfangsbestand %(betrag)s + Einnahmen %(betrag_)s − Ausgaben %(betrag__)s = Endbestand %(betrag___)s  (%(anzahl)s Buchungen)") % {"betrag": geld(d['anfang']), "betrag_": geld(d['einnahmen']), "betrag__": geld(d['ausgaben']), "betrag___": geld(d['ende']), "anzahl": d['anzahl']}]
    ist = d["ist"]
    for name, diff in (("Barkasse", ist["bar_diff"]), ("Bankkonten", ist["bank_diff"])):
        if diff is not None and diff != 0:
            hinweise.append(gettext("Achtung: Differenz %(name)s: %(betrag)s zwischen Buchbestand und Ist-Bestand!") % {"name": name, "betrag": geld(diff)})
    if d["ohne_beleg"]:
        hinweise.append(gettext("%(ohne_beleg)s manuelle Buchungen ohne hochgeladenen Beleg (für die Kassenprüfung ggf. ergänzen).") % {"ohne_beleg": d['ohne_beleg']})
    if b.ablage_id:
        hinweise.append(gettext("In Ablage gespeichert: %(ablage)s") % {"ablage": b.ablage})
    abschnitte = [
        {"titel": gettext("Kontenübersicht"), "spalten": [gettext("Konto"), gettext("Anfangsbestand"), gettext("Einnahmen"), gettext("Ausgaben"), gettext("Endbestand")], "add_url": None,
         "zeilen": [_zeile(k["name"], geld(k["anfang"]), geld(k["einnahmen"]), geld(k["ausgaben"]), geld(k["ende"]))
                    for k in d["konten"]]},
        {"titel": gettext("Einnahmen"), "spalten": [gettext("Sphäre"), gettext("Kategorie"), gettext("Betrag"), gettext("Vorjahr")], "add_url": None,
         "zeilen": [_zeile(g["label"], n, geld(s), geld(v)) for g in d["einnahmen_gruppen"] for n, s, v in g["zeilen"]]
         + [_zeile("", "Summe", geld(d["einnahmen"]), geld(d["vorjahr"]["einnahmen"]))]},
        {"titel": gettext("Ausgaben"), "spalten": [gettext("Sphäre"), gettext("Kategorie"), gettext("Betrag"), gettext("Vorjahr")], "add_url": None,
         "zeilen": [_zeile(g["label"], n, geld(s), geld(v)) for g in d["ausgaben_gruppen"] for n, s, v in g["zeilen"]]
         + [_zeile("", "Summe", geld(d["ausgaben"]), geld(d["vorjahr"]["ausgaben"]))]},
        {"titel": gettext("Ergebnis nach Sphären"), "spalten": [gettext("Sphäre"), gettext("Einnahmen"), gettext("Ausgaben"), gettext("Ergebnis")], "add_url": None,
         "zeilen": [_zeile(l, geld(e), geld(a), geld(r)) for l, e, a, r in d["sphaeren"]]},
    ]
    return {"aktionen": aktionen, "hinweise": hinweise, "abschnitte": abschnitte,
            "vorschau": pdf_vorschau(reverse("kassenbericht_pdf", args=[b.pk]))}


def _bericht(request, pk, aktion):
    _pruefen(request, aktion)
    return get_object_or_404(Kassenbericht, pk=pk, verein=request.verein)


@login_required
@xframe_options_sameorigin
def kassenbericht_pdf_view(request, pk):
    b = _bericht(request, pk, "view")
    r = HttpResponse(kassenbericht_pdf(b), content_type="application/pdf")
    r["Content-Disposition"] = f'inline; filename="{b.titel[:60]}.pdf"'
    return r


@login_required
def kassenbericht_xlsx_view(request, pk):
    b = _bericht(request, pk, "view")
    r = HttpResponse(kassenbericht_xlsx(b), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    r["Content-Disposition"] = f'attachment; filename="{b.titel[:60]}.xlsx"'
    return r


@login_required
@require_POST
def kassenbericht_abschliessen(request, pk):
    b = _bericht(request, pk, "change")
    if b.status != "entwurf":
        return redirect("kassenbericht_detail", pk=b.pk)
    b.status, b.abgeschlossen_am = "abgeschlossen", date.today()
    b.save()
    doc = ablegen(request.verein, b.titel, "kassenbericht", f"{b.titel[:60]}.pdf", kassenbericht_pdf(b), datum=b.bis,
                  beschreibung=f"Zeitraum {b.von:%d.%m.%Y}–{b.bis:%d.%m.%Y}")
    b.ablage = doc
    b.save(update_fields=["ablage", "geaendert"])
    _auto_uebergeben(doc)
    messages.success(request, gettext("Kassenbericht abgeschlossen und als PDF in der Ablage gespeichert."))
    return redirect("kassenbericht_detail", pk=b.pk)


@login_required
@require_POST
def kassenbericht_oeffnen(request, pk):
    b = _bericht(request, pk, "delete")
    b.status, b.abgeschlossen_am = "entwurf", None
    b.save()
    messages.warning(request, gettext("Kassenbericht wieder geöffnet. Der Zeitraum ist für Buchungen entsperrt."))
    return redirect("kassenbericht_detail", pk=b.pk)
