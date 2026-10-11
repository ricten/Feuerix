from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Max
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext as _

from apps.core.anbindungen import anbindungen
from apps.core.crud import abschnitt, knopf
from apps.core.util import geld

from .models import Anmeldung, Aufgabe, Schicht, Schichteinsatz, Tagesordnungspunkt, Veranstaltung
from .helfer import finde_mitglied
from .pdf import schichtplan_pdf

STANDARD_TOP = [
    ("Begrüßung und Feststellung der ordnungsgemäßen Einladung und Beschlussfähigkeit", ""),
    ("Genehmigung der Tagesordnung", ""),
    ("Genehmigung des Protokolls der letzten Versammlung", ""),
    ("Bericht des Vorstands", ""),
    ("Kassenbericht", ""),
    ("Bericht der Kassenprüfer", ""),
    ("Entlastung des Vorstands", ""),
    ("Wahlen (falls vorgesehen)", ""),
    ("Anträge", ""),
    ("Verschiedenes", ""),
]



def naechste_top_position(veranstaltung):
    """Vorschlag fuer die Position eines neuen Tagesordnungspunkts: hoechste vorhandene + 1 (bei Luecken oder
    Doppelten waere "Anzahl + 1" bereits vergeben)."""
    hoechste = veranstaltung.tagesordnung.aggregate(m=Max("position"))["m"]
    return (hoechste or 0) + 1

def packlisten_knoepfe(v):
    """Knoepfe zur druckbaren Packliste je Verleih-Vorgang (bzw. Einzelverleih) dieser Veranstaltung - laufende zuerst,
    stornierte werden nicht beruecksichtigt. Mehrere Vorgaenge (z. B. verschiedene Entleiher) bekommen je einen Knopf."""
    aktiv = ("reserviert", "ausgegeben")
    positionen = sorted(v.verleihe.exclude(status="storniert").select_related("entleiher", "veranstaltung"),
                        key=lambda p: (p.status not in aktiv, p.pk))
    ziele, gesehen = [], set()
    for p in positionen:
        schluessel = p.vorgang or ("einzel", p.pk)
        if schluessel in gesehen:
            continue
        gesehen.add(schluessel)
        ziele.append((p, reverse("verleih_vorgang_packliste", args=[p.vorgang]) if p.vorgang
                      else reverse("verleih_packliste", args=[p.pk])))
    return [knopf("Packliste drucken (PDF)" if len(ziele) == 1 else f"Packliste: {p.wer}", url, stil="outline-primary")
            for p, url in ziele[:4]]


