"""Lizenzverwaltung (kostenlos und unbegrenzt): Die Installation muss sich innerhalb von LICENSE_TRIAL_DAYS Tagen beim
Lizenzserver (der Portalverwaltung) registrieren, sonst wird der Zugriff verweigert. Uebermittelt werden nur die Namen der
Vereine, deren Anzahl, die Kontakt-E-Mail, die Versionsnummer und die IP-Adresse (die der Server ohnehin sieht) - keine
Vereins- oder Mitgliederdaten.

* Ohne LICENSE_SERVER_URL ist die Lizenzpruefung aus (kein Zwang, nichts wird uebermittelt).
* Von der Portalverwaltung bereitgestellte Instanzen bekommen LICENSE_ID/LICENSE_TOKEN in die .env und gelten sofort als
  registriert; andere registrieren sich ueber die Seite "Lizenz" (Superadmin) oder automatisch mit LICENSE_EMAIL.
* Der Server wird taeglich per Celery Beat gefragt (Anzahl der Vereine, Sperrstatus). Ist er nicht erreichbar, bleibt
  eine einmal registrierte Installation nutzbar - nur eine ausdrueckliche Sperre durch den Betreiber blockiert."""
import json
import math
import urllib.error
import urllib.request
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import Lizenz, Verein

PRUEF_INTERVALL = timedelta(hours=20)


def aktiv():
    return bool(settings.LICENSE_SERVER_URL)


def laden():
    lz, _ = Lizenz.objects.get_or_create(pk=1)
    return lz


def zugang(lz=None):
    """(lizenz_id, token) aus der Datenbank, sonst aus der .env (vom Portal bereitgestellte Instanzen) - oder ('', '')."""
    lz = lz or laden()
    if lz.lizenz_id and lz.token:
        return str(lz.lizenz_id), lz.token
    return settings.LICENSE_ID, settings.LICENSE_TOKEN


def registriert(lz=None):
    lz = lz or laden()
    return bool(all(zugang(lz))) and lz.status != "unbekannt"


def gesperrt(lz=None):
    return (lz or laden()).status == "gesperrt"


def tage_verbleibend(lz=None):
    """Resttage der Probezeit (>= 0), None wenn schon registriert."""
    lz = lz or laden()
    if registriert(lz):
        return None
    rest = lz.erster_start + timedelta(days=settings.LICENSE_TRIAL_DAYS) - timezone.now()
    return max(0, math.ceil(rest.total_seconds() / 86400))


def blockiert():
    """-> '' (alles gut), 'gesperrt' oder 'abgelaufen'."""
    if not aktiv():
        return ""
    lz = laden()
    if gesperrt(lz):
        return "gesperrt"
    if not registriert(lz) and tage_verbleibend(lz) == 0:
        return "abgelaufen"
    return ""


def nutzdaten(email=""):
    try:
        version = (settings.BASE_DIR / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        version = ""
    return {"vereine": list(Verein.objects.filter(aktiv=True).values_list("name", flat=True)), "version": version,
            "email": email}


class LizenzFehler(Exception):
    pass


def _senden(pfad, daten):
    anfrage = urllib.request.Request(
        settings.LICENSE_SERVER_URL.rstrip("/") + pfad, data=json.dumps(daten).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(anfrage, timeout=10) as r:
            return json.loads(r.read(65536))
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise LizenzFehler("unbekannt")
        raise LizenzFehler(f"Der Lizenzserver antwortet mit Fehler {e.code}.")
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise LizenzFehler(f"Der Lizenzserver ist nicht erreichbar ({e}).")


def _uebernehmen(lz, antwort, **extra):
    lz.status = antwort.get("status") or "aktiv"
    lz.meldung = str(antwort.get("meldung") or "")[:200]
    lz.letzte_pruefung, lz.letzter_fehler = timezone.now(), ""
    for k, v in extra.items():
        setattr(lz, k, v)
    lz.save()


def registrieren(email):
    """Registriert die Installation beim Lizenzserver. Wirft LizenzFehler bei Problemen."""
    lz = laden()
    antwort = _senden("/lizenz/registrieren/", nutzdaten(email))
    if not antwort.get("lizenz_id") or not antwort.get("token"):
        raise LizenzFehler("Unerwartete Antwort des Lizenzservers.")
    _uebernehmen(lz, antwort, lizenz_id=antwort["lizenz_id"], token=antwort["token"], kontakt_email=email,
                 registriert_am=timezone.now())
    return lz


def pruefen():
    """Fragt den Lizenzserver (Anzahl Vereine, Sperrstatus). Fehler werden nur gespeichert, nie geworfen."""
    lz = laden()
    lid, token = zugang(lz)
    try:
        if not (lid and token):
            if settings.LICENSE_EMAIL:
                registrieren(settings.LICENSE_EMAIL)
            return laden()
        antwort = _senden("/lizenz/pruefen/", {**nutzdaten(lz.kontakt_email), "lizenz_id": lid, "token": token})
        _uebernehmen(lz, antwort)
    except LizenzFehler as e:
        if str(e) == "unbekannt":     # Lizenz beim Betreiber geloescht -> neu registrieren (Probezeit laeuft ab erstem Start)
            lz.status, lz.lizenz_id, lz.token = "unbekannt", None, ""
            lz.letzter_fehler = "Die Lizenz ist beim Lizenzserver nicht (mehr) bekannt - bitte neu registrieren."
        else:
            lz.letzter_fehler = str(e)[:300]
        lz.letzte_pruefung = timezone.now()
        lz.save()
    return lz


def pruefung_faellig(lz=None):
    lz = lz or laden()
    return aktiv() and (lz.letzte_pruefung is None or timezone.now() - lz.letzte_pruefung > PRUEF_INTERVALL)
