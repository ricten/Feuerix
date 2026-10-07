"""Prüft die Datenmigration 0011 (Ablösung des alten Standardrollen-Sets) direkt gegen die aktuellen Modelle:
Aufruf der echten Migrationsfunktionen (nicht nachgebaut), mit "historischen" Zuständen, die die Migration beim
Hochziehen bereits bestehender Installationen vorfindet."""
import importlib

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.models import Rolle, Verein, Zugang
from apps.members.models import MitgliedTag

migrationsmodul = importlib.import_module("apps.core.migrations.0011_altes_rollensystem_abloesen")


class MigrationAbloesungTests(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        # dso_anlegen (per Signal) hat die sechs DSO-Rollen + Administrator bereits angelegt; zusaetzlich legen wir
        # - wie bei einer gewachsenen Alt-Installation - die alten Standardrollen von Hand an.
        self.vorstand = Rolle.objects.create(verein=self.v, name="Vorstand", rechte=["mitglieder.view"])
        self.kassenwart_alt = Rolle.objects.create(verein=self.v, name="Kassenwart", rechte=["beitraege.view"])
        self.schriftfuehrer_alt = Rolle.objects.create(verein=self.v, name="Schriftführer", rechte=["ablage.view"])
        self.kassenpruefer_alt = Rolle.objects.create(verein=self.v, name="Kassenprüfer", rechte=["bank.view"])
        u = get_user_model().objects.create_user
        self.z_vorstand = Zugang.objects.create(verein=self.v, user=u("a"), rolle=self.vorstand)
        self.z_kassenwart = Zugang.objects.create(verein=self.v, user=u("b"), rolle=self.kassenwart_alt)
        self.z_schriftfuehrer = Zugang.objects.create(verein=self.v, user=u("c"), rolle=self.schriftfuehrer_alt)
        self.z_kassenpruefer = Zugang.objects.create(verein=self.v, user=u("d"), rolle=self.kassenpruefer_alt)

    def _migrieren(self):
        migrationsmodul.vorwaerts(django_apps, None)

    def test_vorstand_wird_zu_administrator(self):
        self._migrieren()
        self.z_vorstand.refresh_from_db()
        self.assertEqual(self.z_vorstand.rolle.name, "Administrator")
        self.assertFalse(Rolle.objects.filter(pk=self.vorstand.pk).exists())

    def test_kassenwart_und_schriftfuehrer_werden_auf_dso_rolle_umgezogen(self):
        self._migrieren()
        self.z_kassenwart.refresh_from_db()
        self.z_schriftfuehrer.refresh_from_db()
        self.assertEqual(self.z_kassenwart.rolle.name, "Kassenwart (DSO)")
        self.assertEqual(self.z_schriftfuehrer.rolle.name, "Schriftführer (DSO)")
        self.assertFalse(Rolle.objects.filter(name__in=["Kassenwart", "Schriftführer"], verein=self.v).exists())

    def test_rolle_ohne_eindeutigen_nachfolger_bleibt_unangetastet(self):
        self._migrieren()
        self.z_kassenpruefer.refresh_from_db()
        self.assertEqual(self.z_kassenpruefer.rolle_id, self.kassenpruefer_alt.pk)
        self.assertTrue(Rolle.objects.filter(pk=self.kassenpruefer_alt.pk).exists())

    def test_dso_rollen_und_administrator_werden_sichergestellt(self):
        Rolle.objects.filter(verein=self.v, name__in=["Administrator", "Kassenwart (DSO)"]).delete()
        MitgliedTag.objects.filter(verein=self.v, name__in=["Administrator", "Kassenwart"]).delete()
        self._migrieren()
        self.assertTrue(Rolle.objects.filter(verein=self.v, name="Administrator", ist_superadmin=False).exists())
        self.assertTrue(Rolle.objects.filter(verein=self.v, name="Kassenwart (DSO)").exists())
        self.assertTrue(MitgliedTag.objects.filter(verein=self.v, name="Administrator").exists())

    def test_ist_idempotent(self):
        self._migrieren()
        self._migrieren()   # darf kein zweites Mal krachen (Rolle schon weg/umgezogen)
        self.z_vorstand.refresh_from_db()
        self.assertEqual(self.z_vorstand.rolle.name, "Administrator")

    def test_administrator_rechte_entsprechen_voller_matrix(self):
        self._migrieren()
        rolle = Rolle.objects.get(verein=self.v, name="Administrator")
        self.assertTrue(all(v == "V" for v in rolle.matrix.values()))
        self.assertIn("mitglieder.delete", rolle.rechte)
