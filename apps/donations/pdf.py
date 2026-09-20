from apps.core.pdf import brief_pdf
from apps.core.util import betrag_in_worten, geld


def zuwendungsbestaetigung_pdf(b):
    """ACHTUNG: Textbausteine an das aktuell gültige amtliche Muster des BMF anpassen/prüfen lassen."""
    d = b.vereinsdaten or {
        "name": b.verein.name, "anschrift": b.verein.adresszeile, "finanzamt": b.verein.finanzamt,
        "steuernummer": b.verein.steuernummer, "bescheid_art": b.verein.get_bescheid_art_display(),
        "bescheid_datum": b.verein.bescheid_datum.isoformat() if b.verein.bescheid_datum else "",
        "bescheid_zeitraum": b.verein.bescheid_zeitraum, "zwecke": b.verein.beguenstigte_zwecke}
    bd = d["bescheid_datum"]
    if bd:
        y, m, t = bd.split("-")
        bd = f"{t}.{m}.{y}"
    was = "Sachzuwendungen" if b.art == "sach" else ("Mitgliedsbeitrag" if b.ist_mitgliedsbeitrag
                                                       else "Geldzuwendungen")
    titel = f"Bestätigung über {was}"
    vor = [
        "im Sinne des § 10b des Einkommensteuergesetzes an eine der in § 5 Abs. 1 Nr. 9 des Körperschaftsteuergesetzes "
        "bezeichneten Körperschaften, Personenvereinigungen oder Vermögensmassen",
        f"Name und Anschrift des Zuwendenden:\n{b.spender_name}\n{b.spender_anschrift}",
    ]
    tab = [["Betrag der Zuwendung in Ziffern", "in Buchstaben", "Tag der Zuwendung"],
           [geld(b.betrag), betrag_in_worten(b.betrag),
            f"{b.datum_von:%d.%m.%Y}" if b.datum_von == b.datum_bis else f"{b.datum_von:%d.%m.%Y} – {b.datum_bis:%d.%m.%Y}"]]
    nach = []
    if b.art == "geld":
        nach.append("Es handelt sich um den Verzicht auf Erstattung von Aufwendungen: "
                    + ("Ja" if b.verzicht_aufwendungen else "Nein"))
    else:
        nach.append(f"Bezeichnung der Sachzuwendung: {b.sach_beschreibung or '–'}\n"
                    f"Herkunft: {b.sach_herkunft or 'keine Angabe'}\nWertermittlung: {b.sach_wertermittlung or '–'}")
    nach += [
        f"Wir sind wegen Förderung der folgenden Zwecke: {d['zwecke'] or '–'}\n"
        f"nach dem {d['bescheid_art']} des Finanzamts {d['finanzamt'] or '–'}, StNr. {d['steuernummer'] or '–'}, "
        f"vom {bd or '–'} {('(' + d['bescheid_zeitraum'] + ')') if d['bescheid_zeitraum'] else ''} "
        "nach § 5 Abs. 1 Nr. 9 des Körperschaftsteuergesetzes von der Körperschaftsteuer und nach § 3 Nr. 6 des "
        "Gewerbesteuergesetzes von der Gewerbesteuer befreit.",
        f"Es wird bestätigt, dass die Zuwendung nur zur Förderung dieser Zwecke verwendet wird.",
        "Hinweis: Wer vorsätzlich oder grob fahrlässig eine unrichtige Zuwendungsbestätigung erstellt oder veranlasst, "
        "dass Zuwendungen nicht zu den in der Zuwendungsbestätigung angegebenen steuerbegünstigten Zwecken verwendet "
        "werden, haftet für die entgangene Steuer (§ 10b Abs. 4 EStG, § 9 Abs. 3 KStG, § 9 Nr. 5 GewStG).",
        f"{d['anschrift']}, den {b.ausgestellt_am:%d.%m.%Y}\n\n\n______________________________\n"
        "(Unterschrift des Zuwendungsempfängers)" if b.ausgestellt_am else "",
    ]
    return brief_pdf(b.verein, [b.spender_name] + b.spender_anschrift.split(", "), titel,
                     meta=[("Nummer", b.nummer or "(Entwurf)")], vor=vor, tabelle=tab, nach=nach,
                     wasserzeichen="ENTWURF – nicht gültig" if b.status == "entwurf" else (
                         "STORNIERT – ungültig" if b.status == "storniert" else None))
