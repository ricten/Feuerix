"""Handbuch und weitere Anleitungen (docs/*.md) direkt in der Weboberflaeche unter "Hilfe" - fuer alle
angemeldeten Benutzer sichtbar, unabhaengig von Modulrechten (reine Lesehilfe, keine Vereinsdaten)."""
import re

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render

# slug -> (Dateiname in docs/, Titel). Nur die anwenderorientierten Dokumente - README/INSTALL/GITHUB.md
# richten sich an Betreiber/Entwickler und gehoeren nicht hierher.
DOKUMENTE = {
    "handbuch": ("HANDBUCH.md", "Handbuch"),
    "kasse-und-import": ("KASSE_UND_IMPORT.md", "Kasse & Mitglieder-Import"),
    "schriftverkehr": ("SCHRIFTVERKEHR.md", "Schriftverkehr & Vorlagen"),
    "selbstdatenpflege": ("SELBSTDATENPFLEGE.md", "Selbstdatenpflege"),
}
STARTDOKUMENT = "handbuch"


def _html(slug):
    dateiname, _titel = DOKUMENTE[slug]
    pfad = settings.BASE_DIR / "docs" / dateiname
    try:
        text = pfad.read_text(encoding="utf-8")
    except OSError:
        raise Http404
    import markdown
    html = markdown.markdown(text, extensions=["tables", "toc", "fenced_code", "sane_lists"])
    # interne Verweise zwischen den Dokumenten (z. B. "KASSE_UND_IMPORT.md" oder "SCHRIFTVERKEHR.md#abschnitt")
    # auf die jeweilige Hilfe-Seite ummuenzen, statt auf die rohe Markdown-Datei zu verlinken.
    for ziel_slug, (ziel_datei, _t) in DOKUMENTE.items():
        html = re.sub(rf'href="(?:\./|\.\./)?{re.escape(ziel_datei)}(#[^"]*)?"',
                     lambda m, s=ziel_slug: f'href="/hilfe/{s}/{m.group(1) or ""}"', html)
    return html


@login_required
def hilfe(request):
    """Übersicht aller Hilfe-Dokumente."""
    eintraege = [{"slug": slug, "titel": titel} for slug, (_, titel) in DOKUMENTE.items()]
    return render(request, "core/hilfe.html", {"titel": "Hilfe", "dokumente": eintraege})


@login_required
def hilfe_dokument(request, slug):
    if slug not in DOKUMENTE:
        raise Http404
    _dateiname, titel = DOKUMENTE[slug]
    eintraege = [{"slug": s, "titel": t, "aktiv": s == slug} for s, (_, t) in DOKUMENTE.items()]
    return render(request, "core/hilfe_dokument.html", {
        "titel": titel, "inhalt_html": _html(slug), "dokumente": eintraege, "aktueller_slug": slug})
