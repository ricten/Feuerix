from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.accounting import erechnung
from apps.accounting.models import Buchung, Buchungskategorie, Kassenbericht, Konto
from apps.accounting.services import berichtsdaten
from apps.core.models import Rolle, Verein, Zugang

UBL_XRECHNUNG = b"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
        xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
        xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:ID>RE-2026-000123</cbc:ID>
  <cbc:IssueDate>2026-03-15</cbc:IssueDate>
  <cbc:DocumentCurrencyCode>EUR</cbc:DocumentCurrencyCode>
  <cac:AccountingSupplierParty><cac:Party><cac:PartyLegalEntity>
    <cbc:RegistrationName>Beispiel Lieferant GmbH</cbc:RegistrationName>
  </cac:PartyLegalEntity></cac:Party></cac:AccountingSupplierParty>
  <cac:LegalMonetaryTotal>
    <cbc:TaxInclusiveAmount currencyID="EUR">238.00</cbc:TaxInclusiveAmount>
    <cbc:PayableAmount currencyID="EUR">238.00</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
</Invoice>"""

CII_ZUGFERD = b"""<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
        xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
        xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100">
  <rsm:ExchangedDocument>
    <ram:ID>ZF-2026-9987</ram:ID>
    <ram:IssueDateTime><udt:DateTimeString format="102">20260320</udt:DateTimeString></ram:IssueDateTime>
  </rsm:ExchangedDocument>
  <rsm:SupplyChainTradeTransaction>
    <ram:ApplicableHeaderTradeAgreement>
      <ram:SellerTradeParty><ram:Name>Muster Handwerk e.K.</ram:Name></ram:SellerTradeParty>
    </ram:ApplicableHeaderTradeAgreement>
    <ram:ApplicableHeaderTradeSettlement>
      <ram:InvoiceCurrencyCode>EUR</ram:InvoiceCurrencyCode>
      <ram:SpecifiedTradeSettlementHeaderMonetarySummation>
        <ram:TaxInclusiveAmount>595.00</ram:TaxInclusiveAmount>
        <ram:DuePayableAmount>595.00</ram:DuePayableAmount>
      </ram:SpecifiedTradeSettlementHeaderMonetarySummation>
    </ram:ApplicableHeaderTradeSettlement>
  </rsm:SupplyChainTradeTransaction>
