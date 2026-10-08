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

# Vorgaben, falls kein Verein (bzw. keine eigenen Einstellungen) übergeben wird - entsprechen den bisherigen
# fest einprogrammierten Werten (A4-Etikettenbogen, 3 Spalten x 6 Zeilen, 58 x 40 mm).
ETIKETT_SPALTEN = 3
ETIKETT_ZEILEN = 6
ETIKETT_BREITE_MM = 58
ETIKETT_HOEHE_MM = 40


def _qr_zeichnen(c, url, x, y, groesse):
    widget = QrCodeWidget(url)
    x0, y0, x1, y1 = widget.getBounds()
    breite, hoehe = x1 - x0, y1 - y0
    d = Drawing(groesse, groesse, transform=[groesse / breite, 0, 0, groesse / hoehe, -x0 * groesse / breite,
                                             -y0 * groesse / hoehe])
    d.add(widget)
    renderPDF.draw(d, c, x, y)


def etiketten_pdf(gegenstaende, scan_url, verein=None):
    """Etiketten mit QR-Code je Gegenstand - der QR-Code verweist auf `scan_url(inventarnummer)`, darüber im
    System zum Scannen per Handy z. B. beim Verleih-Start. `gegenstaende` darf auch Duplikate enthalten (mehrere
    Etiketten desselben Gegenstands).

    Größe und Anordnung kommen aus den Vereinseinstellungen (Verwaltung › Verein/Einstellungen): Standardmäßig
    ein mehrspaltiger A4-Etikettenbogen (3 x 6, 58 x 40 mm). Bei „Etiketten je Zeile“ UND „Etikettenzeilen je
    Seite“ jeweils 1 wird stattdessen die PDF-Seite selbst exakt auf die eingestellte Etikettengröße
    zugeschnitten (ein Etikett = eine Seite) - so lässt sich z. B. ein Dymo LabelWriter 450 mit einer
    Endlos-Etikettenrolle direkt bedrucken, ohne A4-Papierformat."""
    spalten = getattr(verein, "etikett_spalten", ETIKETT_SPALTEN) or ETIKETT_SPALTEN
    zeilen = getattr(verein, "etikett_zeilen", ETIKETT_ZEILEN) or ETIKETT_ZEILEN
    breite = (getattr(verein, "etikett_breite_mm", ETIKETT_BREITE_MM) or ETIKETT_BREITE_MM) * mm
    hoehe = (getattr(verein, "etikett_hoehe_mm", ETIKETT_HOEHE_MM) or ETIKETT_HOEHE_MM) * mm
    einzelblatt = spalten == 1 and zeilen == 1
    pagesize = (breite, hoehe) if einzelblatt else A4
    # QR-Code und Textzeilen proportional zur eingestellten Etikettengröße statt fester 58x40mm-Annahme.
    rand = min(breite, hoehe) * 0.06
    text_hoehe = hoehe * 0.24
    qr_groesse = max(5 * mm, min(breite - 2 * rand, hoehe - text_hoehe - rand))

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=pagesize)
    rand_x = 0 if einzelblatt else (pagesize[0] - spalten * breite) / 2
    rand_y = 0 if einzelblatt else (pagesize[1] - zeilen * hoehe) / 2
    pro_seite = spalten * zeilen
    for i, g in enumerate(gegenstaende):
        pos = i % pro_seite
        if i and pos == 0:
            c.showPage()
        spalte, zeile = pos % spalten, pos // spalten
        x = rand_x + spalte * breite
        y = pagesize[1] - rand_y - (zeile + 1) * hoehe
        if not einzelblatt:
            c.saveState()
            c.setDash(2, 2)
            c.setStrokeColor(colors.lightgrey)
            c.rect(x, y, breite, hoehe)
            c.restoreState()
        _qr_zeichnen(c, scan_url(g.inventarnummer), x + (breite - qr_groesse) / 2,
                    y + hoehe - qr_groesse - rand, qr_groesse)
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(x + breite / 2, y + text_hoehe * 0.55, g.inventarnummer)
        c.setFont("Helvetica", 7)
        c.drawCentredString(x + breite / 2, y + text_hoehe * 0.15, g.bezeichnung[:30])
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
