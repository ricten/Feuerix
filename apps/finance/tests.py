from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Rolle, Verein, Zugang
from apps.finance import services
from apps.finance.models import Beitragsjahr, Rechnung, Zahlung
from apps.members.models import Mitglied, Mitgliedsart


class BeitragsTests(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        art = Mitgliedsart.objects.get(verein=self.v, name="Aktiv")
        self.m = Mitglied.objects.create(verein=self.v, vorname="Max", nachname="Muster", mitgliedsart=art,
                                         eintrittsdatum=date(2015, 1, 1))
        self.bj = Beitragsjahr.objects.create(verein=self.v, jahr=date.today().year, faelligkeit=date(date.today().year, 12, 31),
                                              alters_stichtag=date(date.today().year, 1, 1))

    def test_rechnungslauf_und_nummern(self):
        n, _ = services.beitragsjahr_abrechnen(self.bj)
        self.assertEqual(n, 1)
        r = Rechnung.objects.get(verein=self.v)
        self.assertEqual(r.nummer, f"RE-{date.today().year}-000001")
        self.assertEqual(r.betrag, 60)
        n2, _ = services.beitragsjahr_abrechnen(self.bj)
        self.assertEqual(n2, 0)  # keine Doppelabrechnung

    def test_zahlung_setzt_status_und_ruecklastschrift(self):
        services.beitragsjahr_abrechnen(self.bj)
        r = Rechnung.objects.get(verein=self.v)
        z = Zahlung.objects.create(verein=self.v, rechnung=r, betrag=60)
        r.refresh_from_db()
        self.assertEqual(r.status, "bezahlt")
        Zahlung.objects.create(verein=self.v, rechnung=r, betrag=60, ruecklastschrift=True)
        r.refresh_from_db()
        self.assertEqual(r.status, "offen")

    def test_storno(self):
        services.beitragsjahr_abrechnen(self.bj)
        r = Rechnung.objects.get(verein=self.v, typ="beitrag")
        s = services.storniere(r)
        r.refresh_from_db()
        self.assertEqual((r.status, s.betrag), ("storniert", -60))

    def test_bankzuordnung_ueber_rechnungsnummer(self):
        from apps.finance.models import Bankumsatz
        services.beitragsjahr_abrechnen(self.bj)
        r = Rechnung.objects.get(verein=self.v)
        Bankumsatz.objects.create(verein=self.v, buchungsdatum=date.today(), betrag=60, gegenkonto_name="Max Muster",
                                  verwendungszweck=f"Beitrag {r.nummer}")
        ok, manuell = services.zuordnen(self.v)
        self.assertEqual((ok, manuell), (1, 0))
        r.refresh_from_db()
        self.assertEqual(r.status, "bezahlt")


class RueckzahlungTests(TestCase):
    """Storniert man eine bereits bezahlte Rechnung, muss sich die Rückzahlung an den Zahler buchen lassen -
    aber nur als "Rückzahlung" auf die Storno-Gegenbuchung, nicht als normale Zahlung."""

    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        art = Mitgliedsart.objects.get(verein=self.v, name="Aktiv")
        self.m = Mitglied.objects.create(verein=self.v, vorname="Max", nachname="Muster", mitgliedsart=art,
                                         eintrittsdatum=date(2015, 1, 1))
        User = get_user_model()
        self.user = User.objects.create_user("kasse", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=self.user, rolle=Rolle.objects.get(verein=self.v, name="Kassenwart"))
        self.client.login(username="kasse", password="pw-Test-12345")
        bj = Beitragsjahr.objects.create(verein=self.v, jahr=date.today().year,
                                         faelligkeit=date(date.today().year, 12, 31),
                                         alters_stichtag=date(date.today().year, 1, 1))
        services.beitragsjahr_abrechnen(bj)
        self.r = Rechnung.objects.get(verein=self.v, typ="beitrag")
        Zahlung.objects.create(verein=self.v, rechnung=self.r, betrag=60)
        self.r.refresh_from_db()
        self.s = services.storniere(self.r)

    def test_rueckzahlung_noetig_und_offen_direkt_nach_storno(self):
        self.assertTrue(self.s.rueckzahlung_noetig)
        self.assertEqual(self.s.rueckzahlung_offen, 60)

    def test_rueckzahlung_ueber_formular_moeglich(self):
        r = self.client.post(reverse("zahlung_add"), {
            "rechnung": self.s.pk, "datum": date.today(), "betrag": "60", "art": "rueckzahlung"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Zahlung.objects.filter(rechnung=self.s, art="rueckzahlung").count(), 1)
        self.s.refresh_from_db()
        self.assertEqual(self.s.rueckzahlung_offen, 0)

    def test_normale_zahlung_auf_storno_wird_abgelehnt(self):
        r = self.client.post(reverse("zahlung_add"), {
            "rechnung": self.s.pk, "datum": date.today(), "betrag": "60", "art": "ueberweisung"})
        self.assertEqual(Zahlung.objects.filter(rechnung=self.s).count(), 0)
        self.assertContains(r, "kann keine Zahlung gebucht werden")

    def test_zahlung_auf_stornierte_originalrechnung_bleibt_gesperrt(self):
        r = self.client.post(reverse("zahlung_add"), {
            "rechnung": self.r.pk, "datum": date.today(), "betrag": "60", "art": "rueckzahlung"})
        self.assertEqual(Zahlung.objects.filter(rechnung=self.r).count(), 1)  # nur die aus setUp, keine neue
        self.assertContains(r, "kann keine Zahlung gebucht werden")

    def test_rechnung_detail_zeigt_rueckzahlung_button(self):
        r = self.client.get(reverse("rechnung_detail", args=[self.s.pk]))
        self.assertContains(r, "Rückzahlung buchen")
