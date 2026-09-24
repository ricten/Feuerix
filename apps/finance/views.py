from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.crud import abschnitt, knopf, wert
from apps.core.util import geld

from . import erechnung, fints_service, kontoauszug, sepa, services
from .forms import FinTSPinForm, FinTSTanForm
from .models import Bankumsatz, Beitragsjahr, FinTSZugang, Mahnung, Rechnung, SepaEinzug, SepaEinzugPosition, Zahlung, wirksame_summe
from .pdf import mahnung_pdf, rechnung_pdf


def _pruefen(request, modul, aktion):
    if request.verein is None:
        raise PermissionDenied
    if not request.rechte.darf(modul, aktion):
        raise PermissionDenied


def _rechnung(request, pk, aktion="change"):
    _pruefen(request, "rechnungen", aktion)
    return get_object_or_404(Rechnung, pk=pk, verein=request.verein)


# ---------------------------------------------------------------- Rechnung
def rechnung_kontext(request, r):
    rt, aktionen = request.rechte, []
    if rt.darf("rechnungen", "view"):
        aktionen.append(knopf("PDF", reverse("rechnung_pdf", args=[r.pk]), stil="primary"))
        if r.status != "entwurf":
            aktionen.append(knopf("E-Rechnung (ZUGFeRD-PDF)", reverse("rechnung_erechnung", args=[r.pk])))
    if rt.darf("rechnungen", "change"):
        if r.status == "entwurf":
            aktionen.append(knopf("Ausstellen (nicht mehr änderbar)", reverse("rechnung_ausstellen", args=[r.pk]),
                                  post=True, stil="success",
                                  bestaetigung="Rechnung ausstellen? Danach ist sie unveränderbar und erhält eine Nummer."))
        if r.status in ("offen", "teilbezahlt", "bezahlt") and r.typ in ("beitrag", "individuell", "sammel"):
            aktionen.append(knopf("Per E-Mail senden", reverse("rechnung_mail", args=[r.pk]), post=True))
            aktionen.append(knopf("Storno", reverse("rechnung_storno", args=[r.pk]), post=True, stil="outline-danger",
                                  bestaetigung="Rechnung stornieren? Es wird eine Stornorechnung erzeugt."))
        if r.status in ("offen", "teilbezahlt"):
            aktionen.append(knopf("Mahnung erzeugen", reverse("rechnung_mahnung", args=[r.pk]), post=True,
                                  stil="outline-warning"))
    if rt.darf("zahlungen", "add"):
        if r.status in ("offen", "teilbezahlt"):
            aktionen.append(knopf("Zahlung erfassen", reverse("zahlung_add") +
                                  f"?rechnung={r.pk}&betrag={r.offen_betrag}"
                                  f"&next={reverse('rechnung_detail', args=[r.pk])}", stil="outline-primary"))
        elif r.rueckzahlung_noetig and r.rueckzahlung_offen > 0:
            aktionen.append(knopf("Rückzahlung buchen", reverse("zahlung_add") +
                                  f"?rechnung={r.pk}&art=rueckzahlung&betrag={r.rueckzahlung_offen}"
                                  f"&next={reverse('rechnung_detail', args=[r.pk])}", stil="outline-primary"))
    abschnitte = [
        abschnitt(request, "Positionen", r.positionen.all(),
                  ("text", "menge", "einzelpreis", "steuersatz", ("betrag", "Netto"), ("bruttobetrag", "Brutto")),
                  "rechnungsposition_add" if r.status == "entwurf" else None, {"rechnung": r.pk}),
        abschnitt(request, "Zahlungen", r.zahlungen.all(), ("datum", "betrag", "art", "ruecklastschrift", "referenz")),
        abschnitt(request, "Mahnungen", r.mahnungen.all(), ("stufe", "datum", "frist", "gebuehr")),
        abschnitt(request, "Storno / Gutschriften", r.gegenbuchungen.all(), ("nummer", "typ", "betrag")),
    ]
    hinweise = [f"Offener Betrag: {geld(r.offen_betrag)}"] if r.status in ("offen", "teilbezahlt") else []
    if r.ueberfaellig:
        hinweise.append("Die Rechnung ist überfällig.")
    if r.rueckzahlung_noetig and r.rueckzahlung_offen > 0:
        hinweise.append(f"Rückzahlung an den Zahler noch offen: {geld(r.rueckzahlung_offen)}.")
    return {"aktionen": aktionen, "abschnitte": abschnitte, "hinweise": hinweise}


