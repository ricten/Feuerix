import tempfile
from datetime import time, timedelta
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core import datensicherung
from apps.core.forms import SicherungForm
from apps.core.models import Systemeinstellung, Verein


def _fake_dump(ziel):
    import gzip
    with gzip.open(ziel, "wb") as f:
        f.write(b"-- dump")


class DatensicherungTestBasis(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ordner = Path(self._tmp.name)
        self.medien = self.ordner / "medien"
        self.medien.mkdir()
        (self.medien / "datei.txt").write_text("hallo")
        ueb = override_settings(BACKUP_DIR=self.ordner / "backups", MEDIA_ROOT=self.medien)
        ueb.enable()
        self.addCleanup(ueb.disable)
        User = get_user_model()
        self.root = User.objects.create_superuser("root", password="pw-Test-12345")
        self.normal = User.objects.create_user("anna", password="pw-Test-12345")
        Verein.objects.create(name="V", kuerzel="v")


class AufbewahrungTests(TestCase):
    def test_je_art_bleiben_nur_die_neuesten(self):
        namen = [f"db-2026010{i}-030000.sql.gz" for i in range(1, 6)] + \
                [f"media-2026010{i}-030000.tar.gz" for i in range(1, 4)] + ["fremd.txt"]
        weg = datensicherung.zu_loeschen(namen, 2)
        self.assertCountEqual(weg, ["db-20260101-030000.sql.gz", "db-20260102-030000.sql.gz",
                                    "db-20260103-030000.sql.gz", "media-20260101-030000.tar.gz"])

    def test_zusatzsicherungen_werden_je_art_getrennt_aufbewahrt(self):
        namen = ["db-20260101-030000.sql.gz", "db-20260102-030000.sql.gz",
                 "paperless-db-20260101-023000.sql.gz", "paperless-db-20260102-023000.sql.gz",
                 "paperless-media-20260101-023000.tar.gz", "openslides-db-20260101-023000.sql.gz"]
        self.assertCountEqual(datensicherung.zu_loeschen(namen, 1), ["db-20260101-030000.sql.gz",
                              "paperless-db-20260101-023000.sql.gz"])

    def test_hilfsdateien_und_fremde_namen_sind_keine_sicherungen(self):
        for name in ("db-20260101-030000.sql.gz.part", "paperless-db-1.sql.gz", "andere-20260101-030000.sql.gz"):
            self.assertFalse(datensicherung.DATEINAME.match(name), name)

    def test_fremde_dateien_werden_nie_geloescht(self):
        self.assertEqual(datensicherung.zu_loeschen(["../etc/passwd", "notizen.txt"], 1), [])


class ZielPruefenTests(TestCase):
    def test_kein_ziel_ist_gueltig(self):
        datensicherung.ziel_pruefen(Systemeinstellung())

    def test_interne_hostnamen_abgelehnt(self):
        se = Systemeinstellung(sicherung_ziel="sftp", ziel_host="db", ziel_benutzer="u", ziel_passwort="p")
        with self.assertRaises(ValidationError):
            datensicherung.ziel_pruefen(se)

    def test_privates_netz_ist_erlaubt(self):
        se = Systemeinstellung(sicherung_ziel="sftp", ziel_host="192.168.1.20", ziel_benutzer="u", ziel_passwort="p")
        datensicherung.ziel_pruefen(se)

    def test_zugangsdaten_pflicht(self):
        with self.assertRaises(ValidationError):
            datensicherung.ziel_pruefen(Systemeinstellung(sicherung_ziel="sftp", ziel_host="nas"))

    def test_smb_braucht_freigabe(self):
        se = Systemeinstellung(sicherung_ziel="smb", ziel_host="nas", ziel_benutzer="u", ziel_passwort="p")
        with self.assertRaises(ValidationError):
            datensicherung.ziel_pruefen(se)


class FaelligTests(TestCase):
    def test_nicht_aktiv_nie_faellig(self):
        self.assertFalse(datensicherung.faellig(Systemeinstellung()))

    def test_vor_der_uhrzeit_nicht_faellig(self):
        jetzt = timezone.make_aware(timezone.datetime(2026, 10, 10, 2, 0))
        se = Systemeinstellung(sicherung_aktiv=True, sicherung_uhrzeit=time(3, 0))
        self.assertFalse(datensicherung.faellig(se, jetzt))

    def test_nach_der_uhrzeit_ohne_lauf_faellig(self):
        jetzt = timezone.make_aware(timezone.datetime(2026, 10, 10, 3, 5))
        se = Systemeinstellung(sicherung_aktiv=True, sicherung_uhrzeit=time(3, 0))
        self.assertTrue(datensicherung.faellig(se, jetzt))

    def test_heute_schon_gelaufen_nicht_erneut(self):
        jetzt = timezone.make_aware(timezone.datetime(2026, 10, 10, 15, 0))
        se = Systemeinstellung(sicherung_aktiv=True, sicherung_uhrzeit=time(3, 0),
                               sicherung_letzter_lauf=jetzt - timedelta(hours=11))
        self.assertFalse(datensicherung.faellig(se, jetzt))

    def test_gestern_gelaufen_heute_faellig(self):
        jetzt = timezone.make_aware(timezone.datetime(2026, 10, 10, 3, 30))
        se = Systemeinstellung(sicherung_aktiv=True, sicherung_uhrzeit=time(3, 0),
                               sicherung_letzter_lauf=jetzt - timedelta(hours=24))
        self.assertTrue(datensicherung.faellig(se, jetzt))


class AblaufTests(DatensicherungTestBasis):
    def test_lokale_sicherung_legt_beide_dateien_an_und_vermerkt_erfolg(self):
        with patch("apps.core.datensicherung._db_dump", side_effect=_fake_dump):
            ok, meldung = datensicherung.sicherung_ausfuehren()
        self.assertTrue(ok, meldung)
        namen = [n for n, _g, _z in datensicherung.dateien_auflisten()]
        self.assertEqual(len(namen), 2)
        self.assertTrue(any(n.startswith("db-") for n in namen) and any(n.startswith("media-") for n in namen))
        se = Systemeinstellung.laden()
        self.assertTrue(se.sicherung_letzter_ok)
        self.assertIsNotNone(se.sicherung_letzter_lauf)

    def test_medienarchiv_enthaelt_dateien_unter_media(self):
        import tarfile
        with patch("apps.core.datensicherung._db_dump", side_effect=_fake_dump):
            datensicherung.sicherung_ausfuehren()
        archiv = next(p for p in (self.ordner / "backups").iterdir() if p.name.startswith("media-"))
        with tarfile.open(archiv) as tar:
            self.assertIn("media/datei.txt", tar.getnames())

    def test_fehler_beim_dump_wird_vermerkt_und_hinterlaesst_keine_dateien(self):
        with patch("apps.core.datensicherung._db_dump", side_effect=datensicherung.SicherungFehler("kaputt")):
            ok, meldung = datensicherung.sicherung_ausfuehren()
        self.assertFalse(ok)
        self.assertIn("kaputt", meldung)
        self.assertFalse(Systemeinstellung.laden().sicherung_letzter_ok)
        self.assertEqual(datensicherung.dateien_auflisten(), [])

    def test_externer_fehler_laesst_lokale_sicherung_bestehen(self):
        se = Systemeinstellung.objects.create(sicherung_ziel="smb", ziel_host="nas", ziel_benutzer="u",
                                              ziel_passwort="p", ziel_verzeichnis="backup")
        with patch("apps.core.datensicherung._db_dump", side_effect=_fake_dump), \
                patch("apps.core.datensicherung._smb_hochladen", side_effect=OSError("NAS aus")):
            ok, meldung = datensicherung.sicherung_ausfuehren(se)
        self.assertFalse(ok)
        self.assertIn("NAS aus", meldung)
        self.assertEqual(len(datensicherung.dateien_auflisten()), 2)

    def test_externes_ziel_bekommt_beide_dateien(self):
        se = Systemeinstellung.objects.create(sicherung_ziel="smb", ziel_host="nas", ziel_benutzer="u",
                                              ziel_passwort="p", ziel_verzeichnis="backup", sicherung_aufbewahren=5)
        with patch("apps.core.datensicherung._db_dump", side_effect=_fake_dump), \
                patch("apps.core.datensicherung._smb_hochladen") as hoch:
            ok, _meldung = datensicherung.sicherung_ausfuehren(se)
        self.assertTrue(ok)
        _se, pfade, behalten = hoch.call_args.args
        self.assertEqual(len(pfade), 2)
        self.assertEqual(behalten, 5)

    def test_extern_werden_alle_lokalen_dateien_inkl_zusatzsicherungen_angeboten(self):
        sicher = self.ordner / "backups"
        sicher.mkdir()
        (sicher / "paperless-db-20260101-023000.sql.gz").write_bytes(b"x")
        (sicher / "openslides-db-20260101-023000.sql.gz").write_bytes(b"x")
        se = Systemeinstellung.objects.create(sicherung_ziel="smb", ziel_host="nas", ziel_benutzer="u",
                                              ziel_passwort="p", ziel_verzeichnis="backup")
        with patch("apps.core.datensicherung._db_dump", side_effect=_fake_dump),                 patch("apps.core.datensicherung._smb_hochladen") as hoch:
            datensicherung.sicherung_ausfuehren(se)
        namen = {p.name for p in hoch.call_args.args[1]}
        self.assertIn("paperless-db-20260101-023000.sql.gz", namen)
        self.assertIn("openslides-db-20260101-023000.sql.gz", namen)
        self.assertEqual(len(namen), 4)

    def test_smb_laedt_nur_fehlende_dateien_hoch_und_raeumt_auf(self):
        sicher = self.ordner / "backups"
        sicher.mkdir()
        a, b = sicher / "db-20260101-030000.sql.gz", sicher / "db-20260102-030000.sql.gz"
        a.write_bytes(b"1")
        b.write_bytes(b"2")
        se = Systemeinstellung(sicherung_ziel="smb", ziel_host="nas", ziel_benutzer="u", ziel_passwort="p",
                               ziel_verzeichnis="backup")
        smb = patch("apps.core.datensicherung._smb_sitzung").start()
        self.addCleanup(patch.stopall)
        sitzung = smb.return_value
        sitzung.listdir.side_effect = [["db-20260101-030000.sql.gz"], ["db-20260101-030000.sql.gz",
                                                                       "db-20260102-030000.sql.gz"]]
        from unittest.mock import mock_open
        sitzung.open_file = mock_open()
        datensicherung._smb_hochladen(se, [b, a], 1)
        geoeffnet = [c.args[0] for c in sitzung.open_file.call_args_list]
        self.assertEqual(geoeffnet, ["\\\\nas\\backup\\db-20260102-030000.sql.gz.part"])
        sitzung.rename.assert_called_once()
        sitzung.remove.assert_called_once_with("\\\\nas\\backup\\db-20260101-030000.sql.gz")

    def test_sftp_ohne_bestaetigten_hostkey_wird_nicht_hochgeladen(self):
        se = Systemeinstellung(sicherung_ziel="sftp", ziel_host="nas", ziel_benutzer="u", ziel_passwort="p")
        with self.assertRaises(datensicherung.SicherungFehler):
            datensicherung.extern_hochladen(se, [])

    def test_task_sichert_nur_wenn_faellig(self):
        from apps.core.tasks import datensicherung_faellig_task
        Systemeinstellung.objects.create(sicherung_aktiv=False)
        with patch("apps.core.datensicherung.sicherung_ausfuehren") as lauf:
            datensicherung_faellig_task()
        lauf.assert_not_called()
        se = Systemeinstellung.laden()
        se.sicherung_aktiv, se.sicherung_uhrzeit = True, time(0, 0)
        se.save()
        with patch("apps.core.datensicherung.sicherung_ausfuehren") as lauf:
            datensicherung_faellig_task()
        lauf.assert_called_once()


class DatensicherungViewTests(DatensicherungTestBasis):
    def test_nur_superuser(self):
        self.client.login(username="anna", password="pw-Test-12345")
        self.assertEqual(self.client.get(reverse("datensicherung")).status_code, 403)
        self.assertEqual(self.client.post(reverse("datensicherung_jetzt")).status_code, 403)
        self.assertEqual(self.client.post(reverse("datensicherung_test")).status_code, 403)
        self.assertEqual(self.client.get(reverse("datensicherung_download", args=["db-20260101-030000.sql.gz"])
                                         ).status_code, 403)

    def test_seite_fuer_superuser_und_navigationseintrag(self):
        self.client.login(username="root", password="pw-Test-12345")
        r = self.client.get(reverse("datensicherung"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'href="%s"' % reverse("datensicherung"))  # auch im Menue

    def test_download_liefert_datei_und_blockt_ungueltige_namen(self):
        sicher = self.ordner / "backups"
        sicher.mkdir()
        (sicher / "db-20260101-030000.sql.gz").write_bytes(b"inhalt")
        (self.ordner / "geheim.txt").write_text("geheim")
        self.client.login(username="root", password="pw-Test-12345")
        r = self.client.get(reverse("datensicherung_download", args=["db-20260101-030000.sql.gz"]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(b"".join(r.streaming_content), b"inhalt")
        self.assertIn("attachment", r["Content-Disposition"])
        for boese in ("geheim.txt", "..%2Fgeheim.txt", "db-20260101-030000.sql.gz.bak", "db-1.sql.gz"):
            self.assertEqual(self.client.get(f"/verwaltung/datensicherung/datei/{boese}/").status_code, 404, boese)

    def test_jetzt_sichern_startet_task(self):
        self.client.login(username="root", password="pw-Test-12345")
        with patch("apps.core.tasks.datensicherung_task.delay") as delay:
            r = self.client.post(reverse("datensicherung_jetzt"))
        self.assertRedirects(r, reverse("datensicherung"), fetch_redirect_response=False)
        delay.assert_called_once()

    def test_einstellungen_speichern_verschluesselt_und_behalten_passwort(self):
        self.client.login(username="root", password="pw-Test-12345")
        daten = {"sicherung_aktiv": "on", "sicherung_uhrzeit": "02:30", "sicherung_aufbewahren": "7",
                 "sicherung_ziel": "smb", "ziel_host": "192.168.1.20", "ziel_benutzer": "backup",
                 "ziel_passwort": "geheim123", "ziel_verzeichnis": "backup/feuerix"}
        r = self.client.post(reverse("datensicherung"), daten)
        self.assertRedirects(r, reverse("datensicherung"), fetch_redirect_response=False)
        se = Systemeinstellung.laden()
        self.assertEqual(se.ziel_passwort, "geheim123")
        self.assertEqual(se.sicherung_uhrzeit, time(2, 30))
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute("SELECT ziel_passwort FROM core_systemeinstellung")
            self.assertNotIn("geheim123", cur.fetchone()[0])
        daten["ziel_passwort"] = ""   # leer = behalten
        self.client.post(reverse("datensicherung"), daten)
        self.assertEqual(Systemeinstellung.laden().ziel_passwort, "geheim123")
        self.assertNotContains(self.client.get(reverse("datensicherung")), "geheim123")

    def test_formular_lehnt_internen_host_ab(self):
        form = SicherungForm({"sicherung_uhrzeit": "03:00", "sicherung_aufbewahren": "14", "sicherung_ziel": "sftp",
                              "ziel_host": "redis", "ziel_benutzer": "u", "ziel_passwort": "p"},
                             instance=Systemeinstellung())
        self.assertFalse(form.is_valid())

    def test_verbindungstest_zeigt_fehler_und_vermerkt_ihn(self):
        Systemeinstellung.objects.create(sicherung_ziel="smb", ziel_host="nas", ziel_benutzer="u",
                                         ziel_passwort="p", ziel_verzeichnis="backup")
        self.client.login(username="root", password="pw-Test-12345")
        with patch("apps.core.datensicherung._smb_sitzung", side_effect=OSError("keine Route")):
            r = self.client.post(reverse("datensicherung_test"), follow=True)
        self.assertContains(r, "keine Route")
        self.assertIn("keine Route", Systemeinstellung.laden().sicherung_letzter_test)

    def test_fehlerbanner_nur_fuer_superuser_bei_aktiver_sicherung_mit_fehler(self):
        Systemeinstellung.objects.create(sicherung_aktiv=True, sicherung_letzter_lauf=timezone.now(),
                                         sicherung_letzter_ok=False, sicherung_letzte_meldung="NAS aus",
                                         update_geprueft_am=timezone.now())
        self.client.login(username="root", password="pw-Test-12345")
        self.assertContains(self.client.get(reverse("dashboard")), "Die letzte Datensicherung ist fehlgeschlagen")
        from django.test import RequestFactory
        from apps.core.context import version
        anfrage = RequestFactory().get("/")
        anfrage.user = self.normal
        self.assertNotIn("sicherung_fehler", version(anfrage))
