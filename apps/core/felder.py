"""Feldbezogene Rechte: einzelne besonders schützenswerte Felder (Geburtsdatum, Bankverbindung/SEPA-Mandat) sind
eigenen Rechte-Modulen zugeordnet, damit sie unabhängig vom Rest der Mitgliederdaten vergeben werden können
(Berechtigungsmatrix nach Datenschutzordnung, siehe matrix.py)."""

FELD_RECHTE = {
    "mitglied": {
        "geburtsdatum": "geburtsdatum",
        "kontoinhaber": "bankdaten", "iban": "bankdaten", "bic": "bankdaten",
        "mandatsreferenz": "bankdaten", "mandatsdatum": "bankdaten",
    },
}


def feldstatus(request, model):
    """-> (versteckt, schreibgeschuetzt): Feldnamen, die der Benutzer nicht sehen bzw. nicht ändern darf."""
    zuordnung = FELD_RECHTE.get(model._meta.model_name, {})
    versteckt, schreibgeschuetzt = set(), set()
    rechte = getattr(request, "rechte", None)
    if rechte is None:
        return versteckt, schreibgeschuetzt
    for feld, modul in zuordnung.items():
        if not rechte.darf(modul, "view"):
            versteckt.add(feld)
        elif not rechte.darf(modul, "change"):
            schreibgeschuetzt.add(feld)
    return versteckt, schreibgeschuetzt
