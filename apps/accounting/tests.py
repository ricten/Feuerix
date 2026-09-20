from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.accounting.models import Buchung, Buchungskategorie, Kassenbericht, Konto
from apps.accounting.services import berichtsdaten
from apps.core.models import Verein


class KassenberichtTests(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.bank = Konto.objects.get(verein=self.v, name="Bankkonto")
        self.bank.eroeffnungsbestand, self.bank.eroeffnungsdatum = Decimal("100"), date(2025, 1, 1)
        self.bank.save()
        self.ein = Buchungskategorie.objects.get(verein=self.v, name="Mitgliedsbeiträge", typ="einnahme")
        self.aus = Buchungskategorie.objects.get(verein=self.v, name="Sonstige Ausgaben", typ="ausgabe")

    def buche(self, datum, typ, betrag, kat):
        return Buchung.objects.create(verein=self.v, datum=datum, typ=typ, betrag=Decimal(betrag), konto=self.bank,
                                      kategorie=kat, text="Test")

    def test_bericht_rechnet_bestaende(self):
        self.buche(date(2025, 6, 1), "einnahme", "10", self.ein)   # Vorperiode
        self.buche(date(2026, 2, 1), "einnahme", "50", self.ein)
        self.buche(date(2026, 3, 1), "ausgabe", "20", self.aus)
        b = Kassenbericht.objects.create(verein=self.v, titel="KB 2026", von=date(2026, 1, 1), bis=date(2026, 12, 31))
        d = berichtsdaten(b)
        self.assertEqual((d["anfang"], d["einnahmen"], d["ausgaben"], d["ende"]),
                         (Decimal("110"), Decimal("50"), Decimal("20"), Decimal("140")))
        self.assertEqual(d["sphaeren"][0][3], Decimal("30"))
        self.assertEqual(d["einnahmen_gruppen"][0]["zeilen"][0][1], Decimal("50"))

    def test_belegnummern_und_sperre(self):
        x = self.buche(date(2026, 2, 1), "einnahme", "5", self.ein)
        y = self.buche(date(2026, 2, 2), "einnahme", "5", self.ein)
        self.assertEqual((x.belegnummer, y.belegnummer), ("B-2026-000001", "B-2026-000002"))
        self.assertFalse(x.gesperrt)
        Kassenbericht.objects.create(verein=self.v, titel="KB", von=date(2026, 1, 1), bis=date(2026, 12, 31),
                                     status="abgeschlossen")
        self.assertTrue(x.gesperrt)

    def test_uebernahme_aus_zahlungen_ist_idempotent(self):
        from apps.finance.models import Rechnung, Zahlung
        from apps.accounting.services import uebernehmen
        r = Rechnung.objects.create(verein=self.v, typ="beitrag", status="offen", empfaenger_name="Max", datum=date(2026, 3, 1))
        Zahlung.objects.create(verein=self.v, rechnung=r, betrag=Decimal("60"), datum=date(2026, 3, 5))
        z1 = uebernehmen(self.v, date(2026, 1, 1), date(2026, 12, 31))
        z2 = uebernehmen(self.v, date(2026, 1, 1), date(2026, 12, 31))
        self.assertEqual((z1["zahlung"], z2["zahlung"]), (1, 0))
        self.assertEqual(Buchung.objects.filter(verein=self.v, quelle="zahlung").count(), 1)
