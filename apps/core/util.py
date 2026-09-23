import os
import uuid
from decimal import Decimal


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


def hex_zu_rgb(hex_farbe, standard=(31, 78, 121)):
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


def betrag_in_worten(betrag):
    from num2words import num2words
    betrag = Decimal(betrag).quantize(Decimal("0.01"))
    euro, cent = int(betrag), int((betrag - int(betrag)) * 100)
    text = f"{num2words(euro, lang='de')} Euro"
    if cent:
        text += f" und {num2words(cent, lang='de')} Cent"
    return text
