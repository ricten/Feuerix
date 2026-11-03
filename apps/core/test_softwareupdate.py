"""Update per Weboberflaeche: Stand lesen, Auftrag anlegen, Seite und die Skripte auf dem Server (mit nachgebildetem git/docker)."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import softwareupdate
from .models import AuditLog, Systemeinstellung, Verein

WURZEL = Path(__file__).resolve().parents[2]
PW = "pw-Test-12345"


class Basis(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ordner = Path(self._tmp.name)
        ueb = override_settings(UPDATE_VERZEICHNIS=self.ordner, SOFTWAREUPDATE_PER_WEB=True)
        ueb.enable()
        self.addCleanup(ueb.disable)
        User = get_user_model()
        self.root = User.objects.create_superuser("root", password=PW)
        self.normal = User.objects.create_user("anna", password=PW)
        Verein.objects.create(name="V", kuerzel="v")

    def bereit(self):
        (self.ordner / "host_bereit").write_text("2026-11-04T00:00:00Z")

    def status_schreiben(self, **felder):
        daten = {"zustand": "ok", "schritt": "Fertig", "meldung": "Feuerix wurde aktualisiert.", "von": "1.0.0", "nach": "1.1.0",
                 "gestartet": timezone.now().isoformat(), "beendet": timezone.now().isoformat()}
        daten.update(felder)
        (self.ordner / "status.json").write_text(json.dumps(daten))


class StatusTests(Basis):
    def test_ohne_datei_leerer_stand(self):
        self.assertEqual(softwareupdate.status()["zustand"], "")

    def test_kaputte_oder_fremde_datei_ist_kein_fehler(self):
        for inhalt in ("{kaputt", "[1, 2]", "null", ""):
            (self.ordner / "status.json").write_text(inhalt)
            self.assertEqual(softwareupdate.status()["zustand"], "", inhalt)

    def test_stand_wird_gelesen_und_begrenzt(self):
        self.status_schreiben(zustand="ok", meldung="x" * 1000, von="1.0.0", nach="1.2.0")
        s = softwareupdate.status()
        self.assertEqual((s["zustand"], s["von"], s["nach"]), ("ok", "1.0.0", "1.2.0"))
        self.assertEqual(len(s["meldung"]), 300)
        self.assertIsNotNone(s["gestartet"])

    def test_unbekannter_zustand_wird_nicht_uebernommen(self):
        self.status_schreiben(zustand="<script>")
        self.assertEqual(softwareupdate.status()["zustand"], "")

    def test_haengender_lauf_gilt_als_abgebrochen(self):
        self.status_schreiben(zustand="laeuft", gestartet=(timezone.now() - timedelta(hours=3)).isoformat(), meldung="")
        s = softwareupdate.status()
        self.assertEqual(s["zustand"], "fehler")
        self.assertFalse(softwareupdate.laeuft())

    def test_laeuft_bei_status_oder_auftrag(self):
        self.assertFalse(softwareupdate.laeuft())
        self.status_schreiben(zustand="laeuft")
        self.assertTrue(softwareupdate.laeuft())
        self.status_schreiben(zustand="ok")
        (self.ordner / "auftrag").write_text("{}")
        self.assertTrue(softwareupdate.laeuft())

    def test_auftrag_haengt_nach_fuenf_minuten(self):
        auftrag = self.ordner / "auftrag"
        auftrag.write_text("{}")
        self.assertFalse(softwareupdate.auftrag_haengt())
        alt = (timezone.now() - timedelta(minutes=6)).timestamp()
        os.utime(auftrag, (alt, alt))
        self.assertTrue(softwareupdate.auftrag_haengt())

    def test_log_nur_die_letzten_zeilen(self):
        (self.ordner / "update.log").write_text("\n".join(f"zeile {i}" for i in range(200)))
        log = softwareupdate.log_ende(5)
        self.assertEqual(log.splitlines(), [f"zeile {i}" for i in range(195, 200)])
        self.assertEqual(softwareupdate.log_ende(), softwareupdate.log_ende(softwareupdate.LOG_ZEILEN))


class AnfordernTests(Basis):
    def test_legt_auftrag_an(self):
        self.bereit()
        softwareupdate.anfordern("root")
        daten = json.loads((self.ordner / "auftrag").read_text())
        self.assertEqual(daten["von"], "root")
        self.assertTrue(softwareupdate.laeuft())

    def test_nicht_eingeschaltet(self):
        self.bereit()
        with override_settings(SOFTWAREUPDATE_PER_WEB=False), self.assertRaises(softwareupdate.NichtMoeglich):
            softwareupdate.anfordern("root")
        self.assertFalse((self.ordner / "auftrag").exists())

    def test_server_dienst_nicht_eingerichtet(self):
        with self.assertRaises(softwareupdate.NichtMoeglich):
            softwareupdate.anfordern("root")
        self.assertFalse((self.ordner / "auftrag").exists())

    def test_nicht_doppelt(self):
        self.bereit()
        softwareupdate.anfordern("root")
        with self.assertRaises(softwareupdate.NichtMoeglich):
            softwareupdate.anfordern("root")

    def test_nicht_waehrend_ein_update_laeuft(self):
        self.bereit()
        self.status_schreiben(zustand="laeuft")
        with self.assertRaises(softwareupdate.NichtMoeglich):
            softwareupdate.anfordern("root")
        self.assertFalse((self.ordner / "auftrag").exists())

    def test_benutzername_wird_begrenzt(self):
        self.bereit()
        softwareupdate.anfordern("x" * 500)
        self.assertEqual(len(json.loads((self.ordner / "auftrag").read_text())["von"]), 150)


class SeiteTests(Basis):
    def test_nur_superuser(self):
        for name in ("softwareupdate", "softwareupdate_status"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 302, name)         # nicht angemeldet
        self.client.force_login(self.normal)
        for name in ("softwareupdate", "softwareupdate_status"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)
        self.assertEqual(self.client.post(reverse("softwareupdate_starten")).status_code, 403)
        self.assertFalse((self.ordner / "auftrag").exists())

    def test_starten_nur_per_post(self):
        self.client.force_login(self.root)
        self.assertEqual(self.client.get(reverse("softwareupdate_starten")).status_code, 405)

    def test_seite_nicht_eingerichtet_zeigt_anleitung_ohne_knopf(self):
        self.client.force_login(self.root)
        with override_settings(SOFTWAREUPDATE_PER_WEB=False):
            html = self.client.get(reverse("softwareupdate")).content.decode()
        self.assertIn("update_einrichten.sh", html)
        self.assertNotIn(reverse("softwareupdate_starten"), html)

    def test_seite_bereit_zeigt_knopf(self):
        self.bereit()
        self.client.force_login(self.root)
        html = self.client.get(reverse("softwareupdate")).content.decode()
        self.assertIn(reverse("softwareupdate_starten"), html)
        self.assertNotIn("update_einrichten.sh", html)

    def test_seite_zeigt_neue_version_ergebnis_und_protokoll(self):
        self.bereit()
        se = Systemeinstellung.laden()
        se.update_verfuegbare_version = "99.0.0"
        se.save()
        self.status_schreiben(zustand="fehler", meldung="Die Sicherung ist fehlgeschlagen")
        (self.ordner / "update.log").write_text("=== Feuerix-Update gestartet ===")
        self.client.force_login(self.root)
        html = self.client.get(reverse("softwareupdate")).content.decode()
        self.assertIn("99.0.0", html)
        self.assertIn("Die Sicherung ist fehlgeschlagen", html)
        self.assertIn("Feuerix-Update gestartet", html)

    def test_laufendes_update_blendet_knopf_aus_und_zeigt_schritt(self):
        self.bereit()
        self.status_schreiben(zustand="laeuft", schritt="Neues Image bauen")
        self.client.force_login(self.root)
        html = self.client.get(reverse("softwareupdate")).content.decode()
        self.assertIn("Neues Image bauen", html)
        self.assertIn('id="su-form"', html)
        self.assertRegex(html, r'id="su-form"[^>]*class="d-none"')

    def test_starten_legt_auftrag_an_und_protokolliert(self):
        self.bereit()
        self.client.force_login(self.root)
        antwort = self.client.post(reverse("softwareupdate_starten"))
        self.assertRedirects(antwort, reverse("softwareupdate"))
        self.assertTrue((self.ordner / "auftrag").exists())
        eintrag = AuditLog.objects.get(modell="Software-Update")
        self.assertEqual(eintrag.user_name, "root")
        self.assertIn("angefordert", eintrag.grund)

    def test_starten_ohne_einrichtung_meldet_fehler_und_legt_nichts_an(self):
        self.client.force_login(self.root)
        antwort = self.client.post(reverse("softwareupdate_starten"), follow=True)
        self.assertContains(antwort, "nicht eingerichtet")
        self.assertFalse((self.ordner / "auftrag").exists())
        self.assertFalse(AuditLog.objects.filter(modell="Software-Update").exists())

    def test_status_json(self):
        self.status_schreiben(zustand="laeuft", schritt="Sicherung")
        self.client.force_login(self.root)
        d = self.client.get(reverse("softwareupdate_status")).json()
        self.assertTrue(d["laeuft"])
        self.assertEqual((d["zustand"], d["schritt"]), ("laeuft", "Sicherung"))

    def test_menuepunkt_nur_fuer_superuser(self):
        from types import SimpleNamespace

        from . import einstellungen
        rechte = SimpleNamespace(darf=lambda modul, aktion: True)
        for user, erwartet in ((self.root, True), (self.normal, False)):
            namen = {zeile[3] for _t, _i, zeilen in einstellungen.sichtbare_bereiche(SimpleNamespace(user=user, rechte=rechte))
                     for zeile in zeilen}
            self.assertEqual("softwareupdate" in namen, erwartet, user)

    def test_hinweis_bei_neuer_version_verlinkt_nur_wenn_eingerichtet(self):
        se = Systemeinstellung.laden()
        se.update_verfuegbare_version = "99.0.0"
        se.update_geprueft_am = timezone.now()
        se.save()
        self.client.force_login(self.root)
        with patch("apps.core.tasks.update_pruefen_task.delay"):
            self.assertContains(self.client.get(reverse("dashboard")), "Jetzt aktualisieren …")
            with override_settings(SOFTWAREUPDATE_PER_WEB=False):
                html = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn("Eine neue Feuerix-Version ist verfügbar", html)
        self.assertNotIn("Jetzt aktualisieren …", html)


# --------------------------------------------------------------------------------------- Skripte auf dem Server
class SkriptSyntaxTests(TestCase):
    @unittest.skipUnless(shutil.which("bash"), "bash fehlt")
    def test_syntax(self):
        for name in ("update.sh", "update_einrichten.sh"):
            erg = subprocess.run(["bash", "-n", str(WURZEL / "scripts" / name)], capture_output=True, text=True)
            self.assertEqual(erg.returncode, 0, f"{name}: {erg.stderr}")

    def test_einrichtung_legt_pfad_dienst_timer_und_schalter_an(self):
        text = (WURZEL / "scripts" / "update_einrichten.sh").read_text(encoding="utf-8")
        for erwartet in ("feuerix-update.path", "feuerix-update.service", "PathExists=$DIR/update/auftrag", "chmod 0777 update",
                         "SOFTWAREUPDATE_PER_WEB=1", "update/host_bereit", "feuerix-update-auto.timer", "--nur-wenn-neu", "--entfernen"):
            self.assertIn(erwartet, text)
        self.assertNotIn("docker.sock", text)             # der Container bekommt nie Zugriff auf Docker

    def test_compose_bindet_nur_den_update_ordner_ein(self):
        text = (WURZEL / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("./update:/data/update", text)
        self.assertNotIn("docker.sock", text)
        self.assertTrue((WURZEL / "update" / ".gitkeep").exists())


@unittest.skipUnless(os.name == "posix" and shutil.which("bash") and shutil.which("flock"), "Shell-Skript: nur unter Linux")
class UpdateSkriptTests(TestCase):
    """scripts/update.sh mit nachgebildetem git, docker, curl und sleep (nichts davon laeuft echt)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.proj = Path(self._tmp.name)
        (self.proj / "scripts").mkdir()
        (self.proj / "bin").mkdir()
        (self.proj / "update").mkdir()
        shutil.copy(WURZEL / "scripts" / "update.sh", self.proj / "scripts" / "update.sh")
        (self.proj / "VERSION").write_text("1.0.0\n")
        (self.proj / ".env").write_text("WEB_PORT=8123\nALLOWED_HOSTS=verein.example.org,localhost\n")
        self.aufrufe = self.proj / "aufrufe.txt"
        log = f'echo "{{}} $*" >> "{self.aufrufe}"'
        stubs = {
            # git: rev-parse HEAD / @{u}, show origin/main:VERSION, fetch, pull, reset
            "git": f'''#!/bin/bash
{log.format("git")}
case "$*" in
  "rev-parse --abbrev-ref @{{u}}") echo origin/main ;;
  "rev-parse HEAD") echo "${{FAKE_HEAD:-aaa}}" ;;
  "rev-parse origin/main") echo "${{FAKE_UP:-bbb}}" ;;
  "show origin/main:VERSION") echo 2.0.0 ;;
  fetch*) exit ${{FAKE_FETCH_RC:-0}} ;;
  pull*) exit ${{FAKE_PULL_RC:-0}} ;;
esac
exit 0
''',
            "docker": f'''#!/bin/bash
{log.format("docker")}
case "$*" in
  *exec*backup*) exit ${{FAKE_BACKUP_RC:-0}} ;;
  *build*) exit ${{FAKE_BUILD_RC:-0}} ;;
esac
exit 0
''',
            "curl": f'''#!/bin/bash
{log.format("curl")}
exit ${{FAKE_CURL_RC:-0}}
''',
            "sleep": "#!/bin/bash\nexit 0\n",
        }
        for name, inhalt in stubs.items():
            pfad = self.proj / "bin" / name
            pfad.write_text(inhalt)
            pfad.chmod(0o755)
        (self.proj / "scripts" / "update.sh").chmod(0o755)

    def lauf(self, *args, **env):
        umgebung = {**os.environ, "PATH": f"{self.proj / 'bin'}:{os.environ['PATH']}", **{k: str(v) for k, v in env.items()}}
        return subprocess.run(["bash", str(self.proj / "scripts" / "update.sh"), *args], capture_output=True, text=True,
                              env=umgebung, cwd=str(self.proj))

    def status(self):
        return json.loads((self.proj / "update" / "status.json").read_text())

    def befehle(self):
        return self.aufrufe.read_text().splitlines() if self.aufrufe.exists() else []

    def test_erfolgreiches_update(self):
        (self.proj / "update" / "auftrag").write_text("{}")
        erg = self.lauf()
        self.assertEqual(erg.returncode, 0, erg.stdout + erg.stderr)
        self.assertEqual(self.status()["zustand"], "ok")
        self.assertEqual(self.status()["von"], "1.0.0")
        self.assertFalse((self.proj / "update" / "auftrag").exists())            # Auftrag angenommen
        befehle = "\n".join(self.befehle())
        reihenfolge = [befehle.index(x) for x in ("docker compose exec -T web /app/scripts/backup.sh", "git pull --ff-only",
                                                  "docker compose build", "docker compose up -d")]
        self.assertEqual(reihenfolge, sorted(reihenfolge))                       # Sicherung -> pull -> build -> up
        self.assertIn("Host: verein.example.org", befehle)                       # Erreichbarkeit mit dem ersten erlaubten Host
        self.assertIn("127.0.0.1:8123/login/", befehle)
        self.assertIn("Feuerix-Update gestartet", (self.proj / "update" / "update.log").read_text())

    def test_nichts_neues_meldet_aktuell_und_baut_nicht(self):
        erg = self.lauf(FAKE_HEAD="gleich", FAKE_UP="gleich")
        self.assertEqual(erg.returncode, 0)
        self.assertEqual(self.status()["zustand"], "aktuell")
        self.assertEqual(self.status()["nach"], "1.0.0")                          # kein irrefuehrendes Ziel
        self.assertNotIn("docker compose build", "\n".join(self.befehle()))

    def test_timer_modus_bleibt_still_wenn_nichts_neu_ist(self):
        erg = self.lauf("--nur-wenn-neu", FAKE_HEAD="gleich", FAKE_UP="gleich")
        self.assertEqual(erg.returncode, 0)
        self.assertEqual(erg.stdout.strip(), "")
        self.assertFalse((self.proj / "update" / "status.json").exists())        # kein Eintrag, kein Protokoll
        self.assertFalse((self.proj / "update" / "update.log").exists())

    def test_timer_modus_aktualisiert_wenn_es_etwas_neues_gibt(self):
        erg = self.lauf("--nur-wenn-neu")
        self.assertEqual(erg.returncode, 0, erg.stdout + erg.stderr)
        self.assertEqual(self.status()["zustand"], "ok")

    def test_fehlgeschlagene_sicherung_aendert_nichts(self):
        erg = self.lauf(FAKE_BACKUP_RC=1)
        self.assertEqual(erg.returncode, 1)
        self.assertEqual(self.status()["zustand"], "fehler")
        self.assertIn("nichts verändert", self.status()["meldung"])
        befehle = "\n".join(self.befehle())
        self.assertNotIn("git pull", befehle)
        self.assertNotIn("docker compose build", befehle)

    def test_fehlgeschlagener_pull_baut_nicht(self):
        erg = self.lauf(FAKE_PULL_RC=1)
        self.assertEqual(erg.returncode, 1)
        self.assertEqual(self.status()["zustand"], "fehler")
        self.assertNotIn("docker compose build", "\n".join(self.befehle()))

    def test_fehlgeschlagener_build_setzt_den_code_zurueck(self):
        erg = self.lauf(FAKE_BUILD_RC=1, FAKE_HEAD="alt123")
        self.assertEqual(erg.returncode, 1)
        self.assertEqual(self.status()["zustand"], "fehler")
        befehle = "\n".join(self.befehle())
        self.assertIn("git reset --keep alt123", befehle)                        # zurueck auf den laufenden Stand
        self.assertNotIn("docker compose up -d", befehle)                        # laufende Container bleiben unangetastet

    def test_antwortet_nach_dem_update_nicht(self):
        erg = self.lauf(FAKE_CURL_RC=1)
        self.assertEqual(erg.returncode, 1)
        self.assertEqual(self.status()["zustand"], "fehler")
        self.assertIn("antwortet nach dem Update nicht", self.status()["meldung"])
        self.assertTrue(self.status()["meldung"].rstrip().endswith("up -d."))      # Hinweis nicht abgeschnitten

    def test_fehler_beim_holen_der_neuen_version(self):
        erg = self.lauf(FAKE_FETCH_RC=1)
        self.assertEqual(erg.returncode, 1)
        self.assertIn("git fetch", self.status()["meldung"])

    def test_status_ist_gueltiges_json_auch_mit_sonderzeichen(self):
        (self.proj / "VERSION").write_text('1.0.0 "x" \\ \n')
        self.lauf(FAKE_BACKUP_RC=1)
        self.assertEqual(self.status()["zustand"], "fehler")                     # json.loads in status() wirft nicht
