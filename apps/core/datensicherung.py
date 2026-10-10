"""Datensicherung: Datenbank-Dump + Medienarchiv lokal ablegen und optional auf ein externes Ziel (SFTP oder
SMB-Freigabe, z. B. NAS) kopieren. Dateinamen wie in scripts/backup.sh (db-JJJJMMTT-HHMMSS.sql.gz,
media-JJJJMMTT-HHMMSS.tar.gz), damit scripts/restore.sh auch diese Sicherungen einspielen kann.

Das externe Ziel darf bewusst im privaten Netz liegen (ein NAS tut das fast immer) - deshalb wird hier NICHT
pruefe_oeffentliche_adresse() verwendet. Eingestellt werden kann es nur von Superadministratoren (Serverbetrieb);
interne Docker-Dienste (db, redis, ...) sind trotzdem ausgeschlossen."""
import base64
import gzip
import hashlib
import io
import json
import os
import posixpath
import re
import shutil
import subprocess
import tarfile
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext as _

from .util import INTERNE_HOSTNAMEN

# Feuerix selbst: db-/media-; die Zusatz-Sicherungen von Paperless-ngx und OpenSlides legt scripts/backup-zusatz.sh
# (laeuft auf dem Host, da diese Dienste in eigenen Compose-Stacks laufen) mit denselben Zeitstempeln ins Volume.
DATEINAME = re.compile(r"^(db|media|paperless-db|paperless-data|paperless-media|openslides-db)"
                       r"-\d{8}-\d{6}\.(sql|tar)\.gz$")
STANDARD_PORT = {"sftp": 22, "smb": 445}


class SicherungFehler(Exception):
    pass


def sicherungsordner():
    ordner = Path(settings.BACKUP_DIR)
    ordner.mkdir(parents=True, exist_ok=True)
    return ordner


def dateien_auflisten():
    """Lokale Sicherungsdateien, neueste zuerst: [(name, groesse_bytes, zeitpunkt)]."""
    ordner = Path(settings.BACKUP_DIR)
    if not ordner.is_dir():
        return []
    ergebnis = []
    for p in ordner.iterdir():
        if DATEINAME.match(p.name) and p.is_file():
            st = p.stat()
            ergebnis.append((p.name, st.st_size, datetime.fromtimestamp(st.st_mtime, timezone.get_current_timezone())))
    return sorted(ergebnis, key=lambda e: e[0], reverse=True)


def zu_loeschen(namen, behalten):
    """Aus den Dateinamen (alle Sicherungsarten gemischt) die zu loeschenden bestimmen: je Art (db, media,
    paperless-db, ...) bleiben die `behalten` neuesten (Zeitstempel steckt im Namen, also sortiert der Name
    chronologisch)."""
    je_art = {}
    for n in namen:
        if (m := DATEINAME.match(n)):
            je_art.setdefault(m.group(1), []).append(n)
    loeschen = []
    for gleiche in je_art.values():
        loeschen += sorted(gleiche, reverse=True)[max(behalten, 1):]
    return loeschen


def datei_pfad(name):
    """Absoluter Pfad einer Sicherungsdatei fuer den Download - None bei ungueltigem Namen/fehlender Datei."""
    if not DATEINAME.match(name or ""):
        return None
    pfad = Path(settings.BACKUP_DIR) / name
    return pfad if pfad.is_file() else None


# --- Erstellen -------------------------------------------------------------------------------------------------