@login_required
def rechnung_pdf_view(request, pk):
    r = _rechnung(request, pk, "view")
    resp = HttpResponse(rechnung_pdf(r), content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{r.nummer or "entwurf"}.pdf"'
    return resp


@login_required
def rechnung_erechnung_view(request, pk):
    r = _rechnung(request, pk, "view")
    if r.status == "entwurf":
        messages.error(request, "Entwürfe haben noch keine Rechnungsnummer - bitte zuerst ausstellen.")
        return redirect("rechnung_detail", pk=r.pk)
    try:
        pdf_bytes = erechnung.zugferd_pdf(r)
    except Exception as e:
        messages.error(request, f"E-Rechnung konnte nicht erzeugt werden: {e}")
        return redirect("rechnung_detail", pk=r.pk)
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{r.nummer}-zugferd.pdf"'
    return resp


@login_required
@require_POST
def rechnung_ausstellen(request, pk):
    r = _rechnung(request, pk)
    if r.status != "entwurf":
        messages.error(request, "Nur Entwürfe können ausgestellt werden.")
    elif not r.positionen.exists():
        messages.error(request, "Die Rechnung hat noch keine Positionen.")
    else:
        r.neu_berechnen()
        r.refresh_from_db()
        r.status = "offen"
        r.save()
        messages.success(request, f"Rechnung {r.nummer} ausgestellt.")
    return redirect("rechnung_detail", pk=r.pk)


@login_required
@require_POST
def rechnung_storno(request, pk):
    r = _rechnung(request, pk)
    try:
        s = services.storniere(r)
        text = f"Storniert. Stornorechnung {s.nummer} erstellt."
        if s.rueckzahlung_noetig and s.rueckzahlung_offen > 0:
            text += (f" Es wurden bereits {geld(s.rueckzahlung_offen)} gezahlt – bitte über \"Rückzahlung buchen\" "
                    "auf der Stornorechnung erstatten.")
        messages.success(request, text)
    except ValueError as e:
        messages.error(request, str(e))
    return redirect("rechnung_detail", pk=r.pk)


@login_required
@require_POST
def rechnung_mail(request, pk):
    r = _rechnung(request, pk)
    try:
        services.rechnung_mailen(r)
        messages.success(request, "Rechnung per E-Mail versendet.")
    except Exception as e:  # SMTP- oder Adressfehler
        messages.error(request, f"Versand fehlgeschlagen: {e}")
    return redirect("rechnung_detail", pk=r.pk)


@login_required
@require_POST
def rechnung_mahnung(request, pk):
    r = _rechnung(request, pk)
    m = services.mahnung_erstellen(r)
    messages.success(request, f"{m.get_stufe_display()} erstellt.")
    return redirect("mahnung_detail", pk=m.pk)


def mahnung_kontext(request, m):
    return {"aktionen": [knopf("PDF", reverse("mahnung_pdf", args=[m.pk]), stil="primary")]}


@login_required
def mahnung_pdf_view(request, pk):
    _pruefen(request, "rechnungen", "view")
    m = get_object_or_404(Mahnung, pk=pk, verein=request.verein)
    resp = HttpResponse(mahnung_pdf(m), content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="mahnung-{m.rechnung.nummer}-{m.stufe}.pdf"'
    return resp


# ---------------------------------------------------------------- Beitragsjahr
def beitragsjahr_kontext(request, bj):
    qs = Rechnung.objects.filter(verein=request.verein, typ="beitrag", jahr=bj.jahr).exclude(status="storniert")
    soll = sum((r.betrag for r in qs), Decimal("0"))
    ist = wirksame_summe(qs)
    aktionen = []
    if request.rechte.darf("rechnungen", "add"):
        aktionen.append(knopf("Beitragsrechnungen erzeugen", reverse("beitragsjahr_abrechnen", args=[bj.pk]),
                              post=True, stil="success",
                              bestaetigung="Für alle beitragspflichtigen Mitglieder ohne Rechnung Beitragsrechnungen erzeugen?"))
    if request.rechte.darf("rechnungen", "change"):
        aktionen.append(knopf("Offene Rechnungen per E-Mail versenden", reverse("beitragsjahr_mailen", args=[bj.pk]),
                              post=True, bestaetigung="E-Mails an alle Mitglieder mit Adresse versenden?"))
    aktionen.append(knopf("Rechnungen anzeigen", reverse("rechnung_list") + f"?jahr={bj.jahr}&typ=beitrag"))
    return {"aktionen": aktionen,
            "hinweise": [f"{qs.count()} Rechnungen · Soll {geld(soll)} · bezahlt {geld(ist)} · offen {geld(soll - ist)}"]}


@login_required
@require_POST
def beitragsjahr_abrechnen(request, pk):
    _pruefen(request, "rechnungen", "add")
    bj = get_object_or_404(Beitragsjahr, pk=pk, verein=request.verein)
    n, skip = services.beitragsjahr_abrechnen(bj)
    messages.success(request, f"{n} Beitragsrechnungen erzeugt.")
    if skip:
        messages.warning(request, "Ohne Beitrag übersprungen (Mitgliedsart/Regel fehlt): "
                         + ", ".join(f"{m.name}" for m, _ in skip[:15]) + (" …" if len(skip) > 15 else ""))
    return redirect("beitragsjahr_detail", pk=bj.pk)


@login_required
@require_POST
def beitragsjahr_mailen(request, pk):
    _pruefen(request, "rechnungen", "change")
    from .tasks import rechnung_mailen_task
    bj = get_object_or_404(Beitragsjahr, pk=pk, verein=request.verein)
    n = 0
    for r in Rechnung.objects.filter(verein=request.verein, typ="beitrag", jahr=bj.jahr, status__in=["offen", "teilbezahlt"],
                                     versendet_am__isnull=True, mitglied__email__gt=""):
        rechnung_mailen_task.delay(r.pk)
        n += 1
    messages.success(request, f"{n} E-Mails werden im Hintergrund versendet.")
    return redirect("beitragsjahr_detail", pk=bj.pk)


def beitragsjahr_nach_speichern(request, obj, neu):
    pass


# ---------------------------------------------------------------- Bank
def bankumsatz_kontext(request, u):
    aktionen, abschnitte = [], []
    if request.rechte.darf("bank", "change") and u.status in ("neu", "manuell"):
        offen = Rechnung.objects.filter(verein=request.verein, status__in=["offen", "teilbezahlt"]).select_related("mitglied")[:300]
        return {"aktionen": [knopf("Ignorieren", reverse("bankumsatz_ignorieren", args=[u.pk]), post=True)],
                "zuweisen": {"url": reverse("bankumsatz_zuweisen", args=[u.pk]), "rechnungen": offen}}
    return {"aktionen": aktionen, "abschnitte": abschnitte}


def bank_listen_aktionen(request):
    a = []
    if request.rechte.darf("bank", "add"):
        a.append(knopf("Kontoauszug importieren", reverse("bank_import"), stil="primary"))
        if fints_service.produkt_id_vorhanden():
            for z in FinTSZugang.objects.filter(verein=request.verein):
                a.append(knopf(f"Umsätze abrufen: {z.bezeichnung}", reverse("fints_abrufen", args=[z.pk]),
                               stil="success"))
        a.append(knopf("FinTS-Zugänge", reverse("fintszugang_list")))
    if request.rechte.darf("bank", "change"):
        a.append(knopf("Automatisch zuordnen", reverse("bank_zuordnen"), post=True, stil="success"))
    return a


@login_required
def bank_import(request):
    _pruefen(request, "bank", "add")
    if request.method == "POST" and request.FILES.get("datei"):
        datei = request.FILES["datei"]
        try:
            neu, doppelt, format_ = kontoauszug.importieren(request.verein, datei.name, datei.read())
            ok, manuell = services.zuordnen(request.verein)
            messages.success(request, f"{format_}: {neu} Umsätze importiert ({doppelt} Duplikate übersprungen). "
                                      f"Automatisch zugeordnet: {ok}, manuell erforderlich: {manuell}.")
            return redirect("bankumsatz_list")
        except ValueError as e:
            messages.error(request, str(e))
    return render(request, "finance/bank_import.html", {"titel": "Kontoauszug importieren"})


@login_required
@require_POST
def bank_zuordnen(request):
    _pruefen(request, "bank", "change")
    ok, manuell = services.zuordnen(request.verein)
    messages.success(request, f"Zugeordnet: {ok}, manuelle Zuordnung erforderlich: {manuell}.")
    return redirect("bankumsatz_list")


@login_required
@require_POST
def bankumsatz_zuweisen(request, pk):
    _pruefen(request, "bank", "change")
    u = get_object_or_404(Bankumsatz, pk=pk, verein=request.verein)
    r = get_object_or_404(Rechnung, pk=request.POST.get("rechnung"), verein=request.verein)
    if u.status == "zugeordnet":
        messages.error(request, "Bereits zugeordnet.")
    else:
        try:
            z = Zahlung(verein=request.verein, rechnung=r, datum=u.buchungsdatum, betrag=abs(u.betrag),
                        art="ueberweisung", ruecklastschrift=u.betrag < 0, referenz=u.verwendungszweck[:200],
                        bankumsatz=u)
            z.clean()
            z.save()
            u.status = "zugeordnet"
            u.save(update_fields=["status", "geaendert"])
            messages.success(request, f"Zahlung auf {r.nummer} gebucht.")
        except Exception as e:
            messages.error(request, str(getattr(e, "messages", [e])[0]))
    return redirect("bankumsatz_detail", pk=u.pk)


@login_required
@require_POST
def bankumsatz_ignorieren(request, pk):
    _pruefen(request, "bank", "change")
    u = get_object_or_404(Bankumsatz, pk=pk, verein=request.verein)
    u.status = "ignoriert"
    u.save(update_fields=["status", "geaendert"])
    return redirect("bankumsatz_detail", pk=u.pk)


def fints_zugang_kontext(request, z):
    aktionen = []
    if request.rechte.darf("bank", "add") and fints_service.produkt_id_vorhanden():
        aktionen.append(knopf("Kontodaten abrufen", reverse("fints_kontodaten", args=[z.pk])))
        aktionen.append(knopf("Jetzt abrufen", reverse("fints_abrufen", args=[z.pk]), stil="success"))
    hinweise = []
    if not fints_service.produkt_id_vorhanden():
        hinweise.append("Für diesen Server liegt noch keine FinTS-Produkt-ID vor - der Betreiber muss zuerst eine "
                        "kostenlose Produkt-ID bei der Deutschen Kreditwirtschaft registrieren und entweder "
                        "verschlüsselt unter /admin/ (Systemeinstellungen) oder als Umgebungsvariable "
                        "FINTS_PRODUCT_ID hinterlegen, bevor ein Abruf möglich ist.")
    return {"aktionen": aktionen, "hinweise": hinweise,
            "abschnitte": [abschnitt(request, "Verknüpfte Kassenbuch-Konten", z.konten.all(), ("name", "typ"))]}


def _fints_abbrechen(request, zugang, fehler):
    fints_service.zustand_loeschen(request)
    zugang.letzte_meldung = f"Fehler: {fehler}"[:300]
    zugang.save(update_fields=["letzte_meldung", "geaendert"])
    messages.error(request, f"FinTS-Abruf fehlgeschlagen: {fehler}")
    return redirect("fints_abrufen", pk=zugang.pk)


def _fints_abschliessen(request, zugang, anzahl_neu):
    fints_service.zustand_loeschen(request)
    zugang.letzter_abruf = timezone.now()
    zugang.letzte_meldung = f"{anzahl_neu} neue Umsätze importiert."
    zugang.save(update_fields=["letzter_abruf", "letzte_meldung", "geaendert"])
    messages.success(request, zugang.letzte_meldung)
    return redirect("bankumsatz_list")


@login_required
def fints_abrufen(request, pk):
    _pruefen(request, "bank", "add")
    zugang = get_object_or_404(FinTSZugang, pk=pk, verein=request.verein)
    if not fints_service.produkt_id_vorhanden():
        messages.error(request, "Für diesen Server liegt noch keine FinTS-Produkt-ID vor - der Betreiber muss "
                                "zuerst eine kostenlose Produkt-ID bei der Deutschen Kreditwirtschaft registrieren "
                                "und entweder verschlüsselt unter /admin/ (Systemeinstellungen) oder als "
                                "Umgebungsvariable FINTS_PRODUCT_ID hinterlegen.")
        return redirect("fintszugang_detail", pk=zugang.pk)

    zustand = fints_service.zustand_laden(request)
    if zustand and zustand.get("zugang_pk") != zugang.pk:
        fints_service.zustand_loeschen(request)
        zustand = None

    if zustand:
        tan_form = FinTSTanForm(request.POST or None, decoupled=zustand.get("decoupled", False))
        if request.method == "POST" and tan_form.is_valid():
            von, bis = date.fromisoformat(zustand["von"]), date.fromisoformat(zustand["bis"])
            try:
                client, dialog_data, tan_response, konten_rest = fints_service.client_und_dialog_aus_zustand(zustand, zugang)
                with client.resume_dialog(dialog_data):
                    ergebnis = client.send_tan(tan_response, tan_form.cleaned_data["tan"])
                    status, wert, rest = fints_service.naechster_schritt_nach_tan(
                        client, request.verein, von, bis, konten_rest, ergebnis, zugang)
                    if status == "tan":
                        neue_dialog_data = client.pause_dialog()
                if status == "tan":
                    fints_service.zustand_speichern(request, zugang, zustand["pin"], von, bis, client, wert, rest,
                                                    neue_dialog_data)
                    messages.info(request, "Die Bank verlangt eine weitere TAN.")
                    return redirect("fints_abrufen", pk=zugang.pk)
                return _fints_abschliessen(request, zugang, wert)
            except Exception as e:
                return _fints_abbrechen(request, zugang, e)
        return render(request, "finance/fints_abrufen.html", {
            "titel": "FinTS-Abruf – TAN erforderlich", "tan_form": tan_form, "zustand": zustand, "schritt": "tan"})

    pin_form = FinTSPinForm(request.POST or None)
    if request.method == "POST" and pin_form.is_valid():
        pin = pin_form.cleaned_data["pin"]
        von, bis = date.today() - timedelta(days=zugang.tage), date.today()
        try:
            client = fints_service.neuer_client(zugang, pin)
            with client:
                status, wert, rest = fints_service.naechster_schritt(client, request.verein, von, bis, None, zugang)
                if status == "tan":
                    dialog_data = client.pause_dialog()
            if status == "tan":
                fints_service.zustand_speichern(request, zugang, pin, von, bis, client, wert, rest, dialog_data)
                return redirect("fints_abrufen", pk=zugang.pk)
            return _fints_abschliessen(request, zugang, wert)
        except Exception as e:
            return _fints_abbrechen(request, zugang, e)
    return render(request, "finance/fints_abrufen.html", {
        "titel": "FinTS-Abruf", "pin_form": pin_form, "zugang": zugang, "schritt": "pin"})


@login_required
def fints_kontodaten(request, pk):
    """Ruft nur die Kontenliste eines FinTS-Zugangs ab (kein Transaktions-Import) - zeigt, welche Konten
    (IBAN/BIC) hinter der Verbindung stehen, z. B. um die richtige Zuordnung eines Kassenbuch-Kontos zu prüfen."""
    _pruefen(request, "bank", "add")
    zugang = get_object_or_404(FinTSZugang, pk=pk, verein=request.verein)
    if not fints_service.produkt_id_vorhanden():
        messages.error(request, "Für diesen Server liegt noch keine FinTS-Produkt-ID vor - der Betreiber muss "
                                "zuerst eine kostenlose Produkt-ID bei der Deutschen Kreditwirtschaft registrieren "
                                "und entweder verschlüsselt unter /admin/ (Systemeinstellungen) oder als "
                                "Umgebungsvariable FINTS_PRODUCT_ID hinterlegen.")
        return redirect("fintszugang_detail", pk=zugang.pk)

    zustand = fints_service.konten_zustand_laden(request)
    if zustand and zustand.get("zugang_pk") != zugang.pk:
        fints_service.konten_zustand_loeschen(request)
        zustand = None

    if zustand:
        tan_form = FinTSTanForm(request.POST or None, decoupled=zustand.get("decoupled", False))
        if request.method == "POST" and tan_form.is_valid():
            try:
                client, dialog_data, tan_response = fints_service.konten_client_und_dialog_aus_zustand(zustand, zugang)
                with client.resume_dialog(dialog_data):
                    status, wert, phase = fints_service.konten_schritt_nach_tan(
                        client, tan_response, tan_form.cleaned_data["tan"], zustand["phase"])
                    if status == "tan":
                        neue_dialog_data = client.pause_dialog()
                if status == "tan":
                    fints_service.konten_zustand_speichern(request, zugang, zustand["pin"], client, wert, phase,
                                                           neue_dialog_data)
                    messages.info(request, "Die Bank verlangt eine weitere TAN.")
                    return redirect("fints_kontodaten", pk=zugang.pk)
                fints_service.konten_zustand_loeschen(request)
                return render(request, "finance/fints_kontodaten.html", {
                    "titel": "Kontodaten", "zugang": zugang, "schritt": "ergebnis", "konten": wert})
            except Exception as e:
                fints_service.konten_zustand_loeschen(request)
                messages.error(request, f"Kontodaten-Abruf fehlgeschlagen: {e}")
                return redirect("fints_kontodaten", pk=zugang.pk)
        return render(request, "finance/fints_kontodaten.html", {
            "titel": "Kontodaten – TAN erforderlich", "tan_form": tan_form, "zustand": zustand, "zugang": zugang,
            "schritt": "tan"})

    pin_form = FinTSPinForm(request.POST or None)
    if request.method == "POST" and pin_form.is_valid():
        pin = pin_form.cleaned_data["pin"]
        try:
            client = fints_service.neuer_client(zugang, pin)
            with client:
                status, wert, phase = fints_service.konten_schritt(client)
                if status == "tan":
                    dialog_data = client.pause_dialog()
            if status == "tan":
                fints_service.konten_zustand_speichern(request, zugang, pin, client, wert, phase, dialog_data)
                return redirect("fints_kontodaten", pk=zugang.pk)
            return render(request, "finance/fints_kontodaten.html", {
                "titel": "Kontodaten", "zugang": zugang, "schritt": "ergebnis", "konten": wert})
        except Exception as e:
            messages.error(request, f"Kontodaten-Abruf fehlgeschlagen: {e}")
            return redirect("fintszugang_detail", pk=zugang.pk)
    return render(request, "finance/fints_kontodaten.html", {
        "titel": "Kontodaten abrufen", "pin_form": pin_form, "zugang": zugang, "schritt": "pin"})


# ---------------------------------------------------------------- SEPA-Einzug
def sepa_einzug_kontext(request, e):
    return {"abschnitte": [abschnitt(request, "Positionen", e.positionen.all(),
                                     ("mitglied", "rechnung", "betrag", "sequenztyp"))]}


def sepa_einzuege_listen_aktionen(request):
    a = []
    if request.rechte.darf("zahlungen", "add"):
        a.append(knopf("Neuen Einzug erstellen", reverse("sepa_einzug_neu"), stil="success"))
    return a


@login_required
def sepa_einzug_neu(request):
    _pruefen(request, "zahlungen", "add")
    v = request.verein
    rechnungen = list(sepa.eligible_rechnungen(v))
    bereits_eingezogen = set(SepaEinzugPosition.objects.filter(verein=v).values_list("mitglied_id", flat=True))
    if request.method == "POST":
        try:
            faelligkeitsdatum = date.fromisoformat(request.POST.get("faelligkeitsdatum", ""))
        except ValueError:
            messages.error(request, "Bitte ein gültiges Fälligkeitsdatum angeben.")
            return redirect("sepa_einzug_neu")
        ids = [int(pk) for pk in request.POST.getlist("rechnungen") if pk.isdigit()]
        if not ids:
            messages.error(request, "Bitte mindestens eine Rechnung auswählen.")
            return redirect("sepa_einzug_neu")
        try:
            e = sepa.einzug_erstellen(v, faelligkeitsdatum, ids)
        except ValueError as ex:
            messages.error(request, str(ex))
            return redirect("sepa_einzug_neu")
        messages.success(request, f"SEPA-Einzug {e.nummer} mit {e.anzahl} Lastschrift(en) über {geld(e.summe)} "
                                  "erstellt.")
        return redirect("sepaeinzug_detail", pk=e.pk)
    zeilen = [{"r": r, "sequenztyp": "RCUR" if r.mitglied_id in bereits_eingezogen else "FRST"} for r in rechnungen]
    return render(request, "finance/sepa_einzug_neu.html", {
        "titel": "Neuen SEPA-Einzug erstellen", "zeilen": zeilen,
        "vorschlag_datum": date.today() + timedelta(days=6),
        "verein_unvollstaendig": not (v.iban and v.glaeubiger_id)})