def veranstaltung_kontext(request, v):
    r = request.rechte
    aktionen = []
    if r.darf("verleih", "add"):
        aktionen.append(knopf("Inventar reservieren", reverse("verleih_sammel_add") + f"?veranstaltung={v.pk}"
                              f"&von={timezone.localtime(v.beginn):%Y-%m-%d}"
                              f"&bis={timezone.localtime(v.ende or v.beginn):%Y-%m-%d}"))
    if r.darf("veranstaltungen", "view") and v.schichten.exists():
        aktionen.append(knopf("Schichtplan drucken (PDF)", reverse("veranstaltung_schichtplan_pdf", args=[v.pk]),
                              stil="outline-primary"))
    if r.darf("verleih", "view"):   # Packliste(n) des zur Veranstaltung verliehenen/reservierten Inventars
        aktionen += packlisten_knoepfe(v)
    if r.darf("schriftverkehr", "add"):
        aktionen.append(knopf("Einladung erstellen", reverse("veranstaltung_schriftstueck", args=[v.pk, "einladung"]),
                              post=True, stil="primary"))
        aktionen.append(knopf("Einladung an Mitglieder (Serienbrief)",
                              reverse("veranstaltung_schriftstueck", args=[v.pk, "serienbrief"]), post=True))
        aktionen.append(knopf("Protokoll erstellen", reverse("veranstaltung_schriftstueck", args=[v.pk, "protokoll"]),
                              post=True))
    if r.darf("veranstaltungen", "change") and not v.tagesordnung.exists():
        aktionen.append(knopf("Standard-Tagesordnung (Mitgliederversammlung)", reverse("tagesordnung_standard", args=[v.pk]),
                              post=True, stil="outline-secondary"))
    if r.darf("openslides", "change"):
        if anbindungen(request).openslides:
            aktionen.append(knopf("Tagesordnung nach OpenSlides übertragen" if v.openslides_meeting_id
                                  else "In OpenSlides anlegen", reverse("veranstaltung_openslides", args=[v.pk]), post=True,
                                  stil="outline-success"))
            if v.openslides_meeting_id:
                aktionen.append(knopf("Anwesenheit, Wahlen und Abstimmungen aus OpenSlides übernehmen",
                                      reverse("veranstaltung_wahlergebnisse", args=[v.pk]), post=True,
                                      stil="outline-success",
                                      bestaetigung="Anwesenheit, Wahlen und Abstimmungen aus OpenSlides abrufen? Zuvor übernommene "
                                                   "Ergebnisse dieser Veranstaltung werden dabei ersetzt."))
    s = v.summen()
    hinweise = [f"Plan: Einnahmen {geld(s['plan_ein'])} · Ausgaben {geld(s['plan_aus'])} · "
                f"Ergebnis {geld(s['plan_ein'] - s['plan_aus'])}",
                f"Ist: Einnahmen {geld(s['ist_ein'])} · Ausgaben {geld(s['ist_aus'])} · "
                f"Ergebnis {geld(s['ist_ein'] - s['ist_aus'])}"]
    zugesagt = sum(a.personen for a in v.anmeldungen.filter(status="zugesagt"))
    if v.anmeldungen.exists():
        hinweise.append(f"Zugesagte Personen: {zugesagt}" + (f" von erwartet {v.erwartete_teilnehmer}"
                                                             if v.erwartete_teilnehmer else ""))
    if v.anmeldung_erforderlich:
        link = request.build_absolute_uri(reverse("veranstaltung_rueckmeldung", args=[v.rueckmeldung_code]))
        hinweise.append(format_html('{} <a href="{}">{}</a>', "Rückmeldungs-Link zum Weitergeben:", link, link))
    if v.helfer_eintragung:
        helfer_link = request.build_absolute_uri(reverse("veranstaltung_helfer", args=[v.rueckmeldung_code]))
        hinweise.append(format_html('{} <a href="{}">{}</a>', "Helfer-Link zum Weitergeben (Selbsteintrag in Schichten):",
                                    helfer_link, helfer_link))
    offene_schichten = [sc for sc in v.schichten.all() if sc.einsaetze.count() < sc.benoetigt]
    if offene_schichten:
        hinweise.append(f"{len(offene_schichten)} Schicht(en) noch nicht voll besetzt.")
    ab = [abschnitt(request, "Aufgaben", v.aufgaben.all(), ("titel", "zustaendig", "faellig", "status"),
                    "aufgabe_add", {"veranstaltung": v.pk}),
          abschnitt(request, "Schichtplan", v.schichten.all(), ("bezeichnung", "beginn", "ende", ("besetzung", "Besetzung"),
                                                               ("helfer", "Helfer")), "schicht_add", {"veranstaltung": v.pk}),
          abschnitt(request, "Budget", v.kosten.all(), ("art", "bezeichnung", "plan_betrag", "ist_betrag"),
                    "kostenposition_add", {"veranstaltung": v.pk})]
    top_spalten = ("position", "titel") + (("openslides_topic_id",) if anbindungen(request).openslides else ())
    ab.insert(0, abschnitt(request, "Tagesordnung", v.tagesordnung.all(), top_spalten,
                           "tagesordnungspunkt_add", {"veranstaltung": v.pk, "position": naechste_top_position(v)}))
    if r.darf("teilnehmer", "view"):
        ab.insert(2, abschnitt(request, "Anmeldungen", v.anmeldungen.all(), (("wer", "Name"), "personen", "status"),
                               "anmeldung_add", {"veranstaltung": v.pk}))
    if r.darf("teilnehmer", "view") and v.anwesenheiten.exists():
        ab.append(abschnitt(request, "Anwesenheit (aus OpenSlides)", v.anwesenheiten.select_related("mitglied"),
                            (("wer", "Name"),)))
    if v.wahlergebnisse.filter(art="abstimmung").exists():
        ab.append(abschnitt(request, "Abstimmungen (aus OpenSlides)", v.wahlergebnisse.filter(art="abstimmung"),
                            ("amt", "wahlgang")))
    if v.wahlergebnisse.filter(art="wahl").exists():
        ab.append(abschnitt(request, "Wahlergebnisse (aus OpenSlides)", v.wahlergebnisse.filter(art="wahl"),
                            ("amt", "wahlgang")))
    if r.darf("verleih", "view"):
        ab.append(abschnitt(request, "Reserviertes Inventar", v.verleihe.all(), ("gegenstand", "von", "bis", "status")))
    if r.darf("schriftverkehr", "view"):
        ab.append(abschnitt(request, "Schriftstücke (Einladung, Protokoll …)", v.schriftstuecke.all(),
                            ("datum", "titel", "art", "status")))
    if r.darf("rundschreiben", "view"):
        ab.append(abschnitt(request, "Serienbriefe", v.serienbriefe.all(), ("datum", "titel", "versendet_am")))
    if r.darf("ablage", "view"):
        ab.append(abschnitt(request, "Ablage zu dieser Veranstaltung", v.ablage.all(),
                            ("datum", "titel", "kategorie", "version"), "ablagedokument_add",
                            {"veranstaltung": v.pk, "kategorie": "protokoll"}))
    if v.openslides_meeting_id and anbindungen(request).openslides:
        hinweise.append(f"OpenSlides-Versammlung Nr. {v.openslides_meeting_id} ist verknüpft.")
    return {"aktionen": aktionen, "hinweise": hinweise, "abschnitte": ab}


