"""Mitglieder-Import (CSV/Excel) mit Testlauf, Aktualisierung bestehender Mitglieder und Fehlerbericht."""
from django.db import transaction

from . import tabellen as t
from .models import Abteilung, Familie, Mitglied, Mitgliedsart


class ZeilenFehler(Exception):
    pass


def _suche_bestehend(verein, d):
    nr = d.get("mitgliedsnummer")
    if nr:
        return Mitglied.objects.filter(verein=verein, mitgliedsnummer=int(nr)).first()
    if d.get("geburtsdatum"):
        return Mitglied.objects.filter(verein=verein, vorname__iexact=d["vorname"], nachname__iexact=d["nachname"],
                                       geburtsdatum=d["geburtsdatum"]).first()
    return None


def _wandeln(rohwerte, verein, neu_anlegen, warnungen, zeile):
    """Rohwerte (feld -> Zelle) -> bereinigtes dict; wirft ZeilenFehler bei Problemen."""
    d = {}
    fehler = []
    for feld, wert in rohwerte.items():
        try:
            if feld in ("geburtsdatum", "eintrittsdatum", "austrittsdatum", "mandatsdatum"):
                d[feld] = t.datum(wert)
            elif feld == "individueller_beitrag":
                d[feld] = t.zahl(wert)
            elif feld == "mitgliedsnummer":
                s = t.text(wert)
                d[feld] = int(float(s)) if s else None
            elif feld in ("ist_familienzahler", "vorstandsmitglied", "alters_ehrenabteilung", "einsatzabteilung_aktiv"):
                d[feld] = t.ja(wert)
            elif feld == "anrede":
                d[feld] = t.anrede(wert)
            elif feld == "status":
                s = t.status(wert)
                if s is None:
                    fehler.append(f"Status „{t.text(wert)}“ unbekannt (aktiv, ruhend, ausgetreten, verstorben)")
                else:
                    d[feld] = s
            elif feld == "zahlungsart":
                d[feld] = t.zahlungsart(wert)
            elif feld == "iban":
                s = t.text(wert).replace(" ", "").upper()
                if s and not t.iban_gueltig(s):
                    warnungen.append(f"Zeile {zeile}: IBAN {s} hat keine gültige Prüfsumme – trotzdem übernommen.")
                d[feld] = s
            else:
                d[feld] = t.text(wert)
        except (ValueError, TypeError) as e:
            fehler.append(str(e))
    if not d.get("vorname") and not d.get("nachname"):
        fehler.append("Vor- und Nachname fehlen")
    elif not d.get("nachname"):
        fehler.append("Nachname fehlt")
    elif not d.get("vorname"):
        fehler.append("Vorname fehlt")
    if fehler:
        raise ZeilenFehler("; ".join(fehler))
    return d


def importieren(verein, dateiname, inhalt, testlauf=True, aktualisieren=True, neu_anlegen=False):
    """-> Bericht-dict. Bei testlauf=True wird nichts gespeichert (alles wird zurückgerollt)."""
    kopf, zeilen = t.lesen(dateiname, inhalt)
    zuordnung, unbekannt = t.spaltenzuordnung(kopf)
    if "vorname" not in zuordnung.values() or "nachname" not in zuordnung.values():
        raise ValueError("Die Spalten „Vorname“ und „Nachname“ wurden nicht gefunden. Erkannte Spalten: "
                         + (", ".join(kopf) or "keine"))
    bericht = {"neu": 0, "aktualisiert": 0, "uebersprungen": 0, "fehler": [], "warnungen": [], "unbekannte_spalten": unbekannt,
               "erkannte_spalten": [zuordnung[i] for i in sorted(zuordnung)], "testlauf": testlauf, "gesamt": len(zeilen)}
    if unbekannt:
        bericht["warnungen"].append("Nicht erkannte Spalten (werden ignoriert): " + ", ".join(unbekannt))
    arten = {a.name.lower(): a for a in Mitgliedsart.objects.filter(verein=verein)}
    abt = {a.name.lower(): a for a in Abteilung.objects.filter(verein=verein)}
    fam = {f.name.lower(): f for f in Familie.objects.filter(verein=verein)}

    with transaction.atomic():
        for nr, zeile in enumerate(zeilen, start=2):  # Zeile 1 = Kopf
            roh = {zuordnung[i]: (zeile[i] if i < len(zeile) else None) for i in zuordnung}
            try:
                with transaction.atomic():
                    d = _wandeln(roh, verein, neu_anlegen, bericht["warnungen"], nr)
                    m = _suche_bestehend(verein, d)
                    if m is not None and not aktualisieren:
                        bericht["uebersprungen"] += 1
                        continue
                    neu = m is None
                    if neu:
                        m = Mitglied(verein=verein)
                    # Felder setzen: leere Zellen überschreiben bestehende Werte NICHT
                    for feld, wert in d.items():
                        if feld in ("mitgliedsart", "familie", "abteilungen", "mitgliedsnummer"):
                            continue
                        if wert in (None, "") and not neu:
                            continue
                        setattr(m, feld, wert)
                    if neu and d.get("mitgliedsnummer"):
                        m.mitgliedsnummer = d["mitgliedsnummer"]
                    if d.get("mitgliedsart"):
                        a = arten.get(d["mitgliedsart"].lower())
                        if a is None and neu_anlegen:
                            a = Mitgliedsart.objects.create(verein=verein, name=d["mitgliedsart"])
                            arten[a.name.lower()] = a
                        if a is None:
                            raise ZeilenFehler(f"Mitgliedsart „{d['mitgliedsart']}“ existiert nicht (Option „unbekannte anlegen“ oder "
                                               "vorher unter Mitgliedsarten anlegen)")
                        m.mitgliedsart = a
                    if d.get("familie"):
                        f = fam.get(d["familie"].lower())
                        if f is None:
                            f = Familie.objects.create(verein=verein, name=d["familie"])
                            fam[f.name.lower()] = f
                        m.familie = f
                    m.full_clean(exclude=["verein", "mitgliedsnummer", "foto"])
                    m.save()
                    if d.get("abteilungen"):
                        liste = []
                        for name in [x.strip() for x in d["abteilungen"].replace(";", ",").split(",") if x.strip()]:
                            a = abt.get(name.lower())
                            if a is None:
                                if not neu_anlegen:
                                    raise ZeilenFehler(f"Abteilung „{name}“ existiert nicht")
                                a = Abteilung.objects.create(verein=verein, name=name)
                                abt[name.lower()] = a
                            liste.append(a)
                        m.abteilungen.add(*liste)
                    bericht["neu" if neu else "aktualisiert"] += 1
            except ZeilenFehler as e:
                bericht["fehler"].append((nr, str(e)))
            except Exception as e:  # Validierungs- oder Datenbankfehler einer Zeile
                msg = "; ".join(getattr(e, "messages", [str(e)]))
                bericht["fehler"].append((nr, msg))
        if testlauf:
            transaction.set_rollback(True)
    return bericht
