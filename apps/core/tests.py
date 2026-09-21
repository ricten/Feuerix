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

    def test_detail_zeigt_many_to_many_feld(self):
        from apps.members.models import Abteilung
        a = Abteilung.objects.create(verein=self.v1, name="Löschzug 1")
        self.m1.abteilungen.add(a)
        self.client.login(username="anna", password="pw-Test-12345")
        r = self.client.get(reverse("mitglied_detail", args=[self.m1.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Löschzug 1")

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

    def test_logo_bleibt_beim_speichern_ohne_neue_datei_erhalten(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.anna.is_superuser = True  # "Verwaltung" (Vereinseinstellungen) hat regulär nur der Superadmin
        self.anna.save()
        self.client.login(username="anna", password="pw-Test-12345")
        logo = SimpleUploadedFile("logo.png", b"\x89PNG\r\n\x1a\n" + b"0" * 20, content_type="image/png")
        self.v1.logo = logo
        self.v1.save()
        self.assertTrue(self.v1.logo)
        daten = {"name": self.v1.name, "zahlungsziel_tage": 14, "uebungsleiter_freibetrag": "3300",
                "ehrenamts_freibetrag": "960", "akzentfarbe": "#1F4E79", "bescheid_art": "freistellung"}
        r = self.client.post(reverse("verein_einstellungen"), daten)
        self.assertEqual(r.status_code, 302)
        self.v1.refresh_from_db()
        self.assertTrue(self.v1.logo)

    def test_briefkopf_pdf_wird_erzeugt(self):
        from apps.core.pdf import brief_pdf
        self.v1.unterschrift_1 = "Max Mustermann, 1. Vorsitzender"
        self.v1.akzentfarbe = "#C0392B"
        pdf = brief_pdf(self.v1, ["Herr", "Max Mustermann", "Musterweg 1", "12345 Musterstadt"], "Testbrief")
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_ungueltige_akzentfarbe_faellt_auf_standard_zurueck(self):
        from apps.core.pdf import brief_pdf
        self.v1.akzentfarbe = "keine-farbe"
        pdf = brief_pdf(self.v1, ["Empfänger"], "Testbrief")
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_fusslinie_verwendet_eigene_akzentfarbe(self):
        from reportlab.lib import colors
        from apps.core.pdf import _akzentfarbe_fuss
        self.v1.akzentfarbe = "#EA580C"
        self.v1.akzentfarbe_fuss = "#005199"
        self.assertEqual(_akzentfarbe_fuss(self.v1), colors.HexColor("#005199"))

    def test_fusslinie_faellt_ohne_eigene_farbe_auf_hauptfarbe_zurueck(self):
        from reportlab.lib import colors
        from apps.core.pdf import _akzentfarbe_fuss
        self.v1.akzentfarbe = "#EA580C"
        self.v1.akzentfarbe_fuss = ""
        self.assertEqual(_akzentfarbe_fuss(self.v1), colors.HexColor("#EA580C"))