def rueckmeldung(request, code):
    """Öffentliche Zu-/Absage zu einer Veranstaltung mit Rückmeldepflicht - ohne Anmeldung, über einen nicht
    erratbaren Link (siehe Hinweis auf der Veranstaltungsseite, zum Weitergeben an die Eingeladenen)."""
    v = get_object_or_404(Veranstaltung, rueckmeldung_code=code, anmeldung_erforderlich=True)
    frist_abgelaufen = bool(v.anmeldeschluss and v.anmeldeschluss < date.today())
    gespeichert = None
    if request.method == "POST" and not frist_abgelaufen:
        name = request.POST.get("name", "").strip()
        status = request.POST.get("status")
        if name and status in ("zugesagt", "abgesagt"):
            try:
                personen = max(1, int(request.POST.get("personen") or 1))
            except ValueError:
                personen = 1
            Anmeldung.objects.update_or_create(
                verein_id=v.verein_id, veranstaltung=v, mitglied=None, name=name,
                defaults={"status": status, "personen": personen,
                         "bemerkung": request.POST.get("bemerkung", "")[:200]})
            gespeichert = status
        else:
            messages.error(request, _("Bitte Ihren Namen angeben."))
    return render(request, "events/rueckmeldung.html",
                 {"veranstaltung": v, "frist_abgelaufen": frist_abgelaufen, "gespeichert": gespeichert,
                  "titel": f"{_('Rückmeldung')} – {v.titel}"})


@login_required
@require_POST
def tagesordnung_standard(request, pk):
    if request.verein is None or not request.rechte.darf("veranstaltungen", "change"):
        raise PermissionDenied
    v = get_object_or_404(Veranstaltung, pk=pk, verein=request.verein)
    if not v.tagesordnung.exists():
        for i, (titel, text) in enumerate(STANDARD_TOP, 1):
            Tagesordnungspunkt.objects.create(verein=request.verein, veranstaltung=v, position=i, titel=titel,
                                              beschreibung=text)
        messages.success(request, "Standard-Tagesordnung angelegt – bitte anpassen.")
    return redirect("veranstaltung_detail", pk=v.pk)


