"""Zwei-Faktor-Anmeldung (TOTP nach RFC 6238) und Kontosperre nach Fehlversuchen.

* Superadmins muessen 2FA einrichten (Erzwingung in ZweiFaktorMiddleware), alle anderen koennen.
* Wird das Passwort MAX_FEHLVERSUCHE-mal falsch eingegeben und das Konto hat keine aktive 2FA, wird das Konto
  gesperrt (is_active=False + Merker). Entsperren: Management-Befehl "zweifaktor_zuruecksetzen" oder Django-Admin.
* Mit aktiver 2FA gilt weiter nur die Sperre von django-axes (Benutzername+IP); falsche 2FA-Codes bremsen sich
  selbst aus (SPERRZEIT_MIN Minuten nach MAX_FEHLVERSUCHE Fehlversuchen).
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import ZweiFaktor

MAX_FEHLVERSUCHE = 5
SPERRZEIT_MIN = 15
SCHRITT = 30
ANZAHL_CODES = 8
ISSUER = "Feuerix"


def neues_geheimnis():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(geheimnis, zeitscheibe):
    key = base64.b32decode(geheimnis + "=" * (-len(geheimnis) % 8))
    digest = hmac.new(key, struct.pack(">Q", zeitscheibe), hashlib.sha1).digest()
    o = digest[-1] & 0x0F
    return f"{(struct.unpack('>I', digest[o:o + 4])[0] & 0x7FFFFFFF) % 1000000:06d}"


def totp_pruefen(geheimnis, eingabe, nach_zeitscheibe=0, jetzt=None):
    """Gibt die passende Zeitscheibe zurueck (Toleranz +-1 Schritt) oder None. Zeitscheiben <= nach_zeitscheibe
    werden abgelehnt (kein zweites Einloesen desselben Codes)."""
    eingabe = "".join(ch for ch in (eingabe or "") if ch.isdigit())
    if len(eingabe) != 6 or not geheimnis:
        return None
    aktuell = int((jetzt if jetzt is not None else time.time()) // SCHRITT)
    for z in (aktuell - 1, aktuell, aktuell + 1):
        if z > nach_zeitscheibe and hmac.compare_digest(_code(geheimnis, z), eingabe):
            return z
    return None


def otpauth_uri(user, geheimnis):
    from urllib.parse import quote
    return (f"otpauth://totp/{quote(ISSUER)}:{quote(user.get_username())}?secret={geheimnis}"
            f"&issuer={quote(ISSUER)}&digits=6&period={SCHRITT}")


def qr_svg_uri(daten):
    import segno
    return segno.make(daten, error="m").svg_data_uri(scale=5, border=2)


def _hash_code(code):
    norm = code.strip().replace("-", "").replace(" ", "").lower()
    return hmac.new(settings.SECRET_KEY.encode(), norm.encode(), hashlib.sha256).hexdigest()


def holen(user):
    return ZweiFaktor.objects.get_or_create(user=user)[0]


def ist_aktiv(user):
    return bool(user.is_authenticated and ZweiFaktor.objects.filter(user=user, aktiv=True).exists())


def ist_pflicht(user):
    return bool(settings.ZWEIFAKTOR_PFLICHT and user.is_authenticated and user.is_superuser)


def wiederherstellungscodes_erzeugen(zf):
    """Erzeugt neue Einmalcodes, speichert nur die Hashes und gibt die Klartext-Codes (einmalig) zurueck."""
    codes = [f"{secrets.token_hex(3)}-{secrets.token_hex(3)}" for _ in range(ANZAHL_CODES)]
    zf.wiederherstellungscodes = [_hash_code(c) for c in codes]
    zf.save(update_fields=["wiederherstellungscodes"])
    return codes


def aktivieren(zf, eingabe):
    """Schliesst die Einrichtung ab, wenn der Code zum Geheimnis passt. Gibt die Wiederherstellungscodes zurueck
    oder None bei falschem Code."""
    z = totp_pruefen(zf.geheimnis, eingabe)
    if z is None:
        return None
    zf.aktiv, zf.letzte_zeitscheibe, zf.fehlversuche, zf.gesperrt = True, z, 0, False
    zf.save(update_fields=["aktiv", "letzte_zeitscheibe", "fehlversuche", "gesperrt"])
    return wiederherstellungscodes_erzeugen(zf)


def deaktivieren(zf):
    zf.aktiv, zf.geheimnis, zf.wiederherstellungscodes, zf.letzte_zeitscheibe = False, "", [], 0
    zf.save(update_fields=["aktiv", "geheimnis", "wiederherstellungscodes", "letzte_zeitscheibe"])


def code_pruefen(zf, eingabe):
    """Prueft TOTP-Code oder Wiederherstellungscode bei der Anmeldung. Gibt (ok, fehlertext) zurueck."""
    jetzt = timezone.now()
    if zf.code_gesperrt_bis and zf.code_gesperrt_bis > jetzt:
        return False, "gesperrt"
    z = totp_pruefen(zf.geheimnis, eingabe, zf.letzte_zeitscheibe)
    ok = False
    if z is not None:
        zf.letzte_zeitscheibe, ok = z, True
    else:
        h = _hash_code(eingabe or "")
        for gespeichert in zf.wiederherstellungscodes:
            if hmac.compare_digest(gespeichert, h):
                zf.wiederherstellungscodes = [c for c in zf.wiederherstellungscodes if c != gespeichert]
                ok = True
                break
    if ok:
        zf.code_fehlversuche, zf.code_gesperrt_bis = 0, None
    else:
        zf.code_fehlversuche += 1
        if zf.code_fehlversuche >= MAX_FEHLVERSUCHE:
            zf.code_fehlversuche, zf.code_gesperrt_bis = 0, jetzt + timedelta(minutes=SPERRZEIT_MIN)
    zf.save(update_fields=["letzte_zeitscheibe", "wiederherstellungscodes", "code_fehlversuche",
                           "code_gesperrt_bis"])
    return ok, ("" if ok else "falsch")


def passwort_fehlversuch(username):
    """Zaehlt einen falschen Passwortversuch; sperrt das Konto ohne aktive 2FA ab MAX_FEHLVERSUCHE."""
    from django.contrib.auth import get_user_model
    U = get_user_model()
    user = U.objects.filter(**{U.USERNAME_FIELD: username}).first() if username else None
    if user is None or not user.is_active:
        return
    zf = holen(user)
    if zf.aktiv:
        return
    zf.fehlversuche += 1
    felder = ["fehlversuche"]
    if zf.fehlversuche >= MAX_FEHLVERSUCHE:
        zf.gesperrt = True
        felder.append("gesperrt")
        user.is_active = False
        user.save(update_fields=["is_active"])
    zf.save(update_fields=felder)


def entsperren(user, zweifaktor_zuruecksetzen=False):
    zf = holen(user)
    zf.fehlversuche, zf.code_fehlversuche, zf.code_gesperrt_bis = 0, 0, None
    if zf.gesperrt:
        zf.gesperrt = False
        user.is_active = True
        user.save(update_fields=["is_active"])
    zf.save(update_fields=["fehlversuche", "gesperrt", "code_fehlversuche", "code_gesperrt_bis"])
    if zweifaktor_zuruecksetzen:
        deaktivieren(zf)
