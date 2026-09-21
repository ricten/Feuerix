"""Einlesen von CSV/Excel-Tabellen für den Inventar-Import (reines Python, ohne Django)."""
from apps.members.tabellen import datum, ja, lesen, norm, text, zahl  # noqa: F401 (wiederverwendete Basis-Helfer)

# interne Feldnamen -> mögliche Spaltenüberschriften (normalisiert: klein, ohne Leer-/Sonderzeichen)
SYNONYME = {
    "inventarnummer": ["inventarnummer", "inventarnr", "invnr", "nummer", "nr"],
    "bezeichnung": ["bezeichnung", "name", "gegenstand", "artikel"],
    "kategorie": ["kategorie", "art"],
    "standort": ["standort", "lagerort"],
    "hersteller": ["hersteller", "marke"],
    "modell": ["modell", "typ"],
    "seriennummer": ["seriennummer", "serialnummer", "serial", "sn"],
    "anschaffungsdatum": ["anschaffungsdatum", "kaufdatum", "angeschafftam"],
    "anschaffungspreis": ["anschaffungspreis", "kaufpreis", "preis"],
    "aktueller_wert": ["aktuellerwert", "zeitwert", "wert"],
    "zustand": ["zustand"],
    "garantie_bis": ["garantiebis", "garantie"],
    "verleihbar": ["verleihbar"],
    "leihgebuehr": ["leihgebuehr", "leihgebühr", "gebuehr"],
    "kaution": ["kaution"],
    "notizen": ["notizen", "notiz", "bemerkung", "bemerkungen", "anmerkung"],
}
SPALTEN_ANZEIGE = [  # Reihenfolge und Überschriften der Vorlage / des Exports
    ("inventarnummer", "Inventarnummer"), ("bezeichnung", "Bezeichnung"), ("kategorie", "Kategorie"),
    ("standort", "Standort"), ("hersteller", "Hersteller"), ("modell", "Modell"), ("seriennummer", "Seriennummer"),
    ("anschaffungsdatum", "Anschaffungsdatum"), ("anschaffungspreis", "Anschaffungspreis"),
    ("aktueller_wert", "Aktueller Wert"), ("zustand", "Zustand"), ("garantie_bis", "Garantie bis"),
    ("verleihbar", "Verleihbar"), ("leihgebuehr", "Leihgebühr"), ("kaution", "Kaution"), ("notizen", "Notizen"),
]
_LOOKUP = {}
for _feld, _namen in SYNONYME.items():
    for _n in _namen:
        _LOOKUP.setdefault(_n, _feld)


def feld_fuer(ueberschrift):
    n = norm(ueberschrift)
    return _LOOKUP.get(n) or _LOOKUP.get(n.replace("ae", "a").replace("oe", "o").replace("ue", "u"))


def spaltenzuordnung(kopf):
    """-> ({index: feld}, [nicht erkannte Überschriften])"""
    zuordnung, unbekannt = {}, []
    for i, k in enumerate(kopf):
        f = feld_fuer(k)
        if f and f not in zuordnung.values():
            zuordnung[i] = f
        elif k:
            unbekannt.append(k)
    return zuordnung, unbekannt


def zustand(v):
    s = text(v).lower()
    return {"neu": "neu", "gut": "gut", "gebrauchsspuren": "gebrauchsspuren", "defekt": "defekt",
            "ausgesondert": "ausgesondert"}.get(s, "gut" if not s else None)
