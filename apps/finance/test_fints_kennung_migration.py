"""Prüft die Datenmigration 0008 (Online-Banking-Kennung nachträglich verschlüsselt) direkt gegen die aktuellen
Modelle: Aufruf der echten Migrationsfunktionen (nicht nachgebaut) gegen eine per Roh-SQL auf Klartext gesetzte
Zeile - so, wie die Migration eine bestehende Installation mit alten, unverschlüsselten Werten vorfindet."""
import importlib

from django.db import connection
from django.test import TestCase

from apps.core.models import Verein

from .models import FinTSZugang

migrationsmodul = importlib.import_module("apps.finance.migrations.0008_alter_fintszugang_kennung")


class KennungVerschluesselungsMigrationTests(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.z = FinTSZugang.objects.create(verein=self.v, bezeichnung="Sparkasse", blz="12345678",
                                            kennung="wird-gleich-ueberschrieben",
                                            bank_url="https://banking.example.org/fints30")
        # Simuliert eine bestehende Installation: Roh-SQL statt ORM, damit das verschluesselnde Feld nicht
        # automatisch verschluesselt - genau der Zustand, den die Migration bei bestehenden Daten vorfindet.
        with connection.cursor() as c:
            c.execute("UPDATE finance_fintszugang SET kennung = %s WHERE id = %s",
                      ["mein-klartext-login", self.z.pk])

    def _roh(self):
        with connection.cursor() as c:
            c.execute("SELECT kennung FROM finance_fintszugang WHERE id = %s", [self.z.pk])
            return c.fetchone()[0]

    def test_verschluesseln_macht_rohen_wert_zu_ciphertext_orm_liest_klartext(self):
        self.assertEqual(self._roh(), "mein-klartext-login")
        migrationsmodul.verschluesseln(None, None)
        self.assertNotEqual(self._roh(), "mein-klartext-login")
        self.z.refresh_from_db()
        self.assertEqual(self.z.kennung, "mein-klartext-login")

    def test_entschluesseln_macht_vorgang_rueckgaengig(self):
        migrationsmodul.verschluesseln(None, None)
        migrationsmodul.entschluesseln(None, None)
        self.assertEqual(self._roh(), "mein-klartext-login")

    def test_entschluesseln_auf_bereits_entschluesseltem_wert_ist_unschaedlich(self):
        migrationsmodul.entschluesseln(None, None)   # noch nie verschluesselt
        self.assertEqual(self._roh(), "mein-klartext-login")

    def test_leere_kennung_wird_uebersprungen(self):
        with connection.cursor() as c:
            c.execute("UPDATE finance_fintszugang SET kennung = '' WHERE id = %s", [self.z.pk])
        migrationsmodul.verschluesseln(None, None)   # darf nicht fehlschlagen
        self.assertEqual(self._roh(), "")
