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
STANDARD_AKZENTFARBE = "#AF2B1E"
BRIEFKOPF_TEXTFARBE = "#646363"
RAND_LINKS = 25 * mm
RAND_RECHTS = 10 * mm

SCHRIFTEN = {"Helvetica": "Helvetica-Bold", "Times-Roman": "Times-Bold", "Courier": "Courier-Bold"}


class Layout:
    """Gestaltung eines Briefs (Vorlagen-Layout). Die Standardwerte entsprechen dem bisherigen Aussehen, so dass alle
    Dokumente ohne eigenes Layout (Rechnungen, Mahnungen ...) unveraendert bleiben.
    kopf: voll (Name + Logo + Linie) | name | logo | ohne (z. B. fuer vorgedrucktes Briefpapier)
    logo_position: rechts | links      fuss: voll | seitenzahl | ohne      datum_position: rechts | links"""

    def __init__(self, kopf="voll", logo_position="rechts", schriftart="Helvetica", schriftgroesse=10, rand_links_mm=25,
                 rand_rechts_mm=10, rand_oben_mm=45, rand_unten_mm=28, fuss="voll", absenderzeile=True,
                 datum_position="rechts"):
        self.kopf, self.logo_position = kopf, logo_position
        self.schriftart = schriftart if schriftart in SCHRIFTEN else "Helvetica"
        self.schriftgroesse = float(schriftgroesse)
        self.rand_links, self.rand_rechts = rand_links_mm * mm, rand_rechts_mm * mm
        self.rand_oben_ohne_kopf, self.rand_unten = rand_oben_mm * mm, rand_unten_mm * mm
        self.fuss, self.absenderzeile, self.datum_position = fuss, bool(absenderzeile), datum_position

    def kopie_mit(self, **aenderungen):
        """Dasselbe Layout mit einzelnen geaenderten Werten (Objekt bleibt unveraendert)."""
        neu = Layout.__new__(Layout)
        neu.__dict__.update(self.__dict__)
        neu.__dict__.update(aenderungen)
        return neu

    @classmethod
    def von_vorlage(cls, vorlage):
        """Layout einer Vorlage (documents.Vorlage) - ohne Vorlage das Standardlayout."""
        if vorlage is None:
            return cls()
        return cls(kopf=vorlage.layout_kopf, logo_position=vorlage.layout_logo_position,
                   schriftart=vorlage.layout_schriftart, schriftgroesse=vorlage.layout_schriftgroesse,
                   rand_links_mm=vorlage.layout_rand_links, rand_rechts_mm=vorlage.layout_rand_rechts,
                   rand_oben_mm=vorlage.layout_rand_oben, rand_unten_mm=vorlage.layout_rand_unten,
                   fuss=vorlage.layout_fuss, absenderzeile=vorlage.layout_absenderzeile,
                   datum_position=vorlage.layout_datum_position)


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


def _akzentfarbe_fuss(verein):
    """Zweite Akzentfarbe für die Linie über der Fußzeile; ohne eigene Farbe wie oben."""
    try:
        return colors.HexColor(verein.akzentfarbe_fuss or verein.akzentfarbe or STANDARD_AKZENTFARBE)
    except Exception:
        return _akzentfarbe(verein)


def _logo_groesse(pfad):
    """-> (Breite, Höhe) in Punkten, seitenverhältnistreu in die CI-Logobox eingepasst, oder None."""
    try:
        bild = ImageReader(pfad)
        iw, ih = bild.getSize()
        s = min(LOGO_BREITE / iw, LOGO_HOEHE / ih)
        return iw * s, ih * s
    except Exception:
        return None


def _logo_zeichnen(canvas, verein, layout):
    pfad = logo_datei(verein)
    if not pfad:
        return
    groesse = _logo_groesse(pfad)
    if not groesse:
        return
    w, h = groesse
    x = layout.rand_links if layout.logo_position == "links" else A4[0] - layout.rand_rechts - w
    try:
        canvas.drawImage(ImageReader(pfad), x, A4[1] - 12 * mm - h, width=w, height=h, mask="auto")
    except Exception:
        pass


