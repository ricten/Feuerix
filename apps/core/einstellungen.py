"""Einstellungs-Uebersicht (Verwaltung › Einstellungen): alle Verwaltungs- und Stammdatenseiten nach Themen geordnet.
Das Menue "Verwaltung" bleibt dadurch kurz; was nicht dort steht, ist von hier aus erreichbar. Sichtbar ist je Eintrag nur,
was die eigene Rolle sehen darf."""
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _

# (Thema, Symbol, [(Bezeichnung, url_name, Modul, Beschreibung)])
BEREICHE = [
    (_("Verein & Erscheinungsbild"), "bi-building", [
        (_("Vereinsdaten, Logo, Farben"), "verein_einstellungen#stamm", "verwaltung",
         _("Name, Anschrift, Registereintrag, Logo, Farben, Unterschriften, Startseiten-Banner, Impressum, Etiketten")),
    ]),
    (_("Finanzen"), "bi-cash-coin", [
        (_("Bank, Steuern & Rechnungen"), "verein_einstellungen#finanzen", "verwaltung",
         _("Bankverbindung, Gläubiger-ID, Gemeinnützigkeit, Umsatzsteuer, Zahlungsziel, Rechnungstexte, Freibeträge")),
        (_("Mitgliedsarten / Beiträge"), "mitgliedsart_list", "beitraege", _("Beitragshöhen je Mitgliedsart")),
        (_("Beitragsregeln"), "beitragsregel_list", "beitraege", _("Ermäßigungen und Sonderregeln für Beiträge")),
        (_("FinTS-Zugänge"), "fintszugang_list", "bank", _("Bankzugänge für den automatischen Abruf der Umsätze")),
        (_("Konten"), "konto_list", "kassenbuch", _("Bankkonto und Barkassen des Kassenbuchs")),
        (_("Buchungskategorien"), "buchungskategorie_list", "kassenbuch", _("Kategorien und Sphären für Buchungen")),
    ]),
    (_("Mitglieder & Ehrungen"), "bi-people", [
        (_("Abteilungen"), "abteilung_list", "mitglieder", _("Gliederung des Vereins")),
        (_("Funktionen"), "funktion_list", "mitglieder", _("Ämter und Funktionen")),
        (_("Funktionen: Tags (Zugriffsrechte)"), "mitgliedtag_list", "mitglieder",
         _("Tags, über die Mitglieder Rechte und Gruppen erhalten")),
        (_("Ehrungsarten"), "ehrungsart_list", "ehrungen", _("Arten von Ehrungen und Auszeichnungen")),
        (_("Jubiläumsregeln"), "jubilaeumsregel_list", "ehrungen", _("Wann ein Jubiläum fällig wird")),
        (_("Mitglieder-Import"), "mitglieder_import", "mitglieder", _("Mitglieder aus Excel/CSV übernehmen")),
    ]),
    (_("Inventar"), "bi-box-seam", [
        (_("Inventar-Kategorien"), "kategorie_list", "inventar", _("Kategorien der Gegenstände")),
        (_("Inventar-Lagerorte"), "lagerort_list", "inventar", _("Wo Gegenstände lagern")),
        (_("Inventar-Import"), "gegenstand_import", "inventar", _("Gegenstände aus Excel/CSV übernehmen")),
    ]),
    (_("Zugriff & Sicherheit"), "bi-shield-lock", [
        (_("Benutzer"), "zugang_list", "verwaltung", _("Konten anlegen, Rollen zuweisen, Passwort/2FA zurücksetzen")),
        (_("Rollen (fortgeschritten)"), "rolle_list", "verwaltung", _("Rechte-Sets für Benutzer")),
        (_("Berechtigungsmatrix"), "berechtigungsmatrix", "verwaltung", _("Stufen je Datenbereich und Rolle")),
    ]),
    (_("Externe Anbindungen"), "bi-plug", [
        (_("Übersicht der Anbindungen"), "anbindungen", "openslides",
         _("Status von OpenSlides und Paperless-ngx, Einrichtung")),
        (_("OpenSlides-Anbindung"), "openslides_einstellungen", "openslides",
         _("Online-Versammlungen: Verbindung, Konten, Gruppen")),
        (_("Paperless-Anbindung"), "paperless_einstellungen", "paperless",
         _("Dokumentenarchiv: Verbindung und Übergabe")),
    ]),
]

# Nur fuer Superadministratoren (betrifft die Daten aller Vereine)
SYSTEM = (_("System"), "bi-hdd-stack", [
    (_("Datensicherung"), "datensicherung", None, _("Sicherungen, externes Ziel, Wiederherstellung")),
])


# Nur in der Uebersicht, nicht im Menue "Verwaltung" (dort steht ein einziger Punkt "Externe Anbindungen")
NUR_UEBERSICHT = {"openslides_einstellungen", "paperless_einstellungen"}


def menue_bloecke(request):
    """[(Thema, [(Bezeichnung, Adresse)])] fuer das Menue "Verwaltung" - dieselben Themen wie die Uebersicht."""
    bloecke = [(_("Übersicht"), [(_("Alle Einstellungen (Übersicht)"), reverse("einstellungen"))])]
    gesehen = set()
    for thema, _icon, zeilen in sichtbare_bereiche(request):
        punkte = []
        for label, url, _text, name in zeilen:
            if name in NUR_UEBERSICHT:
                continue
            if url in gesehen:        # dieselbe Seite nicht doppelt im Menue
                continue
            gesehen.add(url)
            punkte.append((label, url))
        if punkte:
            bloecke.append((thema, punkte))
    return bloecke if len(bloecke) > 1 else []


def url_namen():
    """Alle Seiten der Uebersicht - fuer die Hervorhebung des Menues "Verwaltung" auf diesen Seiten."""
    return {u.split("#")[0] for _t, _i, eintraege in [*BEREICHE, SYSTEM] for _l, u, _m, _b in eintraege}


def sichtbare_bereiche(request):
    """[(Thema, Symbol, [(Bezeichnung, Adresse, Beschreibung, url_name)])] - nur Eintraege, die die Rolle sehen darf."""
    rechte = request.rechte
    ergebnis = []
    for thema, icon, eintraege in [*BEREICHE, *([SYSTEM] if request.user.is_superuser else [])]:
        zeilen = []
        for label, url_name, modul, text in eintraege:
            url_name, _, anker = url_name.partition("#")        # "seite#thema" springt zum Thema der Seite
            if url_name == "anbindungen":
                sichtbar = rechte.darf("openslides", "view") or rechte.darf("paperless", "view")
            elif modul is None:
                sichtbar = request.user.is_superuser
            else:
                sichtbar = rechte.darf(modul, "view")
            if sichtbar:
                try:
                    zeilen.append((label, reverse(url_name) + (f"#{anker}" if anker else ""), text, url_name))
                except NoReverseMatch:
                    pass
        if zeilen:
            ergebnis.append((thema, icon, zeilen))
    return ergebnis
