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


def _etikett_layout(breite, hoehe):
    """Berechnet Rand, Textblockhöhe, QR-Code-Größe und den freien Platz unter dem Inhalt für ein Etikett
    gegebener Größe (in Punkten, also bereits *mm). Rand und Textblock sind bewusst kleine ABSOLUTE Maße (nicht
    prozentual zur Etikettenhöhe!): Bei einem schmalen, hohen Etikett würde ein prozentualer Textblock unnötig
    viel Platz beanspruchen und eine große Lücke zwischen QR-Code und Text entstehen lassen. Nur bei sehr
    kleinen Etiketten wird zur Sicherheit heruntergerechnet, damit auf Mini-Formaten nichts überlappt. QR-Code
    und Textblock werden als eine Einheit senkrecht im Etikett zentriert (statt QR oben/Text unten fest
    anzupinnen) - sonst bleibt bei hohen Etiketten eine ungenutzte Lücke in der Mitte stehen."""
    rand = min(3 * mm, min(breite, hoehe) * 0.08)
    text_block = min(12 * mm, hoehe * 0.35)   # Platz fuer drei Zeilen: Inventarnummer, Bezeichnung, Lagerort
    qr_groesse = max(5 * mm, min(breite - 2 * rand, hoehe - text_block - 2 * rand))
    inhalt_hoehe = qr_groesse + rand + text_block
    unten_frei = (hoehe - inhalt_hoehe) / 2
    return {"rand": rand, "text_block": text_block, "qr_groesse": qr_groesse, "unten_frei": unten_frei}


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

    # Deutlich höhere als breite Etiketten (z. B. eine schmale Dymo-Rolle hochkant) werden gedreht gezeichnet:
    # der QR-Code nutzt dann die lange statt der kurzen Seite aus, statt klein und zentriert mit viel Leerraum
    # auf der schmalen Seite zu kleben. Für breiter-als-hohe Etiketten (die uebliche Ausrichtung, z. B. 89x28mm)
    # ist das bereits die optimale Lage - dort wird nicht gedreht.
    gedreht = hoehe > breite * 1.2
    zeichenbreite, zeichenhoehe = (hoehe, breite) if gedreht else (breite, hoehe)
    layout = _etikett_layout(zeichenbreite, zeichenhoehe)
    rand, text_block, qr_groesse, unten_frei = (layout["rand"], layout["text_block"], layout["qr_groesse"],
                                                layout["unten_frei"])

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
        c.saveState()
        if not einzelblatt:
            c.setDash(2, 2)
            c.setStrokeColor(colors.lightgrey)
            c.rect(x, y, breite, hoehe)
        if gedreht:
            # Ursprung in die obere linke Ecke der Zelle legen und 90° im Uhrzeigersinn drehen - danach wird
            # lokal wie im ungedrehten Fall gezeichnet, nur mit vertauschter Breite/Höhe.
            c.translate(x, y + hoehe)
            c.rotate(-90)
        else:
            c.translate(x, y)
        _qr_zeichnen(c, scan_url(g.inventarnummer), (zeichenbreite - qr_groesse) / 2,
                    unten_frei + text_block + rand, qr_groesse)
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(zeichenbreite / 2, unten_frei + text_block * 0.80, g.inventarnummer)
        c.setFont("Helvetica", 7)
        c.drawCentredString(zeichenbreite / 2, unten_frei + text_block * 0.46, g.bezeichnung[:30])
        if g.lagerort_id:
            c.setFont("Helvetica-Oblique", 6)
            c.drawCentredString(zeichenbreite / 2, unten_frei + text_block * 0.14, str(g.lagerort)[:30])
        c.restoreState()
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
