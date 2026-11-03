"""Der Befehl für den Sicherheitstest - und gleich die Mandanten- und Rechtegrenzen, die er prüfen lässt."""
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse

from apps.members.models import Mitglied

from .models import Verein

User = get_user_model()


def vorbereiten(**kw):
    ausgabe = StringIO()
    call_command("sicherheitstest_vorbereiten", testinstanz=True, stdout=ausgabe, **kw)
    return ausgabe.getvalue()


def passwort_aus(ausgabe, name):
    for zeile in ausgabe.splitlines():
        teile = zeile.split()
        if teile and teile[0] == name:
            return teile[1]
    raise AssertionError(name)


class BefehlTests(TestCase):
    def test_ohne_bestaetigung_passiert_nichts(self):
        with self.assertRaises(CommandError):
            call_command("sicherheitstest_vorbereiten", stdout=StringIO())
        self.assertFalse(Verein.objects.exists())

    def test_weigert_sich_bei_fremden_vereinen(self):
        Verein.objects.create(name="Echter Verein", kuerzel="echt")
        with self.assertRaises(CommandError):
            vorbereiten()
        self.assertFalse(User.objects.filter(username__startswith="pt_").exists())

    def test_legt_konten_an_und_kann_zurueckgesetzt_werden(self):
        vorbereiten()
        self.assertEqual(User.objects.filter(username__startswith="pt_").count(), 4)
        with self.assertRaises(CommandError):
            vorbereiten()                    # ohne --zuruecksetzen nicht doppelt
        vorbereiten(zuruecksetzen=True)
        self.assertEqual(User.objects.filter(username__startswith="pt_").count(), 4)
        self.assertEqual(Verein.objects.count(), 2)
        self.assertEqual(Mitglied.objects.count(), 6)      # keine Doppelten nach dem Zurücksetzen


class GrenzenTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ausgabe = vorbereiten()
        cls.a = Verein.objects.get(kuerzel="pentest-a")
        cls.b = Verein.objects.get(kuerzel="pentest-b")

    def anmelden(self, name):
        self.assertTrue(self.client.login(username=name, password=passwort_aus(self.ausgabe, name)))

    def test_anderer_verein_sieht_fremdes_mitglied_nicht(self):
        fremd = Mitglied.objects.filter(verein=self.a).first()
        self.anmelden("pt_admin_b")
        for name in ("mitglied_detail", "mitglied_edit", "mitglied_delete"):
            self.assertEqual(self.client.get(reverse(name, args=[fremd.pk])).status_code, 404, name)
        self.assertEqual(self.client.get(reverse("mitglied_edit", args=[fremd.pk])).status_code, 404)
        liste = self.client.get(reverse("mitglied_list")).content.decode()
        self.assertNotIn("-A", liste)        # Nachnamen der Mitglieder aus Verein A enden auf "-A"
        self.assertIn("-B", liste)

    def test_nur_lesen_kann_nicht_aendern(self):
        eigen = Mitglied.objects.filter(verein=self.a).first()
        self.anmelden("pt_lesen_a")
        self.assertEqual(self.client.get(reverse("mitglied_detail", args=[eigen.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("mitglied_edit", args=[eigen.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("mitglied_delete", args=[eigen.pk])).status_code, 403)
        self.assertTrue(Mitglied.objects.filter(pk=eigen.pk).exists())

    def test_kassenkonto_sieht_keine_mitglieder(self):
        self.anmelden("pt_kasse_a")
        self.assertEqual(self.client.get(reverse("mitglied_list")).status_code, 403)
