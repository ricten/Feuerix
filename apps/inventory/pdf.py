from decimal import Decimal
from io import BytesIO

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from apps.core.pdf import brief_pdf, logo_datei, seiten_pdf
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


def _etikett_modus(breite, hoehe):
    """Entscheidet die Ausrichtung des Etikett-Inhalts:
    - `gedreht`: der Inhalt wird um 90° gedreht gezeichnet (deutlich höhere als breite Etiketten, z. B. eine
      schmale Rolle hochkant) - der QR-Code nutzt dann die lange statt der kurzen Seite aus.
    - `nebeneinander`: QR-Code links, Text rechts statt QR oben/Text unten (sehr flache/breite Etiketten bzw.
      nach dem Drehen immer noch sehr flache Etiketten) - ein gestapeltes Layout würde den QR-Code dort unnötig
      klein werden lassen, da die Höhe der limitierende Faktor wäre.
    -> (gedreht, nebeneinander, zeichenbreite, zeichenhöhe) - Breite/Höhe der Zeichenfläche NACH dem Drehen."""
    gedreht = hoehe > breite * 1.2
    zeichenbreite, zeichenhoehe = (hoehe, breite) if gedreht else (breite, hoehe)
    nebeneinander = zeichenbreite > zeichenhoehe * 1.8
    return gedreht, nebeneinander, zeichenbreite, zeichenhoehe


def _etikett_layout(breite, hoehe, nebeneinander, mit_logo=False):
    """Berechnet die Geometrie (QR-Code-Position/-Größe, Textbereich) für ein Etikett gegebener Größe (in
    Punkten, also bereits *mm). Maße sind bewusst klein und ABSOLUT (nicht prozentual zur Etikettengröße) -
    sonst entstünde bei einem großen Etikett unnötig viel Leerraum bzw. bei einem kleinen Überlappungen. Die
    Rückgabe ist für beide Modi einheitlich (qr_x/qr_y/qr_groesse sowie eine Textbox text_mitte_x/text_unten_y/
    text_hoehe für bis zu drei zentrierte Zeilen), damit das Zeichnen selbst modusunabhängig bleibt:
    - Gestapelt: QR-Code oben, Textbox darunter - beides als Einheit senkrecht zentriert (sonst bliebe bei
      hohen Etiketten eine ungenutzte Lücke in der Mitte stehen).
    - Nebeneinander: QR-Code links über die volle Höhe, Textbox rechts daneben, beide senkrecht zentriert.
    `mit_logo` (nur gestapelt): der QR-Code sitzt dann rechts statt mittig, damit links daneben ein grosser Platz fuers
    Vereinslogo frei bleibt."""
    rand = min(2.5 * mm, min(breite, hoehe) * 0.08)
    if nebeneinander:
        qr_groesse = max(5 * mm, min(hoehe - 2 * rand, breite * 0.55))
        text_x0 = rand + qr_groesse + rand
        text_breite = max(breite - text_x0 - rand, 8 * mm)
        return {"qr_x": rand, "qr_y": (hoehe - qr_groesse) / 2, "qr_groesse": qr_groesse,
               "text_mitte_x": text_x0 + text_breite / 2, "text_unten_y": rand, "text_hoehe": hoehe - 2 * rand}
    text_hoehe = min(11 * mm, hoehe * 0.33)   # Platz fuer drei Zeilen: Inventarnummer, Bezeichnung, Lagerort
    qr_groesse = max(5 * mm, min(breite - 2 * rand, hoehe - text_hoehe - 2 * rand))
    unten_frei = (hoehe - (qr_groesse + rand + text_hoehe)) / 2
    qr_x = breite - rand - qr_groesse if mit_logo else (breite - qr_groesse) / 2
    return {"qr_x": qr_x, "qr_y": unten_frei + text_hoehe + rand, "qr_groesse": qr_groesse,
           "text_mitte_x": breite / 2, "text_unten_y": unten_frei, "text_hoehe": text_hoehe}


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

    gedreht, nebeneinander, zeichenbreite, zeichenhoehe = _etikett_modus(breite, hoehe)
    layout = _etikett_layout(zeichenbreite, zeichenhoehe, nebeneinander)
    logo_pfad = logo_datei(verein) if verein is not None else None
    logo = logo_schwarzweiss(logo_pfad) if logo_pfad else None
    logo_platz = None
    if logo:   # mit Logo rueckt der QR-Code zur Seite (gestapelt) - nur uebernehmen, wenn das Logo dann Platz hat
        mit_logo = _etikett_layout(zeichenbreite, zeichenhoehe, nebeneinander, mit_logo=True)
        logo_platz = _logo_platz(mit_logo, nebeneinander, zeichenbreite, zeichenhoehe)
        if logo_platz:
            layout = mit_logo

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
        _qr_zeichnen(c, scan_url(g.inventarnummer), layout["qr_x"], layout["qr_y"], layout["qr_groesse"])
        if logo_platz:   # Vereinslogo, wenn neben dem QR-Code Platz ist
            _logo_zeichnen(c, logo, logo_platz)
        mitte_x, unten_y, text_hoehe = layout["text_mitte_x"], layout["text_unten_y"], layout["text_hoehe"]
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(mitte_x, unten_y + text_hoehe * 0.80, g.inventarnummer)
        c.setFont("Helvetica", 9)
        c.drawCentredString(mitte_x, unten_y + text_hoehe * 0.46, g.bezeichnung[:30])
        if g.lagerort_id:
            c.setFont("Helvetica-Oblique", 8)
            c.drawCentredString(mitte_x, unten_y + text_hoehe * 0.14, str(g.lagerort)[:30])
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


