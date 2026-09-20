from apps.core.pdf import brief_pdf
from apps.core.util import geld


def _empfaenger(r):
    return [r.empfaenger_name] + (r.empfaenger_anschrift or "").splitlines()


def rechnung_pdf(r):
    v = r.verein
    titel = {"gutschrift": "Gutschrift", "storno": "Stornorechnung"}.get(r.typ, "Rechnung")
    meta = [("Nummer", r.nummer or "(Entwurf)"), ("Datum", f"{r.datum:%d.%m.%Y}")]
    if r.mitglied_id:
        meta.append(("Mitgliedsnummer", str(r.mitglied.mitgliedsnummer)))
    if r.faellig_am and r.betrag > 0:
        meta.append(("Fällig am", f"{r.faellig_am:%d.%m.%Y}"))
    if r.zeitraum_von and r.zeitraum_bis:
        meta.append(("Zeitraum", f"{r.zeitraum_von:%d.%m.%Y} – {r.zeitraum_bis:%d.%m.%Y}"))
    tabelle = [["Bezeichnung", "Menge", "Einzelpreis", "Betrag"]]
    for p in r.positionen.all():
        tabelle.append([p.text, f"{p.menge:g}", geld(p.einzelpreis), geld(p.betrag)])
    tabelle.append(["Gesamtbetrag", "", "", geld(r.betrag)])
    nach = [r.fusstext] if r.fusstext else []
    if r.betrag > 0 and v.iban and r.typ in ("beitrag", "individuell", "sammel"):
        vz = f"MITGLIED {r.mitglied.mitgliedsnummer} " if r.mitglied_id else ""
        nach.append(f"Bitte überweisen Sie {geld(r.betrag)} auf das Konto {v.iban}"
                    f"{(' (' + v.bic + ')') if v.bic else ''}. Verwendungszweck: {vz}{r.nummer}")
        if r.mitglied_id and r.mitglied.zahlungsart == "lastschrift" and r.mitglied.mandatsreferenz:
            nach.append(f"Der Betrag wird per SEPA-Lastschrift eingezogen (Mandatsreferenz "
                        f"{r.mitglied.mandatsreferenz}, Gläubiger-ID {v.glaeubiger_id}).")
    return brief_pdf(v, _empfaenger(r), f"{titel} {r.nummer or ''}".strip(), meta=meta,
                     vor=[r.kopftext] if r.kopftext else [], tabelle=tabelle, nach=nach,
                     wasserzeichen="ENTWURF – noch nicht gültig" if r.status == "entwurf" else None)


def mahnung_pdf(mahn):
    r, v = mahn.rechnung, mahn.rechnung.verein
    offen = r.offen_betrag
    text = [f"zu unserer Rechnung {r.nummer} vom {r.datum:%d.%m.%Y} über {geld(r.betrag)} ist ein offener Betrag von "
            f"{geld(offen)} verzeichnet.",
            f"Wir bitten Sie, {geld(offen + mahn.gebuehr)}"
            f"{' (inkl. ' + geld(mahn.gebuehr) + ' Mahngebühr)' if mahn.gebuehr else ''} bis zum "
            f"{mahn.frist:%d.%m.%Y} zu überweisen."]
    if v.iban:
        text.append(f"Konto: {v.iban}{(' / ' + v.bic) if v.bic else ''}, Verwendungszweck: {r.nummer}")
    text.append("Sollte sich Ihre Zahlung mit diesem Schreiben überschnitten haben, betrachten Sie es bitte als "
                "gegenstandslos.")
    return brief_pdf(v, _empfaenger(r), mahn.get_stufe_display(),
                     meta=[("Datum", f"{mahn.datum:%d.%m.%Y}"), ("Rechnung", r.nummer)], vor=text)
