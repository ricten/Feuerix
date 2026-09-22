MODULE = {
    "mitglieder": "Mitglieder",
    "selbstdienst": "Selbstdatenpflege (Zugänge der Mitglieder verwalten)",
    "dokumente": "Dokumente",
    "ehrungen": "Ehrungen & Jubiläen",
    "beitraege": "Beiträge",
    "rechnungen": "Rechnungen",
    "zahlungen": "Zahlungen",
    "bank": "Bankumsätze",
    "spenden": "Spenden & Spendenquittungen",
    "aufwand": "Aufwandsentschädigungen",
    "inventar": "Inventar",
    "verleih": "Verleih",
    "inventur": "Inventuren",
    "veranstaltungen": "Veranstaltungen",
    "schriftverkehr": "Schriftverkehr (Vorlagen, Serienbriefe, Protokolle)",
    "ablage": "Ablage (Dokumentenarchiv)",
    "openslides": "OpenSlides-Anbindung",
    "paperless": "Paperless-Anbindung",
    "kassenbuch": "Kassenbuch & Kassenbericht",
    "auswertungen": "Auswertungen",
    "audit": "Änderungsprotokoll",
    "verwaltung": "Verwaltung (Benutzer, Rollen, Verein)",
}
AKTIONEN = {"view": "Anzeigen", "add": "Erstellen", "change": "Bearbeiten", "delete": "Löschen"}

LESEN = ("view",)
BEARBEITEN = ("view", "add", "change")
ALLES = tuple(AKTIONEN)


def _r(module, aktionen):
    return [f"{m}.{a}" for m in module for a in aktionen]


STANDARDROLLEN = {
    "Superadministrator": {"ist_superadmin": True, "rechte": []},
    "Vorstand": {"ist_superadmin": False, "rechte": (
        _r(["mitglieder", "ehrungen", "dokumente", "beitraege", "rechnungen", "veranstaltungen", "schriftverkehr", "ablage"],
            BEARBEITEN)
        + _r(["zahlungen", "spenden", "aufwand", "inventar", "verleih", "inventur", "auswertungen", "openslides",
                "paperless", "kassenbuch"], LESEN)
        + _r(["selbstdienst"], ALLES)
        + ["aufwand.change"])},
    "Kassenwart": {"ist_superadmin": False, "rechte": (
        _r(["beitraege", "rechnungen", "zahlungen", "bank", "spenden", "aufwand", "kassenbuch"], BEARBEITEN)
        + ["kassenbuch.delete"] + _r(["mitglieder", "auswertungen", "ablage"], LESEN))},
    "Kassenprüfer": {"ist_superadmin": False, "rechte": (
        _r(["kassenbuch", "rechnungen", "zahlungen", "bank", "spenden", "aufwand", "beitraege", "ablage",
            "auswertungen"], LESEN))},
    "Schriftführer": {"ist_superadmin": False, "rechte": (
        _r(["mitglieder", "ehrungen", "dokumente", "veranstaltungen", "schriftverkehr", "ablage"], BEARBEITEN))},
    "Inventarverwalter": {"ist_superadmin": False, "rechte": (
        _r(["inventar", "verleih", "inventur"], BEARBEITEN) + _r(["mitglieder", "veranstaltungen"], LESEN))},
    "Veranstaltungsplaner": {"ist_superadmin": False, "rechte": (
        _r(["veranstaltungen", "verleih"], BEARBEITEN) + _r(["mitglieder", "inventar"], LESEN))},
    "Mitgliederverwaltung": {"ist_superadmin": False, "rechte": (
        _r(["selbstdienst"], ALLES) + _r(["mitglieder"], LESEN))},
    "Lesebenutzer": {"ist_superadmin": False, "rechte": _r(
        [m for m in MODULE if m not in ("verwaltung", "audit", "bank", "aufwand", "spenden", "openslides", "paperless",
                                        "kassenbuch", "selbstdienst")], LESEN)},
}


class RechteKontext:
    """Rechte des angemeldeten Benutzers im aktuellen Verein."""

    def __init__(self, user, verein):
        self.alles = False
        self.rechte = set()
        self.zugang = None
        if not user.is_authenticated:
            return
        if user.is_superuser:
            self.alles = True
            return
        if verein is None:
            return
        from .models import Zugang
        z = Zugang.objects.select_related("rolle").filter(user=user, verein=verein, aktiv=True).first()
        if z:
            self.zugang = z
            if z.rolle.ist_superadmin:
                self.alles = True
            else:
                self.rechte = set(z.rolle.rechte or []) | set(z.extra_rechte or [])

    def darf(self, modul, aktion="view"):
        return self.alles or f"{modul}.{aktion}" in self.rechte
