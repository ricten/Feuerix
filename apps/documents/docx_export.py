"""Word-Export (.docx) - damit Schriftstücke außerhalb des Systems weiterbearbeitet werden können."""
from io import BytesIO

from .pdf import absaetze
from .platzhalter import ersetzen


def schriftstueck_docx(s):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt

    ctx = s.kontext()
    v = s.verein
    doc = Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(11)
    try:
        if v.logo:
            doc.add_picture(v.logo.path, width=Cm(4.5))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    except Exception:
        pass
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
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()
