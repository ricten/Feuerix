from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Rolle, Verein, Zugang
from apps.members import importer
from apps.members.models import Mitglied

CSV = ("Vorname;Nachname;Geburtstag;E-Mail;Mitgliedsart;PLZ\n"
       "Max;Muster;01.02.1980;m@example.org;Aktiv;35683\n").encode("utf-8")


class ImportTests(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")

    def test_testlauf_speichert_nichts(self):
        b = importer.importieren(self.v, "m.csv", CSV, testlauf=True)
        self.assertEqual((b["neu"], len(b["fehler"])), (1, 0))
        self.assertEqual(Mitglied.objects.filter(verein=self.v).count(), 0)

    def test_import_und_aktualisierung(self):
        b = importer.importieren(self.v, "m.csv", CSV, testlauf=False)
        self.assertEqual(b["neu"], 1)
        m = Mitglied.objects.get(verein=self.v)
        self.assertEqual((m.mitgliedsnummer, m.email, str(m.mitgliedsart)), (1, "m@example.org", "Aktiv"))
        update = "Mitgliedsnummer;Vorname;Nachname;Ort;E-Mail\n1;Max;Muster;Dillenburg;\n".encode("utf-8")
        b = importer.importieren(self.v, "u.csv", update, testlauf=False)
        self.assertEqual((b["neu"], b["aktualisiert"]), (0, 1))
        m.refresh_from_db()
        self.assertEqual(m.ort, "Dillenburg")
        self.assertEqual(m.email, "m@example.org")  # leere Zelle überschreibt nichts

    def test_fehlerhafte_zeile_wird_gemeldet(self):
        daten = "Vorname;Nachname;Geburtstag\nEva;;01.01.1990\nAnna;Beispiel;kein-datum\nOk;Person;\n".encode("utf-8")
        b = importer.importieren(self.v, "f.csv", daten, testlauf=False)
        self.assertEqual(b["neu"], 1)
        self.assertEqual(len(b["fehler"]), 2)

    def test_unbekannte_mitgliedsart(self):
        daten = "Vorname;Nachname;Mitgliedsart\nA;B;Gibtsnicht\n".encode("utf-8")
        self.assertEqual(len(importer.importieren(self.v, "a.csv", daten, testlauf=True)["fehler"]), 1)
        b = importer.importieren(self.v, "a.csv", daten, testlauf=False, neu_anlegen=True)
        self.assertEqual((b["neu"], len(b["fehler"])), (1, 0))

    def test_datenbankfehler_in_einer_zeile_bricht_import_nicht_ab(self):
        """Ein echter Fehler beim Speichern (z. B. defekter FIELD_ENCRYPTION_KEY) darf nur diese Zeile
        überspringen - nachfolgende, gültige Zeilen müssen trotzdem gespeichert werden."""
        daten = "Vorname;Nachname\nFehler;Fall\nOk;Person\n".encode("utf-8")
        orig_save = Mitglied.save

        def kaputt_bei_fehler(self, *a, **kw):
            if self.vorname == "Fehler":
                raise ValueError("simulierter Datenbankfehler")
            return orig_save(self, *a, **kw)

        with patch.object(Mitglied, "save", kaputt_bei_fehler):
            b = importer.importieren(self.v, "x.csv", daten, testlauf=False)
        self.assertEqual(b["neu"], 1)
        self.assertEqual(len(b["fehler"]), 1)
        self.assertTrue(Mitglied.objects.filter(verein=self.v, nachname="Person").exists())
        self.assertFalse(Mitglied.objects.filter(verein=self.v, nachname="Fall").exists())


class SelbstdienstTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.vorstand = User.objects.create_user("vorstand", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=self.vorstand, rolle=Rolle.objects.get(verein=self.v, name="Vorstand"))
        self.m = Mitglied.objects.create(verein=self.v, vorname="Erika", nachname="Muster", email="erika@example.org")

    def test_zugang_einrichten_sendet_mail_und_verknuepft_benutzer(self):
        self.client.login(username="vorstand", password="pw-Test-12345")
        r = self.client.post(reverse("mitglied_zugang_einrichten", args=[self.m.pk]))
        self.assertRedirects(r, reverse("mitglied_detail", args=[self.m.pk]))
        self.m.refresh_from_db()
        self.assertEqual(self.m.benutzer.username, "erika@example.org")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.m.benutzer.username, mail.outbox[0].body)

    def test_ohne_email_keine_einrichtung(self):
        m2 = Mitglied.objects.create(verein=self.v, vorname="Ohne", nachname="Mail")
        self.client.login(username="vorstand", password="pw-Test-12345")
        self.client.post(reverse("mitglied_zugang_einrichten", args=[m2.pk]))
        m2.refresh_from_db()
        self.assertIsNone(m2.benutzer_id)

    def test_lesebenutzer_darf_keinen_zugang_einrichten(self):
        User = get_user_model()
        leser = User.objects.create_user("leser", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=leser, rolle=Rolle.objects.get(verein=self.v, name="Lesebenutzer"))
        self.client.login(username="leser", password="pw-Test-12345")
        r = self.client.post(reverse("mitglied_zugang_einrichten", args=[self.m.pk]))
        self.assertEqual(r.status_code, 403)

    def test_mitglied_kann_eigene_daten_pflegen(self):
        self.client.login(username="vorstand", password="pw-Test-12345")
        self.client.post(reverse("mitglied_zugang_einrichten", args=[self.m.pk]))
        self.m.refresh_from_db()
        passwort, username = self.m.selbstdienst_initialpasswort, self.m.benutzer.username
        self.client.logout()
        self.assertTrue(self.client.login(username=username, password=passwort))
        self.assertRedirects(self.client.get(reverse("nach_login")), reverse("mein_konto"))
        r = self.client.post(reverse("mein_konto"), {"strasse": "Neue Str. 1", "plz": "35683", "ort": "Dillenburg",
                                                      "email": "erika@example.org", "telefon": "", "mobil": "",
                                                      "kontoinhaber": "", "iban": "", "bic": ""})
        self.assertRedirects(r, reverse("mein_konto"))
        self.m.refresh_from_db()
        self.assertEqual(self.m.strasse, "Neue Str. 1")

    def test_gesperrter_zugang_kann_sich_nicht_mehr_anmelden(self):
        self.client.login(username="vorstand", password="pw-Test-12345")
        self.client.post(reverse("mitglied_zugang_einrichten", args=[self.m.pk]))
        self.m.refresh_from_db()
        passwort, username = self.m.selbstdienst_initialpasswort, self.m.benutzer.username
        self.client.post(reverse("mitglied_zugang_sperren", args=[self.m.pk]))
        self.client.logout()
        self.assertFalse(self.client.login(username=username, password=passwort))


class VerwaltungszugangTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.admin = User.objects.create_user("admin", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=self.admin, rolle=Rolle.objects.get(verein=self.v, name="Superadministrator"))
        self.m = Mitglied.objects.create(verein=self.v, vorname="Erika", nachname="Muster", email="erika@example.org")

    def test_verwaltungszugang_einrichten(self):
        self.client.login(username="admin", password="pw-Test-12345")
        kassenwart = Rolle.objects.get(verein=self.v, name="Kassenwart")
        r = self.client.post(reverse("mitglied_verwaltungszugang_einrichten", args=[self.m.pk]), {"rolle": kassenwart.pk})
        self.assertRedirects(r, reverse("mitglied_detail", args=[self.m.pk]))
        self.m.refresh_from_db()
        self.assertIsNotNone(self.m.benutzer_id)
        zugang = Zugang.objects.get(verein=self.v, user=self.m.benutzer)
        self.assertEqual(zugang.rolle, kassenwart)
        self.assertEqual(len(mail.outbox), 1)

    def test_bestehendes_selbstdienst_konto_wird_wiederverwendet(self):
        self.client.login(username="admin", password="pw-Test-12345")
        self.client.post(reverse("mitglied_zugang_einrichten", args=[self.m.pk]))
        self.m.refresh_from_db()
        vorhandener_benutzer_id = self.m.benutzer_id
        kassenwart = Rolle.objects.get(verein=self.v, name="Kassenwart")
        self.client.post(reverse("mitglied_verwaltungszugang_einrichten", args=[self.m.pk]), {"rolle": kassenwart.pk})
        self.m.refresh_from_db()
        self.assertEqual(self.m.benutzer_id, vorhandener_benutzer_id)

    def test_ohne_email_kein_verwaltungszugang(self):
        m2 = Mitglied.objects.create(verein=self.v, vorname="Ohne", nachname="Mail")
        self.client.login(username="admin", password="pw-Test-12345")
        r = self.client.get(reverse("mitglied_verwaltungszugang_einrichten", args=[m2.pk]))
        self.assertRedirects(r, reverse("mitglied_detail", args=[m2.pk]))
        m2.refresh_from_db()
        self.assertIsNone(m2.benutzer_id)
