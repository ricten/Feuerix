from django.urls import NoReverseMatch, reverse

NAV = [
    ("Mitglieder", [
        ("Mitglieder", "mitglied_list", "mitglieder"),
        ("Mitglieder-Import", "mitglieder_import", "mitglieder"),
        ("Jubiläen", "jubilaeen", "ehrungen"),
        ("Ehrungen", "ehrung_list", "ehrungen"),
        ("Dokumente", "dokument_list", "dokumente"),
    ]),
    ("Schriftverkehr", [
        ("Schriftstücke (Einladung, Protokoll …)", "schriftstueck_list", "schriftverkehr"),
        ("Serienbriefe", "serienbrief_list", "schriftverkehr"),
        ("Vorlagen", "vorlage_list", "schriftverkehr"),
        ("Platzhalter-Hilfe", "platzhalter_hilfe", "schriftverkehr"),
        ("Ablage", "ablagedokument_list", "ablage"),
        ("Ablage-Ordner", "ordner_list", "ablage"),
    ]),
    ("Finanzen", [
        ("Beitragsjahre", "beitragsjahr_list", "beitraege"),
        ("Rechnungen", "rechnung_list", "rechnungen"),
        ("Zahlungen", "zahlung_list", "zahlungen"),
        ("Bankumsätze", "bankumsatz_list", "bank"),
        ("Spenden", "spende_list", "spenden"),
        ("Spendenquittungen", "zuwendungsbestaetigung_list", "spenden"),
        ("Aufwandsentschädigungen", "aufwandsentschaedigung_list", "aufwand"),
    ]),
    ("Kasse", [
        ("Kassenbuch (Buchungen)", "buchung_list", "kassenbuch"),
        ("Kassenberichte", "kassenbericht_list", "kassenbuch"),
        ("Konten", "konto_list", "kassenbuch"),
        ("Buchungskategorien", "buchungskategorie_list", "kassenbuch"),
    ]),
    ("Inventar", [
        ("Gegenstände", "gegenstand_list", "inventar"),
        ("Verleih", "verleih_list", "verleih"),
        ("Inventuren", "inventur_list", "inventur"),
    ]),
    ("Veranstaltungen", [
        ("Veranstaltungen", "veranstaltung_list", "veranstaltungen"),
    ]),
    ("Auswertung", [
        ("Auswertungen", "auswertungen", "auswertungen"),
        ("Änderungsprotokoll", "auditlog_list", "audit"),
    ]),
    ("Verwaltung", [
        ("Verein / Einstellungen / Logo", "verein_einstellungen", "verwaltung"),
        ("OpenSlides-Anbindung", "openslides_einstellungen", "openslides"),
        ("Benutzer", "zugang_list", "verwaltung"),
        ("Rollen", "rolle_list", "verwaltung"),
        ("Beitragsregeln", "beitragsregel_list", "beitraege"),
        ("Mitgliedsarten / Beiträge", "mitgliedsart_list", "beitraege"),
        ("Abteilungen", "abteilung_list", "mitglieder"),
        ("Funktionen", "funktion_list", "mitglieder"),
        ("Familien", "familie_list", "mitglieder"),
        ("Ehrungsarten", "ehrungsart_list", "ehrungen"),
        ("Jubiläumsregeln", "jubilaeumsregel_list", "ehrungen"),
        ("Inventar-Kategorien", "kategorie_list", "inventar"),
        ("Inventar-Standorte", "standort_list", "inventar"),
    ]),
]


def mandant(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    navigation = []
    for gruppe, eintraege in NAV:
        punkte = []
        for label, url_name, modul in eintraege:
            if request.rechte.darf(modul, "view"):
                try:
                    punkte.append((label, reverse(url_name)))
                except NoReverseMatch:
                    pass
        if punkte:
            navigation.append((gruppe, punkte))
    return {"verein": request.verein, "vereine": request.vereine, "navigation": navigation}
