from datetime import date

from django.test import TestCase

from apps.core.models import Verein
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