def schicht_kontext(request, s):
    """Detailseite einer Schicht: alle Eingeteilten (Mitglieder und Gaeste, mit Kontakt) und die freien Plaetze."""
    hinweise = [f"{s.freie_plaetze} von {s.benoetigt} Plätzen noch frei."] if s.freie_plaetze else []
    return {"aktionen": [knopf("Schichtplan der Veranstaltung drucken (PDF)",
                               reverse("veranstaltung_schichtplan_pdf", args=[s.veranstaltung_id]), stil="outline-primary")],
            "hinweise": hinweise,
            "abschnitte": [_helfer_abschnitt(request, s)]}


def _helfer_abschnitt(request, s):
    """Tabelle der Eingeteilten einer Schicht. Den Kontakt aus der Mitgliedsakte (wenn beim Selbsteintrag keiner angegeben
    wurde) sieht nur, wer Mitgliederdaten sehen darf."""
    mit_kontakt = request.rechte.darf("mitglieder", "view")
    abschnitt_ = abschnitt(request, "Eingeteilte Helfer", s.einsaetze.none(), ("id",), "schichteinsatz_add",
                           {"schicht": s.pk, "next": request.get_full_path()})
    abschnitt_["spalten"] = ["Helfer", "Zuordnung", "Kontakt", "Bemerkung", "Selbst eingetragen"]
    abschnitt_["zeilen"] = [
        {"url": reverse("schichteinsatz_detail", args=[e.pk]),
         "zellen": [e.wer, e.zuordnung, e.kontakt_anzeige(mit_kontakt) or "–", e.bemerkung or "–",
                    "✓" if e.selbst_eingetragen else "✗"]}
        for e in sorted(s.einsaetze.select_related("mitglied"), key=lambda e: e.wer.casefold())]
    return abschnitt_


@login_required
def schichtplan_pdf_view(request, pk):
    if request.verein is None or not request.rechte.darf("veranstaltungen", "view"):
        raise PermissionDenied
    v = get_object_or_404(Veranstaltung, pk=pk, verein=request.verein)
    r = HttpResponse(schichtplan_pdf(v, mit_mitgliedskontakt=request.rechte.darf("mitglieder", "view")),
                     content_type="application/pdf")
    r["Content-Disposition"] = f'inline; filename="schichtplan-{v.pk}.pdf"'
    return r


