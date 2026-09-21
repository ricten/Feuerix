from decimal import Decimal
from io import BytesIO

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from apps.core.pdf import brief_pdf
from apps.core.util import geld

ETIKETT_SPALTEN = 3
ETIKETT_ZEILEN = 6
ETIKETT_BREITE = 58 * mm
ETIKETT_HOEHE = 40 * mm
ETIKETT_QR_GROESSE = 24 * mm


def _qr_zeichnen(c, url, x, y, groesse):
    widget = QrCodeWidget(url)
    x0, y0, x1, y1 = widget.getBounds()
    breite, hoehe = x1 - x0, y1 - y0
    d = Drawing(groesse, groesse, transform=[groesse / breite, 0, 0, groesse / hoehe, -x0 * groesse / breite,
                                             -y0 * groesse / hoehe])
    d.add(widget)
    renderPDF.draw(d, c, x, y)


def etiketten_pdf(gegenstaende, scan_url):
    """Etikettenbogen (A4, mehrspaltig) mit QR-Code je Gegenstand - der QR-Code verweist auf `scan_url(inventarnummer)`,
    darüber im System zum Scannen per Handy z. B. beim Verleih-Start. `gegenstaende` darf auch Duplikate enthalten
    (mehrere Etiketten desselben Gegenstands)."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    rand_x = (A4[0] - ETIKETT_SPALTEN * ETIKETT_BREITE) / 2
    rand_y = (A4[1] - ETIKETT_ZEILEN * ETIKETT_HOEHE) / 2
    pro_seite = ETIKETT_SPALTEN * ETIKETT_ZEILEN
    for i, g in enumerate(gegenstaende):
        pos = i % pro_seite
        if i and pos == 0:
            c.showPage()
        spalte, zeile = pos % ETIKETT_SPALTEN, pos // ETIKETT_SPALTEN
        x = rand_x + spalte * ETIKETT_BREITE
        y = A4[1] - rand_y - (zeile + 1) * ETIKETT_HOEHE
        c.saveState()
        c.setDash(2, 2)
        c.setStrokeColor(colors.lightgrey)
        c.rect(x, y, ETIKETT_BREITE, ETIKETT_HOEHE)
        c.restoreState()
        _qr_zeichnen(c, scan_url(g.inventarnummer), x + (ETIKETT_BREITE - ETIKETT_QR_GROESSE) / 2,
                    y + ETIKETT_HOEHE - ETIKETT_QR_GROESSE - 3 * mm, ETIKETT_QR_GROESSE)
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(x + ETIKETT_BREITE / 2, y + 6.5 * mm, g.inventarnummer)
        c.setFont("Helvetica", 7)
        c.drawCentredString(x + ETIKETT_BREITE / 2, y + 2 * mm, g.bezeichnung[:30])
    c.save()
    return buf.getvalue()


def leihschein_pdf(v):
    g, verein = v.gegenstand, v.verein
    emp = [v.wer]
    if v.entleiher_id:
        emp = v.entleiher.anschrift_zeilen()
    elif v.entleiher_kontakt:
        emp.append(v.entleiher_kontakt)
    tab = [["Gegenstand", "Inventarnr.", "Zeitraum"],
           [f"{g.bezeichnung} {g.hersteller} {g.modell}".strip(), g.inventarnummer,
            f"{v.von:%d.%m.%Y} – {v.bis:%d.%m.%Y}"]]
    text = [f"Der oben genannte Gegenstand wird von {verein.name} an {v.wer} ausgeliehen. "
            "Der Entleiher verpflichtet sich, den Gegenstand pfleglich zu behandeln und bis zum genannten Termin "
            "vollständig und in ordnungsgemäßem Zustand zurückzugeben. Für Verlust und Beschädigung haftet der Entleiher."]
    if v.zweck:
        text.append(f"Zweck: {v.zweck}")
    text.append(f"Zustand bei Ausgabe: {v.get_zustand_bei_ausgabe_display() if v.zustand_bei_ausgabe else g.get_zustand_display()}")
    if v.leihgebuehr:
        text.append(f"Leihgebühr: {geld(v.leihgebuehr)}")
    if v.kaution:
        text.append(f"Kaution: {geld(v.kaution)} (wird bei ordnungsgemäßer Rückgabe erstattet)")
    text += ["\n\nDatum, Unterschrift Entleiher: ______________________     Unterschrift Verein: ______________________"]
    return brief_pdf(verein, emp, "Leihschein", meta=[("Datum", f"{v.von:%d.%m.%Y}")], tabelle=tab, nach=text)


def leihschein_sammel_pdf(positionen):
    """Ein gemeinsamer Leihschein für mehrere gleichzeitig verliehene Gegenstände (Verleih-Vorgang)."""
    v0, verein = positionen[0], positionen[0].verein
    emp = [v0.wer]
    if v0.entleiher_id:
        emp = v0.entleiher.anschrift_zeilen()
    elif v0.entleiher_kontakt:
        emp.append(v0.entleiher_kontakt)
    tab = [["Gegenstand", "Inventarnr.", "Zeitraum"]]
    gebuehr_gesamt = kaution_gesamt = Decimal("0")
    for v in positionen:
        g = v.gegenstand
        tab.append([f"{g.bezeichnung} {g.hersteller} {g.modell}".strip(), g.inventarnummer,
                   f"{v.von:%d.%m.%Y} – {v.bis:%d.%m.%Y}"])
        gebuehr_gesamt += v.leihgebuehr or 0
        kaution_gesamt += v.kaution or 0
    text = [f"Die oben genannten Gegenstände werden von {verein.name} an {v0.wer} ausgeliehen. "
            "Der Entleiher verpflichtet sich, die Gegenstände pfleglich zu behandeln und bis zum genannten Termin "
            "vollständig und in ordnungsgemäßem Zustand zurückzugeben. Für Verlust und Beschädigung haftet der Entleiher."]
    if v0.zweck:
        text.append(f"Zweck: {v0.zweck}")
    if gebuehr_gesamt:
        text.append(f"Leihgebühr gesamt: {geld(gebuehr_gesamt)}")
    if kaution_gesamt:
        text.append(f"Kaution gesamt: {geld(kaution_gesamt)} (wird bei ordnungsgemäßer Rückgabe erstattet)")
    text += ["\n\nDatum, Unterschrift Entleiher: ______________________     Unterschrift Verein: ______________________"]
    return brief_pdf(verein, emp, "Leihschein", meta=[("Datum", f"{v0.von:%d.%m.%Y}")], tabelle=tab, nach=text)
