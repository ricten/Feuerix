import re

from apps.core.pdf import brief_pdf, seiten_pdf

from .platzhalter import ersetzen, kontext


def absaetze(text):
    """Text -> Absätze (Leerzeile = neuer Absatz; einfache Zeilenumbrüche bleiben erhalten)."""
    return [a.strip("\n") for a in re.split(r"\n[ \t]*\n", text or "") if a.strip()]


def _seite(verein, betreff, text, mitglied, datum, ctx, mit_empfaenger=True, wasserzeichen=None):
    return {
        "empfaenger": mitglied.anschrift_zeilen() if (mitglied is not None and mit_empfaenger) else [],
        "betreff": ersetzen(betreff, ctx) or "Schreiben",
        "meta": [("Datum", ctx["datum"])],
        "vor": absaetze(ersetzen(text, ctx)),
        "wasserzeichen": wasserzeichen,
    }


def schriftstueck_pdf(s):
    ctx = s.kontext()
    seite = _seite(s.verein, s.betreff or s.titel, s.text, s.mitglied, s.datum, ctx,
                   mit_empfaenger=s.art != "protokoll")
    return seiten_pdf(s.verein, [seite], titel=seite["betreff"])


def serienbrief_pdf(sb, mitglieder, limit=None):
    """Ein PDF mit einem Brief je Mitglied (jeder beginnt auf neuer Seite)."""
    seiten = []
    for i, m in enumerate(mitglieder):
        if limit and i >= limit:
            break
        ctx = kontext(sb.verein, mitglied=m, veranstaltung=sb.veranstaltung, datum=sb.datum)
        seiten.append(_seite(sb.verein, sb.betreff or sb.titel, sb.text, m, sb.datum, ctx))
    return seiten_pdf(sb.verein, seiten, titel=sb.titel, seitenzahl=False)


def serienbrief_einzel(sb, m):
    return serienbrief_pdf(sb, [m])
