"""Berechtigungsmatrix nach dem Muster der Datenschutzordnung: Zeilen = Datenbereiche, Spalten = Funktionsträger
(Rollen), Zellen = Stufe (– kein Zugriff, L Lesen, B Bearbeiten, V Vollzugriff).

Aus der Matrix werden die technischen Modulrechte (`modul.aktion`, siehe rechte.py) erzeugt:

* L = Anzeigen, B = Anzeigen/Erstellen/Bearbeiten, V = zusätzlich Löschen.
* Bei personenbezogenen Bereichen steht „Löschen“ NICHT in V, sondern wird ausschließlich über die Zeile
  „Löschung personenbezogener Daten“ vergeben (V = darf löschen) - so wie in der Datenschutzordnung, wo z. B. der
  Kassenwart Beitragsdaten löschen darf, der Schriftführer nicht.
* Feld-Bereiche (Geburtsdatum, Bankverbindung/SEPA) kennen nur Anzeigen und Bearbeiten.
"""
from collections import namedtuple

Bereich = namedtuple("Bereich", "key label module personenbezogen art dso")
# art: "normal" | "feld" (nur Anzeigen/Bearbeiten) | "lesen" (nur Anzeigen)

STUFEN = [("-", "–"), ("L", "L"), ("B", "B"), ("V", "V")]
STUFEN_TEXT = {"-": "kein Zugriff", "L": "Lesen", "B": "Bearbeiten", "V": "Vollzugriff"}
LOESCHUNG = "loeschung"
LOESCHUNG_LABEL = "Löschung personenbezogener Daten"

BEREICHE = [
    Bereich("stamm", "Mitgliederstammdaten (Name, Anschrift, Telefon, E-Mail, Eintritt/Austritt, Status, Export)",
            ["mitglieder", "dokumente", "ehrungen"], True, "normal", True),
    Bereich("geburt", "Geburtsdatum", ["geburtsdatum"], True, "feld", True),
    Bereich("beitrag", "Beitragsdaten (inkl. Rechnungen)", ["beitraege", "rechnungen"], True, "normal", True),
    Bereich("bank", "Bankverbindungen und SEPA-Mandate", ["bankdaten"], True, "feld", True),
    Bereich("zahlung", "Zahlungsverkehr / Rücklastschriften (Zahlungen, Bankumsätze, Kassenbuch, Spenden, Aufwand)",
            ["zahlungen", "bank", "kassenbuch", "spenden", "aufwand"], True, "normal", True),
    Bereich("veranstaltung", "Veranstaltungsdaten", ["veranstaltungen"], False, "normal", True),
    Bereich("teilnehmer", "Teilnehmerlisten (Anmeldungen)", ["teilnehmer"], True, "normal", True),
    Bereich("komm", "Vereinskommunikation (Schriftstücke, Vorlagen)", ["schriftverkehr"], False, "normal", True),
    Bereich("rundschreiben", "Rundschreiben / Verteiler (Serienbriefe)", ["rundschreiben"], True, "normal", True),
    Bereich("software", "Vereinssoftware / Verwaltung (Benutzer, Rollen, Verein, Anbindungen)",
            ["verwaltung", "selbstdienst", "openslides", "paperless"], False, "normal", True),
    Bereich("datenschutz", "Datenschutzdokumentation (Ablage)", ["ablage"], False, "normal", True),
    Bereich("verletzung", "Datenschutzverletzungen (Änderungsprotokoll)", ["audit"], False, "lesen", True),
    Bereich("inventar", "Inventar, Verleih und Inventuren", ["inventar", "verleih", "inventur"], False, "normal", False),
    Bereich("auswertung", "Auswertungen", ["auswertungen"], False, "normal", False),
]
BEREICH = {b.key: b for b in BEREICHE}
PERSONENBEZOGEN = sorted({m for b in BEREICHE if b.personenbezogen for m in b.module})


def _aktionen(bereich, stufe):
    if stufe == "L":
        return ["view"]
    if stufe not in ("B", "V"):
        return []
    if bereich.art == "lesen":
        return ["view"]
    if bereich.art == "feld":
        return ["view", "change"]
    aktionen = ["view", "add", "change"]
    if stufe == "V" and not bereich.personenbezogen:
        aktionen.append("delete")
    return aktionen


