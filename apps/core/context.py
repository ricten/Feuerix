from datetime import timedelta

from django.conf import settings
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from . import einstellungen as _einstellungen
from .anbindungen import anbindungen

NAV = [
    (_("Mitglieder"), "bi-people", [
        (_("Mitglieder"), "mitglied_list", "mitglieder"),
        (_("Familien"), "familie_list", "mitglieder"),
        (_("Jubiläen"), "jubilaeen", "ehrungen"),
        (_("Ehrungen"), "ehrung_list", "ehrungen"),
        (_("Dokumente"), "dokument_list", "dokumente"),
    ]),
    (_("Schriftverkehr"), "bi-envelope-paper", [
        (_("Schriftstücke (Einladung, Protokoll …)"), "schriftstueck_list", "schriftverkehr"),
        (_("Serienbriefe"), "serienbrief_list", "rundschreiben"),
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
    ]),
    (_("Inventar"), "bi-box-seam", [
        (_("Gegenstände"), "gegenstand_list", "inventar"),
        (_("Verleih"), "verleih_list", "verleih"),
        (_("Inventuren"), "inventur_list", "inventur"),
    ]),
    (_("Veranstaltungen"), "bi-calendar-event", [
        (_("Veranstaltungen"), "veranstaltung_list", "veranstaltungen"),
        (_("Aufgaben"), "aufgabe_list", "veranstaltungen"),
    ]),
    (_("Auswertung"), "bi-bar-chart-line", [
        (_("Auswertungen"), "auswertungen", "auswertungen"),
        (_("Änderungsprotokoll"), "auditlog_list", "audit"),
    ]),
    (_("Verwaltung"), "bi-gear", [
        (_("Einstellungen (Übersicht)"), "einstellungen", None),
        (_("Verein / Erscheinungsbild"), "verein_einstellungen", "verwaltung"),
        (_("Benutzer"), "zugang_list", "verwaltung"),
        (_("Externe Anbindungen"), "anbindungen", "openslides"),
    ]),
]


# Menuepunkt -> Anbindung, die dafuer eingerichtet und aktiv sein muss
ANBINDUNGS_MENUE = {"openslides_einstellungen": "openslides", "paperless_einstellungen": "paperless"}

_SUFFIXE = ("_list", "_add", "_detail", "_edit", "_delete")


def _basisname(url_name):
    """'mitglied_detail' -> 'mitglied' (Grundname ohne CRUD-Endung), damit z. B. auch die Bearbeiten-Seite
    eines Mitglieds als zur NAV-Gruppe 'Mitglieder' gehoerig erkannt wird, nicht nur die Listenseite selbst."""
    for suf in _SUFFIXE:
        if url_name and url_name.endswith(suf):
            return url_name[:-len(suf)]
    return url_name


_URL_ICON = {_basisname(url_name): icon for gruppe, icon, eintraege in NAV for label, url_name, modul in eintraege}
_URL_ICON["datensicherung"] = "bi-gear"
for _u in _einstellungen.url_namen():      # alle Seiten der Einstellungs-Uebersicht gehoeren zum Menue "Verwaltung"
    _URL_ICON.setdefault(_basisname(_u), "bi-gear")
for _u in ("openslides_einstellungen", "paperless_einstellungen"):
    _URL_ICON.setdefault(_u, "bi-gear")


def _aktive_icon(request):
    aktueller_name = getattr(getattr(request, "resolver_match", None), "url_name", None)
    return _URL_ICON.get(_basisname(aktueller_name))