def helfer_anmeldung(request, code):
    """Oeffentliche Seite (ohne Anmeldung, ueber den nicht erratbaren Veranstaltungs-Link), auf der sich Helfer selbst in
    freie Schichten eintragen. Sichtbar sind nur Schichten mit Zeit und freien Plaetzen - keine Namen anderer Helfer."""
    v = get_object_or_404(Veranstaltung, rueckmeldung_code=code, helfer_eintragung=True)
    geschlossen = v.status in ("abgesagt", "abgeschlossen")
    jetzt = timezone.now()
    eingetragen, voll, schon = [], [], []
    if request.method == "POST" and not geschlossen and not request.POST.get("website"):   # "website": Spam-Falle
        name = " ".join(request.POST.get("name", "").split())[:150]
        kontakt = request.POST.get("kontakt", "").strip()[:150]
        ist_mitglied = request.POST.get("mitglied") == "ja"
        try:
            nummer = int(request.POST.get("mitgliedsnummer", "").strip() or 0) or None
        except ValueError:
            nummer = None
        try:
            ids = [int(x) for x in request.POST.getlist("schicht")][:10]
        except ValueError:
            ids = []
        if not name:
            messages.error(request, _("Bitte Ihren Namen angeben."))
        elif not ids:
            messages.error(request, _("Bitte mindestens eine Schicht auswählen."))
        else:
            # Gibt der Helfer an, Mitglied zu sein, wird er - wenn eindeutig gefunden - dem Mitglied zugeordnet (dann stehen
            # Name und weitere Daten aus der Mitgliedsakte zur Verfuegung). Die Seite verraet dem Besucher NICHT, ob ein
            # Mitglied gefunden wurde (kein Abfragen der Mitgliederliste ueber das oeffentliche Formular).
            mitglied = finde_mitglied(v.verein_id, name, nummer) if ist_mitglied else None
            with transaction.atomic():   # gleichzeitige Eintragungen duerfen eine Schicht nicht ueberbuchen
                for s in Schicht.objects.select_for_update().filter(pk__in=ids, veranstaltung=v, ende__gte=jetzt):
                    bereits = (s.einsaetze.filter(mitglied=mitglied).exists() if mitglied else
                               s.einsaetze.filter(mitglied__isnull=True, name__iexact=name).exists())
                    if bereits:
                        schon.append(s)
                    elif s.einsaetze.count() >= s.benoetigt:
                        voll.append(s)
                    else:
                        Schichteinsatz.objects.create(
                            verein_id=v.verein_id, schicht=s, mitglied=mitglied, name="" if mitglied else name,
                            kontakt=kontakt, selbst_eingetragen=True, mitglied_angegeben=ist_mitglied)
                        eingetragen.append(s)
    schichten = [s for s in v.schichten.order_by("beginn", "id") if s.ende >= jetzt]
    return render(request, "events/helfer.html", {
        "veranstaltung": v, "schichten": [(s, s.freie_plaetze) for s in schichten], "geschlossen": geschlossen,
        "eingetragen": eingetragen, "voll": voll, "schon": schon, "name": request.POST.get("name", ""),
        "ist_mitglied": request.POST.get("mitglied") == "ja", "mitgliedsnummer": request.POST.get("mitgliedsnummer", ""),
        "titel": f"{_('Helfer gesucht')} – {v.titel}"})


def aufgabe_kontext(request, a):
    ctx = {"abschnitte": [abschnitt(request, "Zwischennotizen (wie ein Ticket-Verlauf)", a.notizen.all(),
                                   ("erstellt", "erstellt_von", "text"), "aufgabenotiz_add",
                                   {"aufgabe": a.pk, "next": request.get_full_path()})],
          "aufgabe_beobachten": {"url": reverse("aufgabe_beobachten", args=[a.pk]),
                                 "beobachtet": a.beobachter.filter(pk=request.user.pk).exists()}}
    if a.status != "erledigt" and request.rechte.darf("veranstaltungen", "change"):
        ctx["aufgabe_erledigen"] = {"url": reverse("aufgabe_erledigen", args=[a.pk]), "ergebnis": a.ergebnis}
    return ctx


@login_required
@require_POST
def aufgabe_erledigen(request, pk):
    a = get_object_or_404(Aufgabe, pk=pk, verein=request.verein)
    if not request.rechte.darf("veranstaltungen", "change"):
        raise PermissionDenied
    ergebnis = request.POST.get("ergebnis", "").strip()
    if not ergebnis:
        messages.error(request, _("Bitte ein Ergebnis eintragen."))
    else:
        a.status, a.ergebnis = "erledigt", ergebnis
        a.save()
        messages.success(request, _("Aufgabe als erledigt markiert."))
    return redirect("aufgabe_detail", pk=a.pk)


@login_required
@require_POST
def aufgabe_beobachten(request, pk):
    """Schaltet die eigene Benachrichtigung bei Änderungen an dieser Aufgabe um - unabhängig vom
    Schreibrecht, da reines Beobachten (nur Lesen + E-Mail-Benachrichtigung) kein 'change' auf die Aufgabe
    selbst ist."""
    a = get_object_or_404(Aufgabe, pk=pk, verein=request.verein)
    if a.beobachter.filter(pk=request.user.pk).exists():
        a.beobachter.remove(request.user)
        messages.success(request, _("Benachrichtigungen für diese Aufgabe deaktiviert."))
    else:
        a.beobachter.add(request.user)
        messages.success(request, _("Sie werden ab jetzt bei Änderungen an dieser Aufgabe benachrichtigt."))
    return redirect("aufgabe_detail", pk=a.pk)


