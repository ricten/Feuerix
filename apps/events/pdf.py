"""Druckbarer Schichtplan einer Veranstaltung."""
from django.utils import timezone

from apps.core.pdf import seiten_pdf
from apps.documents.platzhalter import WOCHENTAGE


def _zeit(s):
    b, e = timezone.localtime(s.beginn), timezone.localtime(s.ende)
    if b.date() == e.date():
        return f"{b:%H:%M} – {e:%H:%M} Uhr"
    return f"{b:%d.%m. %H:%M} – {e:%d.%m. %H:%M} Uhr"


def schichtplan_pdf(veranstaltung):
    """Alle Schichten der Veranstaltung nach Tag und Beginn, je Schicht alle Eingeteilten (Mitglieder und eingetragene
    Gaeste mit Kontakt); freie Plaetze bleiben als Schreiblinien zum handschriftlichen Eintragen stehen."""
    v = veranstaltung
    schichten = list(v.schichten.prefetch_related("einsaetze__mitglied").order_by("beginn", "id"))
    zeilen = [["Schicht", "Zeit", "Eingeteilte Helfer"]]
    tag, offene = None, 0
    for s in schichten:
        beginn = timezone.localtime(s.beginn)
        if beginn.date() != tag:
            tag = beginn.date()
            zeilen.append([f"**{WOCHENTAGE[beginn.weekday()]}, {beginn:%d.%m.%Y}", "", ""])
        helfer = []
        for e in sorted(s.einsaetze.all(), key=lambda e: e.wer.casefold()):
            helfer.append(f"{e.wer} ({e.kontakt})" if e.kontakt else e.wer)
        frei = max(s.benoetigt - len(helfer), 0)
        offene += frei
        helfer += ["_" * 34] * frei
        zeilen.append([f"{s.bezeichnung}\nBesetzung {len(s.einsaetze.all())}/{s.benoetigt}", _zeit(s),
                       "\n".join(helfer) or "–"])
    beginn = timezone.localtime(v.beginn)
    vor = [f"{WOCHENTAGE[beginn.weekday()]}, {beginn:%d.%m.%Y} {beginn:%H:%M} Uhr" + (f" · {v.ort}" if v.ort else ""),
           f"Stand: {timezone.localdate():%d.%m.%Y}"]
    nach = ["Mit Schreiblinien markierte Plätze sind noch frei und können handschriftlich ergänzt werden."] if offene else []
    if not schichten:
        zeilen.append(["(noch keine Schichten angelegt)", "", ""])
    seite = {"empfaenger": [], "betreff": f"Schichtplan – {v.titel}", "vor": vor,
             "tabellen": [{"zeilen": zeilen, "breiten": [48, 36, 91], "rechts_ab": 99}], "nach": nach}
    return seiten_pdf(v.verein, [seite], titel=f"Schichtplan {v.titel}")