def _logo_breite(verein, layout):
    """Platz, den das Logo im Briefkopf braucht (0 ohne Logo oder bei Kopf ohne Logo)."""
    if layout.kopf not in ("voll", "logo") or not logo_datei(verein):
        return 0
    groesse = _logo_groesse(logo_datei(verein))
    return groesse[0] if groesse else 0


def _briefkopf_hoehe(verein, layout=None):
    """-> (Paragraph oder None, Höhe in Punkten) für den Vereinsnamen als Briefkopf-Überschrift (neben dem Logo).
    Textfarbe bewusst neutral grau (nicht die Akzentfarbe) - die Akzentfarbe ist nur für die Trennlinie."""
    layout = layout or Layout()
    if layout.kopf not in ("voll", "name"):
        return None, 0
    logo_b = LOGO_BREITE if layout.kopf == "voll" else 0
    breite = A4[0] - layout.rand_links - layout.rand_rechts - logo_b - (8 * mm if logo_b else 0)
    stil = ParagraphStyle("briefkopf", fontName="Helvetica", fontSize=22, leading=25,
                          textColor=colors.HexColor(BRIEFKOPF_TEXTFARBE))
    p = Paragraph(escape(verein.name), stil)
    _, hoehe = p.wrap(breite, 60 * mm)
    return p, hoehe


def _briefkopf_zeichnen(canvas, verein, kopf_p, kopf_hoehe, linie_y, layout=None):
    layout = layout or Layout()
    if layout.kopf == "ohne":
        return
    kopf_top_y = A4[1] - 15 * mm
    logo_b = _logo_breite(verein, layout)
    links = layout.logo_position == "links" and logo_b
    if kopf_p is not None:
        x = layout.rand_links + (logo_b + 8 * mm if links else 0)
        kopf_p.drawOn(canvas, x, kopf_top_y - kopf_hoehe)
    if layout.kopf in ("voll", "logo"):
        _logo_zeichnen(canvas, verein, layout)
    linie_start, linie_ende = layout.rand_links, A4[0] - layout.rand_rechts
    if logo_b and not links:
        linie_ende = min(linie_ende, A4[0] - layout.rand_rechts - logo_b - 4 * mm)
    canvas.setStrokeColor(_akzentfarbe(verein))
    canvas.setLineWidth(0.6)
    canvas.line(linie_start, linie_y, linie_ende, linie_y)


