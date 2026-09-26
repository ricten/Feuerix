from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
import os

from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from apps.core.crud import abschnitt, knopf
from apps.events.models import Veranstaltung

from . import services
from .docx_export import schriftstueck_docx
from .models import Ablagedokument, Schriftstueck, Serienbrief, Vorlage
from .pdf import schriftstueck_pdf, serienbrief_pdf
from .platzhalter import PLATZHALTER, kontext, offene


def _pruefen(request, modul, aktion):
    if request.verein is None or not request.rechte.darf(modul, aktion):
        raise PermissionDenied


VORSCHAU_TYPEN = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                  ".gif": "image/gif", ".webp": "image/webp"}   # bewusst ohne SVG/HTML (aktive Inhalte)


def vorschau_art(dateiname):
    """-> "pdf", "bild" oder None (keine Vorschau moeglich)."""
    endung = os.path.splitext(dateiname or "")[1].lower()
    if endung not in VORSCHAU_TYPEN:
        return None
    return "pdf" if endung == ".pdf" else "bild"


@login_required
@xframe_options_sameorigin
def ablage_vorschau(request, pk):
    """Datei einer Ablage-Dokuments inline (Vorschau) - nur PDF/Bilder, mit Rechtepruefung und Vereinsfilter."""
    _pruefen(request, "ablage", "view")
    d = get_object_or_404(Ablagedokument, pk=pk, verein=request.verein)
    endung = os.path.splitext(d.dateiname)[1].lower()
    if not d.datei or endung not in VORSCHAU_TYPEN:
        raise Http404
    r = FileResponse(d.datei.open("rb"), content_type=VORSCHAU_TYPEN[endung])
    r["Content-Disposition"] = f'inline; filename="{os.path.basename(d.datei.name)}"'
    return r


def _pdf_antwort(inhalt, name, inline=True):
    r = HttpResponse(inhalt, content_type="application/pdf")
    r["Content-Disposition"] = f'{"inline" if inline else "attachment"}; filename="{name}"'
    return r


# ---------------------------------------------------------------- Schriftstück
def schriftstueck_kontext(request, s):
    rt, aktionen = request.rechte, [
        knopf("PDF ansehen", reverse("schriftstueck_pdf", args=[s.pk]), stil="primary"),
        knopf("Word (.docx)", reverse("schriftstueck_docx", args=[s.pk]))]
    if rt.darf("ablage", "add"):
        aktionen.append(knopf("Als PDF in Ablage speichern", reverse("schriftstueck_ablegen", args=[s.pk]), post=True,
                              stil="success"))
    if s.veranstaltung_id:
        aktionen.append(knopf("Zur Veranstaltung", reverse("veranstaltung_detail", args=[s.veranstaltung_id])))
    hinweise = []
    fehlend = offene(s.text + " " + s.betreff, s.kontext())
    if fehlend:
        hinweise.append("Nicht ersetzbare Platzhalter (fehlender Bezug): " + ", ".join("{" + f + "}" for f in fehlend))
    if s.ablage_id:
        hinweise.append(f"Zuletzt abgelegt als {s.ablage}.")
    return {"aktionen": aktionen, "hinweise": hinweise}


@login_required
def schriftstueck_pdf_view(request, pk):
    _pruefen(request, "schriftverkehr", "view")
    s = get_object_or_404(Schriftstueck, pk=pk, verein=request.verein)
    return _pdf_antwort(schriftstueck_pdf(s), f"{s.titel[:50]}.pdf")