def _db_dump(ziel):
    db = settings.DATABASES["default"]
    env = {**os.environ, "PGPASSWORD": db.get("PASSWORD") or ""}
    befehl = ["pg_dump", "--clean", "--if-exists", "-h", str(db.get("HOST") or ""), "-p", str(db.get("PORT") or "5432"),
              "-U", str(db.get("USER") or ""), str(db["NAME"])]
    try:
        with gzip.open(ziel, "wb") as out:
            prozess = subprocess.Popen(befehl, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            shutil.copyfileobj(prozess.stdout, out)
            fehler = prozess.stderr.read().decode(errors="replace").strip()
            if prozess.wait() != 0:
                raise SicherungFehler(_("Datenbank-Dump fehlgeschlagen: %(fehler)s") % {"fehler": fehler[:300]})
    except FileNotFoundError:
        ziel.unlink(missing_ok=True)
        raise SicherungFehler(_("pg_dump ist nicht installiert."))
    except Exception:
        ziel.unlink(missing_ok=True)
        raise


def _medien_archiv(ziel):
    with tarfile.open(ziel, "w:gz") as tar:
        medien = Path(settings.MEDIA_ROOT)
        if medien.is_dir():
            tar.add(medien, arcname="media")


def lokal_sichern():
    """Legt Datenbank-Dump und Medienarchiv im Sicherungsordner ab, gibt die beiden Pfade zurueck."""
    stempel = timezone.localtime().strftime("%Y%m%d-%H%M%S")
    ordner = sicherungsordner()
    db_pfad, medien_pfad = ordner / f"db-{stempel}.sql.gz", ordner / f"media-{stempel}.tar.gz"
    _db_dump(db_pfad)
    try:
        _medien_archiv(medien_pfad)
    except Exception:
        db_pfad.unlink(missing_ok=True)
        medien_pfad.unlink(missing_ok=True)
        raise
    return [db_pfad, medien_pfad]


def lokal_aufraeumen(behalten):
    ordner = Path(settings.BACKUP_DIR)
    for name in zu_loeschen([p.name for p in ordner.iterdir()], behalten):
        (ordner / name).unlink(missing_ok=True)


# --- Externe Ziele ---------------------------------------------------------------------------------------------

def ziel_pruefen(se):
    """ValidationError, wenn die Zieleinstellungen unvollstaendig oder unzulaessig sind (fuer Formular und Lauf)."""
    if not se.sicherung_ziel:
        return
    host = (se.ziel_host or "").strip().lower()
    if not host:
        raise ValidationError(_("Bitte Server / NAS angeben."))
    if host in INTERNE_HOSTNAMEN:
        raise ValidationError(_("Diese Adresse ist nicht erlaubt (interner Hostname)."))
    if not se.ziel_benutzer:
        raise ValidationError(_("Bitte einen Benutzernamen angeben."))
    if not (se.ziel_passwort or se.ziel_schluessel):
        raise ValidationError(_("Bitte ein Passwort oder (nur SFTP) einen privaten Schlüssel angeben."))
    if se.sicherung_ziel == "smb" and not (se.ziel_verzeichnis or "").strip("/\\ "):
        raise ValidationError(_("Bei SMB bitte Freigabe (und ggf. Unterordner) angeben, z. B. backup/feuerix."))


def _port(se):
    return se.ziel_port or STANDARD_PORT[se.sicherung_ziel]


def _sftp_verbinden(se):
    """Oeffnet eine SFTP-Verbindung (paramiko) und prueft den Hostschluessel gegen den gespeicherten
    Fingerabdruck. Ohne gespeicherten Fingerabdruck wird die Verbindung nur aufgebaut, wenn `se` zum Testen
    verwendet wird (Rueckgabe des gesehenen Fingerabdrucks, der Aufrufer speichert ihn)."""
    import paramiko
    transport = paramiko.Transport((se.ziel_host.strip(), _port(se)))
    transport.banner_timeout = 15
    try:
        transport.start_client(timeout=20)
        schluessel = transport.get_remote_server_key()
        fingerabdruck = "SHA256:" + base64.b64encode(hashlib.sha256(schluessel.asbytes()).digest()).decode().rstrip("=")
        if se.ziel_hostkey and se.ziel_hostkey.strip() != fingerabdruck:
            raise SicherungFehler(_("Der Hostschlüssel des Servers hat sich geändert (erwartet %(erwartet)s, "
                                    "erhalten %(erhalten)s). Verbindung aus Sicherheitsgründen abgebrochen.")
                                  % {"erwartet": se.ziel_hostkey, "erhalten": fingerabdruck})
        if se.ziel_schluessel:
            pkey = paramiko.PKey.from_private_key(io.StringIO(se.ziel_schluessel),
                                                  password=se.ziel_passwort or None)
            transport.auth_publickey(se.ziel_benutzer, pkey)
        else:
            transport.auth_password(se.ziel_benutzer, se.ziel_passwort)
        return paramiko.SFTPClient.from_transport(transport), transport, fingerabdruck
    except Exception:
        transport.close()
        raise


def _sftp_verzeichnis(sftp, pfad):
    """Legt das Zielverzeichnis samt fehlender Elternordner an."""
    aktuell = "/" if pfad.startswith("/") else ""
    for teil in [t for t in pfad.split("/") if t]:
        aktuell = posixpath.join(aktuell, teil)
        try:
            sftp.stat(aktuell)
        except OSError:
            sftp.mkdir(aktuell)


def _sftp_hochladen(se, pfade, behalten):
    sftp, transport, _fp = _sftp_verbinden(se)
    try:
        ziel = (se.ziel_verzeichnis or ".").strip() or "."
        _sftp_verzeichnis(sftp, ziel)
        vorhanden = set(sftp.listdir(ziel))
        for p in pfade:
            if p.name in vorhanden:
                continue
            ziel_datei = posixpath.join(ziel, p.name)
            sftp.put(str(p), ziel_datei + ".part")   # erst unter Hilfsnamen, damit nie halbe Dateien "vorhanden" sind
            sftp.rename(ziel_datei + ".part", ziel_datei)
        for name in zu_loeschen(sftp.listdir(ziel), behalten):
            sftp.remove(posixpath.join(ziel, name))
    finally:
        sftp.close()
        transport.close()


def _smb_basis(se):
    teile = [t for t in (se.ziel_verzeichnis or "").replace("\\", "/").split("/") if t]
    return "\\\\" + se.ziel_host.strip() + "\\" + "\\".join(teile)


def _smb_sitzung(se):
    import smbclient
    smbclient.register_session(se.ziel_host.strip(), username=se.ziel_benutzer, password=se.ziel_passwort,
                               port=_port(se), connection_timeout=20)
    return smbclient


def _smb_hochladen(se, pfade, behalten):
    smb = _smb_sitzung(se)
    basis = _smb_basis(se)
    try:
        smb.makedirs(basis, exist_ok=True)
        vorhanden = set(smb.listdir(basis))
        for p in pfade:
            if p.name in vorhanden:
                continue
            with open(p, "rb") as quelle, smb.open_file(basis + "\\" + p.name + ".part", mode="wb") as ziel:
                shutil.copyfileobj(quelle, ziel, 1024 * 1024)
            smb.rename(basis + "\\" + p.name + ".part", basis + "\\" + p.name)
        for name in zu_loeschen(smb.listdir(basis), behalten):
            smb.remove(basis + "\\" + name)
    finally:
        smb.reset_connection_cache()


def extern_hochladen(se, pfade):
    ziel_pruefen(se)
    if se.sicherung_ziel == "sftp":
        if not se.ziel_hostkey:
            raise SicherungFehler(_("Hostschlüssel noch nicht bestätigt - bitte zuerst „Verbindung testen“."))
        _sftp_hochladen(se, pfade, se.sicherung_aufbewahren)
    elif se.sicherung_ziel == "smb":
        _smb_hochladen(se, pfade, se.sicherung_aufbewahren)


def verbindung_testen(se):
    """Prueft das externe Ziel (Anmelden, Zielverzeichnis anlegen, Testdatei schreiben/loeschen). Gibt eine
    Erfolgsmeldung zurueck; bei SFTP wird ein noch unbekannter Hostschluessel in `se.ziel_hostkey` eingetragen
    (Aufrufer speichert `se`). Wirft SicherungFehler/ValidationError/Verbindungsfehler bei Problemen."""
    ziel_pruefen(se)
    if not se.sicherung_ziel:
        raise SicherungFehler(_("Es ist kein externes Ziel ausgewählt."))
    testname = f".feuerix-test-{uuid.uuid4().hex[:8]}"
    if se.sicherung_ziel == "sftp":
        sftp, transport, fingerabdruck = _sftp_verbinden(se)
        try:
            ziel = (se.ziel_verzeichnis or ".").strip() or "."
            _sftp_verzeichnis(sftp, ziel)
            pfad = posixpath.join(ziel, testname)
            with sftp.open(pfad, "wb") as f:
                f.write(b"ok")
            sftp.remove(pfad)
        finally:
            sftp.close()
            transport.close()
        neu = not se.ziel_hostkey
        se.ziel_hostkey = fingerabdruck
        return _("Verbindung erfolgreich.") + (
            " " + _("Hostschlüssel übernommen: %(fp)s - bitte mit dem Fingerabdruck Ihres Servers vergleichen.")
            % {"fp": fingerabdruck} if neu else "")
    smb = _smb_sitzung(se)
    basis = _smb_basis(se)
    try:
        smb.makedirs(basis, exist_ok=True)
        with smb.open_file(basis + "\\" + testname, mode="wb") as f:
            f.write(b"ok")
        smb.remove(basis + "\\" + testname)
    finally:
        smb.reset_connection_cache()
    return _("Verbindung erfolgreich.")


# --- Ablauf ----------------------------------------------------------------------------------------------------

def sicherung_ausfuehren(se=None):
    """Komplette Sicherung: lokal erstellen, aufraeumen, ggf. extern kopieren; Ergebnis in den
    Systemeinstellungen vermerken. Gibt (ok, meldung) zurueck."""
    from .models import Systemeinstellung
    se = se or Systemeinstellung.laden()
    teile, ok = [], True
    try:
        neue = lokal_sichern()
        teile.append(_("Lokal gesichert: %(namen)s") % {"namen": ", ".join(p.name for p in neue)})
        lokal_aufraeumen(se.sicherung_aufbewahren)
        # Alle lokalen Sicherungsdateien (auch die Zusatz-Sicherungen von Paperless/OpenSlides) und auch
        # aeltere, die nach einem frueheren Fehlschlag noch nicht extern liegen.
        pfade = [Path(settings.BACKUP_DIR) / n for n, _g, _z in dateien_auflisten()]
    except Exception as e:
        return _ergebnis(se, False, _("Lokale Sicherung fehlgeschlagen: %(fehler)s") % {"fehler": e})
    if se.sicherung_ziel:
        try:
            extern_hochladen(se, pfade)
            teile.append(_("Extern kopiert (%(ziel)s: %(host)s).") % {
                "ziel": dict(Systemeinstellung.ZIEL_ARTEN)[se.sicherung_ziel], "host": se.ziel_host})
        except Exception as e:
            ok = False
            teile.append(_("Kopie auf das externe Ziel fehlgeschlagen: %(fehler)s") % {"fehler": e})
    return _ergebnis(se, ok, " ".join(str(t) for t in teile))


def _ergebnis(se, ok, meldung):
    se.sicherung_letzter_lauf = timezone.now()
    se.sicherung_letzter_ok = ok
    se.sicherung_letzte_meldung = str(meldung)[:2000]
    se.save()
    return ok, se.sicherung_letzte_meldung


def faellig(se, jetzt=None):
    """True, wenn die automatische Sicherung heute zur eingestellten Uhrzeit faellig war und noch nicht lief."""
    if not se.sicherung_aktiv:
        return False
    jetzt = timezone.localtime(jetzt or timezone.now())
    geplant = jetzt.replace(hour=se.sicherung_uhrzeit.hour, minute=se.sicherung_uhrzeit.minute, second=0,
                            microsecond=0)
    return jetzt >= geplant and (se.sicherung_letzter_lauf is None or se.sicherung_letzter_lauf < geplant)


# --- Wiederherstellung ------------------------------------------------------------------------------------------
# Laeuft im Celery-Worker (nicht im Webprozess). Waehrenddessen steht eine Sperrdatei im Sicherungsordner, und die
# WartungMiddleware beantwortet alle Seitenaufrufe mit "Wartung" - sonst wuerden Anfragen mitten in den Austausch
# der Datenbank geraten. Das Ergebnis steht in einer JSON-Datei neben den Sicherungen, nicht in der Datenbank, da
# die ja gerade ersetzt wird.
SPERRDATEI = "wiederherstellung.lock"
ERGEBNISDATEI = "wiederherstellung.json"
SPERRE_MAX_SEKUNDEN = 2 * 60 * 60   # eine liegengebliebene Sperre (Absturz) hebt sich nach 2 Stunden selbst auf
_SCHEMA_ZEILEN = {b"CREATE SCHEMA public;", b"DROP SCHEMA IF EXISTS public;", b"DROP SCHEMA public;"}


def wartung_aktiv():
    sperre = Path(settings.BACKUP_DIR) / SPERRDATEI
    try:
        return timezone.now().timestamp() - sperre.stat().st_mtime < SPERRE_MAX_SEKUNDEN
    except OSError:
        return False


def letzte_wiederherstellung():
    try:
        return json.loads((Path(settings.BACKUP_DIR) / ERGEBNISDATEI).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def ist_gzip(pfad):
    with open(pfad, "rb") as f:
        return f.read(2) == b"\x1f\x8b"


def sicherung_speichern(upload):
    """Legt eine hochgeladene Sicherungsdatei im Sicherungsordner ab (nur gueltige Namen, keine Ueberschreibung,
    nur gzip-Inhalt). Gibt den Dateinamen zurueck oder wirft ValidationError."""
    name = Path(upload.name).name
    if not DATEINAME.match(name):
        raise ValidationError(_("Ungültiger Dateiname - erwartet z. B. db-20261010-030000.sql.gz oder "
                                "media-20261010-030000.tar.gz."))
    ziel = sicherungsordner() / name
    if ziel.exists():
        raise ValidationError(_("Eine Sicherung mit diesem Namen existiert bereits."))
    hilfe = ziel.with_name(name + ".part")
    try:
        with open(hilfe, "wb") as out:
            for chunk in upload.chunks():
                out.write(chunk)
        if not ist_gzip(hilfe):
            raise ValidationError(_("Die Datei ist keine gültige Sicherung (kein gzip-Archiv)."))
        hilfe.replace(ziel)
    finally:
        hilfe.unlink(missing_ok=True)
    return name


def db_einspielen(pfad):
    """Spielt einen Datenbank-Dump ein: das Schema `public` wird verworfen und neu angelegt, danach der Dump in
    EINER Transaktion (psql -1, ON_ERROR_STOP) - bei jedem Fehler bleibt die bisherige Datenbank unveraendert.
    Funktioniert auch mit Dumps ohne --clean (aeltere Sicherungen)."""
    db = settings.DATABASES["default"]
    env = {**os.environ, "PGPASSWORD": db.get("PASSWORD") or ""}
    befehl = ["psql", "-q", "-1", "-v", "ON_ERROR_STOP=1", "-h", str(db.get("HOST") or ""),
              "-p", str(db.get("PORT") or "5432"), "-U", str(db.get("USER") or ""), "-d", str(db["NAME"]),
              "-f", "-"]
    with tempfile.TemporaryFile() as fehlerdatei:
        try:
            prozess = subprocess.Popen(befehl, env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                       stderr=fehlerdatei)
        except FileNotFoundError:
            raise SicherungFehler(_("psql ist nicht installiert."))
        try:
            prozess.stdin.write(b"DROP SCHEMA public CASCADE;\nCREATE SCHEMA public;\n")
            with gzip.open(pfad, "rb") as quelle:
                for zeile in quelle:
                    if zeile.strip() not in _SCHEMA_ZEILEN:   # das Schema legt die Wiederherstellung selbst an
                        prozess.stdin.write(zeile)
        except BrokenPipeError:
            pass   # psql ist wegen eines Fehlers vorzeitig beendet - Meldung unten
        finally:
            try:
                prozess.stdin.close()
            except BrokenPipeError:
                pass
        rc = prozess.wait()
        fehlerdatei.seek(0)
        fehler = fehlerdatei.read().decode(errors="replace").strip()
    if rc != 0:
        raise SicherungFehler(_("Einspielen der Datenbank fehlgeschlagen (die bisherige Datenbank blieb "
                                "unverändert): %(fehler)s") % {"fehler": fehler[-400:]})


def medien_einspielen(pfad):
    """Entpackt ein Medienarchiv (Wurzel `media/`) nach MEDIA_ROOT; vorhandene Dateien werden ueberschrieben,
    nicht im Archiv enthaltene bleiben liegen. Gibt die Zahl der Dateien zurueck."""
    ziel = Path(settings.MEDIA_ROOT)
    ziel.mkdir(parents=True, exist_ok=True)
    anzahl = 0
    with tarfile.open(pfad, "r:gz") as tar:
        for eintrag in tar.getmembers():
            name = eintrag.name.removeprefix("./").rstrip("/")
            if name == "media":
                continue
            if not name.startswith("media/"):
                raise SicherungFehler(_("Unerwarteter Aufbau des Medienarchivs: %(name)s") % {"name": eintrag.name})
            eintrag.name = name[len("media/"):]
            tar.extract(eintrag, ziel, filter="data")   # "data": blockt absolute Pfade, .. und Geraetedateien
            anzahl += eintrag.isfile()
    return anzahl


def _wiederherstellung_vermerken(ok, meldung, db_name, media_name, benutzer):
    ergebnis = {"zeit": timezone.now().isoformat(), "ok": ok, "meldung": str(meldung), "db": db_name,
                "media": media_name or "", "benutzer": benutzer}
    (sicherungsordner() / ERGEBNISDATEI).write_text(json.dumps(ergebnis, ensure_ascii=False), encoding="utf-8")


def wiederherstellen(db_name="", media_name="", benutzer=""):
    """Spielt Datenbank-Sicherung (und optional Medienarchiv) ein. Vorher wird automatisch eine Sicherung des
    aktuellen Stands angelegt; schlaegt die fehl, wird NICHTS veraendert. Gibt (ok, meldung) zurueck."""
    from django.core.cache import cache
    from django.core.management import call_command
    from django.db import connections
    db_pfad = datei_pfad(db_name) if db_name.startswith("db-") else None
    media_pfad = datei_pfad(media_name) if media_name.startswith("media-") else None
    if db_pfad is None:
        return False, _("Die Datenbank-Sicherung wurde nicht gefunden.")
    if media_name and media_pfad is None:
        return False, _("Die Medien-Sicherung wurde nicht gefunden.")
    if wartung_aktiv():
        return False, _("Es läuft bereits eine Wiederherstellung.")
    sperre = sicherungsordner() / SPERRDATEI
    sperre.write_text(benutzer or "-", encoding="utf-8")
    try:
        try:
            vorher = lokal_sichern()
        except Exception as e:
            ok, meldung = False, _("Abgebrochen, nichts wurde verändert - die Sicherung des aktuellen Stands "
                                   "schlug fehl: %(fehler)s") % {"fehler": e}
        else:
            namen = ", ".join(p.name for p in vorher)
            try:
                db_einspielen(db_pfad)
                teile = [_("Datenbank aus %(name)s wiederhergestellt.") % {"name": db_name}]
                if media_pfad:
                    teile.append(_("%(n)d Dateien aus %(name)s wiederhergestellt.")
                                 % {"n": medien_einspielen(media_pfad), "name": media_name})
                connections.close_all()
                call_command("migrate", interactive=False, verbosity=0)   # Sicherung aus aelterer Version
                cache.clear()
                teile.append(_("Der Stand vor der Wiederherstellung wurde gesichert (%(namen)s).")
                             % {"namen": namen})
                ok, meldung = True, " ".join(str(t) for t in teile)
            except Exception as e:
                ok, meldung = False, _("Wiederherstellung fehlgeschlagen: %(fehler)s Der Stand davor liegt als "
                                       "%(namen)s vor.") % {"fehler": e, "namen": namen}
    finally:
        sperre.unlink(missing_ok=True)
    _wiederherstellung_vermerken(ok, meldung, db_name, media_name, benutzer)
    return ok, str(meldung)
