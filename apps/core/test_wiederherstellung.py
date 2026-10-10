import gzip
import io
import os
import tarfile
import time
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.core import datensicherung
from apps.core.test_datensicherung import DatensicherungTestBasis, _fake_dump

PW = "pw-Test-12345"


def _gz(pfad, inhalt):
    with gzip.open(pfad, "wb") as f:
        f.write(inhalt)


class FakePsql:
    """Ersatz fuer subprocess.Popen(psql ...): sammelt, was auf stdin geschrieben wird."""
    letzter = None

    def __init__(self, befehl, rc=0, **kw):
        self.befehl, self.kw, self.rc = befehl, kw, rc
        self.eingabe = io.BytesIO()
        self.stdin = self
        FakePsql.letzter = self

    def write(self, daten):
        self.eingabe.write(daten)

    def close(self):
        pass

    def wait(self):
        if self.rc:
            self.kw["stderr"].write("FEHLER: kaputt".encode())
        return self.rc


class DbEinspielenTests(DatensicherungTestBasis):
    def _dump(self, inhalt):
        pfad = self.ordner / "db-20260101-030000.sql.gz"
        _gz(pfad, inhalt)
        return pfad

    def test_schema_wird_neu_angelegt_und_dump_in_einer_transaktion_eingespielt(self):
        pfad = self._dump(b"CREATE SCHEMA public;\nCREATE TABLE a (x int);\nDROP SCHEMA IF EXISTS public;\n")
        with patch("apps.core.datensicherung.subprocess.Popen", side_effect=lambda b, **kw: FakePsql(b, **kw)):
            datensicherung.db_einspielen(pfad)
        psql = FakePsql.letzter
        self.assertEqual(psql.befehl[0], "psql")
        self.assertIn("-1", psql.befehl)
        self.assertIn("ON_ERROR_STOP=1", psql.befehl)
        eingabe = psql.eingabe.getvalue()
        self.assertTrue(eingabe.startswith(b"DROP SCHEMA public CASCADE;\nCREATE SCHEMA public;\n"))
        self.assertIn(b"CREATE TABLE a (x int);", eingabe)
        self.assertNotIn(b"DROP SCHEMA IF EXISTS public;", eingabe)   # Schema-Zeilen des Dumps werden uebergangen
        self.assertEqual(eingabe.count(b"CREATE SCHEMA public;"), 1)

    def test_fehler_von_psql_wird_gemeldet(self):
        pfad = self._dump(b"SELECT 1;\n")
        with patch("apps.core.datensicherung.subprocess.Popen", side_effect=lambda b, **kw: FakePsql(b, rc=3, **kw)):
            with self.assertRaisesMessage(datensicherung.SicherungFehler, "kaputt"):
                datensicherung.db_einspielen(pfad)

    def test_fehlendes_psql(self):
        pfad = self._dump(b"SELECT 1;\n")
        with patch("apps.core.datensicherung.subprocess.Popen", side_effect=FileNotFoundError):
            with self.assertRaises(datensicherung.SicherungFehler):
                datensicherung.db_einspielen(pfad)


class MedienEinspielenTests(DatensicherungTestBasis):
    def _archiv(self, dateien):
        pfad = self.ordner / "media-20260101-030000.tar.gz"
        with tarfile.open(pfad, "w:gz") as tar:
            for name, inhalt in dateien.items():
                info = tarfile.TarInfo(name)
                info.size = len(inhalt)
                tar.addfile(info, io.BytesIO(inhalt))
        return pfad

    def test_dateien_werden_nach_media_root_entpackt_und_ueberschrieben(self):
        pfad = self._archiv({"media/ordner/a.txt": b"neu", "media/b.txt": b"bb"})
        (self.medien / "ordner").mkdir()
        (self.medien / "ordner" / "a.txt").write_text("alt")
        (self.medien / "bleibt.txt").write_text("x")
        self.assertEqual(datensicherung.medien_einspielen(pfad), 2)
        self.assertEqual((self.medien / "ordner" / "a.txt").read_text(), "neu")
        self.assertEqual((self.medien / "b.txt").read_text(), "bb")
        self.assertTrue((self.medien / "bleibt.txt").exists())

    def test_pfad_ausbruch_wird_abgewiesen(self):
        pfad = self._archiv({"media/../boese.txt": b"x"})
        with self.assertRaises(Exception):
            datensicherung.medien_einspielen(pfad)
        self.assertFalse((self.ordner / "boese.txt").exists())
        self.assertFalse((self.medien.parent / "boese.txt").exists())

    def test_fremder_aufbau_wird_abgewiesen(self):
        pfad = self._archiv({"etc/passwd": b"x"})
        with self.assertRaises(datensicherung.SicherungFehler):
            datensicherung.medien_einspielen(pfad)