def rechte_aus_matrix(matrix):
    """{bereich: stufe, "loeschung": stufe} -> sortierte Liste "modul.aktion"."""
    rechte = set()
    for b in BEREICHE:
        for m in b.module:
            rechte.update(f"{m}.{a}" for a in _aktionen(b, matrix.get(b.key, "-")))
    if matrix.get(LOESCHUNG) == "V":
        rechte.update(f"{m}.delete" for m in PERSONENBEZOGEN if f"{m}.view" in rechte and m not in
                      {"geburtsdatum", "bankdaten"})
    return sorted(rechte)


def matrix_aus_rechte(rechte):
    """Bestmögliche Rückrechnung für Rollen ohne gespeicherte Matrix (z. B. selbst angelegte Rollen)."""
    rechte = set(rechte or [])
    matrix = {}
    for b in BEREICHE:
        stufe = "-"
        for m in b.module:
            if f"{m}.delete" in rechte and not b.personenbezogen:
                stufe = "V"
                break
            if f"{m}.add" in rechte or f"{m}.change" in rechte:
                stufe = "B" if stufe != "V" else stufe
            elif f"{m}.view" in rechte and stufe == "-":
                stufe = "L"
        matrix[b.key] = stufe
    matrix[LOESCHUNG] = "V" if any(f"{m}.delete" in rechte for m in PERSONENBEZOGEN) else "-"
    return matrix


def matrix_der_rolle(rolle):
    """Gespeicherte Matrix, sofern sie noch zu den Rechten passt, sonst aus den Rechten abgeleitet."""
    gespeichert = getattr(rolle, "matrix", None) or {}
    if gespeichert and rechte_aus_matrix(gespeichert) == sorted(rolle.rechte or []):
        return {**{b.key: "-" for b in BEREICHE}, LOESCHUNG: "-", **gespeichert}
    return matrix_aus_rechte(rolle.rechte)


# ----------------------------------------------------------------------------------------------- Datenschutzordnung
# Berechtigungsmatrix des Fördervereins (Stand 09/2026): sechs Funktionsträger. Reihenfolge der Werte:
# stamm, geburt, beitrag, bank, zahlung, veranstaltung, teilnehmer, komm, rundschreiben, software, datenschutz,
# verletzung, Löschung.
_DSO_SPALTEN = ["stamm", "geburt", "beitrag", "bank", "zahlung", "veranstaltung", "teilnehmer", "komm",
                "rundschreiben", "software", "datenschutz", "verletzung", LOESCHUNG]
_DSO_WERTE = {
    "1. Vorsitzender": "V L L - L V L V V V V V V",
    "2. Vorsitzender": "V L L - L V L V V V V V V",
    "Kassenwart": "B - V V V L - L - V L L V",
    "Stellv. Kassenwart": "B - V V V L - L - V L L V",
    "Schriftführer": "V V - - - V V V V V B L B",
    "Stellv. Schriftführer": "B B - - - B B B B B B L B",
}
DSO_SUFFIX = " (DSO)"


def _dso_matrix(werte):
    return dict(zip(_DSO_SPALTEN, [("-" if w == "–" else w) for w in werte.split()]))


DSO_ROLLEN = {name + DSO_SUFFIX: _dso_matrix(w) for name, w in _DSO_WERTE.items()}
# Funktion -> (Paperless-Gruppe lesend?, OpenSlides-Gruppe in Versammlungen)
DSO_TAGS = {
    "1. Vorsitzender": (False, "Admin"),
    "2. Vorsitzender": (False, "Admin"),
    "Kassenwart": (True, "Delegates"),
    "Stellv. Kassenwart": (True, "Delegates"),
    "Schriftführer": (False, "Staff"),
    "Stellv. Schriftführer": (False, "Staff"),
}

# Zusätzlich zu den sechs Funktionen der Datenschutzordnung: "Administrator" mit vollen Rechten (z. B. für die
# technische Betreuung der Software). Kein Teil der Datenschutzordnung selbst, deshalb ohne "(DSO)"-Zusatz -
# zählt aber zu den Personen mit Zugriff (§ 6) und wird deshalb bei der Besetzungsprüfung mitgezählt.
ADMINISTRATOR = "Administrator"
_ADMIN_MATRIX = {**{b.key: "V" for b in BEREICHE}, LOESCHUNG: "V"}
_ALLE_ROLLEN = {**DSO_ROLLEN, ADMINISTRATOR: _ADMIN_MATRIX}
_ALLE_TAGS = {**DSO_TAGS, ADMINISTRATOR: (False, "Admin")}


