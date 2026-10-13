import re

from apps.core.pdf import Layout, brief_pdf, seiten_pdf

from . import anlagen, richtext
from .platzhalter import ersetzen, kontext


def absaetze(text):
    """Text -> Absätze (Leerzeile = neuer Absatz; einfache Zeilenumbrüche bleiben erhalten)."""
    return [a.strip("\n") for a in re.split(r"\n[ \t]*\n", text or "") if a.strip()]


def _seite(verein, betreff, text, mitglied, datum, ctx, mit_empfaenger=True, wasserzeichen=None):
    return {
        "empfaenger": mitglied.anschrift_zeilen() if (mitglied is not None and mit_empfaenger) else [],
        "betreff": ersetzen(betreff, ctx) or "Schreiben",
        "datum": f"Datum: {ctx['datum']}",
        "vor": [lambda stile, layout, breite, h=richtext.text_ersetzt(text, ctx):
                richtext.flowables(h, stile, layout, breite)],
        "wasserzeichen": wasserzeichen,
    }


def schriftstueck_pdf(s):
    ctx = s.kontext()
    seite = _seite(s.verein, s.betreff or s.titel, s.text, s.mitglied, s.datum, ctx,
                   mit_empfaenger=s.art != "protokoll")
    seiten = [seite]
    if s.art == "protokoll" and s.veranstaltung_id:   # Teilnehmerliste/Abstimmungen/Wahlen als Anlagen (eigene Seiten)
        seiten += anlagen.pdf_seiten(s.veranstaltung, ctx.get("veranstaltung_datum", ""))
    return seiten_pdf(s.verein, seiten, titel=seite["betreff"], layout=Layout.von_vorlage(s.vorlage))


def serienbrief_pdf(sb, mitglieder, limit=None):
    """Ein PDF mit einem Brief je Mitglied (jeder beginnt auf neuer Seite)."""
    seiten = []
    for i, m in enumerate(mitglieder):
        if limit and i >= limit:
            break
        ctx = kontext(sb.verein, mitglied=m, veranstaltung=sb.veranstaltung, datum=sb.datum)
        seiten.append(_seite(sb.verein, sb.betreff or sb.titel, sb.text, m, sb.datum, ctx))
    return seiten_pdf(sb.verein, seiten, titel=sb.titel, seitenzahl=False, layout=Layout.von_vorlage(sb.vorlage))


def serienbrief_einzel(sb, m):
    return serienbrief_pdf(sb, [m])
