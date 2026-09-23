from django.conf import settings
from django.urls import NoReverseMatch, reverse

NAV = [
    ("Mitglieder", "bi-people", [
        ("Mitglieder", "mitglied_list", "mitglieder"),
        ("Jubiläen", "jubilaeen", "ehrungen"),
        ("Ehrungen", "ehrung_list", "ehrungen"),
        ("Dokumente", "dokument_list", "dokumente"),
    ]),
    ("Schriftverkehr", "bi-envelope-paper", [
        ("Schriftstücke (Einladung, Protokoll …)", "schriftstueck_list", "schriftverkehr"),
        ("Serienbriefe", "serienbrief_list", "schriftverkehr"),
        ("Vorlagen", "vorlage_list", "schriftverkehr"),
        ("Platzhalter-Hilfe", "platzhalter_hilfe", "schriftverkehr"),
        ("Ablage", "ablagedokument_list", "ablage"),
        ("Ablage-Ordner", "ordner_list", "ablage"),
    ]),
    ("Finanzen", "bi-cash-coin", [
        ("Beitragsjahre", "beitragsjahr_list", "beitraege"),
        ("Rechnungen", "rechnung_list", "rechnungen"),
        ("Zahlungen", "zahlung_list", "zahlungen"),
        ("Bankumsätze", "bankumsatz_list", "bank"),
        ("SEPA-Einzüge", "sepaeinzug_list", "zahlungen"),
        ("Spenden", "spende_list", "spenden"),
        ("Spendenquittungen", "zuwendungsbestaetigung_list", "spenden"),
        ("Aufwandsentschädigungen", "aufwandsentschaedigung_list", "aufwand"),
    ]),
    ("Kasse", "bi-wallet2", [
        ("Kassenbuch (Buchungen)", "buchung_list", "kassenbuch"),
        ("Kassenberichte", "kassenbericht_list", "kassenbuch"),
        ("Konten", "konto_list", "kassenbuch"),
        ("Buchungskategorien", "buchungskategorie_list", "kassenbuch"),
    ]),
    ("Inventar", "bi-box-seam", [
        ("Gegenstände", "gegenstand_list", "inventar"),
        ("Verleih", "verleih_list", "verleih"),
        ("Inventuren", "inventur_list", "inventur"),
    ]),
    ("Veranstaltungen", "bi-calendar-event", [
        ("Veranstaltungen", "veranstaltung_list", "veranstaltungen"),
    ]),
    ("Auswertung", "bi-bar-chart-line", [
        ("Auswertungen", "auswertungen", "auswertungen"),
        ("Änderungsprotokoll", "auditlog_list", "audit"),
    ]),
    ("Verwaltung", "bi-gear", [
        ("Verein / Einstellungen / Logo", "verein_einstellungen", "verwaltung"),
        ("OpenSlides-Anbindung", "openslides_einstellungen", "openslides"),
        ("Paperless-Anbindung", "paperless_einstellungen", "paperless"),
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
        ("Mitglieder-Import", "mitglieder_import", "mitglieder"),
        ("Inventar-Import", "gegenstand_import", "inventar"),
    ]),
]


_SUFFIXE = ("_list", "_add", "_detail", "_edit", "_delete")


def _basisname(url_name):
    """'mitglied_detail' -> 'mitglied' (Grundname ohne CRUD-Endung), damit z. B. auch die Bearbeiten-Seite
    eines Mitglieds als zur NAV-Gruppe 'Mitglieder' gehoerig erkannt wird, nicht nur die Listenseite selbst."""
    for suf in _SUFFIXE:
        if url_name and url_name.endswith(suf):
            return url_name[:-len(suf)]
    return url_name


_URL_ICON = {_basisname(url_name): icon for _, icon, eintraege in NAV for _, url_name, _ in eintraege}


def _aktive_icon(request):
    aktueller_name = getattr(getattr(request, "resolver_match", None), "url_name", None)
    return _URL_ICON.get(_basisname(aktueller_name))


def version(request):
    """Version aus der VERSION-Datei im Projektwurzelverzeichnis - fuer Footer/Support (welcher Stand laeuft)."""
    try:
        app_version = (settings.BASE_DIR / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        app_version = ""
    return {"app_version": app_version}


def _farbkontext(verein):
    """CSS-Variablen fuer die Akzentfarbe der Weboberflaeche - je Verein einstellbar (Vereinseinstellungen)."""
    from .util import hex_zu_rgb, lesbare_textfarbe
    akzent = (verein.akzentfarbe if verein and verein.akzentfarbe else "") or "#1F4E79"
    r, g, b = hex_zu_rgb(akzent)
    return {
        "web_akzentfarbe": akzent,
        "web_akzent_rgb": f"{r},{g},{b}",
        "web_akzenttextfarbe": lesbare_textfarbe(akzent),
    }


def oeffentlich(request):
    """Impressum/Downloads-Links im Footer - auch ohne Anmeldung (z. B. auf der Login-Seite) sichtbar.
    Bei genau einem aktiven Verein wird direkt verlinkt, bei mehreren (Mandantenfaehigkeit) je Verein einzeln.
    Liefert ausserdem die Akzentfarbe fuer anonyme Seiten (Login, Impressum), da mandant() dort leer bleibt."""
    from .models import Verein
    vereine = list(Verein.objects.filter(aktiv=True))
    ctx = {"einzelverein": vereine[0]} if len(vereine) == 1 else {"mehrere_vereine_oeffentlich": vereine}
    if not getattr(request, "verein", None):
        ctx.update(_farbkontext(vereine[0] if len(vereine) == 1 else None))
    return ctx


def mandant(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    navigation = []
    for gruppe, icon, eintraege in NAV:
        punkte = []
        for label, url_name, modul in eintraege:
            if request.rechte.darf(modul, "view"):
                try:
                    punkte.append((label, reverse(url_name)))
                except NoReverseMatch:
                    pass
        if punkte:
            navigation.append((gruppe, icon, punkte))
    verein = request.verein
    if verein is None:
        m = getattr(request.user, "mitglied_zugang", None)
        if m is not None:
            verein = m.verein
    return {"verein": verein, "vereine": request.vereine, "navigation": navigation,
            "aktive_icon": _aktive_icon(request), **_farbkontext(verein)}
