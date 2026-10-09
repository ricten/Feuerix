from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext as _

from apps.core.crud import abschnitt, knopf
from apps.core.util import geld

from .models import Anmeldung, Aufgabe, Tagesordnungspunkt, Veranstaltung

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
        aktionen.append(knopf("Inventar reservieren", reverse("verleih_sammel_add") + f"?veranstaltung={v.pk}"
                              f"&von={timezone.localtime(v.beginn):%Y-%m-%d}"
                              f"&bis={timezone.localtime(v.ende or v.beginn):%Y-%m-%d}"))
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
            if v.openslides_meeting_id:
                aktionen.append(knopf("Wahlergebnisse aus OpenSlides übernehmen",
                                      reverse("veranstaltung_wahlergebnisse", args=[v.pk]), post=True,
                                      stil="outline-success",
                                      bestaetigung="Wahlergebnisse aus OpenSlides abrufen? Zuvor übernommene "
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
    offene_schichten = [sc for sc in v.schichten.all() if sc.einsaetze.count() < sc.benoetigt]
    if offene_schichten:
        hinweise.append(f"{len(offene_schichten)} Schicht(en) noch nicht voll besetzt.")
    ab = [abschnitt(request, "Aufgaben", v.aufgaben.all(), ("titel", "zustaendig", "faellig", "status"),
                    "aufgabe_add", {"veranstaltung": v.pk}),
          abschnitt(request, "Schichtplan", v.schichten.all(), ("bezeichnung", "beginn", "ende", ("besetzung", "Besetzung"),
                                                               ("helfer", "Helfer")), "schicht_add", {"veranstaltung": v.pk}),
          abschnitt(request, "Budget", v.kosten.all(), ("art", "bezeichnung", "plan_betrag", "ist_betrag"),
                    "kostenposition_add", {"veranstaltung": v.pk})]
    ab.insert(0, abschnitt(request, "Tagesordnung", v.tagesordnung.all(), ("position", "titel", "openslides_topic_id"),
                           "tagesordnungspunkt_add", {"veranstaltung": v.pk, "position": v.tagesordnung.count() + 1}))
    if r.darf("teilnehmer", "view"):
        ab.insert(2, abschnitt(request, "Anmeldungen", v.anmeldungen.all(), (("wer", "Name"), "personen", "status"),
                               "anmeldung_add", {"veranstaltung": v.pk}))
    if v.wahlergebnisse.exists():
        ab.append(abschnitt(request, "Wahlergebnisse (aus OpenSlides)", v.wahlergebnisse.all(), ("amt", "wahlgang")))
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
    if v.openslides_meeting_id:
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
    return {"abschnitte": [abschnitt(request, "Eingetragene Helfer", s.einsaetze.all(), ("mitglied", "bemerkung"),
                                     "schichteinsatz_add", {"schicht": s.pk, "next": request.get_full_path()})]}


def aufgabe_kontext(request, a):
    ctx = {"abschnitte": [abschnitt(request, "Zwischennotizen (wie ein Ticket-Verlauf)", a.notizen.all(),
                                   ("erstellt", "erstellt_von", "text"), "aufgabenotiz_add",
                                   {"aufgabe": a.pk, "next": request.get_full_path()})]}
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


def notiz_nach_speichern(request, obj, neu):
    if neu:
        obj.erstellt_von = request.user.get_username()
        obj.save(update_fields=["erstellt_von"])


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