def notiz_nach_speichern(request, obj, neu):
    if neu:
        obj.erstellt_von = request.user.get_username()
        obj.save(update_fields=["erstellt_von"])
        if obj.aufgabe.beobachter.exists():
            from .services import aufgabe_beobachter_notiz_benachrichtigen
            aufgabe_beobachter_notiz_benachrichtigen(obj)


@login_required
def veranstaltungen_ics(request):
    """Kalenderexport (iCalendar) aller nicht abgesagten Veranstaltungen."""
    if request.verein is None or not request.rechte.darf("veranstaltungen", "view"):
        raise PermissionDenied

    def esc(t):
        return (t or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

    def utc(d):
        return d.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    zeilen = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:-//Vereinsverwaltung//{esc(request.verein.name)}//DE"]
    for v in Veranstaltung.objects.filter(verein=request.verein).exclude(status="abgesagt"):
        zeilen += ["BEGIN:VEVENT", f"UID:{v.pk}@{request.verein.kuerzel}", f"DTSTAMP:{utc(timezone.now())}",
                   f"DTSTART:{utc(v.beginn)}", f"DTEND:{utc(v.ende or v.beginn)}", f"SUMMARY:{esc(v.titel)}",
                   f"LOCATION:{esc(v.ort)}", f"DESCRIPTION:{esc(v.beschreibung)}", "END:VEVENT"]
    zeilen.append("END:VCALENDAR")
    r = HttpResponse("\r\n".join(zeilen) + "\r\n", content_type="text/calendar; charset=utf-8")
    r["Content-Disposition"] = 'attachment; filename="veranstaltungen.ics"'
    return r


def listen_aktionen(request):
    return [knopf("Kalender (.ics)", reverse("veranstaltungen_ics"))]


def wahlergebnis_kontext(request, w):
    """Detailseite eines Wahl-/Abstimmungsergebnisses: statt eines einzigen Textblocks getrennte Tabellen - bei Wahlen
    Kandidat*in und Stimmen, bei Abstimmungen "Antrag" (Antragsteller*in, Text, Begruendung) und "Ergebnis"
    (Stimmen, Status). Aeltere Eintraege ohne strukturierte Einzelheiten werden aus dem gespeicherten Text zerlegt."""
    from django.utils.html import conditional_escape
    from django.utils.safestring import mark_safe

    from apps.documents.anlagen import TEXTFELDER

    paare = [tuple(p) for p in (w.details or []) if len(p) == 2]
    if not paare:
        for zeile in (w.ergebnis or "").splitlines():
            bezeichnung, trenner, rest = zeile.partition(": ")
            paare.append((bezeichnung, rest) if trenner else ("", zeile))

    def zeilen(eintraege):
        # Zeilenumbrueche im Text (z. B. mehrzeiliger Antragstext) sichtbar lassen
        return [{"url": None, "zellen": [bez, mark_safe(conditional_escape(wert).replace("\n", "<br>"))]}
                for bez, wert in eintraege]

    if w.art == "wahl":
        return {"abschnitte": [{"titel": "Stimmen je Kandidat*in", "spalten": ["Kandidat*in", "Stimmen"],
                                "zeilen": zeilen(paare), "add_url": None}]}
    antrag = [(b, x) for b, x in paare if b in TEXTFELDER and b != "Status in OpenSlides"]
    ergebnis = [(b, x) for b, x in paare if b not in TEXTFELDER or b == "Status in OpenSlides"]
    abschnitte = []
    if antrag:
        abschnitte.append({"titel": "Antrag" if w.amt.startswith("Antrag") else "Thema", "spalten": ["Angabe", "Inhalt"],
                           "zeilen": zeilen(antrag), "add_url": None})
    if ergebnis:
        abschnitte.append({"titel": "Ergebnis", "spalten": ["Angabe", "Wert"], "zeilen": zeilen(ergebnis),
                           "add_url": None})
    return {"abschnitte": abschnitte}
