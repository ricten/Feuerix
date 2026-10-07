"""Handbuch und weitere Anleitungen (docs/*.md) direkt in der Weboberflaeche unter "Hilfe" - fuer alle
angemeldeten Benutzer sichtbar, unabhaengig von Modulrechten (reine Lesehilfe, keine Vereinsdaten). Jedes
Dokument liegt deutsch und englisch vor; ausgespielt wird die zur aktiven Oberflaechen-Sprache passende
Fassung (siehe apps.core._sprachauswahl / Django-i18n), englisch nur bei exakt "en"."""
import re

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render
from django.utils.translation import get_language

# slug -> {"de": (Dateiname, Titel), "en": (Dateiname, Titel)}. Nur die anwenderorientierten Dokumente -
# README/INSTALL/GITHUB.md richten sich an Betreiber/Entwickler und gehoeren nicht hierher.
DOKUMENTE = {
    "handbuch": {"de": ("HANDBUCH.md", "Handbuch"), "en": ("HANDBUCH.en.md", "Handbook")},
    "kasse-und-import": {"de": ("KASSE_UND_IMPORT.md", "Kasse & Mitglieder-Import"),
                         "en": ("KASSE_UND_IMPORT.en.md", "Cash Book & Member Import")},
    "schriftverkehr": {"de": ("SCHRIFTVERKEHR.md", "Schriftverkehr & Vorlagen"),
                       "en": ("SCHRIFTVERKEHR.en.md", "Correspondence & Templates")},
    "selbstdatenpflege": {"de": ("SELBSTDATENPFLEGE.md", "Selbstdatenpflege"),
                          "en": ("SELBSTDATENPFLEGE.en.md", "Self-Service Data")},
}
STARTDOKUMENT = "handbuch"


def _sprache():
    return "en" if get_language() == "en" else "de"


def _eintrag(slug, sprache=None):
    return DOKUMENTE[slug][sprache or _sprache()]


def _html(slug):
    sprache = _sprache()
    dateiname, _titel = _eintrag(slug, sprache)
    pfad = settings.BASE_DIR / "docs" / dateiname
    try:
        text = pfad.read_text(encoding="utf-8")
    except OSError:
        raise Http404
    import markdown
    html = markdown.markdown(text, extensions=["tables", "toc", "fenced_code", "sane_lists"])
    # interne Verweise zwischen den Dokumenten (z. B. "KASSE_UND_IMPORT.md"/"KASSE_UND_IMPORT.en.md" oder
    # "SCHRIFTVERKEHR.md#abschnitt") auf die jeweilige Hilfe-Seite ummuenzen, statt auf die rohe Markdown-Datei
    # zu verlinken - unabhaengig davon, ob der Linktext zufaellig auf die deutsche oder englische Datei zeigt.
    for ziel_slug, sprachen in DOKUMENTE.items():
        for ziel_datei, _t in sprachen.values():
            html = re.sub(rf'href="(?:\./|\.\./)?{re.escape(ziel_datei)}(#[^"]*)?"',
                         lambda m, s=ziel_slug: f'href="/hilfe/{s}/{m.group(1) or ""}"', html)
    return html


@login_required
def hilfe(request):
    """Übersicht aller Hilfe-Dokumente."""
    sprache = _sprache()
    eintraege = [{"slug": slug, "titel": sprachen[sprache][1]} for slug, sprachen in DOKUMENTE.items()]
    return render(request, "core/hilfe.html", {"titel": "Hilfe", "dokumente": eintraege})


@login_required
def hilfe_dokument(request, slug):
    if slug not in DOKUMENTE:
        raise Http404
    sprache = _sprache()
    _dateiname, titel = _eintrag(slug, sprache)
    eintraege = [{"slug": s, "titel": sprachen[sprache][1], "aktiv": s == slug} for s, sprachen in DOKUMENTE.items()]
    return render(request, "core/hilfe_dokument.html", {
        "titel": titel, "inhalt_html": _html(slug), "dokumente": eintraege, "aktueller_slug": slug})
