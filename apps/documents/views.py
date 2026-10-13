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

from apps.core.anbindungen import anbindungen
from apps.core.crud import abschnitt, knopf, pdf_vorschau
from apps.core.pdf import Layout, seiten_pdf
from apps.events.models import Veranstaltung

from . import richtext, services
from .docx_export import schriftstueck_docx
from .models import Ablagedokument, Schriftstueck, Serienbrief, Vorlage
from .pdf import absaetze, schriftstueck_pdf, serienbrief_pdf
from .platzhalter import OPENSLIDES_PLATZHALTER, PLATZHALTER, ersetzen, kontext, offene
from django.utils.translation import gettext, gettext_lazy
from django.utils.text import format_lazy


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


def _auto_uebergeben(dokument):
    from apps.paperless import auto
    try:
        auto.ablage_fertig(dokument)
    except Exception:  # Paperless-Probleme duerfen das Ablegen nie verhindern
        pass


def _pdf_antwort(inhalt, name, inline=True):
    r = HttpResponse(inhalt, content_type="application/pdf")
    r["Content-Disposition"] = f'{"inline" if inline else "attachment"}; filename="{name}"'
    return r


# ---------------------------------------------------------------- Schriftstück
def schriftstueck_kontext(request, s):
    rt, aktionen = request.rechte, [
        knopf(gettext_lazy("PDF ansehen"), reverse("schriftstueck_pdf", args=[s.pk]), stil="primary"),
        knopf(gettext_lazy("Word (.docx)"), reverse("schriftstueck_docx", args=[s.pk]))]
    if rt.darf("ablage", "add"):
        aktionen.append(knopf(gettext_lazy("Als PDF in Ablage speichern"), reverse("schriftstueck_ablegen", args=[s.pk]), post=True,
                              stil="success"))
    if s.veranstaltung_id:
        aktionen.append(knopf(gettext_lazy("Zur Veranstaltung"), reverse("veranstaltung_detail", args=[s.veranstaltung_id])))
        if (s.art == "protokoll" and s.veranstaltung.openslides_meeting_id and rt.darf("schriftverkehr", "change")
                and rt.darf("openslides", "change") and anbindungen(request).openslides):
            aktionen.append(knopf(gettext_lazy("Anwesenheit, Abstimmungen und Wahlen aus OpenSlides abrufen (als Anlagen)"),
                                  reverse("schriftstueck_abstimmungen", args=[s.pk]), post=True,
                                  stil="outline-success"))
    hinweise = []
    fehlend = offene(s.text + " " + s.betreff, s.kontext())
    if fehlend:
        hinweise.append(gettext("Nicht ersetzbare Platzhalter (fehlender Bezug): %(platzhalter)s") % {
            "platzhalter": ", ".join("{" + f + "}" for f in fehlend)})
    if s.ablage_id:
        hinweise.append(gettext("Zuletzt abgelegt als %(ablage)s.") % {"ablage": s.ablage})
    return {"aktionen": aktionen, "hinweise": hinweise,
            "vorschau": pdf_vorschau(reverse("schriftstueck_pdf", args=[s.pk]))}


@login_required
@xframe_options_sameorigin
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
    # Erst-Ablage = eigenes Dokument (Version 1), auch wenn z. B. das Protokoll einer fruehreren Sitzung genauso heisst;
    # nur erneutes Ablegen DESSELBEN Schriftstuecks ergibt eine neue Version.
    d = services.ablegen(request.verein, s.titel, kat, f"{s.titel[:60]}.pdf", schriftstueck_pdf(s), datum=s.datum,
                         veranstaltung=s.veranstaltung, erste_version=s.ablage_id is None)
    s.ablage = d
    s.save(update_fields=["ablage", "geaendert"])
    if s.status == "final":
        _auto_uebergeben(d)
    messages.success(request, gettext("In Ablage gespeichert: %(ordner)s · Version %(version)s.") % {"ordner": d.ordner, "version": d.version})
    return redirect("schriftstueck_detail", pk=s.pk)


# ---------------------------------------------------------------- Vorlage
def vorlage_kontext(request, v):
    return {"aktionen": [knopf(gettext_lazy("Layout-Vorschau (PDF)"), reverse("vorlage_vorschau", args=[v.pk]), stil="primary")],
            "vorschau": pdf_vorschau(reverse("vorlage_vorschau", args=[v.pk]))}


