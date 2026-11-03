"""Update per Weboberflaeche (Verwaltung > Software-Update) - die Seite im Container, die Arbeit auf dem Server.

Der Container darf kein Docker steuern und sich nicht selbst ersetzen. Deshalb gilt: Er legt im gemeinsamen Ordner
UPDATE_VERZEICHNIS (auf dem Server: update/) nur eine **Auftragsdatei** an. Ein systemd-Pfad-Dienst auf dem Server (eingerichtet mit
scripts/update_einrichten.sh) startet daraufhin scripts/update.sh, das Sicherung, git pull, Image bauen und Neustart erledigt und den
Stand in status.json sowie die Ausgabe in update.log schreibt. Hier wird beides nur gelesen. Der Inhalt der Auftragsdatei wird vom
Server nie ausgewertet (kein Befehl, keine Parameter) - sie loest nur den festen Ablauf aus.

Nur fuer Feuerix ohne Portalverwaltung; mit der Portalverwaltung aktualisiert diese die Instanzen."""
import json
import os
from datetime import datetime, timedelta, timezone as dt_zone
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

ZUSTAENDE = ("laeuft", "ok", "fehler", "aktuell")
# Ein Update, das so lange "laeuft" meldet, gilt als abgebrochen (z. B. Server neu gestartet) und blockiert nichts mehr.
LAUF_VERFALL = timedelta(hours=2)
# So lange darf ein Auftrag unbearbeitet liegen, bevor die Seite vermutet, dass der Server-Dienst nicht reagiert.
AUFTRAG_WARTEZEIT = timedelta(minutes=5)
LOG_ZEILEN = 60


def verzeichnis():
    return Path(settings.UPDATE_VERZEICHNIS)


def aktiv():
    """Schalter SOFTWAREUPDATE_PER_WEB (setzt scripts/update_einrichten.sh)."""
    return bool(settings.SOFTWAREUPDATE_PER_WEB)


def host_bereit():
    """Der Server-Dienst ist eingerichtet (update_einrichten.sh legt update/host_bereit an) und der Ordner ist beschreibbar."""
    v = verzeichnis()
    return (v / "host_bereit").is_file() and os.access(v, os.W_OK)


def _text(wert, laenge=300):
    return str(wert if wert is not None else "")[:laenge]


def _zeit(wert):
    try:
        z = parse_datetime(str(wert))
    except (ValueError, TypeError):
        return None
    return z if z is None or z.tzinfo else z.replace(tzinfo=dt_zone.utc)


def status():
    """Stand des letzten Laufs aus status.json -> dict mit zustand ('' = noch nie), schritt, meldung, von, nach, gestartet,
    beendet (Datum oder None). Fehlende oder kaputte Datei ergibt einen leeren Stand, nie eine Ausnahme."""
    leer = {"zustand": "", "schritt": "", "meldung": "", "von": "", "nach": "", "gestartet": None, "beendet": None}
    try:
        roh = json.loads((verzeichnis() / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return leer
    if not isinstance(roh, dict):
        return leer
    s = dict(leer)
    zustand = _text(roh.get("zustand"), 20)
    s["zustand"] = zustand if zustand in ZUSTAENDE else ""
    for feld in ("schritt", "meldung", "von", "nach"):
        s[feld] = _text(roh.get(feld))
    s["gestartet"] = _zeit(roh.get("gestartet"))
    s["beendet"] = _zeit(roh.get("beendet"))
    if s["zustand"] == "laeuft" and s["gestartet"] and timezone.now() - s["gestartet"] > LAUF_VERFALL:
        s["zustand"], s["meldung"] = "fehler", s["meldung"] or "Das Update wurde nicht abgeschlossen (abgebrochen?)."
    return s


def auftrag_alter():
    """Alter der Auftragsdatei oder None, wenn keine vorliegt."""
    try:
        return timezone.now() - datetime.fromtimestamp((verzeichnis() / "auftrag").stat().st_mtime, dt_zone.utc)
    except OSError:
        return None


def laeuft():
    """Ein Update ist beauftragt (Auftrag liegt) oder wird gerade ausgefuehrt."""
    return auftrag_alter() is not None or status()["zustand"] == "laeuft"


def auftrag_haengt():
    alter = auftrag_alter()
    return alter is not None and alter > AUFTRAG_WARTEZEIT


def log_ende(zeilen=LOG_ZEILEN):
    """Letzte Zeilen von update.log (leer, wenn es noch keins gibt)."""
    try:
        text = (verzeichnis() / "update.log").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return "\n".join(text.splitlines()[-zeilen:])[-8000:]


class NichtMoeglich(Exception):
    """Der Auftrag kann nicht angelegt werden (Text ist fuer die Anzeige gedacht)."""


def anfordern(benutzername):
    """Legt die Auftragsdatei an. Raises NichtMoeglich mit einer verstaendlichen Begruendung."""
    from django.utils.translation import gettext as _
    if not aktiv():
        raise NichtMoeglich(_("Das Update per Weboberfläche ist nicht eingerichtet."))
    if not host_bereit():
        raise NichtMoeglich(_("Der Server-Dienst für das Update ist nicht eingerichtet oder der Ordner ist nicht beschreibbar."))
    if laeuft():
        raise NichtMoeglich(_("Es läuft bereits ein Update oder ein Auftrag wartet auf den Server."))
    inhalt = json.dumps({"von": _text(benutzername, 150), "zeit": timezone.now().isoformat()})
    try:
        fd = os.open(verzeichnis() / "auftrag", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    except FileExistsError:
        raise NichtMoeglich(_("Es wartet bereits ein Auftrag auf den Server."))
    except OSError as e:
        raise NichtMoeglich(_("Der Auftrag konnte nicht angelegt werden: %(fehler)s") % {"fehler": e})
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(inhalt)
    try:
        os.chmod(verzeichnis() / "auftrag", 0o666)      # der Server-Benutzer muss die Datei wieder loeschen koennen
    except OSError:
        pass