def packliste_pdf(positionen):
    """Druckbare Packliste/Ausgabeliste zu einem Verleih-Vorgang (oder einzelnem Verleih): jede Position mit
    Inventarnummer, Gegenstand, Lagerort und Ankreuzfeldern fuer Ausgabe und Rueckgabe sowie Platz fuer
    Bemerkungen - zum Abhaken beim Zusammenstellen und bei der Rueckgabe."""
    v0, verein = positionen[0], positionen[0].verein
    positionen = sorted(positionen, key=lambda p: (p.gegenstand.lagerort.name if p.gegenstand.lagerort_id else "",
                                                   p.gegenstand.bezeichnung))
    von = min(p.von for p in positionen)
    bis = max(p.bis for p in positionen)
    zeilen = [["Nr.", "Inv.-Nr.", "Gegenstand", "Lagerort", "Ausgabe", "Rückgabe", "Bemerkung"]]
    for i, p in enumerate(positionen, 1):
        g = p.gegenstand
        zeilen.append([str(i), g.inventarnummer, f"{g.bezeichnung} {g.hersteller} {g.modell}".strip(),
                       str(g.lagerort) if g.lagerort_id else "", "[    ]", "[    ]", ""])
    vor = [f"Entleiher: {v0.wer}", f"Zeitraum: {von:%d.%m.%Y} – {bis:%d.%m.%Y}"]
    if v0.veranstaltung_id:
        vor.append(f"Veranstaltung: {v0.veranstaltung.titel}")
    if v0.zweck:
        vor.append(f"Zweck: {v0.zweck}")
    vor.append(f"Anzahl Positionen: {len(positionen)}")
    seite = {
        "empfaenger": [], "betreff": "Packliste", "vor": vor,
        "tabellen": [{"zeilen": zeilen, "breiten": [9, 24, 50, 30, 17, 17, 28], "rechts_ab": 99}],
        "nach": ["Ausgabe vollständig bestätigt (Datum, Unterschrift): ________________________________",
                 "Rückgabe vollständig bestätigt (Datum, Unterschrift): _____________________________"],
    }
    return seiten_pdf(verein, [seite], titel="Packliste")


# ---------------- Vereinslogo auf dem Etikett (nur wenn Platz ist)
LOGO_MIN = 7 * mm
LOGO_MAX = 25 * mm


def _logo_platz(layout, nebeneinander, breite, hoehe):
    """Freier Platz (x, y, Breite, Hoehe) fuer das Vereinslogo oder None, wenn kein Platz ist (mind. LOGO_MIN):
    gestapelt links neben dem QR-Code, nebeneinander ueber dem QR-Code in der linken Spalte. Er liegt ausserhalb von
    QR-Code und Textfeld, damit nichts ueberlappt."""
    rand = min(2.5 * mm, min(breite, hoehe) * 0.08)
    if nebeneinander:
        y = layout["qr_y"] + layout["qr_groesse"] + rand / 2
        platz = (layout["qr_x"], y, layout["qr_groesse"], hoehe - rand - y)
    else:
        platz = (rand, layout["qr_y"], layout["qr_x"] - 2 * rand, layout["qr_groesse"])
    return platz if platz[2] >= LOGO_MIN and platz[3] >= LOGO_MIN else None


def logo_schwarzweiss(pfad):
    """Das Vereinslogo als Graustufenbild mit kraeftigem Kontrast (Etiketten werden meist auf Thermo-/Schwarzweissdruckern
    gedruckt; Farben wuerden dort unschoen gerastert). Transparente Bereiche werden weiss. None, wenn nicht lesbar."""
    from PIL import Image, ImageOps
    try:
        bild = Image.open(pfad)
        bild.load()
        if bild.mode in ("RGBA", "LA", "P") and ("A" in bild.getbands() or "transparency" in bild.info):
            rgba = bild.convert("RGBA")
            bild = Image.alpha_composite(Image.new("RGBA", rgba.size, (255, 255, 255, 255)), rgba)
        return ImageOps.autocontrast(bild.convert("L"), cutoff=1)
    except Exception:
        return None


def _logo_zeichnen(c, bild, platz):
    """Logo (Graustufen-PIL-Bild) seitenverhaeltnistreu und zentriert in den freien Platz einpassen."""
    breite, hoehe = bild.size
    x, y, w, h = platz
    w, h = min(w, LOGO_MAX), min(h, LOGO_MAX)
    skala = min(w / breite, h / hoehe)
    zw, zh = breite * skala, hoehe * skala
    c.drawImage(ImageReader(bild), x + (platz[2] - zw) / 2, y + (platz[3] - zh) / 2, zw, zh)
