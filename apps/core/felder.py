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


# Felder/Spalten, die es nur mit einer angebundenen Instanz gibt: Modell -> Anbindung -> Feldnamen. Nur fuer die
# normale Oberflaeche (Listen, Detailseiten, Formulare) - der DSGVO-Datenexport eines Mitglieds nutzt feldstatus()
# und enthaelt gespeicherte Daten weiterhin vollstaendig.
ANBINDUNGS_FELDER = {
    "mitglied": {"openslides": ("openslides_user_id", "openslides_username", "openslides_initialpasswort")},
    "mitgliedtag": {"paperless": ("paperless_gruppe", "paperless_nur_lesen"), "openslides": ("openslides_gruppe",)},
    "tagesordnungspunkt": {"openslides": ("openslides_topic_id",)},
    "veranstaltung": {"openslides": ("openslides_meeting_id",)},
    "wahlergebnis": {"openslides": ("openslides_poll_id",)},
    "anwesenheit": {"openslides": ("openslides_user_id",)},
    "ablagedokument": {"paperless": (
        "dokumenttyp", "tags", "paperless_tags", "paperless_status", "paperless_gesendet_am", "paperless_task_id",
        "paperless_fehler", "paperless_pruefsumme", "paperless_info", "paperless_uebergeben")},
}


def anbindung_versteckt(request, model):
    """Feldnamen des Modells, die ohne angebundene Instanz (OpenSlides/Paperless) nicht angezeigt werden."""
    from .anbindungen import anbindungen
    zuordnung = ANBINDUNGS_FELDER.get(model._meta.model_name, {})
    a = anbindungen(request)
    return {feld for anbindung, felder in zuordnung.items() if not a.aktiv(anbindung) for feld in felder}
