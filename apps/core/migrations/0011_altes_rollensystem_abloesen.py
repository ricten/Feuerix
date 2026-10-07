"""Löst das alte, feste Standardrollen-Set (Vorstand, Kassenwart, Kassenprüfer, Schriftführer, Inventarverwalter,
Veranstaltungsplaner, Mitgliederverwaltung, Lesebenutzer) ab: Rechte werden ab sofort über die Berechtigungsmatrix
nach der Datenschutzordnung vergeben (apps/core/matrix.py), inkl. einer neuen Rolle/Tag "Administrator" mit vollen
Rechten (z. B. für die technische Betreuung der Software).

Für jeden bestehenden Verein werden die sechs Datenschutzordnungs-Rollen samt Administrator angelegt (idempotent,
wie beim Anlegen eines neuen Vereins). Benutzer mit einer alten Rolle, zu der es ein eindeutiges Gegenstück gibt,
werden automatisch umgezogen und die alte Rolle anschließend gelöscht:

    Vorstand        -> Administrator          (war die mit Abstand umfangreichste alte Rolle)
    Kassenwart       -> Kassenwart (DSO)
    Schriftführer    -> Schriftführer (DSO)

Für die übrigen alten Rollen (Kassenprüfer, Inventarverwalter, Veranstaltungsplaner, Mitgliederverwaltung,
Lesebenutzer) gibt es kein eindeutiges Gegenstück in der Datenschutzordnung - sie werden NICHT automatisch
ersetzt, um keine Berechtigungen unkontrolliert auszuweiten oder einzuschränken. Sie bleiben als gewöhnliche
(nicht mehr automatisch erzeugte) Rollen bestehen und sind über Verwaltung › Rollen bzw. die Berechtigungsmatrix
weiter änderbar; wer sie ablösen möchte, weist die betroffenen Zugänge manuell einer passenden Rolle zu.

Diese Migration ist bewusst in sich geschlossen (keine Importe aus apps.core.matrix/rechte), damit sie auch dann
unverändert nachvollziehbar bleibt, wenn sich die Matrix-Definitionen künftig weiterentwickeln - siehe die
historische Migration 0010 für dasselbe Vorgehen.
"""
from django.db import migrations

# ---------------------------------------------------------------- eingefrorener Stand von apps/core/matrix.py
BEREICHE = [
    # (key, module, personenbezogen, art)
    ("stamm", ["mitglieder", "dokumente", "ehrungen"], True, "normal"),
    ("geburt", ["geburtsdatum"], True, "feld"),
    ("beitrag", ["beitraege", "rechnungen"], True, "normal"),
    ("bank", ["bankdaten"], True, "feld"),
    ("zahlung", ["zahlungen", "bank", "kassenbuch", "spenden", "aufwand"], True, "normal"),
    ("veranstaltung", ["veranstaltungen"], False, "normal"),
    ("teilnehmer", ["teilnehmer"], True, "normal"),
    ("komm", ["schriftverkehr"], False, "normal"),
    ("rundschreiben", ["rundschreiben"], True, "normal"),
    ("software", ["verwaltung", "selbstdienst", "openslides", "paperless"], False, "normal"),
    ("datenschutz", ["ablage"], False, "normal"),
    ("verletzung", ["audit"], False, "lesen"),
    ("inventar", ["inventar", "verleih", "inventur"], False, "normal"),
    ("auswertung", ["auswertungen"], False, "normal"),
]
PERSONENBEZOGEN = sorted({m for _, module, pb, _ in BEREICHE if pb for m in module})
LOESCHUNG = "loeschung"


def _aktionen(art, personenbezogen, stufe):
    if stufe == "L":
        return ["view"]
    if stufe not in ("B", "V"):
        return []
    if art == "lesen":
        return ["view"]
    if art == "feld":
        return ["view", "change"]
    aktionen = ["view", "add", "change"]
    if stufe == "V" and not personenbezogen:
        aktionen.append("delete")
    return aktionen


def rechte_aus_matrix(matrix):
    rechte = set()
    for key, module, personenbezogen, art in BEREICHE:
        for m in module:
            rechte.update(f"{m}.{a}" for a in _aktionen(art, personenbezogen, matrix.get(key, "-")))
    if matrix.get(LOESCHUNG) == "V":
        rechte.update(f"{m}.delete" for m in PERSONENBEZOGEN if f"{m}.view" in rechte and m not in
                      {"geburtsdatum", "bankdaten"})
    return sorted(rechte)


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
ADMINISTRATOR = "Administrator"


def _matrix(werte):
    return dict(zip(_DSO_SPALTEN, [("-" if w == "–" else w) for w in werte.split()]))


ROLLEN = {name + DSO_SUFFIX: _matrix(w) for name, w in _DSO_WERTE.items()}
ROLLEN[ADMINISTRATOR] = _matrix(" ".join(["V"] * len(_DSO_SPALTEN)))

TAGS = {   # Funktion -> (Paperless-Gruppe nur lesend?, OpenSlides-Gruppe)
    "1. Vorsitzender": (False, "Admin"), "2. Vorsitzender": (False, "Admin"),
    "Kassenwart": (True, "Delegates"), "Stellv. Kassenwart": (True, "Delegates"),
    "Schriftführer": (False, "Staff"), "Stellv. Schriftführer": (False, "Staff"),
    ADMINISTRATOR: (False, "Admin"),
}

# alte Rolle (exakter Name) -> eindeutiger Nachfolger
NACHFOLGER = {
    "Vorstand": ADMINISTRATOR,
    "Kassenwart": "Kassenwart" + DSO_SUFFIX,
    "Schriftführer": "Schriftführer" + DSO_SUFFIX,
}


def _dso_und_administrator_anlegen(Rolle, MitgliedTag, verein):
    rollen = {}
    for name, matrix in ROLLEN.items():
        rolle, _ = Rolle.objects.get_or_create(verein=verein, name=name, defaults={
            "ist_superadmin": False, "rechte": rechte_aus_matrix(matrix), "matrix": matrix})
        rollen[name] = rolle
        funktion = name[:-len(DSO_SUFFIX)] if name.endswith(DSO_SUFFIX) else name
        lesen, os_gruppe = TAGS[funktion]
        MitgliedTag.objects.get_or_create(verein=verein, name=funktion, defaults={
            "rolle": rolle, "paperless_gruppe": funktion, "paperless_nur_lesen": lesen,
            "openslides_gruppe": os_gruppe})
    return rollen


def vorwaerts(apps, schema_editor):
    Verein = apps.get_model("core", "Verein")
    Rolle = apps.get_model("core", "Rolle")
    Zugang = apps.get_model("core", "Zugang")
    MitgliedTag = apps.get_model("members", "MitgliedTag")
    for verein in Verein.objects.all():
        rollen = _dso_und_administrator_anlegen(Rolle, MitgliedTag, verein)
        for alt_name, neu_name in NACHFOLGER.items():
            alte_rolle = Rolle.objects.filter(verein=verein, name=alt_name).first()
            if alte_rolle is None:
                continue
            Zugang.objects.filter(verein=verein, rolle=alte_rolle).update(rolle=rollen[neu_name])
            alte_rolle.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0010_neue_module_rechte"),
        ("members", "0004_matrix_und_tags"),
    ]
    operations = [migrations.RunPython(vorwaerts, migrations.RunPython.noop)]
