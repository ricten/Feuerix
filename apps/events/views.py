from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.urls import reverse
from django.utils import timezone

from apps.core.crud import abschnitt, knopf
from apps.core.util import geld

from .models import Tagesordnungspunkt, Veranstaltung

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


def veranstaltung_kontext(request, v):
    r = request.rechte
    aktionen = []
    if r.darf("verleih", "add"):
        aktionen.append(knopf("Inventar reservieren", reverse("verleih_add") + f"?veranstaltung={v.pk}"
                              f"&von={timezone.localtime(v.beginn):%Y-%m-%d}"
                              f"&bis={timezone.localtime(v.ende or v.beginn):%Y-%m-%d}&next="
                              + reverse("veranstaltung_detail", args=[v.pk])))
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
        from apps.openslides.models import OpenSlidesVerbindung
        vb = OpenSlidesVerbindung.objects.filter(verein=request.verein, aktiv=True).first()
        if vb:
            aktionen.append(knopf("Tagesordnung nach OpenSlides übertragen" if v.openslides_meeting_id
                                  else "In OpenSlides anlegen", reverse("veranstaltung_openslides", args=[v.pk]), post=True,
                                  stil="outline-success"))
    s = v.summen()
    hinweise = [f"Plan: Einnahmen {geld(s['plan_ein'])} · Ausgaben {geld(s['plan_aus'])} · "
                f"Ergebnis {geld(s['plan_ein'] - s['plan_aus'])}",
                f"Ist: Einnahmen {geld(s['ist_ein'])} · Ausgaben {geld(s['ist_aus'])} · "
                f"Ergebnis {geld(s['ist_ein'] - s['ist_aus'])}"]
    zugesagt = sum(a.personen for a in v.anmeldungen.filter(status="zugesagt"))
    if v.anmeldungen.exists():
        hinweise.append(f"Zugesagte Personen: {zugesagt}" + (f" von erwartet {v.erwartete_teilnehmer}"
                                                             if v.erwartete_teilnehmer else ""))
    offene_schichten = [sc for sc in v.schichten.all() if sc.einsaetze.count() < sc.benoetigt]
    if offene_schichten:
        hinweise.append(f"{len(offene_schichten)} Schicht(en) noch nicht voll besetzt.")
    ab = [abschnitt(request, "Aufgaben", v.aufgaben.all(), ("titel", "zustaendig", "faellig", "status"),
                    "aufgabe_add", {"veranstaltung": v.pk}),
          abschnitt(request, "Schichtplan", v.schichten.all(), ("bezeichnung", "beginn", "ende", ("besetzung", "Besetzung"),
                                                               ("helfer", "Helfer")), "schicht_add", {"veranstaltung": v.pk}),
          abschnitt(request, "Anmeldungen", v.anmeldungen.all(), (("wer", "Name"), "personen", "status"),
                    "anmeldung_add", {"veranstaltung": v.pk}),
          abschnitt(request, "Budget", v.kosten.all(), ("art", "bezeichnung", "plan_betrag", "ist_betrag"),
                    "kostenposition_add", {"veranstaltung": v.pk})]
    ab.insert(0, abschnitt(request, "Tagesordnung", v.tagesordnung.all(), ("position", "titel", "openslides_topic_id"),
                           "tagesordnungspunkt_add", {"veranstaltung": v.pk, "position": v.tagesordnung.count() + 1}))
    if r.darf("verleih", "view"):
        ab.append(abschnitt(request, "Reserviertes Inventar", v.verleihe.all(), ("gegenstand", "von", "bis", "status")))
    if r.darf("schriftverkehr", "view"):
        ab.append(abschnitt(request, "Schriftstücke (Einladung, Protokoll …)", v.schriftstuecke.all(),
                            ("datum", "titel", "art", "status")))
        ab.append(abschnitt(request, "Serienbriefe", v.serienbriefe.all(), ("datum", "titel", "versendet_am")))
    if r.darf("ablage", "view"):
        ab.append(abschnitt(request, "Ablage zu dieser Veranstaltung", v.ablage.all(),
                            ("datum", "titel", "kategorie", "version"), "ablagedokument_add",
                            {"veranstaltung": v.pk, "kategorie": "protokoll"}))
    if v.openslides_meeting_id:
        hinweise.append(f"OpenSlides-Versammlung Nr. {v.openslides_meeting_id} ist verknüpft.")
    return {"aktionen": aktionen, "hinweise": hinweise, "abschnitte": ab}


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
    return {"abschnitte": [abschnitt(request, "Eingetragene Helfer", s.einsaetze.all(), ("mitglied", "bemerkung"),
                                     "schichteinsatz_add", {"schicht": s.pk, "next": request.get_full_path()})]}


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