def dso_anlegen(verein):
    """Legt die sechs Rollen der Datenschutzordnung sowie die Rolle/das Tag "Administrator" (volle Rechte) samt
    zugehörigen Tags (Rolle + Paperless-Gruppe + OpenSlides-Gruppe) an. Bereits vorhandene Rollen/Tags bleiben
    unverändert (idempotent). -> (neue_rollen, neue_tags)"""
    from apps.members.models import MitgliedTag

    from .models import Rolle
    neue_rollen = neue_tags = 0
    for name, matrix in _ALLE_ROLLEN.items():
        rolle, neu = Rolle.objects.get_or_create(verein=verein, name=name, defaults={
            "ist_superadmin": False, "rechte": rechte_aus_matrix(matrix), "matrix": matrix})
        neue_rollen += int(neu)
        funktion = name[:-len(DSO_SUFFIX)] if name.endswith(DSO_SUFFIX) else name
        lesen, os_gruppe = _ALLE_TAGS[funktion]
        beschreibung = ("Volle Rechte (z. B. technische Betreuung der Software)" if funktion == ADMINISTRATOR
                       else "Funktionsträger nach Datenschutzordnung")
        tag, neu_tag = MitgliedTag.objects.get_or_create(verein=verein, name=funktion, defaults={
            "rolle": rolle, "paperless_gruppe": funktion, "paperless_nur_lesen": lesen, "openslides_gruppe": os_gruppe,
            "beschreibung": beschreibung})
        neue_tags += int(neu_tag)
    return neue_rollen, neue_tags


def dso_pruefung(verein):
    """Hinweise zur Datenschutzordnung: § 6 (höchstens sechs Personen mit regelmäßigem Zugriff), Vertretung,
    § 17 (Rechte nach Funktionsende entziehen)."""
    from apps.members.models import Mitglied, MitgliedTag

    from .models import Rolle, Zugang
    hinweise = []
    dso_tags = MitgliedTag.objects.filter(verein=verein, rolle__isnull=False)
    traeger = Mitglied.objects.filter(verein=verein, status="aktiv", tags__in=dso_tags).distinct()
    if traeger.count() > 6:
        hinweise.append(f"§ 6 der Datenschutzordnung: regelmäßigen Zugriff sollen ausschließlich sechs Personen "
                        f"haben - aktuell tragen {traeger.count()} Mitglieder ein Funktions-Tag mit Rolle.")
    # Besetzung je Funktion wird nur fuer die sechs DSO-Funktionen geprueft - "Administrator" muss nicht
    # zwingend vergeben sein.
    for t in dso_tags.exclude(name=ADMINISTRATOR):
        n = Mitglied.objects.filter(verein=verein, status="aktiv", tags=t).count()
        if n == 0:
            hinweise.append(f"Funktion „{t.name}“ ist nicht besetzt (Tag keinem aktiven Mitglied zugeordnet).")
        elif n > 1:
            hinweise.append(f"Funktion „{t.name}“ ist mehrfach besetzt ({n} Mitglieder).")
    verwaltete = set(dso_tags.values_list("rolle_id", flat=True))
    for z in Zugang.objects.filter(verein=verein, aktiv=True, rolle_id__in=verwaltete).select_related("user"):
        m = Mitglied.objects.filter(verein=verein, benutzer=z.user).first()
        if m is None or m.status != "aktiv" or not m.tags.filter(rolle_id=z.rolle_id).exists():
            hinweise.append(f"§ 17: Benutzer „{z.user}“ hat die Rolle „{z.rolle}“, ohne die Funktion (Tag) zu "
                            "besitzen - Rechte entziehen.")
    personen = Zugang.objects.filter(verein=verein, aktiv=True, rolle__ist_superadmin=False).exclude(
        rolle__rechte=[]).count()
    if personen > 6:
        hinweise.append(f"{personen} Benutzerzugänge mit Rechten - die Datenschutzordnung sieht höchstens sechs "
                        "Personen mit regelmäßigem Zugriff vor.")
    return hinweise
