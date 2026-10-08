import os
import re
import unicodedata
import uuid
from decimal import Decimal


def ascii_kennung(s):
    """Normalisiert einen Namen zu einer ASCII-tauglichen Kennung (z. B. für Benutzernamen in Paperless/OpenSlides):
    Umlaute/ß ausgeschrieben, alles andere auf a-z0-9._- reduziert."""
    s = (s or "").lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9._-]", "", s.replace(" ", "-"))


def geld(wert):
    if wert is None:
        return "–"
    s = f"{Decimal(wert):,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def upload_pfad(instance, dateiname):
    return f"{instance.verein_id}/{instance._meta.model_name}/{uuid.uuid4().hex[:12]}_{os.path.basename(dateiname)}"


def logo_pfad(instance, dateiname):
    ext = os.path.splitext(dateiname)[1].lower()[:5]
    return f"vereine/{instance.kuerzel}/logo_{uuid.uuid4().hex[:8]}{ext}"


def hex_zu_rgb(hex_farbe, standard=(175, 43, 30)):
    """Zerlegt einen Hex-Farbcode (z. B. '#1F4E79') in ein (r, g, b)-Tupel, mit Standardwert bei ungültigem Wert."""
    hex_farbe = (hex_farbe or "").lstrip("#")
    if len(hex_farbe) != 6:
        return standard
    try:
        return tuple(int(hex_farbe[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return standard


def lesbare_textfarbe(hex_farbe):
    """'#000' oder '#fff', je nachdem was auf hex_farbe als Hintergrund besser lesbar ist (Helligkeitsformel)."""
    r, g, b = hex_zu_rgb(hex_farbe)
    helligkeit = (r * 299 + g * 587 + b * 114) / 1000
    return "#000" if helligkeit > 150 else "#fff"


def rgb_zu_hex(r, g, b):
    """Formatiert ein (r, g, b)-Tupel (auch mit Fließkommazahlen) als Hex-Farbcode '#RRGGBB'."""
    r, g, b = (max(0, min(255, round(x))) for x in (r, g, b))
    return f"#{r:02X}{g:02X}{b:02X}"


def gemischte_farbe(hex_a, hex_b, anteil_a):
    """Mischt zwei Hex-Farben linear (anteil_a = Anteil der ersten Farbe, 0..1) - serverseitig statt per CSS
    color-mix(), damit z. B. die Kontrastfarbe zum Ergebnis zuverlässig berechnet werden kann."""
    ra, ga, ba = hex_zu_rgb(hex_a)
    rb, gb, bb = hex_zu_rgb(hex_b)
    anteil_b = 1 - anteil_a
    return rgb_zu_hex(ra * anteil_a + rb * anteil_b, ga * anteil_a + gb * anteil_b, ba * anteil_a + bb * anteil_b)


def betrag_in_worten(betrag):
    from num2words import num2words
    betrag = Decimal(betrag).quantize(Decimal("0.01"))
    euro, cent = int(betrag), int((betrag - int(betrag)) * 100)
    text = f"{num2words(euro, lang='de')} Euro"
    if cent:
        text += f" und {num2words(cent, lang='de')} Cent"
    return text