</rsm:CrossIndustryInvoice>"""


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

    def test_uebernahme_bucht_rueckzahlung_als_ausgabe(self):
        from apps.finance.models import Rechnung, Zahlung
        from apps.accounting.services import uebernehmen
        s = Rechnung.objects.create(verein=self.v, typ="storno", status="verbucht", empfaenger_name="Max",
                                    datum=date(2026, 3, 1))
        Zahlung.objects.create(verein=self.v, rechnung=s, betrag=Decimal("60"), art="rueckzahlung",
                               datum=date(2026, 3, 5))
        uebernehmen(self.v, date(2026, 1, 1), date(2026, 12, 31))
        b = Buchung.objects.get(verein=self.v, quelle="zahlung")
        self.assertEqual((b.typ, b.betrag, b.kategorie.name), ("ausgabe", Decimal("60"), "Erstattungen / Rückzahlungen"))


class ERechnungParserTests(TestCase):
    def test_ubl_xrechnung_wird_gelesen(self):
        d = erechnung.parse_rechnung(erechnung.xml_aus_datei("re.xml", UBL_XRECHNUNG))
        self.assertEqual(d["nummer"], "RE-2026-000123")
        self.assertEqual(d["datum"], date(2026, 3, 15))
        self.assertEqual(d["betrag"], Decimal("238.00"))
        self.assertEqual(d["verkaeufer"], "Beispiel Lieferant GmbH")

    def test_cii_zugferd_wird_gelesen(self):
        d = erechnung.parse_rechnung(erechnung.xml_aus_datei("re.xml", CII_ZUGFERD))
        self.assertEqual(d["nummer"], "ZF-2026-9987")
        self.assertEqual(d["datum"], date(2026, 3, 20))
        self.assertEqual(d["betrag"], Decimal("595.00"))
        self.assertEqual(d["verkaeufer"], "Muster Handwerk e.K.")

    def test_zugferd_pdf_mit_eingebettetem_xml_wird_gelesen(self):
        from pypdf import PdfWriter
        import io
        w = PdfWriter()
        w.add_blank_page(width=200, height=200)
        w.add_attachment("factur-x.xml", CII_ZUGFERD)
        buf = io.BytesIO()
        w.write(buf)
        xml_bytes = erechnung.xml_aus_datei("rechnung.pdf", buf.getvalue())
        d = erechnung.parse_rechnung(xml_bytes)
        self.assertEqual(d["nummer"], "ZF-2026-9987")

    def test_unlesbare_datei_gibt_none(self):
        self.assertIsNone(erechnung.xml_aus_datei("foto.jpg", b"\xff\xd8\xff\x00binaerdaten"))
        self.assertIsNone(erechnung.parse_rechnung(b"das ist kein xml"))


class ERechnungImportTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.user = User.objects.create_user("kasse", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=self.user, rolle=Rolle.objects.get(verein=self.v, name="Kassenwart"))
        self.client.login(username="kasse", password="pw-Test-12345")

    def test_import_xml_erstellt_ausgefuellte_buchung(self):
        datei = SimpleUploadedFile("rechnung.xml", UBL_XRECHNUNG, content_type="application/xml")
        r = self.client.post(reverse("erechnung_importieren"), {"datei": datei})
        b = Buchung.objects.get(verein=self.v)
        self.assertRedirects(r, reverse("buchung_edit", args=[b.pk]))
        self.assertEqual((b.typ, b.betrag, b.datum), ("ausgabe", Decimal("238.00"), date(2026, 3, 15)))
        self.assertIn("RE-2026-000123", b.text)
        self.assertIn("Beispiel Lieferant GmbH", b.text)
        self.assertTrue(b.beleg.name.endswith("rechnung.xml"))

    def test_import_ohne_lesbare_erechnung_legt_trotzdem_beleg_an(self):
        datei = SimpleUploadedFile("sonstiges.xml", b"<Sonstiges/>", content_type="application/xml")
        r = self.client.post(reverse("erechnung_importieren"), {"datei": datei}, follow=True)
        b = Buchung.objects.get(verein=self.v)
        self.assertEqual(b.betrag, Decimal("0.01"))
        self.assertTrue(b.beleg)
        self.assertContains(r, "keine lesbare E-Rechnung")

    def test_ohne_konto_zeigt_fehler_statt_absturz(self):
        Konto.objects.filter(verein=self.v).delete()
        datei = SimpleUploadedFile("rechnung.xml", UBL_XRECHNUNG, content_type="application/xml")
        r = self.client.post(reverse("erechnung_importieren"), {"datei": datei}, follow=True)
        self.assertEqual(Buchung.objects.filter(verein=self.v).count(), 0)
        self.assertContains(r, "mindestens ein Konto anlegen")


class BelegAblageTests(TestCase):
    """Belege (Buchung.beleg) waren bisher nur ueber das Kassenbuch erreichbar, nicht in der allgemeinen
    Ablage (Schriftverkehr) auffindbar - ueber "Beleg in Ablage uebernehmen" lassen sie sich dort einordnen."""

    def setUp(self):
        from apps.documents.models import Ablagedokument

        self.Ablagedokument = Ablagedokument
        User = get_user_model()
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.user = User.objects.create_user("kasse", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=self.user, rolle=Rolle.objects.get(verein=self.v, name="Kassenwart"))
        self.client.login(username="kasse", password="pw-Test-12345")
        konto = Konto.objects.filter(verein=self.v, aktiv=True).first()
        kategorie = Buchungskategorie.objects.filter(verein=self.v, typ="ausgabe").first()
        self.b = Buchung.objects.create(
            verein=self.v, datum=date(2026, 3, 1), typ="ausgabe", betrag=Decimal("42.00"), konto=konto,
            kategorie=kategorie, text="Testbeleg",
            beleg=SimpleUploadedFile("quittung.pdf", b"%PDF-1.4 Inhalt", content_type="application/pdf"))

    def test_knopf_erscheint_nur_solange_nicht_abgelegt(self):
        r = self.client.get(reverse("buchung_detail", args=[self.b.pk]))
        self.assertContains(r, "Beleg in Ablage übernehmen")

    def test_beleg_ablegen_erstellt_ablagedokument(self):
        r = self.client.post(reverse("buchung_beleg_ablegen", args=[self.b.pk]), follow=True)
        self.b.refresh_from_db()
        self.assertIsNotNone(self.b.ablage_id)
        doc = self.Ablagedokument.objects.get(pk=self.b.ablage_id)
        self.assertEqual(doc.kategorie, "beleg")
        self.assertEqual(doc.datum, date(2026, 3, 1))
        self.assertTrue(doc.datei.name.endswith("quittung.pdf"))
        self.assertContains(r, "Beleg in der Ablage abgelegt")
        self.assertContains(r, "Beleg in Ablage gespeichert")

    def test_doppeltes_ablegen_wird_abgefangen(self):
        self.client.post(reverse("buchung_beleg_ablegen", args=[self.b.pk]))
        anzahl_vorher = self.Ablagedokument.objects.filter(verein=self.v).count()
        r = self.client.post(reverse("buchung_beleg_ablegen", args=[self.b.pk]), follow=True)
        self.assertEqual(self.Ablagedokument.objects.filter(verein=self.v).count(), anzahl_vorher)
        self.assertContains(r, "bereits in der Ablage abgelegt")

    def test_ohne_beleg_kein_knopf_und_fehler_bei_direktem_aufruf(self):
        ohne_beleg = Buchung.objects.create(
            verein=self.v, datum=date(2026, 3, 2), typ="ausgabe", betrag=Decimal("10.00"),
            konto=Konto.objects.filter(verein=self.v).first(),
            kategorie=Buchungskategorie.objects.filter(verein=self.v, typ="ausgabe").first(), text="Ohne Beleg")
        r = self.client.get(reverse("buchung_detail", args=[ohne_beleg.pk]))
        self.assertNotContains(r, "Beleg in Ablage übernehmen")
        r = self.client.post(reverse("buchung_beleg_ablegen", args=[ohne_beleg.pk]), follow=True)
        self.assertContains(r, "hat keinen Beleg")

    def test_ohne_recht_verboten(self):
        User = get_user_model()
        User.objects.create_user("leser", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=User.objects.get(username="leser"),
                              rolle=Rolle.objects.get(verein=self.v, name="Lesebenutzer"))
        self.client.login(username="leser", password="pw-Test-12345")
        r = self.client.post(reverse("buchung_beleg_ablegen", args=[self.b.pk]))
        self.assertEqual(r.status_code, 403)
