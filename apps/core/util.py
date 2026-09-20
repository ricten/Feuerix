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


def betrag_in_worten(betrag):
    from num2words import num2words
    betrag = Decimal(betrag).quantize(Decimal("0.01"))
    euro, cent = int(betrag), int((betrag - int(betrag)) * 100)
    text = f"{num2words(euro, lang='de')} Euro"
    if cent:
        text += f" und {num2words(cent, lang='de')} Cent"
    return text
