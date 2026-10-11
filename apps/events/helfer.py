"""Zuordnung eines bei der Helfer-Selbsteintragung angegebenen Namens zu einem Mitglied des Vereins."""
import re

from apps.core.util import ascii_kennung
from apps.members.models import Mitglied

AKTIVE_STATUS = ("aktiv", "ruhend")


def _woerter(text):
    """Namensbestandteile normalisiert (klein, Umlaute ausgeschrieben, nur Buchstaben/Ziffern), Reihenfolge egal;
    Bindestriche trennen wie Leerzeichen ("Meier-Schmidt" = "Meier Schmidt")."""
    woerter = [re.sub(r"[^a-z0-9]", "", ascii_kennung(w)) for w in re.split(r"[\s,;\-–]+", text or "")]
    return sorted(w for w in woerter if w)


def finde_mitglied(verein_id, name, mitgliedsnummer=None):
    """Das Mitglied (aktiv/ruhend) dieses Vereins, dessen Vor- und Nachname zum angegebenen Namen passen - unabhaengig
    von Reihenfolge ("Max Muster", "Muster, Max"), Gross-/Kleinschreibung und Umlaut-Schreibweise. Ist der Name nicht
    eindeutig (zwei Mitglieder gleichen Namens), entscheidet eine zusaetzlich angegebene Mitgliedsnummer; ohne passende
    Nummer wird NICHT geraten (None) - dann bleibt der Helfer ein Gast und die Verwaltung ordnet ihn bei Bedarf zu."""
    gesucht = _woerter(name)
    if not gesucht:
        return None
    treffer = [m for m in Mitglied.objects.filter(verein_id=verein_id, status__in=AKTIVE_STATUS)
               if _woerter(f"{m.vorname} {m.nachname}") == gesucht]
    if len(treffer) == 1:
        return treffer[0]
    if len(treffer) > 1 and mitgliedsnummer:
        passend = [m for m in treffer if m.mitgliedsnummer == mitgliedsnummer]
        if len(passend) == 1:
            return passend[0]
    return None