class WiederherstellenTests(DatensicherungTestBasis):
    def setUp(self):
        super().setUp()
        self.sicher = self.ordner / "backups"
        self.sicher.mkdir()
        _gz(self.sicher / "db-20260101-030000.sql.gz", b"SELECT 1;")
        with tarfile.open(self.sicher / "media-20260101-030000.tar.gz", "w:gz") as tar:
            info = tarfile.TarInfo("media/x.txt")
            info.size = 2
            tar.addfile(info, io.BytesIO(b"ok"))

    def _lauf(self, **kw):
        with patch("apps.core.datensicherung._db_dump", side_effect=_fake_dump), \
                patch("apps.core.datensicherung.db_einspielen", **kw.get("db", {})) as db, \
                patch("django.core.management.call_command") as migrate:
            erg = datensicherung.wiederherstellen("db-20260101-030000.sql.gz", kw.get("media", ""), "root")
        return erg, db, migrate

    def test_erfolg_sichert_vorher_spielt_ein_migriert_und_entfernt_sperre(self):
        (ok, meldung), db, migrate = self._lauf(media="media-20260101-030000.tar.gz")
        self.assertTrue(ok, meldung)
        db.assert_called_once()
        migrate.assert_called_once()
        self.assertEqual((self.medien / "x.txt").read_text(), "ok")
        self.assertGreaterEqual(len(datensicherung.dateien_auflisten()), 4)   # 2 vorhandene + Sicherung davor
        self.assertFalse((self.sicher / datensicherung.SPERRDATEI).exists())
        erg = datensicherung.letzte_wiederherstellung()
        self.assertTrue(erg["ok"])
        self.assertEqual(erg["benutzer"], "root")

    def test_ohne_vorherige_sicherung_wird_nichts_veraendert(self):
        with patch("apps.core.datensicherung._db_dump", side_effect=datensicherung.SicherungFehler("kein pg_dump")), \
                patch("apps.core.datensicherung.db_einspielen") as db:
            ok, meldung = datensicherung.wiederherstellen("db-20260101-030000.sql.gz")
        self.assertFalse(ok)
        db.assert_not_called()
        self.assertIn("nichts wurde verändert", meldung)
        self.assertFalse((self.sicher / datensicherung.SPERRDATEI).exists())

    def test_fehler_beim_einspielen_wird_gemeldet_und_sperre_aufgehoben(self):
        (ok, meldung), _db, migrate = self._lauf(db={"side_effect": datensicherung.SicherungFehler("kaputt")})
        self.assertFalse(ok)
        self.assertIn("kaputt", meldung)
        self.assertIn("davor", meldung)
        migrate.assert_not_called()
        self.assertFalse((self.sicher / datensicherung.SPERRDATEI).exists())
        self.assertFalse(datensicherung.letzte_wiederherstellung()["ok"])

    def test_unbekannte_oder_unpassende_dateien(self):
        for db, media in (("db-20990101-030000.sql.gz", ""), ("media-20260101-030000.tar.gz", ""),
                          ("db-20260101-030000.sql.gz", "db-20260101-030000.sql.gz"),
                          ("db-20260101-030000.sql.gz", "media-20990101-030000.tar.gz")):
            with patch("apps.core.datensicherung.db_einspielen") as einspielen:
                ok, _m = datensicherung.wiederherstellen(db, media)
            self.assertFalse(ok, (db, media))
            einspielen.assert_not_called()

    def test_parallele_wiederherstellung_wird_abgewiesen(self):
        (self.sicher / datensicherung.SPERRDATEI).write_text("x")
        with patch("apps.core.datensicherung.db_einspielen") as db:
            ok, _m = datensicherung.wiederherstellen("db-20260101-030000.sql.gz")
        self.assertFalse(ok)
        db.assert_not_called()


class WartungsmodusTests(DatensicherungTestBasis):
    def test_waehrend_der_sperre_antwortet_jede_seite_mit_503(self):
        sicher = self.ordner / "backups"
        sicher.mkdir()
        sperre = sicher / datensicherung.SPERRDATEI
        sperre.write_text("x")
        r = self.client.get("/")
        self.assertEqual(r.status_code, 503)
        self.assertContains(r, "Wartung", status_code=503)
        self.assertEqual(r["Retry-After"], "30")

    def test_ohne_sperre_normal(self):
        self.assertNotEqual(self.client.get("/").status_code, 503)

    def test_alte_sperre_hebt_sich_auf(self):
        sicher = self.ordner / "backups"
        sicher.mkdir()
        sperre = sicher / datensicherung.SPERRDATEI
        sperre.write_text("x")
        alt = time.time() - datensicherung.SPERRE_MAX_SEKUNDEN - 60
        os.utime(sperre, (alt, alt))
        self.assertFalse(datensicherung.wartung_aktiv())
        self.assertNotEqual(self.client.get("/").status_code, 503)


