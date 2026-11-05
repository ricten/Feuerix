"""scripts/backup.sh (laeuft im Container mit /bin/sh = dash): ein fehlgeschlagener Dump darf nie als Sicherung durchgehen."""
import gzip
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from django.test import TestCase

SKRIPT = Path(__file__).resolve().parents[2] / "scripts" / "backup.sh"


@unittest.skipUnless(os.name == "posix" and shutil.which("sh") and shutil.which("gzip") and shutil.which("tar"), "Shell-Skript: nur unter Linux")
class BackupSkriptTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        wurzel = Path(self._tmp.name)
        self.daten = wurzel / "daten"
        self.ziel = self.daten / "backups"
        (self.daten / "media").mkdir(parents=True)
        self.ziel.mkdir()
        (self.daten / "media" / "beleg.txt").write_text("Beleg")
        (wurzel / "bin").mkdir()
        self.bin = wurzel / "bin"

    def pg_dump(self, rc=0, ausgabe="-- PostgreSQL database dump\nSELECT 1;\n"):
        stub = self.bin / "pg_dump"
        stub.write_text(f"#!/bin/sh\nprintf '%s' '{ausgabe}'\nexit {rc}\n")
        stub.chmod(0o755)

    def lauf(self):
        umgebung = {**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}", "BACKUP_DIR": str(self.ziel), "DATA_DIR": str(self.daten),
                    "POSTGRES_PASSWORD": "x", "POSTGRES_HOST": "db", "POSTGRES_USER": "u", "POSTGRES_DB": "d"}
        return subprocess.run(["sh", str(SKRIPT)], capture_output=True, text=True, env=umgebung)

    def dateien(self):
        return sorted(p.name for p in self.ziel.iterdir())

    def test_erfolg_schreibt_dump_und_medien(self):
        self.pg_dump()
        erg = self.lauf()
        self.assertEqual(erg.returncode, 0, erg.stderr)
        db = [n for n in self.dateien() if n.startswith("db-")]
        self.assertEqual(len(db), 1)
        self.assertIn("SELECT 1;", gzip.open(self.ziel / db[0], "rt").read())
        self.assertEqual(len([n for n in self.dateien() if n.startswith("media-")]), 1)
        self.assertFalse([n for n in self.dateien() if n.endswith(".tmp")])         # keine Reste

    def test_fehlgeschlagener_dump_ist_ein_fehler_und_hinterlaesst_nichts(self):
        self.pg_dump(rc=1, ausgabe="")
        erg = self.lauf()
        self.assertNotEqual(erg.returncode, 0)
        self.assertIn("pg_dump", erg.stderr)
        self.assertEqual(self.dateien(), [])                  # weder leere "Sicherung" noch Medienarchiv noch Temp-Datei

    def test_teilweiser_dump_mit_fehlercode_zaehlt_nicht(self):
        self.pg_dump(rc=1, ausgabe="-- halber Dump")
        self.assertNotEqual(self.lauf().returncode, 0)
        self.assertEqual(self.dateien(), [])

    def test_leerer_dump_ist_ein_fehler(self):
        self.pg_dump(rc=0, ausgabe="")
        erg = self.lauf()
        self.assertNotEqual(erg.returncode, 0)
        self.assertIn("leer", erg.stderr)
        self.assertEqual(self.dateien(), [])

    def test_gute_alte_sicherungen_bleiben_bei_fehlern_unangetastet(self):
        for i in range(1, 15):
            for name in (f"db-202601{i:02d}-030000.sql.gz", f"media-202601{i:02d}-030000.tar.gz"):
                (self.ziel / name).write_bytes(b"alt")
        vorher = self.dateien()
        self.pg_dump(rc=1, ausgabe="")
        self.assertNotEqual(self.lauf().returncode, 0)
        self.assertEqual(self.dateien(), vorher)              # die Aufbewahrung raeumt nur nach einer gelungenen Sicherung auf

    def test_aufbewahrung_behaelt_nach_erfolg_die_letzten_14(self):
        for i in range(1, 17):
            p = self.ziel / f"db-202601{i:02d}-030000.sql.gz"
            p.write_bytes(b"alt")
            os.utime(p, (1_700_000_000 + i, 1_700_000_000 + i))
        self.pg_dump()
        self.assertEqual(self.lauf().returncode, 0)
        db = [n for n in self.dateien() if n.startswith("db-")]
        self.assertEqual(len(db), 14)
        self.assertNotIn("db-20260101-030000.sql.gz", db)     # die aeltesten sind weg
