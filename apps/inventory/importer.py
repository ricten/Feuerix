"""Inventar-Import (CSV/Excel) mit Testlauf, Aktualisierung bestehender Gegenstände und Fehlerbericht."""
from django.db import transaction

from . import tabellen as t
from .models import Gegenstand, Kategorie, Standort


class ZeilenFehler(Exception):
    pass


def _suche_bestehend(verein, d):
    nr = d.get("inventarnummer")
    return Gegenstand.objects.filter(verein=verein, inventarnummer=nr).first() if nr else None


def _wandeln(rohwerte, warnungen, zeile):
    """Rohwerte (feld -> Zelle) -> bereinigtes dict; wirft ZeilenFehler bei Problemen."""
    d = {}
    fehler = []
    for feld, wert in rohwerte.items():
        try:
            if feld in ("anschaffungsdatum", "garantie_bis"):
                d[feld] = t.datum(wert)
            elif feld in ("anschaffungspreis", "aktueller_wert", "leihgebuehr", "kaution"):
                d[feld] = t.zahl(wert)
            elif feld == "verleihbar":
                d[feld] = t.ja(wert)
            elif feld == "zustand":
                s = t.zustand(wert)
                if s is None:
                    fehler.append(f"Zustand „{t.text(wert)}“ unbekannt (neu, gut, gebrauchsspuren, defekt, ausgesondert)")
                else:
                    d[feld] = s
            else:
                d[feld] = t.text(wert)
        except (ValueError, TypeError) as e:
            fehler.append(str(e))
    if not d.get("bezeichnung"):
        fehler.append("Bezeichnung fehlt")
    if fehler:
        raise ZeilenFehler("; ".join(fehler))
    return d


def importieren(verein, dateiname, inhalt, testlauf=True, aktualisieren=True, neu_anlegen=False):
    """-> Bericht-dict. Bei testlauf=True wird nichts gespeichert (alles wird zurückgerollt)."""
    kopf, zeilen = t.lesen(dateiname, inhalt)
    zuordnung, unbekannt = t.spaltenzuordnung(kopf)
    if "bezeichnung" not in zuordnung.values():
        raise ValueError("Die Spalte „Bezeichnung“ wurde nicht gefunden. Erkannte Spalten: "
                         + (", ".join(kopf) or "keine"))
    bericht = {"neu": 0, "aktualisiert": 0, "uebersprungen": 0, "fehler": [], "warnungen": [], "unbekannte_spalten": unbekannt,
               "erkannte_spalten": [zuordnung[i] for i in sorted(zuordnung)], "testlauf": testlauf, "gesamt": len(zeilen)}
    if unbekannt:
        bericht["warnungen"].append("Nicht erkannte Spalten (werden ignoriert): " + ", ".join(unbekannt))
    kategorien = {k.name.lower(): k for k in Kategorie.objects.filter(verein=verein)}
    standorte = {s.name.lower(): s for s in Standort.objects.filter(verein=verein)}

    with transaction.atomic():
        for nr, zeile in enumerate(zeilen, start=2):  # Zeile 1 = Kopf
            roh = {zuordnung[i]: (zeile[i] if i < len(zeile) else None) for i in zuordnung}
            try:
                with transaction.atomic():
                    d = _wandeln(roh, bericht["warnungen"], nr)
                    g = _suche_bestehend(verein, d)
                    if g is not None and not aktualisieren:
                        bericht["uebersprungen"] += 1
                        continue
                    neu = g is None
                    if neu:
                        g = Gegenstand(verein=verein)
                    # Felder setzen: leere Zellen überschreiben bestehende Werte NICHT
                    for feld, wert in d.items():
                        if feld in ("kategorie", "standort", "inventarnummer"):
                            continue
                        if wert in (None, "") and not neu:
                            continue
                        setattr(g, feld, wert)
                    if neu and d.get("inventarnummer"):
                        g.inventarnummer = d["inventarnummer"]
                    if d.get("kategorie"):
                        k = kategorien.get(d["kategorie"].lower())
                        if k is None:
                            if not neu_anlegen:
                                raise ZeilenFehler(f"Kategorie „{d['kategorie']}“ existiert nicht (Option „unbekannte "
                                                   "anlegen“ oder vorher unter Inventar-Kategorien anlegen)")
                            k = Kategorie.objects.create(verein=verein, name=d["kategorie"])
                            kategorien[k.name.lower()] = k
                        g.kategorie = k
                    if d.get("standort"):
                        s = standorte.get(d["standort"].lower())
                        if s is None:
                            if not neu_anlegen:
                                raise ZeilenFehler(f"Standort „{d['standort']}“ existiert nicht (Option „unbekannte "
                                                   "anlegen“ oder vorher unter Inventar-Standorte anlegen)")
                            s = Standort.objects.create(verein=verein, name=d["standort"])
                            standorte[s.name.lower()] = s
                        g.standort = s
                    g.full_clean(exclude=["verein", "inventarnummer", "foto", "dokument"])
                    g.save()
                    bericht["neu" if neu else "aktualisiert"] += 1
            except ZeilenFehler as e:
                bericht["fehler"].append((nr, str(e)))
            except Exception as e:  # Validierungs- oder Datenbankfehler einer Zeile
                msg = "; ".join(getattr(e, "messages", [str(e)]))
                bericht["fehler"].append((nr, msg))
        if testlauf:
            transaction.set_rollback(True)
    return bericht