@login_required
@xframe_options_sameorigin
def vorlage_vorschau(request, pk):
    """Beispiel-PDF der Vorlage mit ihrem Layout (Beispielempfaenger, Platzhalter soweit ohne Mitglied ersetzbar)."""
    _pruefen(request, "schriftverkehr", "view")
    v = get_object_or_404(Vorlage, pk=pk, verein=request.verein)
    ctx = kontext(request.verein)
    seite = {"empfaenger": ["Max Mustermann", "Musterstraße 1", "12345 Musterstadt"],
             "betreff": ersetzen(v.betreff, ctx) or v.name, "datum": f"Datum: {ctx['datum']}",
             "vor": [lambda stile, layout, breite, h=richtext.text_ersetzt(v.text, ctx):
                     richtext.flowables(h, stile, layout, breite)],
             "wasserzeichen": "VORSCHAU – Beispielempfänger"}
    pdf = seiten_pdf(request.verein, [seite], titel=v.name, layout=Layout.von_vorlage(v))
    return _pdf_antwort(pdf, f"Vorschau {v.name[:40]}.pdf")


# ---------------------------------------------------------------- Serienbrief
def _versandweg(sb, m):
    """'E-Mail', 'Post' oder 'Post + E-Mail' je Empfaenger entsprechend der Versandart des Serienbriefs."""
    if sb.versandart == "post":
        return "Post"
    if sb.versandart == "mail":
        return "E-Mail" if m.email else "–"
    if sb.versandart == "mail_post":
        return "E-Mail" if m.email else "Post"
    return "Post + E-Mail" if m.email else "Post"


def serienbrief_kontext(request, sb):
    rt = request.rechte
    empf = sb.empfaenger()
    n = empf.count()
    mit_mail = empf.exclude(email="").count()
    n_mail = sb.mail_empfaenger().count()
    n_post = sb.post_empfaenger().count()
    aktionen = [knopf(gettext_lazy("Vorschau (erster Empfänger)"), reverse("serienbrief_pdf", args=[sb.pk]), stil="primary")]
    if n_post:
        aktionen.append(knopf(format_lazy(gettext_lazy("Briefe für den Postversand als PDF ({n_post})"), n_post=n_post),
                              reverse("serienbrief_pdf", args=[sb.pk]) + "?alle=1"))
        if rt.darf("ablage", "add"):
            aktionen.append(knopf(gettext_lazy("Briefe erzeugen & in Ablage speichern"), reverse("serienbrief_ablegen", args=[sb.pk]),
                                  post=True, stil="success",
                                  bestaetigung=gettext("%(n_post)s Briefe als PDF erzeugen und in der Ablage speichern?") % {"n_post": n_post}))
    if rt.darf("rundschreiben", "change") and n_mail:
        aktionen.append(knopf(format_lazy(gettext_lazy("Per E-Mail senden ({n_mail})"), n_mail=n_mail), reverse("serienbrief_mailen", args=[sb.pk]), post=True,
                              stil="outline-primary",
                              bestaetigung=gettext("E-Mail mit PDF-Anhang an %(n_mail)s Mitglieder senden?") % {"n_mail": n_mail}))
    hinweise = [gettext("%(n)s Empfänger, davon %(mit_mail)s mit E-Mail-Adresse. Versand: %(get_versandart_display)s.") % {"n": n, "mit_mail": mit_mail, "get_versandart_display": sb.get_versandart_display()},
                gettext("Per E-Mail: %(n_mail)s · Per Post (Brief-PDF): %(n_post)s.") % {"n_mail": n_mail, "n_post": n_post}]
    fehlend = offene(sb.text + " " + sb.betreff, kontext(sb.verein, mitglied=empf.first(), veranstaltung=sb.veranstaltung))
    if fehlend:
        hinweise.append(gettext("Nicht ersetzbare Platzhalter: %(platzhalter)s") % {
            "platzhalter": ", ".join("{" + f + "}" for f in fehlend)})
    if sb.versand_info:
        hinweise.append(gettext("E-Mail-Versand: %(versand_info)s") % {"versand_info": sb.versand_info})
    return {"aktionen": aktionen, "hinweise": hinweise,
            "abschnitte": [{"titel": gettext("Empfängerliste (erste 50 von %(n)s)") % {"n": n},
                            "spalten": [gettext("Mitglied"), gettext("E-Mail"), gettext("Ort"), gettext("Versand")],
                            "zeilen": [{"url": None, "zellen": [m.name, m.email or "–", m.ort or "–", _versandweg(sb, m)]}
                                       for m in empf[:50]],
                            "add_url": None}],
            "vorschau": pdf_vorschau(reverse("serienbrief_pdf", args=[sb.pk]))}


