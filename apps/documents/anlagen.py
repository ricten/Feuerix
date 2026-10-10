"""Anlagen zum Protokoll: Teilnehmerliste, Abstimmungen und Wahlen aus OpenSlides, je als eigene Seite hinter dem
Protokolltext (PDF und Word). Alle Wahlen stehen zusammengefasst in EINEM Block/auf EINER Anlage, ebenso alle
sonstigen Abstimmungen; die Teilnehmerliste ist eine eigene Anlage. Es gibt nur Anlagen, zu denen Daten vorliegen
(Reihenfolge: Teilnehmerliste, Abstimmungen, Wahlen - fortlaufend nummeriert).

Das Ergebnis dieses Moduls ist neutral (Titel, Absaetze, Bloecke, Tabellen) und wird von PDF- und Word-Erzeugung
jeweils in ihr Format uebersetzt."""

# Angaben, die als Fliesstext statt als Tabellenzeile gesetzt werden (koennen lang sein)
TEXTFELDER = ("Antragsteller*in", "Antragstext", "Begründung", "Text", "Status in OpenSlides")

BESCHLUSS_ZEILE = "Beschluss (bitte ankreuzen):   [   ] angenommen     [   ] abgelehnt"
GEWAEHLT_ZEILE = "Gewählt: ______________________________________"


def _vorhanden(veranstaltung):
    """Welche Anlagen es gibt: {"anwesenheit": Anwesende, "abstimmung": [...], "wahl": [...]} (leere weglassen)."""
    daten = {}
    anwesende = list(veranstaltung.anwesenheiten.select_related("mitglied"))
    if anwesende:
        daten["anwesenheit"] = sorted(anwesende, key=lambda a: a.wer.casefold())
    for art in ("abstimmung", "wahl"):
        ergebnisse = list(veranstaltung.wahlergebnisse.filter(art=art).order_by("id"))
        if ergebnisse:
            daten[art] = ergebnisse
    return daten


def anlagen_nummern(veranstaltung):
    """{"anwesenheit": 1, "abstimmung": 2, "wahl": 3} - nur fuer vorhandene Anlagen, fortlaufend."""
    if veranstaltung is None:
        return {}
    return {art: nr for nr, art in enumerate(_vorhanden(veranstaltung), start=1)}


def _titel(w):
    return f"{w.amt} – {w.wahlgang}" if w.wahlgang else w.amt


def _abstimmung_block(w):
    paare = [tuple(p) for p in (w.details or []) if len(p) == 2]
    if not paare:   # aeltere Eintraege ohne strukturierte Einzelheiten: gespeicherten Text unveraendert zeigen
        return {"titel": _titel(w), "absaetze": [w.ergebnis], "nach": [BESCHLUSS_ZEILE]}
    text = [f"{label}: {wert}" for label, wert in paare if label in TEXTFELDER]
    zahlen = [[label, wert] for label, wert in paare if label not in TEXTFELDER]
    block = {"titel": _titel(w), "absaetze": text, "nach": [BESCHLUSS_ZEILE]}
    if zahlen:
        block.update({"zeilen": [["Ergebnis", "Wert"]] + zahlen, "breiten": [60, 105], "rechts_ab": 99})
    return block


def _wahl_block(w):
    paare = [list(p) for p in (w.details or []) if len(p) == 2]
    if not paare:
        return {"titel": _titel(w), "absaetze": [w.ergebnis], "nach": [GEWAEHLT_ZEILE]}
    return {"titel": _titel(w), "zeilen": [["Kandidat*in", "Stimmen"]] + paare, "breiten": [105, 60], "rechts_ab": 99,
            "nach": [GEWAEHLT_ZEILE]}


def anlagen(veranstaltung, datum_text=""):
    """Liste der Anlagen einer Veranstaltung: [{"art", "titel", "vor", "tabellen", "bloecke", "nach"}]."""
    if veranstaltung is None:
        return []
    daten, nummern = _vorhanden(veranstaltung), {}
    nummern = {art: nr for nr, art in enumerate(daten, start=1)}
    kopf = f"{veranstaltung.titel}" + (f", {datum_text}" if datum_text else "")
    ergebnis = []
    if "anwesenheit" in daten:
        zeilen = [["Nr.", "Name", "Mitglied / Gast"]] + [
            [str(i), a.wer, "Mitglied" if a.mitglied_id else "Gast"] for i, a in enumerate(daten["anwesenheit"], 1)]
        ergebnis.append({
            "art": "anwesenheit", "titel": f"Anlage {nummern['anwesenheit']}: Teilnehmerliste", "vor": [
                kopf, f"Anwesende Personen laut Anwesenheitserfassung in OpenSlides: {len(daten['anwesenheit'])}"],
            "tabellen": [{"zeilen": zeilen, "breiten": [15, 100, 50], "rechts_ab": 99}], "bloecke": [],
            "nach": ["Die Stimmberechtigung der Anwesenden und die Beschlussfähigkeit sind vom Versammlungsleiter "
                     "festzustellen."]})
    if "abstimmung" in daten:
        ergebnis.append({
            "art": "abstimmung", "titel": f"Anlage {nummern['abstimmung']}: Abstimmungen", "vor": [
                kopf, "Ergebnisse der in OpenSlides durchgeführten Abstimmungen. Ob ein Antrag angenommen ist, "
                      "ist vom Versammlungsleiter anhand der Satzung festzustellen."],
            "tabellen": [], "bloecke": [_abstimmung_block(w) for w in daten["abstimmung"]], "nach": []})
    if "wahl" in daten:
        ergebnis.append({
            "art": "wahl", "titel": f"Anlage {nummern['wahl']}: Wahlergebnisse", "vor": [
                kopf, "Stimmenverteilung der in OpenSlides durchgeführten Wahlen. Wer gewählt ist, ist vom "
                      "Versammlungsleiter anhand der Satzung festzustellen."],
            "tabellen": [], "bloecke": [_wahl_block(w) for w in daten["wahl"]], "nach": []})
    return ergebnis


def pdf_seiten(veranstaltung, datum_text=""):
    """Anlagen als Seiten-Dicts fuer apps.core.pdf.seiten_pdf (jede beginnt auf neuer Seite mit Briefkopf)."""
    return [{"empfaenger": [], "betreff": a["titel"], "vor": a["vor"], "tabellen": a["tabellen"],
             "bloecke": a["bloecke"], "nach": a["nach"]} for a in anlagen(veranstaltung, datum_text)]