def version(request):
    """Version aus der VERSION-Datei im Projektwurzelverzeichnis - fuer Footer/Support (welcher Stand laeuft).
    Fuer Superadministratoren wird ausserdem (hoechstens einmal pro UPDATE_CHECK_INTERVALL_STUNDEN, im
    Hintergrund per Celery) geprueft, ob eine neuere Version veroeffentlicht wurde - das Ergebnis der
    VORHERIGEN Pruefung wird sofort angezeigt, die neu angestossene erst beim naechsten Seitenaufruf."""
    try:
        app_version = (settings.BASE_DIR / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        app_version = ""
    try:      # Codename der Version (Feuerwehrjargon), Datei VERSION_NAME - fehlt sie, bleibt die Anzeige bei der Nummer
        app_version_name = (settings.BASE_DIR / "VERSION_NAME").read_text(encoding="utf-8").strip()
    except OSError:
        app_version_name = ""
    ctx = {"app_version": app_version, "app_version_name": app_version_name}
    if getattr(request.user, "is_superuser", False):
        from .models import Systemeinstellung
        se = Systemeinstellung.laden()
        intervall = timedelta(hours=settings.UPDATE_CHECK_INTERVALL_STUNDEN)
        if settings.UPDATE_CHECK_URL and (se.update_geprueft_am is None
                                          or timezone.now() - se.update_geprueft_am > intervall):
            from .tasks import update_pruefen_task
            update_pruefen_task.delay()
        neu = se.update_anzeigen(app_version)
        if neu:
            ctx["update_verfuegbare_version"] = neu
            # Sprung direkt zum Abschnitt der neuen Version (GitHub-Anker: "## 1.71.2" -> #1712)
            ctx["update_changelog_url"] = (f"{settings.PRODUCT_CHANGELOG_URL}#{neu.replace('.', '')}"
                                           if settings.PRODUCT_CHANGELOG_URL else settings.PRODUCT_SOURCE_URL)
        from .models import ZweiFaktorAnfrage
        offen = ZweiFaktorAnfrage.objects.filter(erledigt_am__isnull=True).count()
        if offen:
            ctx["zf_anfragen_offen"] = offen
        if se.sicherung_aktiv and se.sicherung_letzter_lauf and not se.sicherung_letzter_ok:
            ctx["sicherung_fehler"] = se.sicherung_letzte_meldung
    return ctx


def _farbkontext(verein):
    """CSS-Variablen fuer die Weboberflaeche - je Verein einstellbar (Vereinseinstellungen): eine Hauptfarbe und
    zwei Akzentfarben (Farbverlaeufe bzw. Icon-Hervorhebungen). Nicht gesetzte Farben werden serverseitig
    abgeleitet (nie per CSS color-mix mit unbekanntem Ergebnis) - nur so laesst sich dazu zuverlaessig eine
    kontrastreiche Text-/Icon-Farbe berechnen, unabhaengig davon wie hell oder dunkel die gewaehlte Farbe ist."""
    from .util import gemischte_farbe, hex_zu_rgb, lesbare_textfarbe
    # Fuer die automatisch abgeleitete zweite Farbe (Gradient-/Hintergrundpartner) darf noch ordentlich Farbe
    # uebrigbleiben - sie dient selbst als Hintergrund, nicht als Text.
    GRADIENT_ANTEIL = 0.6
    # Fuer "garantiert dunkel genug"-Text-/Icon-Farben dagegen deutlich dunkler mischen: 40% Original + 60%
    # Schwarz haelt auch aus Weiss/Leuchtgelb noch eine Leuchtdichte unter dem WCAG-Schwellenwert (~0.179) fuer
    # "braucht weisse Gegenfarbe" - nur so bleibt die Ableitung unabhaengig von der gewaehlten Akzentfarbe
    # zuverlaessig als Text/Icon auf hellen Flaechen lesbar.
    TEXT_DUNKEL_ANTEIL = 0.4
    haupt = (verein.akzentfarbe_web if verein and verein.akzentfarbe_web else "") or \
        (verein.akzentfarbe if verein and verein.akzentfarbe else "") or "#AF2B1E"
    akzent1 = (verein.akzentfarbe_web_2 if verein and verein.akzentfarbe_web_2 else "") or \
        gemischte_farbe(haupt, "#000000", GRADIENT_ANTEIL)
    akzent2 = (verein.akzentfarbe_web_3 if verein and verein.akzentfarbe_web_3 else "") or "#F7FA00"
    r, g, b = hex_zu_rgb(haupt)
    return {
        "web_akzentfarbe": haupt,
        "web_akzentfarbe_2": akzent1,
        "web_akzentfarbe_3": akzent2,
        "web_akzent_rgb": f"{r},{g},{b}",
        # Kontrastfarbe fuer Text/Icons jeweils eigens je Hintergrund berechnet - das Menue-Band (Akzentfarbe 1)
        # braucht nicht zwangslaeufig dieselbe Textfarbe wie das Logo-Band (Hauptfarbe) darueber.
        "web_akzenttextfarbe": lesbare_textfarbe(haupt),
        "web_akzentfarbe_2_textfarbe": lesbare_textfarbe(akzent1),
        # Dunklere Variante der Haupt-/zweiten Akzentfarbe - fuer Icons/Text auf hell abgetoenten Hintergruenden
        # derselben Farbe (eine reine Aufhellung mit Weiss liesse sich sonst nicht zuverlaessig gegen sich
        # selbst lesbar halten, vor allem bei ohnehin hellen Farben wie Leuchtgelb).
        "web_akzentfarbe_dunkel": gemischte_farbe(haupt, "#000000", TEXT_DUNKEL_ANTEIL),
        "web_akzentfarbe_3_dunkel": gemischte_farbe(akzent2, "#000000", TEXT_DUNKEL_ANTEIL),
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
    produkt = {"product_name": settings.PRODUCT_NAME, "product_tagline": settings.PRODUCT_TAGLINE,
              "product_source_url": settings.PRODUCT_SOURCE_URL}
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return produkt
    navigation = []
    anb = anbindungen(request)
    for gruppe, icon, eintraege in NAV:
        punkte = []
        for label, url_name, modul in eintraege:
            if url_name in ANBINDUNGS_MENUE and not anb.aktiv(ANBINDUNGS_MENUE[url_name]):
                continue   # Einstellungsseite erst im Menue, wenn die Instanz angebunden ist (sonst ueber "Externe Anbindungen")
            if url_name == "anbindungen":
                sichtbar = request.rechte.darf("openslides", "view") or request.rechte.darf("paperless", "view")
            elif url_name == "einstellungen":
                sichtbar = bool(_einstellungen.sichtbare_bereiche(request))
            else:
                sichtbar = request.rechte.darf(modul, "view")
            if sichtbar:
                try:
                    punkte.append((label, reverse(url_name)))
                except NoReverseMatch:
                    pass
        if punkte:
            navigation.append((gruppe, icon, punkte))
    navigation = [(g, i, p, None) for g, i, p in navigation]
    for n, (gruppe, icon, punkte, _b) in enumerate(navigation):
        if icon == "bi-gear":     # Menue "Verwaltung": alle Einstellungen nach Themen (siehe einstellungen.py)
            bloecke = _einstellungen.menue_bloecke(request)
            if bloecke:
                navigation[n] = (gruppe, icon, [(l, u) for _t, ps in bloecke for l, u in ps], bloecke)
    try:   # fuer alle angemeldeten Benutzer sichtbar - unabhaengig von Modulrechten (reine Lesehilfe)
        navigation.append((_("Hilfe"), "bi-question-circle", [(_("Handbuch & Anleitungen"), reverse("hilfe"))], None))
    except NoReverseMatch:
        pass
    verein = request.verein
    if verein is None:
        m = getattr(request.user, "mitglied_zugang", None)
        if m is not None:
            verein = m.verein
    seitenleiste = []
    if verein is not None and _aktive_icon(request) == "bi-gear" and request.resolver_match.url_name != "einstellungen":
        seitenleiste = _einstellungen.seitenleiste(request)      # Einstellungsseiten: Navigation links daneben
    return {**produkt, "verein": verein, "vereine": request.vereine, "navigation": navigation,
            "aktive_icon": _aktive_icon(request), "seitenleiste": seitenleiste, **_farbkontext(verein)}