@login_required
@xframe_options_sameorigin
def serienbrief_pdf_view(request, pk):
    _pruefen(request, "rundschreiben", "view")
    sb = get_object_or_404(Serienbrief, pk=pk, verein=request.verein)
    if request.GET.get("alle"):
        pdf = serienbrief_pdf(sb, sb.post_empfaenger())
    else:     # Vorschau: erster Empfaenger des Kreises (auch wenn dieser per E-Mail bedient wird)
        pdf = serienbrief_pdf(sb, sb.empfaenger(), limit=1)
    return _pdf_antwort(pdf, f"{sb.titel[:50]}.pdf")


@login_required
@require_POST
def serienbrief_ablegen(request, pk):
    _pruefen(request, "rundschreiben", "view")
    _pruefen(request, "ablage", "add")
    sb = get_object_or_404(Serienbrief, pk=pk, verein=request.verein)
    empf = list(sb.post_empfaenger())
    if not empf:
        messages.error(request, gettext("Keine Empfänger für den Postversand gefunden."))
        return redirect("serienbrief_detail", pk=sb.pk)
    d = services.ablegen(request.verein, sb.titel, "serienbrief", f"{sb.titel[:60]}.pdf", serienbrief_pdf(sb, empf),
                         datum=sb.datum, veranstaltung=sb.veranstaltung,
                         beschreibung=f"{len(empf)} Briefe (Post) · Empfängerkreis: {sb.get_status_filter_display()}"
                                     f" · Versand: {sb.get_versandart_display()}")
    sb.ablage = d
    sb.save(update_fields=["ablage", "geaendert"])
    _auto_uebergeben(d)
    messages.success(request, gettext("%(anzahl)s Briefe in der Ablage gespeichert (%(ordner)s, Version %(version)s).") % {"anzahl": len(empf), "ordner": d.ordner, "version": d.version})
    return redirect("ablagedokument_detail", pk=d.pk)


@login_required
@require_POST
def serienbrief_mailen(request, pk):
    _pruefen(request, "rundschreiben", "change")
    from .tasks import serienbrief_mailen_task
    sb = get_object_or_404(Serienbrief, pk=pk, verein=request.verein)
    serienbrief_mailen_task.delay(sb.pk)
    messages.success(request, gettext("Der Versand läuft im Hintergrund. Das Ergebnis erscheint hier nach kurzer Zeit."))
    return redirect("serienbrief_detail", pk=sb.pk)


# ---------------------------------------------------------------- Vorlagen
def vorlagen_listen_aktionen(request):
    a = []
    if request.rechte.darf("schriftverkehr", "add"):
        a.append(knopf(gettext_lazy("Standardvorlagen nachladen"), reverse("vorlagen_standard"), post=True))
    return a


@login_required
@require_POST
def vorlagen_standard(request):
    _pruefen(request, "schriftverkehr", "add")
    n = services.standardvorlagen_anlegen(request.verein)
    messages.success(request, gettext("%(n)s fehlende Standardvorlagen angelegt.") % {"n": n} if n else gettext("Alle Standardvorlagen sind vorhanden."))
    return redirect("vorlage_list")


@login_required
def platzhalter_hilfe(request):
    _pruefen(request, "schriftverkehr", "view")
    gruppen = PLATZHALTER
    if not anbindungen(request).openslides:   # ohne OpenSlides-Anbindung keine OpenSlides-Platzhalter anbieten
        gruppen = [(titel, [e for e in eintraege if e[0] not in OPENSLIDES_PLATZHALTER])
                   for titel, eintraege in PLATZHALTER if not titel.startswith("OpenSlides")]
    return render(request, "documents/platzhalter.html", {"gruppen": gruppen, "titel": gettext("Platzhalter")})


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
        messages.error(request, gettext("Keine passende Vorlage vorhanden (Schriftverkehr › Vorlagen › Standardvorlagen nachladen)."))
        return redirect("veranstaltung_detail", pk=v.pk)
    if art == "serienbrief":
        obj = Serienbrief.objects.create(verein=request.verein, titel=gettext("Einladung %(titel)s") % {"titel": v.titel}, vorlage=vl, veranstaltung=v,
                                         betreff=vl.betreff, text=vl.text, datum=date.today(),
                                         versandart="mail_post")
        return redirect("serienbrief_detail", pk=obj.pk)
    obj = Schriftstueck.objects.create(verein=request.verein, titel=f"{'Protokoll' if art == 'protokoll' else 'Einladung'} "
                                       f"{v.titel}", art=vorlagenart, vorlage=vl, veranstaltung=v, betreff=vl.betreff,
                                       text=vl.text, datum=date.today())
    messages.success(request, gettext("Entwurf aus Vorlage erstellt – Text bei Bedarf anpassen."))
    return redirect("schriftstueck_detail", pk=obj.pk)
