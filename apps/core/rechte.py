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
    "geburtsdatum": "Mitgliederdaten: Geburtsdatum",
    "bankdaten": "Mitgliederdaten: Bankverbindung und SEPA-Mandat",
    "teilnehmer": "Teilnehmerlisten (Anmeldungen zu Veranstaltungen)",
    "rundschreiben": "Rundschreiben / Verteiler (Serienbriefe)",
}
AKTIONEN = {"view": "Anzeigen", "add": "Erstellen", "change": "Bearbeiten", "delete": "Löschen"}

LESEN = ("view",)
BEARBEITEN = ("view", "add", "change")
ALLES = tuple(AKTIONEN)


def _r(module, aktionen):
    return [f"{m}.{a}" for m in module for a in aktionen]


# Das frei konfigurierbare Standardrollen-Set (Vorstand/Kassenwart/Kassenprüfer/Schriftführer/...) wurde abgelöst:
# Rechte werden jetzt über die Berechtigungsmatrix nach der Datenschutzordnung vergeben (siehe matrix.py), die für
# jeden Verein automatisch die passenden Rollen (u. a. "Kassenwart (DSO)", "Schriftführer (DSO)") sowie die Rolle
# "Administrator" (volle Rechte) samt zugehörigen Tags anlegt. Nur "Superadministrator" (Rechte-Bypass, siehe
# RechteKontext) bleibt als technischer Sonderfall hier bestehen.
STANDARDROLLEN = {
    "Superadministrator": {"ist_superadmin": True, "rechte": []},
}


def neue_module_ableiten(rechte):
    """Rechte der Module, die aus bestehenden herausgelöst wurden (bisheriges Verhalten bleibt erhalten):
    Geburtsdatum/Bankdaten folgen Mitglieder, Teilnehmer folgt Veranstaltungen, Rundschreiben folgt Schriftverkehr."""
    r = set(rechte)
    for alt, neu, aktionen in (("mitglieder", "geburtsdatum", ("view", "change")),
                               ("mitglieder", "bankdaten", ("view", "change")),
                               ("veranstaltungen", "teilnehmer", tuple(AKTIONEN)),
                               ("schriftverkehr", "rundschreiben", tuple(AKTIONEN))):
        r.update(f"{neu}.{a}" for a in aktionen if f"{alt}.{a}" in r)
    return sorted(r)


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
