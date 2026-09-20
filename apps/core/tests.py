from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import AuditLog, Rolle, Verein, Zugang, naechste_nummer
from apps.members.models import Mitglied


class MandantenTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.v1 = Verein.objects.create(name="Verein A", kuerzel="a")
        self.v2 = Verein.objects.create(name="Verein B", kuerzel="b")
        self.anna = User.objects.create_user("anna", password="pw-Test-12345")
        self.leser = User.objects.create_user("leser", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v1, user=self.anna, rolle=Rolle.objects.get(verein=self.v1, name="Vorstand"))
        Zugang.objects.create(verein=self.v1, user=self.leser, rolle=Rolle.objects.get(verein=self.v1, name="Lesebenutzer"))
        self.m1 = Mitglied.objects.create(verein=self.v1, vorname="Anton", nachname="Eins")
        self.m2 = Mitglied.objects.create(verein=self.v2, vorname="Berta", nachname="Zwei")

    def test_neuer_verein_bekommt_standarddaten(self):
        from apps.accounting.models import Buchungskategorie, Konto
        from apps.documents.models import Ordner, Vorlage
        from apps.members.models import Mitgliedsart
        self.assertTrue(Rolle.objects.filter(verein=self.v2, name="Kassenwart").exists())
        self.assertTrue(Mitgliedsart.objects.filter(verein=self.v2, name="Aktiv").exists())
        self.assertTrue(Vorlage.objects.filter(verein=self.v2, name="Einladung Mitgliederversammlung").exists())
        self.assertTrue(Ordner.objects.filter(verein=self.v2, name="Protokolle").exists())
        self.assertEqual(Konto.objects.filter(verein=self.v2).count(), 2)
        self.assertTrue(Buchungskategorie.objects.filter(verein=self.v2, name="Spenden").exists())

    def test_liste_zeigt_nur_eigenen_verein(self):
        self.client.login(username="anna", password="pw-Test-12345")
        r = self.client.get(reverse("mitglied_list"))
        self.assertContains(r, "Eins")
        self.assertNotContains(r, "Zwei")

    def test_detail_eines_fremden_vereins_ist_404(self):
        self.client.login(username="anna", password="pw-Test-12345")
        self.assertEqual(self.client.get(reverse("mitglied_detail", args=[self.m1.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("mitglied_detail", args=[self.m2.pk])).status_code, 404)

    def test_rechte_werden_geprueft(self):
        self.client.login(username="leser", password="pw-Test-12345")
        self.assertEqual(self.client.get(reverse("mitglied_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("mitglied_add")).status_code, 403)
        self.assertEqual(self.client.get(reverse("auditlog_list")).status_code, 403)

    def test_anmeldung_erforderlich(self):
        r = self.client.get(reverse("mitglied_list"))
        self.assertEqual(r.status_code, 302)

    def test_nummern_je_verein(self):
        self.assertEqual(naechste_nummer(self.v1, "X"), 1)
        self.assertEqual(naechste_nummer(self.v1, "X"), 2)
        self.assertEqual(naechste_nummer(self.v2, "X"), 1)
        self.assertEqual(self.m1.mitgliedsnummer, 1)
        self.assertEqual(self.m2.mitgliedsnummer, 1)

    def test_aenderungen_werden_protokolliert(self):
        self.m1.ort = "Dillenburg"
        self.m1.save()
        self.assertTrue(AuditLog.objects.filter(verein=self.v1, aktion="angelegt", modell="Mitglied").exists())
        log = AuditLog.objects.filter(verein=self.v1, aktion="geaendert", modell="Mitglied").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.aenderungen["Ort"][1], "Dillenburg")

    def test_iban_wird_verschluesselt_gespeichert(self):
        from django.db import connection
        self.m1.iban = "DE89370400440532013000"
        self.m1.save()
        with connection.cursor() as c:
            c.execute("SELECT iban FROM members_mitglied WHERE id = %s", [self.m1.pk])
            roh = c.fetchone()[0]
        self.assertNotIn("DE89", roh)
        self.m1.refresh_from_db()
        self.assertEqual(self.m1.iban, "DE89370400440532013000")