@login_required
def schriftstueck_docx_view(request, pk):
    _pruefen(request, "schriftverkehr", "view")
    s = get_object_or_404(Schriftstueck, pk=pk, verein=request.verein)
    r = HttpResponse(schriftstueck_docx(s), content_type=
                     "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    r["Content-Disposition"] = f'attachment; filename="{s.titel[:50]}.docx"'
    return r


@login_required
@require_POST
def schriftstueck_ablegen(request, pk):
    _pruefen(request, "ablage", "add")
    s = get_object_or_404(Schriftstueck, pk=pk, verein=request.verein)
    kat = {"protokoll": "protokoll", "einladung": "einladung", "serienbrief": "serienbrief"}.get(s.art, "sonstiges")
    d = services.ablegen(request.verein, s.titel, kat, f"{s.titel[:60]}.pdf", schriftstueck_pdf(s), datum=s.datum,
                         veranstaltung=s.veranstaltung)
    s.ablage = d
    s.save(update_fields=["ablage", "geaendert"])
    messages.success(request, f"In Ablage gespeichert: {d.ordner} · Version {d.version}.")
    return redirect("schriftstueck_detail", pk=s.pk)


# ---------------------------------------------------------------- Serienbrief
def serienbrief_kontext(request, sb):
    rt = request.rechte
    empf = sb.empfaenger()
    n = empf.count()
    mit_mail = empf.exclude(email="").count()
    aktionen = [knopf("Vorschau (erster Empfänger)", reverse("serienbrief_pdf", args=[sb.pk]), stil="primary"),
                knopf("Alle Briefe als PDF", reverse("serienbrief_pdf", args=[sb.pk]) + "?alle=1")]
    if rt.darf("ablage", "add"):
        aktionen.append(knopf("Alle Briefe erzeugen & in Ablage speichern", reverse("serienbrief_ablegen", args=[sb.pk]),
                              post=True, stil="success",
                              bestaetigung=f"{n} Briefe als PDF erzeugen und in der Ablage speichern?"))
    if rt.darf("schriftverkehr", "change") and mit_mail:
        aktionen.append(knopf(f"Per E-Mail senden ({mit_mail})", reverse("serienbrief_mailen", args=[sb.pk]), post=True,
                              stil="outline-primary",
                              bestaetigung=f"E-Mail mit PDF-Anhang an {mit_mail} Mitglieder senden?"))
    hinweise = [f"{n} Empfänger, davon {mit_mail} mit E-Mail-Adresse."]
    fehlend = offene(sb.text + " " + sb.betreff, kontext(sb.verein, mitglied=empf.first(), veranstaltung=sb.veranstaltung))
    if fehlend:
        hinweise.append("Nicht ersetzbare Platzhalter: " + ", ".join("{" + f + "}" for f in fehlend))
    if sb.versand_info:
        hinweise.append(f"E-Mail-Versand: {sb.versand_info}")
    return {"aktionen": aktionen, "hinweise": hinweise,
            "abschnitte": [{"titel": f"Empfängerliste (erste 50 von {n})", "spalten": ["Mitglied", "E-Mail", "Ort"],
                            "zeilen": [{"url": None, "zellen": [m.name, m.email or "–", m.ort or "–"]} for m in empf[:50]],
                            "add_url": None}]}


@login_required
def serienbrief_pdf_view(request, pk):
    _pruefen(request, "schriftverkehr", "view")
    sb = get_object_or_404(Serienbrief, pk=pk, verein=request.verein)
    empf = sb.empfaenger()
    pdf = serienbrief_pdf(sb, empf) if request.GET.get("alle") else serienbrief_pdf(sb, empf, limit=1)
    return _pdf_antwort(pdf, f"{sb.titel[:50]}.pdf")


@login_required
@require_POST
def serienbrief_ablegen(request, pk):
    _pruefen(request, "ablage", "add")
    sb = get_object_or_404(Serienbrief, pk=pk, verein=request.verein)
    empf = list(sb.empfaenger())
    if not empf:
        messages.error(request, "Keine Empfänger gefunden.")
        return redirect("serienbrief_detail", pk=sb.pk)
    d = services.ablegen(request.verein, sb.titel, "serienbrief", f"{sb.titel[:60]}.pdf", serienbrief_pdf(sb, empf),
                         datum=sb.datum, veranstaltung=sb.veranstaltung,
                         beschreibung=f"{len(empf)} Briefe · Empfängerkreis: {sb.get_status_filter_display()}")
    sb.ablage = d
    sb.save(update_fields=["ablage", "geaendert"])
    messages.success(request, f"{len(empf)} Briefe in der Ablage gespeichert ({d.ordner}, Version {d.version}).")
    return redirect("ablagedokument_detail", pk=d.pk)


@login_required
@require_POST
def serienbrief_mailen(request, pk):
    _pruefen(request, "schriftverkehr", "change")
    from .tasks import serienbrief_mailen_task
    sb = get_object_or_404(Serienbrief, pk=pk, verein=request.verein)
    serienbrief_mailen_task.delay(sb.pk)
    messages.success(request, "Der Versand läuft im Hintergrund. Das Ergebnis erscheint hier nach kurzer Zeit.")
    return redirect("serienbrief_detail", pk=sb.pk)


# ---------------------------------------------------------------- Vorlagen
def vorlagen_listen_aktionen(request):
    a = []
    if request.rechte.darf("schriftverkehr", "add"):
        a.append(knopf("Standardvorlagen nachladen", reverse("vorlagen_standard"), post=True))
    return a


@login_required
@require_POST
def vorlagen_standard(request):
    _pruefen(request, "schriftverkehr", "add")
    n = services.standardvorlagen_anlegen(request.verein)
    messages.success(request, f"{n} fehlende Standardvorlagen angelegt." if n else "Alle Standardvorlagen sind vorhanden.")
    return redirect("vorlage_list")


@login_required
def platzhalter_hilfe(request):
    _pruefen(request, "schriftverkehr", "view")
    return render(request, "documents/platzhalter.html", {"gruppen": PLATZHALTER, "titel": "Platzhalter"})


# ---------------------------------------------------------------- aus Veranstaltung
@login_required
@require_POST
def aus_veranstaltung(request, pk, art):
    """Einladung / Protokoll / Einladungs-Serienbrief für eine Veranstaltung aus der Standardvorlage erzeugen."""
    _pruefen(request, "schriftverkehr", "add")
    v = get_object_or_404(Veranstaltung, pk=pk, verein=request.verein)
    vorlagenart = "protokoll" if art == "protokoll" else "einladung"
    vl = (Vorlage.objects.filter(verein=request.verein, art=vorlagenart, aktiv=True).order_by("-ist_standard", "name").first())
    if vl is None:
        messages.error(request, "Keine passende Vorlage vorhanden (Schriftverkehr › Vorlagen › Standardvorlagen nachladen).")
        return redirect("veranstaltung_detail", pk=v.pk)
    if art == "serienbrief":
        obj = Serienbrief.objects.create(verein=request.verein, titel=f"Einladung {v.titel}", vorlage=vl, veranstaltung=v,
                                         betreff=vl.betreff, text=vl.text, datum=date.today())
        return redirect("serienbrief_detail", pk=obj.pk)
    obj = Schriftstueck.objects.create(verein=request.verein, titel=f"{'Protokoll' if art == 'protokoll' else 'Einladung'} "
                                       f"{v.titel}", art=vorlagenart, vorlage=vl, veranstaltung=v, betreff=vl.betreff,
                                       text=vl.text, datum=date.today())
    messages.success(request, "Entwurf aus Vorlage erstellt – Text bei Bedarf anpassen.")
    return redirect("schriftstueck_detail", pk=obj.pk)
