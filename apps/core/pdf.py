"""PDF-Erzeugung (Briefe, Rechnungen, Serienbriefe ...) mit Vereins-CI (Briefkopf mit Name/Logo/Akzentfarbe,
Fußzeile mit Vereinsregister/Vertretung/Bankverbindung)."""
import os
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (BaseDocTemplate, Frame, NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer,
                                Table, TableStyle)

LOGO_BREITE = 55 * mm
LOGO_HOEHE = 28 * mm
STANDARD_AKZENTFARBE = "#1F4E79"
BRIEFKOPF_TEXTFARBE = "#646363"


def _p(text, stil):
    return Paragraph(escape(str(text)).replace("\n", "<br/>"), stil)


def logo_datei(verein):
    try:
        if verein.logo and os.path.exists(verein.logo.path):
            return verein.logo.path
    except Exception:
        pass
    return None


def _akzentfarbe(verein):
    try:
        return colors.HexColor(verein.akzentfarbe or STANDARD_AKZENTFARBE)
    except Exception:
        return colors.HexColor(STANDARD_AKZENTFARBE)


def _logo_zeichnen(canvas, verein):
    pfad = logo_datei(verein)
    if not pfad:
        return
    try:
        bild = ImageReader(pfad)
        iw, ih = bild.getSize()
        s = min(LOGO_BREITE / iw, LOGO_HOEHE / ih)
        w, h = iw * s, ih * s
        canvas.drawImage(bild, A4[0] - 20 * mm - w, A4[1] - 12 * mm - h, width=w, height=h, mask="auto")
    except Exception:
        pass


def _briefkopf_hoehe(verein):
    """-> (Paragraph, Höhe in Punkten) für den Vereinsnamen als Briefkopf-Überschrift (links neben dem Logo).
    Textfarbe bewusst neutral grau (nicht die Akzentfarbe) - die Akzentfarbe ist nur für die Trennlinie."""
    breite = A4[0] - 25 * mm - 20 * mm - LOGO_BREITE - 8 * mm
    stil = ParagraphStyle("briefkopf", fontName="Helvetica", fontSize=22, leading=25,
                          textColor=colors.HexColor(BRIEFKOPF_TEXTFARBE))
    p = Paragraph(escape(verein.name), stil)
    _, hoehe = p.wrap(breite, 60 * mm)
    return p, hoehe


def _briefkopf_zeichnen(canvas, verein, kopf_p, kopf_hoehe, linie_y):
    kopf_top_y = A4[1] - 15 * mm
    kopf_p.drawOn(canvas, 25 * mm, kopf_top_y - kopf_hoehe)
    _logo_zeichnen(canvas, verein)
    canvas.setStrokeColor(_akzentfarbe(verein))
    canvas.setLineWidth(1.1)
    canvas.line(25 * mm, linie_y, A4[0] - 20 * mm, linie_y)


def _fuss(canvas, verein, seitenzahl, doc):
    canvas.saveState()
    canvas.setStrokeColor(_akzentfarbe(verein))
    canvas.setLineWidth(0.6)
    canvas.line(25 * mm, 23 * mm, A4[0] - 20 * mm, 23 * mm)
    canvas.setFont("Helvetica", 8.5)
    canvas.setFillColor(colors.HexColor(BRIEFKOPF_TEXTFARBE))
    vertretung = ", ".join(x for x in (verein.unterschrift_1, verein.adresszeile) if x)
    zeilen = [
        " | ".join(x for x in (verein.name, verein.vereinsregister, verein.email) if x),
        vertretung,
        " | ".join(x for x in (
            f"Bank: {verein.bankname}" if verein.bankname else "",
            f"IBAN: {verein.iban}" if verein.iban else "",
            f"BIC: {verein.bic}" if verein.bic else "",
            f"Steuernr.: {verein.steuernummer}" if verein.steuernummer else "") if x),
    ]
    y = 18.5 * mm
    for z in zeilen:
        if z:
            canvas.drawCentredString(A4[0] / 2, y, z)
            y -= 4 * mm
    if seitenzahl:
        canvas.drawRightString(A4[0] - 20 * mm, 8 * mm, f"Seite {doc.page}")
    canvas.restoreState()


def _stile():
    st = getSampleStyleSheet()
    normal = ParagraphStyle("n", parent=st["BodyText"], fontSize=10, leading=13.5)
    return {
        "normal": normal,
        "klein": ParagraphStyle("k", parent=normal, fontSize=7.5, textColor=colors.grey),
        "rechts": ParagraphStyle("r", parent=normal, alignment=2),
        "kopf": ParagraphStyle("h", parent=st["Heading2"], spaceAfter=6),
    }