class WiederherstellenViewTests(DatensicherungTestBasis):
    def setUp(self):
        super().setUp()
        self.sicher = self.ordner / "backups"
        self.sicher.mkdir()
        _gz(self.sicher / "db-20260101-030000.sql.gz", b"x")
        self.url = reverse("datensicherung_wiederherstellen")
        self.daten = {"db": "db-20260101-030000.sql.gz", "media": "", "passwort": PW,
                      "bestaetigung": "WIEDERHERSTELLEN"}

    def _post(self, **aend):
        self.client.login(username="root", password=PW)
        with patch("apps.core.tasks.wiederherstellung_task.delay") as delay:
            r = self.client.post(self.url, {**self.daten, **aend})
        self.assertRedirects(r, reverse("datensicherung"), fetch_redirect_response=False)
        return delay

    def test_nur_superuser(self):
        self.client.login(username="anna", password=PW)
        self.assertEqual(self.client.post(self.url, self.daten).status_code, 403)
        self.assertEqual(self.client.post(reverse("datensicherung_hochladen")).status_code, 403)

    def test_mit_passwort_und_bestaetigung_wird_gestartet(self):
        delay = self._post()
        delay.assert_called_once_with("db-20260101-030000.sql.gz", "", "root")

    def test_falsches_passwort_oder_bestaetigung_startet_nichts(self):
        self._post(passwort="falsch").assert_not_called()
        self._post(bestaetigung="ja").assert_not_called()
        self._post(bestaetigung="").assert_not_called()

    def test_ungueltige_dateinamen_starten_nichts(self):
        self._post(db="../x.sql.gz").assert_not_called()
        self._post(db="db-20990101-030000.sql.gz").assert_not_called()
        self._post(media="../../etc/passwd").assert_not_called()

    def test_nicht_waehrend_laufender_wiederherstellung(self):
        (self.sicher / datensicherung.SPERRDATEI).write_text("x")
        self.client.login(username="root", password=PW)
        # die Sperre schaltet die ganze Anwendung ab -> Wartungsseite statt Weiterleitung
        self.assertEqual(self.client.post(self.url, self.daten).status_code, 503)

    def test_seite_zeigt_formular_und_ergebnis(self):
        datensicherung._wiederherstellung_vermerken(True, "Alles gut", "db-x", "", "root")
        self.client.login(username="root", password=PW)
        r = self.client.get(reverse("datensicherung"))
        self.assertContains(r, "db-20260101-030000.sql.gz")
        self.assertContains(r, "Alles gut")
        self.assertContains(r, "WIEDERHERSTELLEN")


class HochladenTests(DatensicherungTestBasis):
    def _hoch(self, name, inhalt):
        self.client.login(username="root", password=PW)
        return self.client.post(reverse("datensicherung_hochladen"),
                                {"dateien": SimpleUploadedFile(name, inhalt)}, follow=True)

    def test_gueltige_datei_wird_abgelegt(self):
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as g:
            g.write(b"-- dump")
        r = self._hoch("db-20260101-030000.sql.gz", buf.getvalue())
        self.assertContains(r, "Hochgeladen")
        self.assertTrue((self.ordner / "backups" / "db-20260101-030000.sql.gz").is_file())
        self.assertFalse(list((self.ordner / "backups").glob("*.part")))

    def test_ungueltiger_name_inhalt_oder_doppelt_wird_abgelehnt(self):
        r = self._hoch("..evil.txt", b"x")
        self.assertContains(r, "Ungültiger Dateiname")
        r = self._hoch("db-20260101-030000.sql.gz", b"kein gzip")
        self.assertContains(r, "kein gzip")
        self.assertEqual(datensicherung.dateien_auflisten(), [])
        self.assertFalse(list((self.ordner / "backups").glob("*.part")))
        sicher = self.ordner / "backups"
        _gz(sicher / "db-20260101-030000.sql.gz", b"x")
        r = self._hoch("db-20260101-030000.sql.gz", gzip.compress(b"y"))
        self.assertContains(r, "existiert bereits")
