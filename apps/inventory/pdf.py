from apps.core.pdf import brief_pdf
from apps.core.util import geld


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
