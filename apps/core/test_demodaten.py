from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.events.models import Schichteinsatz, Veranstaltung
from apps.inventory.models import Verleih
from apps.members.models import Mitglied

from .models import Verein


class DemodatenTests(TestCase):
    def setUp(self):
        self.verein = Verein.objects.create(name="Testverein", kuerzel="test")

    def lauf(self, *args):
        call_command("demodaten", "--verein", "test", *args, stdout=StringIO())

    def test_szenarien_werden_angelegt(self):
        self.lauf()
        v = Veranstaltung.objects.filter(verein=self.verein)
        self.assertEqual(v.count(), 7)
        self.assertEqual({x.status for x in v}, {"abgeschlossen", "bestaetigt", "geplant", "idee", "abgesagt"})
        self.assertTrue(Schichteinsatz.objects.filter(verein=self.verein, selbst_eingetragen=True).exists())
        status = set(Verleih.objects.filter(verein=self.verein).values_list("status", flat=True))
        self.assertEqual(status, {"reserviert", "ausgegeben", "zurueckgegeben", "storniert"})
        self.assertTrue(any(x.ueberfaellig for x in Verleih.objects.filter(verein=self.verein, status="ausgegeben")))
        self.assertTrue(Verleih.objects.filter(verein=self.verein, vorgang__isnull=False, veranstaltung__isnull=True).exists())
        self.assertTrue(Verleih.objects.filter(verein=self.verein, veranstaltung__isnull=False).exists())

    def test_keine_doppelten_demodaten_ohne_flag(self):
        self.lauf()
        with self.assertRaises(CommandError):
            self.lauf()

    def test_zuruecksetzen_entfernt_und_legt_neu_an(self):
        self.lauf()
        anzahl = Verleih.objects.count()
        self.lauf("--zuruecksetzen")
        self.assertEqual(Verleih.objects.count(), anzahl)
        self.assertEqual(Veranstaltung.objects.filter(verein=self.verein).count(), 7)

    def test_zuruecksetzen_laesst_echte_daten_unberuehrt(self):
        echte = Veranstaltung.objects.create(
            verein=self.verein, titel="Echt", beginn=timezone.now(), notizen="wichtig")
        self.lauf()
        self.lauf("--zuruecksetzen")
        self.assertTrue(Veranstaltung.objects.filter(pk=echte.pk).exists())
        self.assertFalse(Mitglied.objects.exclude(notizen="[Demo]").exists())