def _fuss(canvas, verein, seitenzahl, doc, layout=None):
    layout = layout or Layout()
    if layout.fuss == "ohne":
        return
    canvas.saveState()
    if layout.fuss == "seitenzahl":
        canvas.setFont("Helvetica", 8.5)
        canvas.setFillColor(colors.HexColor(BRIEFKOPF_TEXTFARBE))
        if seitenzahl:
            canvas.drawRightString(A4[0] - layout.rand_rechts, 8 * mm, f"Seite {doc.page}")
        canvas.restoreState()
        return
    mit_name = layout.fuss != "ohne_name"      # Vereinsname steht schon im Briefkopf - Fusszeile ohne ihn moeglich
    vertretung = ", ".join(x for x in (verein.unterschrift_1, verein.adresszeile) if x)
    erste_zeile = " | ".join(x for x in ((verein.name if mit_name else ""), verein.vereinsregister, verein.email) if x)
    if not mit_name and not (erste_zeile or vertretung or verein.bankname or verein.iban or verein.bic
                             or verein.steuernummer):
        canvas.restoreState()
        return _fuss(canvas, verein, seitenzahl, doc, layout.kopie_mit(fuss="seitenzahl"))     # nichts anzuzeigen
    canvas.setStrokeColor(_akzentfarbe_fuss(verein))
    canvas.setLineWidth(0.4)
    canvas.line(layout.rand_links, 23 * mm, A4[0] - layout.rand_rechts, 23 * mm)
    canvas.setFont("Helvetica", 8.5)
    canvas.setFillColor(colors.HexColor(BRIEFKOPF_TEXTFARBE))
    zeilen = [
        erste_zeile,
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
        canvas.drawRightString(A4[0] - layout.rand_rechts, 8 * mm, f"Seite {doc.page}")
    canvas.restoreState()


def _stile(layout=None):
    layout = layout or Layout()
    st = getSampleStyleSheet()
    schrift = layout.schriftart
    groesse = layout.schriftgroesse
    normal = ParagraphStyle("n", parent=st["BodyText"], fontName=schrift, fontSize=groesse, leading=groesse * 1.35)
    return {
        "normal": normal,
        "klein": ParagraphStyle("k", parent=normal, fontSize=7.5, textColor=colors.grey),
        "rechts": ParagraphStyle("r", parent=normal, alignment=0 if layout.datum_position == "links" else 2),
        "rechts_tabelle": ParagraphStyle("rt", parent=normal, alignment=2),
        "kopf": ParagraphStyle("h", parent=st["Heading2"], fontName=SCHRIFTEN[schrift], spaceAfter=6),
    }


def _tabelle(t_, normal, rechts):
    """Eine Tabelle (optional mit fetter Titelzeile) als Liste von Flowables - fuer Tabellen und Bloecke."""
    story = []
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
    return story + [tb, Spacer(1, 4 * mm)]


def _seite(verein, s, stile, layout=None):
    layout = layout or Layout()
    normal, klein, kopf = stile["normal"], stile["klein"], stile["kopf"]
    datum_stil, rechts = stile["rechts"], stile["rechts_tabelle"]     # Datum kann links stehen, Tabellenzahlen bleiben rechts
    story = []
    absender = ", ".join(x for x in (verein.name, verein.anschrift, f"{verein.plz} {verein.ort}".strip()) if x)
    if layout.absenderzeile and absender != verein.name:     # nur der Vereinsname wuerde den Briefkopf bloss wiederholen
        t = Table([[_p(absender, klein)]], colWidths=[105 * mm], hAlign="LEFT")
        t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        story += [t, Spacer(1, 8 * mm)]
    story += [_p("\n".join(z for z in s.get("empfaenger", []) if z), normal), Spacer(1, 10 * mm)]
    if s.get("datum"):
        # Einfache Briefe (Serienbrief u. ä.) brauchen nur eine Zeile - die zweispaltige Meta-Tabelle
        # unten (für Rechnungen/Mahnungen mit mehreren Angaben) sähe hier mit nur einem kurzen Wert
        # unschön aus (breiter Leerraum bis zum rechten Rand).
        story += [_p(s["datum"], datum_stil), Spacer(1, 6 * mm)]
    elif s.get("meta"):
        m = Table([[_p(k, normal), _p(v, normal)] for k, v in s["meta"]], colWidths=[40 * mm, 55 * mm], hAlign="RIGHT")
        m.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
        story += [m, Spacer(1, 6 * mm)]
    story.append(Paragraph(f"<b>{escape(s['betreff'])}</b>", kopf))
    if s.get("wasserzeichen"):
        story.append(Paragraph(f"<font color='red'><b>{escape(s['wasserzeichen'])}</b></font>", normal))
    for a in s.get("vor", ()):
        if callable(a):      # formatierter Text (documents.richtext): erzeugt seine Bausteine passend zum Layout
            story += a(stile, layout, A4[0] - layout.rand_links - layout.rand_rechts)
        else:
            story += [_p(a, normal), Spacer(1, 3 * mm)]
    tabellen = list(s.get("tabellen", []))
    if s.get("tabelle"):
        tabellen.insert(0, {"zeilen": s["tabelle"]})
    for b in s.get("bloecke", ()):
        # Block = Ueberschrift, Absaetze, Tabelle - einzeln und nacheinander (z. B. je Abstimmung/Wahl in den Anlagen)
        story.append(Paragraph(f"<b>{escape(b['titel'])}</b>", ParagraphStyle(
            "bt", parent=normal, spaceBefore=8, spaceAfter=2, keepWithNext=1)))
        for a in b.get("absaetze", ()):
            story += [_p(a, normal), Spacer(1, 1.5 * mm)]
        if b.get("zeilen"):
            story += _tabelle({k: v for k, v in b.items() if k not in ("titel", "absaetze", "nach")}, normal, rechts)
        for a in b.get("nach", ()):
            story += [Spacer(1, 1 * mm), _p(a, normal), Spacer(1, 2 * mm)]
    for t_ in tabellen:
        story += _tabelle(t_, normal, rechts)
    for a in s.get("nach", ()):
        story += [_p(a, normal), Spacer(1, 3 * mm)]
    return story


def seiten_pdf(verein, seiten, titel="Dokument", seitenzahl=True, layout=None):
    """Mehrere Briefe in einem PDF (Serienbrief); jeder beginnt auf neuer Seite mit Briefkopf (Name, Logo,
    Akzentfarbe). `layout` (siehe Layout) gestaltet Briefkopf, Schrift, Raender und Fusszeile - ohne Angabe das
    bisherige Standardaussehen."""
    layout = layout or Layout()
    buf = BytesIO()
    kopf_p, kopf_hoehe = _briefkopf_hoehe(verein, layout)
    kopf_top_y = A4[1] - 15 * mm
    if layout.kopf == "ohne":
        erste_topmargin = layout.rand_oben_ohne_kopf          # z. B. vorgedrucktes Briefpapier
        linie_y = A4[1] - erste_topmargin
    else:
        linie_y = kopf_top_y - kopf_hoehe - 4 * mm
        logo_groesse = _logo_groesse(logo_datei(verein)) if (layout.kopf in ("voll", "logo") and logo_datei(verein)) else None
        if logo_groesse:
            # Linie endet an der Logo-Unterkante (nicht an der festen Logobox), sonst könnte sie bei
            # schmalen/hochformatigen Logos zu weit oben oder unten landen.
            linie_y = min(linie_y, A4[1] - 12 * mm - logo_groesse[1] - 3 * mm)
        linie_y += 2 * mm
        erste_topmargin = A4[1] - linie_y + 6 * mm

    rand = layout.rand_links + layout.rand_rechts
    unten = layout.rand_unten
    doc = BaseDocTemplate(buf, pagesize=A4, title=titel, author=verein.name, leftMargin=layout.rand_links,
                          rightMargin=layout.rand_rechts, topMargin=erste_topmargin, bottomMargin=unten)
    frame_erste = Frame(layout.rand_links, unten, A4[0] - rand, A4[1] - erste_topmargin - unten, id="f_erste",
                        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    frame_folge = Frame(layout.rand_links, unten, A4[0] - rand, A4[1] - 18 * mm - unten, id="f_folge", leftPadding=0,
                        rightPadding=0, topPadding=0, bottomPadding=0)

    def erste(canvas, d):
        _briefkopf_zeichnen(canvas, verein, kopf_p, kopf_hoehe, linie_y, layout)
        _fuss(canvas, verein, seitenzahl, d, layout)

    def folge(canvas, d):
        _fuss(canvas, verein, seitenzahl, d, layout)

    doc.addPageTemplates([PageTemplate(id="Erste", frames=[frame_erste], onPage=erste),
                          PageTemplate(id="Folge", frames=[frame_folge], onPage=folge)])
    stile = _stile(layout)
    story = [NextPageTemplate("Folge")]
    for i, s in enumerate(seiten):
        if i:
            story += [NextPageTemplate("Erste"), PageBreak(), NextPageTemplate("Folge")]
        story += _seite(verein, s, stile, layout)
    if not seiten:
        story.append(Spacer(1, 1))
    doc.build(story)
    return buf.getvalue()


def brief_pdf(verein, empfaenger, betreff, meta=(), vor=(), tabelle=None, nach=(), titel=None, wasserzeichen=None):
    """Einzelner Brief (Rechnung, Mahnung, Leihschein, Zuwendungsbestätigung ...)."""
    return seiten_pdf(verein, [{"empfaenger": empfaenger, "betreff": betreff, "meta": meta, "vor": vor,
                                "tabelle": tabelle, "nach": nach, "wasserzeichen": wasserzeichen}],
                      titel=titel or betreff)
