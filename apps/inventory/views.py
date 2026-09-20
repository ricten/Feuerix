from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.crud import abschnitt, knopf

from .models import Gegenstand, Inventur, Inventurposition, Verleih
from .pdf import leihschein_pdf


def _pruefen(request, modul, aktion):
    if request.verein is None or not request.rechte.darf(modul, aktion):
        raise PermissionDenied


# ---------------------------------------------------------------- Gegenstand
def gegenstand_kontext(request, g):
    aktionen = []
    if request.rechte.darf("verleih", "add") and g.verleihbar:
        aktionen.append(knopf("Verleih / Reservierung anlegen", reverse("verleih_add") + f"?gegenstand={g.pk}",
                              stil="primary"))
    hinweise = []
    akt = g.aktuell_verliehen
    if akt:
        hinweise.append(f"Aktuell verliehen an {akt.wer} bis {akt.bis:%d.%m.%Y}.")
    if g.garantie_bis and g.garantie_bis < date.today():
        hinweise.append("Garantie abgelaufen.")
    abschnitte = []
    if request.rechte.darf("verleih", "view"):
        abschnitte.append(abschnitt(request, "Verleihhistorie", g.verleihe.all(),
                                    ("von", "bis", ("wer", "Entleiher"), "status", "veranstaltung")))
    return {"aktionen": aktionen, "hinweise": hinweise, "abschnitte": abschnitte}


# ---------------------------------------------------------------- Verleih
def verleih_kontext(request, v):
    rt, aktionen = request.rechte, [knopf("Leihschein (PDF)", reverse("verleih_leihschein", args=[v.pk]))]
    if rt.darf("verleih", "change"):
        if v.status == "reserviert":
            aktionen.append(knopf("Ausgeben", reverse("verleih_ausgeben", args=[v.pk]), post=True, stil="success"))
            aktionen.append(knopf("Reservierung stornieren", reverse("verleih_stornieren", args=[v.pk]), post=True,
                                  stil="outline-danger", bestaetigung="Reservierung stornieren?"))
        if v.status == "ausgegeben":
            aktionen.append(knopf("Rückgabe – in Ordnung", reverse("verleih_rueckgabe", args=[v.pk]), post=True,
                                  stil="success", felder={"zustand": v.gegenstand.zustand}))
            aktionen.append(knopf("Rückgabe – defekt", reverse("verleih_rueckgabe", args=[v.pk]), post=True,
                                  stil="outline-danger", felder={"zustand": "defekt"},
                                  bestaetigung="Gegenstand als defekt markieren?"))
    hinweise = []
    if v.ueberfaellig:
        hinweise.append("Rückgabe überfällig!")
    if v.status == "zurueckgegeben" and v.kaution and not v.kaution_zurueckgezahlt:
        hinweise.append(f"Kaution ({v.kaution} €) noch nicht als zurückgezahlt markiert.")
    return {"aktionen": aktionen, "hinweise": hinweise}


def _verleih(request, pk):
    _pruefen(request, "verleih", "change")
    return get_object_or_404(Verleih, pk=pk, verein=request.verein)


@login_required
@require_POST
def verleih_ausgeben(request, pk):
    v = _verleih(request, pk)
    if v.status != "reserviert":
        messages.error(request, "Nur Reservierungen können ausgegeben werden.")
    elif v.gegenstand.zustand in ("defekt", "ausgesondert"):
        messages.error(request, "Gegenstand ist defekt bzw. ausgesondert.")
    else:
        v.status, v.ausgegeben_am = "ausgegeben", timezone.now()
        v.ausgegeben_von = request.user.get_username()
        v.zustand_bei_ausgabe = v.gegenstand.zustand
        v.save()
        messages.success(request, "Ausgegeben.")
    return redirect("verleih_detail", pk=v.pk)