def _seite(verein, s, stile):
    normal, klein, rechts, kopf = stile["normal"], stile["klein"], stile["rechts"], stile["kopf"]
    absender = ", ".join(x for x in (verein.name, verein.anschrift, f"{verein.plz} {verein.ort}".strip()) if x)
    t = Table([[_p(absender, klein)]], colWidths=[105 * mm], hAlign="LEFT")
    t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    story = [t, Spacer(1, 8 * mm)]
    story += [_p("\n".join(z for z in s.get("empfaenger", []) if z), normal), Spacer(1, 10 * mm)]
    if s.get("meta"):
        m = Table([[_p(k, normal), _p(v, normal)] for k, v in s["meta"]], colWidths=[40 * mm, 55 * mm], hAlign="RIGHT")
        m.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
        story += [m, Spacer(1, 6 * mm)]
    story.append(Paragraph(f"<b>{escape(s['betreff'])}</b>", kopf))
    if s.get("wasserzeichen"):
        story.append(Paragraph(f"<font color='red'><b>{escape(s['wasserzeichen'])}</b></font>", normal))
    for a in s.get("vor", ()):
        story += [_p(a, normal), Spacer(1, 3 * mm)]
    tabellen = list(s.get("tabellen", []))
    if s.get("tabelle"):
        tabellen.insert(0, {"zeilen": s["tabelle"]})
    for t_ in tabellen:
        zeilen_roh = t_["zeilen"]
        ab = t_.get("rechts_ab", len(zeilen_roh[0]) - 1)  # ab dieser Spalte rechtsbündig
        if t_.get("titel"):
            story.append(Paragraph(f"<b>{escape(t_['titel'])}</b>", ParagraphStyle(
                "tt", parent=normal, spaceBefore=4, spaceAfter=2, keepWithNext=1)))
        zeilen = []
        n_stil, r_stil = (normal, rechts)
        if t_.get("klein"):
            n_stil = ParagraphStyle("nk", parent=normal, fontSize=8, leading=10)
            r_stil = ParagraphStyle("rk", parent=n_stil, alignment=2)
        for i, z in enumerate(zeilen_roh):
            zeile = []
            for j, c in enumerate(z):
                c = str(c)
                fett = c.startswith("**")
                text = escape(c[2:] if fett else c).replace("\n", "<br/>")
                zeile.append(Paragraph(f"<b>{text}</b>" if fett else text, r_stil if j >= ab else n_stil))
            zeilen.append(zeile)
        breiten = t_.get("breiten")
        tb = Table(zeilen, hAlign="LEFT", repeatRows=1, colWidths=[b * mm for b in breiten] if breiten else None)
        tb.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
            ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.lightgrey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke)]))
        story += [tb, Spacer(1, 4 * mm)]
    for a in s.get("nach", ()):
        story += [_p(a, normal), Spacer(1, 3 * mm)]
    return story


def seiten_pdf(verein, seiten, titel="Dokument", seitenzahl=True):
    """Mehrere Briefe in einem PDF (Serienbrief); jeder beginnt auf neuer Seite mit Briefkopf (Name, Logo,
    Akzentfarbe)."""
    buf = BytesIO()
    kopf_p, kopf_hoehe = _briefkopf_hoehe(verein)
    kopf_top_y = A4[1] - 15 * mm
    linie_y = min(kopf_top_y - kopf_hoehe - 4 * mm, A4[1] - 12 * mm - LOGO_HOEHE - 3 * mm)
    erste_topmargin = A4[1] - linie_y + 6 * mm

    doc = BaseDocTemplate(buf, pagesize=A4, title=titel, author=verein.name, leftMargin=25 * mm, rightMargin=20 * mm,
                          topMargin=erste_topmargin, bottomMargin=28 * mm)
    frame_erste = Frame(25 * mm, 28 * mm, A4[0] - 45 * mm, A4[1] - erste_topmargin - 28 * mm, id="f_erste",
                        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    frame_folge = Frame(25 * mm, 28 * mm, A4[0] - 45 * mm, A4[1] - 46 * mm, id="f_folge", leftPadding=0,
                        rightPadding=0, topPadding=0, bottomPadding=0)

    def erste(canvas, d):
        _briefkopf_zeichnen(canvas, verein, kopf_p, kopf_hoehe, linie_y)
        _fuss(canvas, verein, seitenzahl, d)

    def folge(canvas, d):
        _fuss(canvas, verein, seitenzahl, d)

    doc.addPageTemplates([PageTemplate(id="Erste", frames=[frame_erste], onPage=erste),
                          PageTemplate(id="Folge", frames=[frame_folge], onPage=folge)])
    stile = _stile()
    story = [NextPageTemplate("Folge")]
    for i, s in enumerate(seiten):
        if i:
            story += [NextPageTemplate("Erste"), PageBreak(), NextPageTemplate("Folge")]
        story += _seite(verein, s, stile)
    if not seiten:
        story.append(Spacer(1, 1))
    doc.build(story)
    return buf.getvalue()


def brief_pdf(verein, empfaenger, betreff, meta=(), vor=(), tabelle=None, nach=(), titel=None, wasserzeichen=None):
    """Einzelner Brief (Rechnung, Mahnung, Leihschein, Zuwendungsbestätigung ...)."""
    return seiten_pdf(verein, [{"empfaenger": empfaenger, "betreff": betreff, "meta": meta, "vor": vor,
                                "tabelle": tabelle, "nach": nach, "wasserzeichen": wasserzeichen}],
                      titel=titel or betreff)
