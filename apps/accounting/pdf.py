from apps.core.pdf import seiten_pdf
from apps.core.util import geld

from .services import berichtsdaten


def _g(v):
    return geld(v)


def _kopfzeile(b):
    return [("Zeitraum", f"{b.von:%d.%m.%Y} – {b.bis:%d.%m.%Y}")] + ([("Kassenwart/in", b.kassenwart)] if b.kassenwart else [])


def kassenbericht_seiten(b, d=None):
    d = d or berichtsdaten(b)
    vj = d["vorjahr"]
    tab_konten = [["Konto", "Anfangsbestand", "Einnahmen", "Ausgaben", "Endbestand"]]
    for k in d["konten"]:
        tab_konten.append([k["name"], _g(k["anfang"]), _g(k["einnahmen"]), _g(k["ausgaben"]), _g(k["ende"])])
    tab_konten.append(["**Summe", f"**{_g(d['anfang'])}", f"**{_g(d['einnahmen'])}", f"**{_g(d['ausgaben'])}",
                       f"**{_g(d['ende'])}"])

    def kat_tabelle(gruppen, gesamt, gesamt_vj, titel):
        zeilen = [["Kategorie", "Betrag", f"Vorjahr ({vj['von']:%Y})"]]
        for g in gruppen:
            zeilen.append([f"**{g['label']}", "", ""])
            zeilen += [[f"   {n}", _g(s), _g(v)] for n, s, v in g["zeilen"]]
        zeilen.append([f"**Summe {titel}", f"**{_g(gesamt)}", f"**{_g(gesamt_vj)}"])
        return zeilen

    tab_sph = [["Sphäre", "Einnahmen", "Ausgaben", "Ergebnis"]] + [[l, _g(e), _g(a), _g(r)] for l, e, a, r in d["sphaeren"]]
    tabellen = [
        {"titel": "1. Kontenübersicht", "zeilen": tab_konten, "rechts_ab": 1, "breiten": [45, 30, 30, 30, 30]},
        {"titel": "2. Einnahmen", "zeilen": kat_tabelle(d["einnahmen_gruppen"], d["einnahmen"], vj["einnahmen"], "Einnahmen"),
         "rechts_ab": 1, "breiten": [85, 40, 40]},
        {"titel": "3. Ausgaben", "zeilen": kat_tabelle(d["ausgaben_gruppen"], d["ausgaben"], vj["ausgaben"], "Ausgaben"),
         "rechts_ab": 1, "breiten": [85, 40, 40]},
        {"titel": "4. Ergebnis nach steuerlichen Sphären", "zeilen": tab_sph, "rechts_ab": 1, "breiten": [65, 33, 33, 34]},
    ]
    ist = d["ist"]
    bestaende = []
    if ist["bar_ist"] is not None or ist["bank_ist"] is not None:
        zeilen = [["Bestand", "Buchmäßig", "Ist (gezählt / Kontoauszug)", "Differenz"]]
        if ist["bar_ist"] is not None:
            zeilen.append(["Barkasse", _g(ist["bar_soll"]), _g(ist["bar_ist"]), _g(ist["bar_diff"])])
        if ist["bank_ist"] is not None:
            zeilen.append(["Bankkonten", _g(ist["bank_soll"]), _g(ist["bank_ist"]), _g(ist["bank_diff"])])
        tabellen.append({"titel": "5. Bestandsabgleich (Soll/Ist)", "zeilen": zeilen, "rechts_ab": 1, "breiten": [40, 35, 55, 35]})
    nach = [f"Ergebnis des Zeitraums: {_g(d['ueberschuss'])} ({'Überschuss' if d['ueberschuss'] >= 0 else 'Fehlbetrag'}). "
            f"Anfangsbestand {_g(d['anfang'])}, Endbestand {_g(d['ende'])}."]
    if b.pruefbemerkung:
        nach += ["Bemerkungen / Prüfungsergebnis:\n" + b.pruefbemerkung]
    nach += ["\nOrt, Datum: ____________________________",
             "\n\n______________________________\nKassenwart/in " + (b.kassenwart or ""),
             "\n\n______________________________\nKassenprüfer/in 1 " + (b.pruefer_1 or ""),
             "\n\n______________________________\nKassenprüfer/in 2 " + (b.pruefer_2 or "")]
    seite1 = {"empfaenger": [], "betreff": b.titel, "meta": _kopfzeile(b),
              "vor": [f"Bericht über die Einnahmen und Ausgaben des {b.verein.name} für den Zeitraum "
                      f"{b.von:%d.%m.%Y} bis {b.bis:%d.%m.%Y}."],
              "tabellen": tabellen, "nach": nach,
              "wasserzeichen": "ENTWURF – noch nicht abgeschlossen" if b.status == "entwurf" else None}
    journal = [["Datum", "Beleg", "Buchungstext", "Kategorie", "Einnahme", "Ausgabe"]]
    for x in d["buchungen"]:
        journal.append([f"{x.datum:%d.%m.%Y}", x.belegnummer, x.text, x.kategorie.name,
                        _g(x.betrag) if x.typ == "einnahme" else "", _g(x.betrag) if x.typ == "ausgabe" else ""])
    journal.append(["", "", "**Summen", "", f"**{_g(d['einnahmen'])}", f"**{_g(d['ausgaben'])}"])
    seite2 = {"empfaenger": [], "betreff": f"Anlage: Kassenbuch {b.von:%d.%m.%Y} – {b.bis:%d.%m.%Y}", "meta": [],
              "tabellen": [{"zeilen": journal, "rechts_ab": 4, "breiten": [20, 27, 44, 34, 20, 20], "klein": True}]}
    return [seite1, seite2]


def kassenbericht_pdf(b):
    return seiten_pdf(b.verein, kassenbericht_seiten(b), titel=b.titel, seitenzahl=True)
