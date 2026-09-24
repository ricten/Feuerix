from django.conf import settings
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _

NAV = [
    (_("Mitglieder"), "bi-people", [
        (_("Mitglieder"), "mitglied_list", "mitglieder"),
        (_("Jubiläen"), "jubilaeen", "ehrungen"),
        (_("Ehrungen"), "ehrung_list", "ehrungen"),
        (_("Dokumente"), "dokument_list", "dokumente"),
    ]),
    (_("Schriftverkehr"), "bi-envelope-paper", [
        (_("Schriftstücke (Einladung, Protokoll …)"), "schriftstueck_list", "schriftverkehr"),
        (_("Serienbriefe"), "serienbrief_list", "schriftverkehr"),
        (_("Vorlagen"), "vorlage_list", "schriftverkehr"),
        (_("Platzhalter-Hilfe"), "platzhalter_hilfe", "schriftverkehr"),
        (_("Ablage"), "ablagedokument_list", "ablage"),
        (_("Ablage-Ordner"), "ordner_list", "ablage"),
    ]),
    (_("Finanzen"), "bi-cash-coin", [
        (_("Beitragsjahre"), "beitragsjahr_list", "beitraege"),
        (_("Rechnungen"), "rechnung_list", "rechnungen"),
        (_("Zahlungen"), "zahlung_list", "zahlungen"),
        (_("Bankumsätze"), "bankumsatz_list", "bank"),
        (_("SEPA-Einzüge"), "sepaeinzug_list", "zahlungen"),
        (_("Spenden"), "spende_list", "spenden"),
        (_("Spendenquittungen"), "zuwendungsbestaetigung_list", "spenden"),
        (_("Aufwandsentschädigungen"), "aufwandsentschaedigung_list", "aufwand"),
    ]),
    (_("Kasse"), "bi-wallet2", [
        (_("Kassenbuch (Buchungen)"), "buchung_list", "kassenbuch"),
        (_("Kassenberichte"), "kassenbericht_list", "kassenbuch"),
        (_("Konten"), "konto_list", "kassenbuch"),
        (_("Buchungskategorien"), "buchungskategorie_list", "kassenbuch"),
    ]),
    (_("Inventar"), "bi-box-seam", [
        (_("Gegenstände"), "gegenstand_list", "inventar"),
        (_("Verleih"), "verleih_list", "verleih"),
        (_("Inventuren"), "inventur_list", "inventur"),
    ]),
    (_("Veranstaltungen"), "bi-calendar-event", [
        (_("Veranstaltungen"), "veranstaltung_list", "veranstaltungen"),
    ]),
    (_("Auswertung"), "bi-bar-chart-line", [
        (_("Auswertungen"), "auswertungen", "auswertungen"),
        (_("Änderungsprotokoll"), "auditlog_list", "audit"),
    ]),
    (_("Verwaltung"), "bi-gear", [
        (_("Verein / Einstellungen / Logo"), "verein_einstellungen", "verwaltung"),
        (_("OpenSlides-Anbindung"), "openslides_einstellungen", "openslides"),
        (_("Paperless-Anbindung"), "paperless_einstellungen", "paperless"),
        (_("FinTS-Anbindung"), "fints_einstellungen", "bank"),
        (_("Benutzer"), "zugang_list", "verwaltung"),
        (_("Rollen"), "rolle_list", "verwaltung"),
        (_("Beitragsregeln"), "beitragsregel_list", "beitraege"),
        (_("Mitgliedsarten / Beiträge"), "mitgliedsart_list", "beitraege"),
        (_("Abteilungen"), "abteilung_list", "mitglieder"),
        (_("Funktionen"), "funktion_list", "mitglieder"),
        (_("Familien"), "familie_list", "mitglieder"),
        (_("Ehrungsarten"), "ehrungsart_list", "ehrungen"),
        (_("Jubiläumsregeln"), "jubilaeumsregel_list", "ehrungen"),
        (_("Inventar-Kategorien"), "kategorie_list", "inventar"),
        (_("Inventar-Standorte"), "standort_list", "inventar"),
        (_("Mitglieder-Import"), "mitglieder_import", "mitglieder"),
        (_("Inventar-Import"), "gegenstand_import", "inventar"),
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


_URL_ICON = {_basisname(url_name): icon for gruppe, icon, eintraege in NAV for label, url_name, modul in eintraege}


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
    produkt = {"product_name": settings.PRODUCT_NAME, "product_tagline": settings.PRODUCT_TAGLINE}
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return produkt
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
    return {**produkt, "verein": verein, "vereine": request.vereine, "navigation": navigation,
            "aktive_icon": _aktive_icon(request), **_farbkontext(verein)}
