"""Platzhalter in Vorlagen: {vorname}, {tagesordnung} ... (bewusst kein Template-Code -> sicher bearbeitbar)."""
import re
from datetime import date

from django.utils import timezone

PLATZHALTER = [
    ("Empfänger (Mitglied)", [
        ("briefanrede", "Komplette Anrede, z. B. „Sehr geehrter Herr Müller,“ (ohne Mitglied: „Liebe Mitglieder,“)"),
        ("vorname", "Vorname"), ("nachname", "Nachname"), ("name", "Vor- und Nachname"),
        ("mitgliedsnummer", "Mitgliedsnummer"), ("strasse", "Straße und Hausnummer"), ("plz", "Postleitzahl"),
        ("ort", "Ort"), ("email", "E-Mail-Adresse"), ("eintritt", "Eintrittsdatum (TT.MM.JJJJ)"),
        ("mitglied_seit_jahre", "Jahre der Mitgliedschaft (für Jubiläumsschreiben)"),
        ("mitgliedsart", "Mitgliedsart"),
    ]),
    ("Verein", [
        ("verein", "Name des Vereins"), ("verein_anschrift", "Anschrift des Vereins"), ("verein_ort", "Ort des Vereins"),
        ("verein_email", "E-Mail des Vereins"), ("unterschrift_1", "Unterschrift 1 (aus den Vereinsdaten)"),
        ("unterschrift_2", "Unterschrift 2 (aus den Vereinsdaten)"),
    ]),
    ("Datum", [("heute", "Heutiges Datum"), ("datum", "Datum des Schriftstücks / Briefdatums"), ("jahr", "Aktuelles Jahr")]),
    ("Veranstaltung", [
        ("veranstaltung", "Titel"), ("veranstaltung_datum", "Datum mit Wochentag, z. B. „Samstag, 12.09.2026“"),
        ("veranstaltung_uhrzeit", "Beginn (Uhrzeit)"), ("veranstaltung_ende", "Ende (Uhrzeit)"),
        ("veranstaltung_ort", "Ort"), ("veranstaltung_beschreibung", "Beschreibung"),
        ("anmeldeschluss", "Anmeldeschluss"),
        ("tagesordnung", "Nummerierte Tagesordnung (aus den Tagesordnungspunkten der Veranstaltung)"),
        ("wahlergebnisse", "Stimmenverteilung der aus OpenSlides übernommenen Wahlen (wer gewählt ist, bitte "
                           "selbst eintragen)"),
    ]),
    ("OpenSlides (Zugangsdaten)", [
        ("openslides_url", "Adresse der OpenSlides-Instanz"),
        ("openslides_benutzername", "OpenSlides-Benutzername des Mitglieds"),
        ("openslides_passwort", "Startpasswort (nur solange es gespeichert ist)"),
    ]),
]
WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
_RE = re.compile(r"\{([a-z_0-9]+)\}")


def _d(d):
    return d.strftime("%d.%m.%Y") if d else ""


def briefanrede(m):
    if m is None:
        return "Liebe Mitglieder,"
    if m.anrede == "herr":
        return f"Sehr geehrter Herr {m.nachname},"
    if m.anrede == "frau":
        return f"Sehr geehrte Frau {m.nachname},"
    if m.anrede == "firma":
        return "Sehr geehrte Damen und Herren,"
    return f"Guten Tag {m.vorname} {m.nachname},"


def kontext(verein, mitglied=None, veranstaltung=None, datum=None):
    heute = date.today()
    k = {
        "verein": verein.name, "verein_anschrift": verein.adresszeile, "verein_ort": verein.ort,
        "verein_email": verein.email, "unterschrift_1": verein.unterschrift_1, "unterschrift_2": verein.unterschrift_2,
        "heute": _d(heute), "datum": _d(datum or heute), "jahr": str(heute.year),
        "briefanrede": briefanrede(mitglied),
    }
    m = mitglied
    if m is not None:
        k.update({
            "vorname": m.vorname, "nachname": m.nachname, "name": m.name, "mitgliedsnummer": str(m.mitgliedsnummer or ""),
            "strasse": m.strasse, "plz": m.plz, "ort": m.ort, "email": m.email, "eintritt": _d(m.eintrittsdatum),
            "mitglied_seit_jahre": str(m.mitgliedsjahre() or ""),
            "mitgliedsart": str(m.mitgliedsart) if m.mitgliedsart_id else "",
            "openslides_benutzername": m.openslides_username, "openslides_passwort": m.openslides_initialpasswort,
        })
    try:
        from apps.openslides.models import OpenSlidesVerbindung
        vb = OpenSlidesVerbindung.objects.filter(verein=verein).first()
        k["openslides_url"] = vb.url if vb else ""
    except Exception:
        k["openslides_url"] = ""
    v = veranstaltung
    if v is not None:
        b = timezone.localtime(v.beginn)
        e = timezone.localtime(v.ende) if v.ende else None
        top = [f"TOP {t.position}: {t.titel}" for t in v.tagesordnung.all()]
        k.update({
            "veranstaltung": v.titel, "veranstaltung_datum": f"{WOCHENTAGE[b.weekday()]}, {b:%d.%m.%Y}",
            "veranstaltung_uhrzeit": f"{b:%H:%M}", "veranstaltung_ende": f"{e:%H:%M}" if e else "",
            "veranstaltung_ort": v.ort, "veranstaltung_beschreibung": v.beschreibung,
            "anmeldeschluss": _d(v.anmeldeschluss),
            "tagesordnung": "\n".join(top) if top else "(noch keine Tagesordnungspunkte erfasst)",
        })
        wahlen = [f"{w.amt}{' – ' + w.wahlgang if w.wahlgang else ''}:\n{w.ergebnis}" for w in v.wahlergebnisse.all()]
        k["wahlergebnisse"] = "\n\n".join(wahlen) if wahlen else "(keine Wahlergebnisse aus OpenSlides übernommen)"
    return k


def ersetzen(text, ctx):
    return _RE.sub(lambda mo: str(ctx[mo.group(1)]) if mo.group(1) in ctx else mo.group(0), text or "")


def offene(text, ctx):
    """Platzhalter, die im gegebenen Kontext nicht ersetzt werden konnten."""
    return sorted({k for k in _RE.findall(text or "") if k not in ctx})
