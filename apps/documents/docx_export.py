"""Word-Export (.docx) - damit Schriftstücke außerhalb des Systems weiterbearbeitet werden können.
Briefkopf/Fuß folgen dem gleichen CI wie die PDF-Erzeugung (apps/core/pdf.py): großer Vereinsname in
neutralem Grau mit Trennlinie in der Akzentfarbe, Logo rechts, Fußzeile mit Vertretungsberechtigtem und
Bankverbindung."""
from io import BytesIO

from .pdf import absaetze
from .platzhalter import ersetzen

STANDARD_AKZENTFARBE = "1F4E79"
BRIEFKOPF_TEXTFARBE = "646363"


def _farbe(verein):
    from docx.shared import RGBColor
    hex_ = (verein.akzentfarbe or "").lstrip("#")
    try:
        return RGBColor.from_string(hex_)
    except ValueError:
        return RGBColor.from_string(STANDARD_AKZENTFARBE)


def _trennlinie(paragraph, farbe):
    """Fügt dem Absatz einen unteren Rahmen hinzu (python-docx kennt keine Linie/HR direkt)."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    pbdr = OxmlElement("w:pBdr")
    unten = OxmlElement("w:bottom")
    unten.set(qn("w:val"), "single")
    unten.set(qn("w:sz"), "18")
    unten.set(qn("w:space"), "1")
    unten.set(qn("w:color"), "%02X%02X%02X" % (farbe[0], farbe[1], farbe[2]))
    pbdr.append(unten)
    paragraph._p.get_or_add_pPr().append(pbdr)


def _fusszeile(doc, verein):
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt, RGBColor
    absatz = doc.sections[0].footer.paragraphs[0]
    absatz.alignment = WD_ALIGN_PARAGRAPH.CENTER
    zeilen = [z for z in (
        " | ".join(x for x in (verein.name, verein.vereinsregister, verein.email) if x),
        ", ".join(x for x in (verein.unterschrift_1, verein.adresszeile) if x),
        " | ".join(x for x in (
            f"Bank: {verein.bankname}" if verein.bankname else "",
            f"IBAN: {verein.iban}" if verein.iban else "",
            f"BIC: {verein.bic}" if verein.bic else "") if x),
    ) if z]
    for i, z in enumerate(zeilen):
        lauf = absatz.add_run(z)
        lauf.font.size = Pt(10)
        lauf.font.color.rgb = RGBColor.from_string(BRIEFKOPF_TEXTFARBE)
        if i < len(zeilen) - 1:
            lauf.add_break()


def schriftstueck_docx(s):
    from docx import Document
    from docx.enum.table import WD_ALIGN_VERTICAL
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    ctx = s.kontext()
    v = s.verein
    farbe = _farbe(v)

    doc = Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(11)

    # Briefkopf: Vereinsname (groß, neutrales Grau) links, Logo rechts, in einer randlosen Tabelle;
    # die Akzentfarbe des Vereins wird nur für die Trennlinie darunter verwendet.
    kopf = doc.add_table(rows=1, cols=2)
    kopf.columns[0].width = Cm(11)
    kopf.columns[1].width = Cm(5)
    name_zelle, logo_zelle = kopf.rows[0].cells
    name_zelle.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    logo_zelle.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    lauf = name_zelle.paragraphs[0].add_run(v.name)
    lauf.font.size = Pt(24)
    lauf.font.color.rgb = RGBColor.from_string(BRIEFKOPF_TEXTFARBE)
    lauf.font.name = "Montserrat"
    lauf._element.rPr.rFonts.set(qn("w:hAnsi"), "Montserrat")
    logo_absatz = logo_zelle.paragraphs[0]
    logo_absatz.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    try:
        if v.logo:
            logo_absatz.add_run().add_picture(v.logo.path, width=Cm(4.5))
    except Exception:
        pass

    linie = doc.add_paragraph()
    linie.paragraph_format.space_before = Pt(2)
    linie.paragraph_format.space_after = Pt(10)
    _trennlinie(linie, farbe)

    absender = ", ".join(x for x in (v.name, v.anschrift, f"{v.plz} {v.ort}".strip()) if x)
    p = doc.add_paragraph(absender)
    p.runs[0].font.size = Pt(8)
    if s.mitglied_id and s.art != "protokoll":
        doc.add_paragraph("\n".join(z for z in s.mitglied.anschrift_zeilen() if z))
    d = doc.add_paragraph(ctx["datum"])
    d.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    doc.add_heading(ersetzen(s.betreff or s.titel, ctx), level=2)
    for a in absaetze(ersetzen(s.text, ctx)):
        doc.add_paragraph(a)

    _fusszeile(doc, v)

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()