@login_required
@require_POST
def verleih_rueckgabe(request, pk):
    v = _verleih(request, pk)
    zustand = request.POST.get("zustand", "")
    if v.status != "ausgegeben":
        messages.error(request, "Nur ausgegebene Gegenstände können zurückgenommen werden.")
    elif zustand not in dict(Gegenstand.ZUSTAND):
        messages.error(request, "Ungültiger Zustand.")
    else:
        v.status, v.zurueckgegeben_am, v.zustand_bei_rueckgabe = "zurueckgegeben", timezone.now(), zustand
        v.save()
        if v.gegenstand.zustand != zustand:
            v.gegenstand.zustand = zustand
            v.gegenstand.save()
        messages.success(request, "Rückgabe gebucht." + (" Bitte Kaution zurückzahlen." if v.kaution else ""))
    return redirect("verleih_detail", pk=v.pk)


@login_required
@require_POST
def verleih_stornieren(request, pk):
    v = _verleih(request, pk)
    if v.status == "reserviert":
        v.status = "storniert"
        v.save()
    return redirect("verleih_detail", pk=v.pk)


@login_required
def verleih_leihschein(request, pk):
    _pruefen(request, "verleih", "view")
    v = get_object_or_404(Verleih, pk=pk, verein=request.verein)
    r = HttpResponse(leihschein_pdf(v), content_type="application/pdf")
    r["Content-Disposition"] = f'inline; filename="leihschein-{v.pk}.pdf"'
    return r


# ---------------------------------------------------------------- Inventur
def inventur_kontext(request, inv):
    z = inv.zaehlung()
    aktionen = []
    if request.rechte.darf("inventur", "change") and inv.status == "laufend":
        aktionen.append(knopf("Inventur abschließen", reverse("inventur_abschliessen", args=[inv.pk]), post=True,
                              stil="success", bestaetigung="Inventur abschließen? Danach sind die Ergebnisse fixiert."))
    gesamt = sum(z.values())
    hinweise = [f"{gesamt} Gegenstände · ✓ {z['gefunden']} gefunden · ⚠ {z['nicht_gefunden']} nicht gefunden · "
                f"⚠ {z['beschaedigt']} beschädigt · offen {z['offen']}"]
    zeilen = []
    kann = request.rechte.darf("inventur", "change") and inv.status == "laufend"
    filt = request.GET.get("zeige", "")
    for p in inv.positionen.all():
        if filt and p.ergebnis != filt:
            continue
        akt = []
        if kann:
            for erg, label, stil in (("gefunden", "✓", "success"), ("nicht_gefunden", "✗", "danger"),
                                     ("beschaedigt", "⚠", "warning")):
                akt.append(knopf(label, reverse("inventurposition_setzen", args=[p.pk]), post=True,
                                 stil=("" if p.ergebnis != erg else "") + stil, felder={"ergebnis": erg}))
        zeilen.append({"url": None, "zellen": [p.inventarnummer, p.bezeichnung, p.standort_text,
                                                p.get_ergebnis_display()], "aktionen": akt})
    return {"aktionen": aktionen, "hinweise": hinweise, "abschnitte": [
        {"titel": "Positionen" + (f" (Filter: {filt})" if filt else ""),
         "spalten": ["Nr.", "Bezeichnung", "Standort (Soll)", "Ergebnis"], "zeilen": zeilen, "add_url": None,
         "mit_aktionen": True}]}


@login_required
@require_POST
def inventurposition_setzen(request, pk):
    _pruefen(request, "inventur", "change")
    p = get_object_or_404(Inventurposition, pk=pk, verein=request.verein)
    if p.inventur.status != "laufend":
        raise PermissionDenied
    erg = request.POST.get("ergebnis")
    if erg in dict(Inventurposition.ERGEBNIS):
        p.ergebnis = erg
        p.save(update_fields=["ergebnis", "geaendert"])
    return redirect("inventur_detail", pk=p.inventur_id)


@login_required
@require_POST
def inventur_abschliessen(request, pk):
    _pruefen(request, "inventur", "change")
    inv = get_object_or_404(Inventur, pk=pk, verein=request.verein)
    if inv.status == "laufend":
        inv.status, inv.abgeschlossen_am = "abgeschlossen", date.today()
        inv.save()
        messages.success(request, "Inventur abgeschlossen.")
    return redirect("inventur_detail", pk=inv.pk)
