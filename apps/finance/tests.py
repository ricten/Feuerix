import io
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounting import erechnung as erechnung_import
from apps.core.models import Rolle, Verein, Zugang
from apps.finance import erechnung, kontoauszug, sepa, services
from apps.finance.models import Bankumsatz, Beitragsjahr, FinTSZugang, Rechnung, Rechnungsposition, SepaEinzug, Zahlung
from apps.members.models import Mitglied, Mitgliedsart

MT940_BEISPIEL = (
    ":20:STARTUMSMT940\n"
    ":25:DE02120300000000202051\n"
    ":28C:1/1\n"
    ":60F:C260301EUR1000,00\n"
    ":61:2603150315C60,00NMSCNONREF\n"
    ":86:EREF+RG2026-1 MREF+MREF-001 CRED+DE98ZZZ09999999999 SVWZ+Mitgliedsbeitrag 2026 ABWA+Max Muster\n"
    ":61:2603160316D25,50NTRFNONREF\n"
    ":86:SVWZ+Vereinsbedarf Rechnung 123\n"
    ":62F:C260316EUR1034,50\n"
).encode("utf-8")

CAMT053_BEISPIEL = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
  <BkToCstmrStmt><Stmt>
    <Ntry>
      <Amt Ccy="EUR">60.00</Amt>
      <CdtDbtInd>CRDT</CdtDbtInd>
      <BookgDt><Dt>2026-03-15</Dt></BookgDt>
      <NtryDtls><TxDtls>
        <RltdPties>
          <Dbtr><Nm>Max Muster</Nm></Dbtr>
          <DbtrAcct><Id><IBAN>DE89370400440532013000</IBAN></Id></DbtrAcct>
        </RltdPties>
        <RmtInf><Ustrd>Mitgliedsbeitrag 2026</Ustrd></RmtInf>
      </TxDtls></NtryDtls>
    </Ntry>
    <Ntry>
      <Amt Ccy="EUR">25.50</Amt>
      <CdtDbtInd>DBIT</CdtDbtInd>
      <BookgDt><Dt>2026-03-16</Dt></BookgDt>
      <NtryDtls><TxDtls>
        <RltdPties>
          <Cdtr><Nm>Beispiel Handwerk GmbH</Nm></Cdtr>
          <CdtrAcct><Id><IBAN>DE12500105170648489890</IBAN></Id></CdtrAcct>
        </RltdPties>
        <RmtInf><Ustrd>Vereinsbedarf Rechnung 123</Ustrd></RmtInf>
      </TxDtls></NtryDtls>
    </Ntry>
  </Stmt></BkToCstmrStmt>
</Document>""".encode("utf-8")

CSV_BEISPIEL = (
    "Buchungstag;Betrag;Name;IBAN;Verwendungszweck\n"
    "15.03.2026;60,00;Max Muster;DE89370400440532013000;Mitgliedsbeitrag 2026\n"
).encode("utf-8")


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


class SepaExportTests(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test", iban="DE02120300000000202051",
                                       bic="BYLADEM1001", glaeubiger_id="DE98ZZZ09999999999")
        art = Mitgliedsart.objects.get(verein=self.v, name="Aktiv")
        self.m1 = Mitglied.objects.create(verein=self.v, vorname="Max", nachname="Muster", mitgliedsart=art,
                                          eintrittsdatum=date(2015, 1, 1), zahlungsart="lastschrift",
                                          iban="DE89370400440532013000", mandatsreferenz="MREF-001",
                                          mandatsdatum=date(2020, 1, 1))
        self.m2 = Mitglied.objects.create(verein=self.v, vorname="Erika", nachname="Musterfrau", mitgliedsart=art,
                                          eintrittsdatum=date(2016, 1, 1), zahlungsart="lastschrift",
                                          iban="DE75512108001245126199", mandatsreferenz="MREF-002",
                                          mandatsdatum=date(2021, 1, 1))
        bj = Beitragsjahr.objects.create(verein=self.v, jahr=date.today().year,
                                         faelligkeit=date(date.today().year, 12, 31),
                                         alters_stichtag=date(date.today().year, 1, 1))
        services.beitragsjahr_abrechnen(bj)
        self.r1 = Rechnung.objects.get(verein=self.v, mitglied=self.m1)
        self.r2 = Rechnung.objects.get(verein=self.v, mitglied=self.m2)

    def test_eligible_rechnungen_filtert_unvollstaendige_mandate_aus(self):
        self.m2.mandatsdatum = None
        self.m2.save()
        self.assertEqual(list(sepa.eligible_rechnungen(self.v)), [self.r1])

    def test_eligible_rechnungen_ignoriert_ueberweiser(self):
        self.m1.zahlungsart = "ueberweisung"
        self.m1.save()
        self.assertEqual(list(sepa.eligible_rechnungen(self.v)), [self.r2])

    def test_einzug_erstellen_erste_lastschrift_ist_frst(self):
        e = sepa.einzug_erstellen(self.v, date(2026, 4, 1), [self.r1.pk, self.r2.pk])
        self.assertEqual(e.anzahl, 2)
        self.assertEqual(e.summe, self.r1.betrag + self.r2.betrag)
        self.assertTrue(all(p.sequenztyp == "FRST" for p in e.positionen.all()))
        self.assertTrue(e.datei.name.endswith(".xml"))
        self.assertEqual(e.nummer, "EZG-2026-000001")

    def test_zweiter_einzug_desselben_mitglieds_ist_rcur(self):
        sepa.einzug_erstellen(self.v, date(2026, 4, 1), [self.r1.pk])
        r_neu = services.rechnung_erstellen(self.v, [("Testposten", 1, 10)], mitglied=self.m1)
        e2 = sepa.einzug_erstellen(self.v, date(2026, 5, 1), [r_neu.pk])
        self.assertEqual(e2.positionen.get().sequenztyp, "RCUR")

    def test_ohne_glaeubiger_id_wird_abgelehnt(self):
        self.v.glaeubiger_id = ""
        self.v.save()
        with self.assertRaises(ValueError):
            sepa.einzug_erstellen(self.v, date(2026, 4, 1), [self.r1.pk])

    def test_ohne_ausgewaehlte_rechnungen_wird_abgelehnt(self):
        with self.assertRaises(ValueError):
            sepa.einzug_erstellen(self.v, date(2026, 4, 1), [])

    def test_pain008_xml_struktur_und_betraege(self):
        e = sepa.einzug_erstellen(self.v, date(2026, 4, 1), [self.r1.pk, self.r2.pk])
        root = ET.fromstring(e.datei.read())
        ns = {"p": sepa.PAIN008_NS}
        grp = root.find("p:CstmrDrctDbtInitn/p:GrpHdr", ns)
        self.assertEqual(grp.find("p:NbOfTxs", ns).text, "2")
        self.assertEqual(grp.find("p:CtrlSum", ns).text, f"{e.summe:.2f}")
        pmtinfs = root.findall("p:CstmrDrctDbtInitn/p:PmtInf", ns)
        self.assertEqual(len(pmtinfs), 1)  # beide FRST -> ein gemeinsamer Block
        self.assertEqual(pmtinfs[0].find("p:PmtTpInf/p:SeqTp", ns).text, "FRST")
        self.assertEqual(pmtinfs[0].find("p:CdtrAcct/p:Id/p:IBAN", ns).text, self.v.iban)
        self.assertEqual(pmtinfs[0].find("p:CdtrSchmeId/p:Id/p:PrvtId/p:Othr/p:Id", ns).text, self.v.glaeubiger_id)
        ibans = {x.text for x in pmtinfs[0].findall(".//p:DbtrAcct/p:Id/p:IBAN", ns)}
        self.assertEqual(ibans, {self.m1.iban, self.m2.iban})
        mandate = {x.text for x in pmtinfs[0].findall(".//p:MndtId", ns)}
        self.assertEqual(mandate, {"MREF-001", "MREF-002"})

    def test_pain008_xml_getrennte_bloecke_bei_gemischtem_sequenztyp(self):
        sepa.einzug_erstellen(self.v, date(2026, 4, 1), [self.r1.pk])  # m1 -> FRST erledigt
        r_neu = services.rechnung_erstellen(self.v, [("Testposten", 1, 10)], mitglied=self.m1)
        e2 = sepa.einzug_erstellen(self.v, date(2026, 5, 1), [r_neu.pk, self.r2.pk])  # m1 RCUR, m2 FRST
        root = ET.fromstring(e2.datei.read())
        ns = {"p": sepa.PAIN008_NS}
        pmtinfs = root.findall("p:CstmrDrctDbtInitn/p:PmtInf", ns)
        self.assertEqual(len(pmtinfs), 2)
        seqtypen = sorted(p.find("p:PmtTpInf/p:SeqTp", ns).text for p in pmtinfs)
        self.assertEqual(seqtypen, ["FRST", "RCUR"])

    def test_offener_betrag_bei_teilzahlung_wird_verwendet(self):
        Zahlung.objects.create(verein=self.v, rechnung=self.r1, betrag=20)
        self.r1.refresh_from_db()
        e = sepa.einzug_erstellen(self.v, date(2026, 4, 1), [self.r1.pk])
        self.assertEqual(e.positionen.get().betrag, self.r1.betrag - 20)


class SepaViewTests(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test", iban="DE02120300000000202051",
                                       bic="BYLADEM1001", glaeubiger_id="DE98ZZZ09999999999")
        art = Mitgliedsart.objects.get(verein=self.v, name="Aktiv")
        self.m1 = Mitglied.objects.create(verein=self.v, vorname="Max", nachname="Muster", mitgliedsart=art,
                                          eintrittsdatum=date(2015, 1, 1), zahlungsart="lastschrift",
                                          iban="DE89370400440532013000", mandatsreferenz="MREF-001",
                                          mandatsdatum=date(2020, 1, 1))
        bj = Beitragsjahr.objects.create(verein=self.v, jahr=date.today().year,
                                         faelligkeit=date(date.today().year, 12, 31),
                                         alters_stichtag=date(date.today().year, 1, 1))
        services.beitragsjahr_abrechnen(bj)
        self.r1 = Rechnung.objects.get(verein=self.v, mitglied=self.m1)
        User = get_user_model()
        self.user = User.objects.create_user("kasse", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=self.user, rolle=Rolle.objects.get(verein=self.v, name="Kassenwart"))

    def test_neu_seite_zeigt_eligible_rechnung(self):
        self.client.login(username="kasse", password="pw-Test-12345")
        r = self.client.get(reverse("sepa_einzug_neu"))
        self.assertContains(r, "Muster")

    def test_post_erstellt_einzug_und_leitet_weiter(self):
        self.client.login(username="kasse", password="pw-Test-12345")
        r = self.client.post(reverse("sepa_einzug_neu"),
                             {"faelligkeitsdatum": "2026-04-01", "rechnungen": [self.r1.pk]})
        e = SepaEinzug.objects.get(verein=self.v)
        self.assertRedirects(r, reverse("sepaeinzug_detail", args=[e.pk]))

    def test_ohne_recht_verboten(self):
        User = get_user_model()
        User.objects.create_user("leser", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=User.objects.get(username="leser"),
                              rolle=Rolle.objects.get(verein=self.v, name="Lesebenutzer"))
        self.client.login(username="leser", password="pw-Test-12345")
        r = self.client.post(reverse("sepa_einzug_neu"),
                             {"faelligkeitsdatum": "2026-04-01", "rechnungen": [self.r1.pk]})
        self.assertEqual(r.status_code, 403)

    def test_detail_zeigt_positionen(self):
        self.client.login(username="kasse", password="pw-Test-12345")
        self.client.post(reverse("sepa_einzug_neu"), {"faelligkeitsdatum": "2026-04-01", "rechnungen": [self.r1.pk]})
        e = SepaEinzug.objects.get(verein=self.v)
        r = self.client.get(reverse("sepaeinzug_detail", args=[e.pk]))
        self.assertContains(r, "Muster")
        self.assertContains(r, e.nummer)


class KontoauszugMT940Tests(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")

    def test_import_liest_beide_zeilen(self):
        neu, doppelt = kontoauszug.mt940_import(self.v, MT940_BEISPIEL)
        self.assertEqual((neu, doppelt), (2, 0))
        u1 = Bankumsatz.objects.get(betrag=Decimal("60.00"))
        self.assertEqual((u1.buchungsdatum, u1.gegenkonto_name, u1.verwendungszweck),
                         (date(2026, 3, 15), "Max Muster", "Mitgliedsbeitrag 2026"))
        u2 = Bankumsatz.objects.get(betrag=Decimal("-25.50"))
        self.assertEqual((u2.buchungsdatum, u2.verwendungszweck), (date(2026, 3, 16), "Vereinsbedarf Rechnung 123"))

    def test_erneuter_import_erkennt_duplikate(self):
        kontoauszug.mt940_import(self.v, MT940_BEISPIEL)
        neu, doppelt = kontoauszug.mt940_import(self.v, MT940_BEISPIEL)
        self.assertEqual((neu, doppelt), (0, 2))

    def test_ohne_umsatzzeilen_wird_abgelehnt(self):
        with self.assertRaises(ValueError):
            kontoauszug.mt940_import(self.v, b":20:LEER\n:28C:1/1\n")


class KontoauszugCamt053Tests(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")

    def test_import_liest_beide_eintraege(self):
        neu, doppelt = kontoauszug.camt053_import(self.v, CAMT053_BEISPIEL)
        self.assertEqual((neu, doppelt), (2, 0))
        u1 = Bankumsatz.objects.get(betrag=Decimal("60.00"))
        self.assertEqual((u1.buchungsdatum, u1.gegenkonto_name, u1.gegenkonto_iban, u1.verwendungszweck),
                         (date(2026, 3, 15), "Max Muster", "DE89370400440532013000", "Mitgliedsbeitrag 2026"))
        u2 = Bankumsatz.objects.get(betrag=Decimal("-25.50"))
        self.assertEqual((u2.gegenkonto_name, u2.gegenkonto_iban), ("Beispiel Handwerk GmbH", "DE12500105170648489890"))

    def test_erneuter_import_erkennt_duplikate(self):
        kontoauszug.camt053_import(self.v, CAMT053_BEISPIEL)
        neu, doppelt = kontoauszug.camt053_import(self.v, CAMT053_BEISPIEL)
        self.assertEqual((neu, doppelt), (0, 2))

    def test_ohne_eintraege_wird_abgelehnt(self):
        with self.assertRaises(ValueError):
            kontoauszug.camt053_import(self.v, b'<?xml version="1.0"?><Document><BkToCstmrStmt/></Document>')

    def test_kaputtes_xml_wird_abgelehnt(self):
        with self.assertRaises(ValueError):
            kontoauszug.camt053_import(self.v, b"<Document><Ntry>")


class KontoauszugDispatcherTests(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")

    def test_erkennt_camt053_an_dateiendung(self):
        neu, doppelt, format_ = kontoauszug.importieren(self.v, "auszug.xml", CAMT053_BEISPIEL)
        self.assertEqual((neu, format_), (2, "CAMT.053"))

    def test_erkennt_mt940_an_dateiendung(self):
        neu, doppelt, format_ = kontoauszug.importieren(self.v, "auszug.sta", MT940_BEISPIEL)
        self.assertEqual((neu, format_), (2, "MT940"))

    def test_erkennt_mt940_auch_mit_txt_endung_am_inhalt(self):
        neu, doppelt, format_ = kontoauszug.importieren(self.v, "auszug.txt", MT940_BEISPIEL)
        self.assertEqual((neu, format_), (2, "MT940"))

    def test_erkennt_csv(self):
        neu, doppelt, format_ = kontoauszug.importieren(self.v, "auszug.csv", CSV_BEISPIEL)
        self.assertEqual((neu, format_), (1, "CSV"))

    def test_unbekanntes_format_wird_abgelehnt(self):
        with self.assertRaises(ValueError):
            kontoauszug.importieren(self.v, "auszug.doc", b"irgendwas")


class BankImportViewTests(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        User = get_user_model()
        self.user = User.objects.create_user("kasse", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=self.user, rolle=Rolle.objects.get(verein=self.v, name="Kassenwart"))
        self.client.login(username="kasse", password="pw-Test-12345")

    def test_mt940_datei_hochladen(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        datei = SimpleUploadedFile("auszug.sta", MT940_BEISPIEL, content_type="application/octet-stream")
        r = self.client.post(reverse("bank_import"), {"datei": datei}, follow=True)
        self.assertContains(r, "MT940")
        self.assertEqual(Bankumsatz.objects.filter(verein=self.v).count(), 2)

    def test_camt053_datei_hochladen(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        datei = SimpleUploadedFile("auszug.xml", CAMT053_BEISPIEL, content_type="application/xml")
        r = self.client.post(reverse("bank_import"), {"datei": datei}, follow=True)
        self.assertContains(r, "CAMT.053")
        self.assertEqual(Bankumsatz.objects.filter(verein=self.v).count(), 2)


class ErechnungExportTests(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Freiwillige Feuerwehr Test e.V.", kuerzel="test",
                                       anschrift="Feuerwehrstraße 1", plz="12345", ort="Testhausen",
                                       steuernummer="123/456/78901", iban="DE02120300000000202051",
                                       bankname="Musterbank")
        self.r = Rechnung.objects.create(verein=self.v, typ="individuell", status="offen",
                                         empfaenger_name="Beispiel Handwerk GmbH",
                                         empfaenger_anschrift="Handwerkerweg 3\n54321 Musterstadt",
                                         datum=date(2026, 3, 1), faellig_am=date(2026, 3, 15))
        Rechnungsposition.objects.create(verein=self.v, rechnung=self.r, text="Saalmiete", menge=1,
                                         einzelpreis=Decimal("150.00"))
        Rechnungsposition.objects.create(verein=self.v, rechnung=self.r, text="Reinigung", menge=2,
                                         einzelpreis=Decimal("25.00"))
        self.r.refresh_from_db()

    def test_xml_ist_gueltig_und_enthaelt_kernfelder(self):
        """generate_cii_xml validiert bereits intern gegen das offizielle EN16931/Factur-X-XSD - kommen
        Bytes zurueck, ist die Struktur amtlich schema-valide (siehe auch die XSD-Ablehnungstests unten)."""
        xml_bytes = erechnung.zugferd_xml(self.r)
        d = erechnung_import.parse_rechnung(xml_bytes)
        self.assertEqual(d["format"], "ZUGFeRD/XRechnung (CII)")
        self.assertEqual(d["nummer"], self.r.nummer)
        self.assertEqual(d["datum"], date(2026, 3, 1))
        self.assertEqual(d["betrag"], self.r.betrag)
        self.assertEqual(d["verkaeufer"], self.v.name)
        self.assertEqual(d["waehrung"], "EUR")

    def test_entwurf_ohne_nummer_bekommt_platzhalter(self):
        entwurf = Rechnung.objects.create(verein=self.v, typ="individuell", status="entwurf",
                                          empfaenger_name="Max Muster", datum=date(2026, 3, 1))
        Rechnungsposition.objects.create(verein=self.v, rechnung=entwurf, text="Posten", menge=1,
                                         einzelpreis=Decimal("10.00"))
        entwurf.refresh_from_db()
        xml_bytes = erechnung.zugferd_xml(entwurf)
        d = erechnung_import.parse_rechnung(xml_bytes)
        self.assertEqual(d["nummer"], f"ENTWURF-{entwurf.pk}")

    def test_pdf_enthaelt_eingebettete_xml_als_factur_x_datei(self):
        pdf_bytes = erechnung.zugferd_pdf(self.r)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        self.assertIn("factur-x.xml", reader.attachments)

    def test_roundtrip_mit_dem_e_rechnung_importer_lesbar(self):
        """Die eigene ZUGFeRD-PDF-Ausgabe muss vom bestehenden E-Rechnung-Import (apps.accounting.erechnung)
        wieder korrekt eingelesen werden koennen - Symmetrie zwischen Erstellen und Lesen."""
        pdf_bytes = erechnung.zugferd_pdf(self.r)
        xml_bytes = erechnung_import.xml_aus_datei("rechnung.pdf", pdf_bytes)
        d = erechnung_import.parse_rechnung(xml_bytes)
        self.assertEqual(d["format"], "ZUGFeRD/XRechnung (CII)")
        self.assertEqual(d["nummer"], self.r.nummer)
        self.assertEqual(d["datum"], date(2026, 3, 1))
        self.assertEqual(d["betrag"], self.r.betrag)
        self.assertEqual(d["verkaeufer"], self.v.name)

    def test_xsd_pruefung_lehnt_ungueltigen_betrag_ab(self):
        """Beweist, dass wirklich gegen das amtliche Schema geprueft wird und nicht nur hausgemachtes XML
        blind ausgegeben wird: ein nicht-numerischer Betrag muss vom XSD-Datentyp abgelehnt werden."""
        from facturx.generate_xml import generate_cii_xml
        daten = erechnung._cii_data_dict(self.r)
        daten["BT-115"] = "keine-zahl"
        with self.assertRaises(Exception):
            generate_cii_xml(daten, level=erechnung.LEVEL, check_xsd=True, check_schematron=False)

    def test_xsd_pruefung_lehnt_fehlendes_pflichtfeld_ab(self):
        from facturx.generate_xml import generate_cii_xml
        daten = erechnung._cii_data_dict(self.r)
        del daten["BT-27"]  # Verkaeufername ist Pflicht
        with self.assertRaises(Exception):
            generate_cii_xml(daten, level=erechnung.LEVEL, check_xsd=True, check_schematron=False)


class UmsatzsteuerTests(TestCase):
    """Umsatzsteuer-Ausweisung fuer nicht gemeinnuetzige Vereine / den wirtschaftlichen Geschaeftsbetrieb -
    Standard weiterhin 0 % (unveraendertes Verhalten fuer bestehende gemeinnuetzige Vereine)."""

    def setUp(self):
        self.v = Verein.objects.create(name="Handel e.V.", kuerzel="handel", umsatzsteuerpflichtig=True,
                                       ust_idnr="DE123456789")
        self.r = Rechnung.objects.create(verein=self.v, typ="individuell", status="entwurf",
                                         empfaenger_name="Max Muster", datum=date(2026, 3, 1))

    def test_position_berechnet_netto_steuer_brutto(self):
        p = Rechnungsposition.objects.create(verein=self.v, rechnung=self.r, text="Ware", menge=2,
                                             einzelpreis=Decimal("10.00"), steuersatz=Decimal("19.00"))
        self.assertEqual(p.nettobetrag, Decimal("20.00"))
        self.assertEqual(p.steuerbetrag, Decimal("3.80"))
        self.assertEqual(p.bruttobetrag, Decimal("23.80"))
        self.assertEqual(p.betrag, p.nettobetrag)

    def test_position_ohne_steuersatz_ist_weiterhin_wie_vorher(self):
        p = Rechnungsposition.objects.create(verein=self.v, rechnung=self.r, text="Ware", menge=2,
                                             einzelpreis=Decimal("10.00"))
        self.assertEqual(p.steuersatz, Decimal("0"))
        self.assertEqual(p.steuerbetrag, Decimal("0.00"))
        self.assertEqual(p.bruttobetrag, p.nettobetrag)

    def test_rechnung_summiert_gemischte_steuersaetze(self):
        Rechnungsposition.objects.create(verein=self.v, rechnung=self.r, text="Ware (19 %)", menge=2,
                                         einzelpreis=Decimal("10.00"), steuersatz=Decimal("19.00"))
        Rechnungsposition.objects.create(verein=self.v, rechnung=self.r, text="Ware (steuerfrei)", menge=1,
                                         einzelpreis=Decimal("5.00"))
        self.r.refresh_from_db()
        self.assertEqual(self.r.nettobetrag, Decimal("25.00"))
        self.assertEqual(self.r.steuerbetrag, Decimal("3.80"))
        self.assertEqual(self.r.betrag, Decimal("28.80"))
        gruppen = self.r.steuer_gruppen
        self.assertEqual(gruppen[Decimal("19.00")], {"netto": Decimal("20.00"), "steuer": Decimal("3.80")})
        self.assertEqual(gruppen[Decimal("0")]["steuer"], Decimal("0.00"))

    def test_storno_uebernimmt_steuersatz_der_originalposition(self):
        Rechnungsposition.objects.create(verein=self.v, rechnung=self.r, text="Ware", menge=1,
                                         einzelpreis=Decimal("100.00"), steuersatz=Decimal("19.00"))
        self.r.status = "offen"
        self.r.nummer_vergeben()
        self.r.save()
        storno = services.storniere(self.r)
        self.assertEqual(storno.positionen.get().steuersatz, Decimal("19.00"))
        self.assertEqual(storno.steuerbetrag, Decimal("-19.00"))
        self.assertEqual(storno.betrag, Decimal("-119.00"))

    def test_rechnungsposition_form_schlaegt_standardsatz_vor(self):
        from apps.finance.forms import RechnungspositionForm
        form = RechnungspositionForm(verein=self.v)
        self.assertEqual(form.fields["steuersatz"].initial, Decimal("19.00"))
        andere_verein = Verein.objects.create(name="Verein B", kuerzel="b")
        form2 = RechnungspositionForm(verein=andere_verein)
        self.assertNotEqual(form2.fields["steuersatz"].initial, Decimal("19.00"))

    def test_pdf_ohne_umsatzsteuer_bleibt_unveraendert(self):
        """Regressionsschutz: ein Verein ohne Umsatzsteuerpflicht und ohne Steuersatz auf den Positionen
        bekommt weiterhin die einfache Rechnung ohne Steuerspalte/-hinweis (Standardfall gemeinnuetziger Vereine)."""
        v = Verein.objects.create(name="Gemeinnuetziger Verein e.V.", kuerzel="gemeinnuetzig")
        r = Rechnung.objects.create(verein=v, typ="individuell", status="offen", empfaenger_name="Max Muster",
                                    datum=date(2026, 3, 1))
        Rechnungsposition.objects.create(verein=v, rechnung=r, text="Beitrag", menge=1, einzelpreis=Decimal("50.00"))
        r.refresh_from_db()
        from apps.finance.pdf import rechnung_pdf
        pdf_bytes = rechnung_pdf(r)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        from pypdf import PdfReader
        text = "".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf_bytes)).pages)
        self.assertIn("Gesamtbetrag", text)
        self.assertNotIn("USt", text)

    def test_pdf_mit_umsatzsteuer_zeigt_aufschluesselung(self):
        Rechnungsposition.objects.create(verein=self.v, rechnung=self.r, text="Ware", menge=1,
                                         einzelpreis=Decimal("100.00"), steuersatz=Decimal("19.00"))
        self.r.status = "offen"
        self.r.nummer_vergeben()
        self.r.save()
        from apps.finance.pdf import rechnung_pdf
        pdf_bytes = rechnung_pdf(self.r)
        from pypdf import PdfReader
        text = "".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf_bytes)).pages)
        self.assertIn("Nettobetrag", text)
        self.assertIn("19", text)
        self.assertIn("USt", text)
        self.assertIn("Gesamtbetrag", text)
        self.assertIn("brutto", text)

    def test_erechnung_bildet_gemischte_steuersaetze_in_bg23_ab(self):
        Rechnungsposition.objects.create(verein=self.v, rechnung=self.r, text="Ware (19 %)", menge=1,
                                         einzelpreis=Decimal("100.00"), steuersatz=Decimal("19.00"))
        Rechnungsposition.objects.create(verein=self.v, rechnung=self.r, text="Ware (steuerfrei)", menge=1,
                                         einzelpreis=Decimal("50.00"))
        self.r.status = "offen"
        self.r.nummer_vergeben()
        self.r.save()
        xml_bytes = erechnung.zugferd_xml(self.r)
        text = xml_bytes.decode("utf-8")
        self.assertIn("<ram:RateApplicablePercent>19.00</ram:RateApplicablePercent>", text)
        self.assertIn("<ram:CategoryCode>S</ram:CategoryCode>", text)
        self.assertIn("<ram:CategoryCode>E</ram:CategoryCode>", text)
        self.assertIn("ExemptionReason", text)

    def test_erechnung_nutzt_eigenen_steuerhinweis(self):
        self.v.rechnung_steuerhinweis = "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet"
        self.v.save()
        Rechnungsposition.objects.create(verein=self.v, rechnung=self.r, text="Ware", menge=1,
                                         einzelpreis=Decimal("10.00"))
        self.r.status = "offen"
        self.r.nummer_vergeben()
        self.r.save()
        xml_bytes = erechnung.zugferd_xml(self.r)
        self.assertIn("Gemäß § 19 UStG", xml_bytes.decode("utf-8"))


class ErechnungViewTests(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test", iban="DE02120300000000202051")
        self.r = Rechnung.objects.create(verein=self.v, typ="individuell", status="offen",
                                         empfaenger_name="Max Muster", datum=date(2026, 3, 1))
        Rechnungsposition.objects.create(verein=self.v, rechnung=self.r, text="Posten", menge=1,
                                         einzelpreis=Decimal("42.00"))
        self.r.refresh_from_db()
        User = get_user_model()
        self.user = User.objects.create_user("kasse", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=self.user, rolle=Rolle.objects.get(verein=self.v, name="Kassenwart"))
        self.client.login(username="kasse", password="pw-Test-12345")

    def test_download_liefert_zugferd_pdf(self):
        r = self.client.get(reverse("rechnung_erechnung", args=[self.r.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertIn(self.r.nummer, r["Content-Disposition"])
        self.assertTrue(r.content.startswith(b"%PDF"))

    def test_entwurf_wird_abgelehnt(self):
        entwurf = Rechnung.objects.create(verein=self.v, typ="individuell", status="entwurf",
                                          empfaenger_name="Max Muster", datum=date(2026, 3, 1))
        r = self.client.get(reverse("rechnung_erechnung", args=[entwurf.pk]), follow=True)
        self.assertContains(r, "noch keine Rechnungsnummer")

    def test_detailseite_zeigt_knopf_nur_bei_ausgestellter_rechnung(self):
        entwurf = Rechnung.objects.create(verein=self.v, typ="individuell", status="entwurf",
                                          empfaenger_name="Max Muster", datum=date(2026, 3, 1))
        r1 = self.client.get(reverse("rechnung_detail", args=[entwurf.pk]))
        self.assertNotContains(r1, "E-Rechnung (ZUGFeRD-PDF)")
        r2 = self.client.get(reverse("rechnung_detail", args=[self.r.pk]))
        self.assertContains(r2, "E-Rechnung (ZUGFeRD-PDF)")


# ---------------------------------------------------------------- FinTS (mit Testdouble statt echter Bank)
class _FakeAmount:
    def __init__(self, amount):
        self.amount = amount


class _FakeTransaction:
    def __init__(self, datum, betrag, name="", iban="", zweck=""):
        self.data = {"date": datum, "amount": _FakeAmount(Decimal(str(betrag))), "purpose": zweck,
                     "applicant_iban": iban, "applicant_name": name}


class _FakeNeedTANResponse:
    """Ersetzt fints.client.NeedTANResponse in Tests - echte Instanzen brauchen eine echte Bankverbindung."""

    def __init__(self, challenge="Bitte TAN eingeben", decoupled=False):
        self.challenge = challenge
        self.challenge_html = challenge
        self.challenge_matrix = None
        self.decoupled = decoupled

    def get_data(self):
        import pickle
        return pickle.dumps(self)


class _FakeNeedRetryResponse:
    @staticmethod
    def from_data(blob):
        import pickle
        return pickle.loads(blob)


class _FakeResumeDialog:
    def __init__(self, client):
        self.client = client

    def __enter__(self):
        return self.client

    def __exit__(self, *a):
        return False


class _FakeFinTSClient:
    """Testdouble fuer fints.client.FinTS3PinTanClient - bildet genau die Schritte nach, die fints_service nutzt."""

    def __init__(self, blz="", kennung="", pin="", url="", product_id=None, from_data=None, konten=None,
                kontenabruf_ergebnis=None, send_tan_ergebnis=None, init_tan_response=None, fehler=None):
        self.from_data = from_data
        self.init_tan_response = init_tan_response
        self._konten = konten or []
        self._kontenabruf_ergebnis = kontenabruf_ergebnis
        self._send_tan_ergebnis = send_tan_ergebnis
        self._fehler = fehler

    def __enter__(self):
        if self._fehler:
            raise self._fehler
        return self

    def __exit__(self, *a):
        return False

    def get_sepa_accounts(self):
        return self._konten

    def get_transactions(self, konto, von, bis):
        return self._kontenabruf_ergebnis

    def deconstruct(self, including_private=False):
        return b"client-blob"

    def pause_dialog(self):
        return b"dialog-blob"

    def resume_dialog(self, dialog_data):
        return _FakeResumeDialog(self)

    def send_tan(self, tan_response, tan):
        return self._send_tan_ergebnis


@override_settings(FINTS_PRODUCT_ID="TEST123456")
class FinTSAbrufTests(TestCase):
    def setUp(self):
        from fints.models import SEPAAccount
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        User = get_user_model()
        self.user = User.objects.create_user("kasse", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=self.user, rolle=Rolle.objects.get(verein=self.v, name="Kassenwart"))
        self.client.login(username="kasse", password="pw-Test-12345")
        self.zugang = FinTSZugang.objects.create(verein=self.v, bezeichnung="Testbank", blz="12030000",
                                                 kennung="test-kennung", bank_url="https://fints.beispielbank.de",
                                                 tage=30)
        self.konto = SEPAAccount(iban="DE02120300000000202051", bic="BYLADEM1001", accountnumber="202051",
                                 subaccount="", blz="12030000")

    def test_mehrere_zugaenge_pro_verein_moeglich(self):
        zweiter = FinTSZugang.objects.create(verein=self.v, bezeichnung="Zweitbank", blz="50010517",
                                             kennung="andere-kennung", bank_url="https://banking.example.org")
        self.assertEqual(FinTSZugang.objects.filter(verein=self.v).count(), 2)
        r = self.client.get(reverse("fintszugang_list"))
        self.assertContains(r, "Testbank")
        self.assertContains(r, "Zweitbank")
        self.assertEqual(zweiter.blz, "50010517")

    def test_konto_kann_einem_zugang_zugeordnet_werden(self):
        from apps.accounting.models import Konto
        konto = Konto.objects.create(verein=self.v, name="Vereinskonto", typ="bank", fints_zugang=self.zugang)
        self.assertEqual(konto.fints_zugang, self.zugang)
        r = self.client.get(reverse("fintszugang_detail", args=[self.zugang.pk]))
        self.assertContains(r, "Vereinskonto")

        # Wird der Zugang geloescht, bleibt das Konto erhalten (nur die Zuordnung faellt weg) - kein CASCADE.
        self.zugang.delete()
        konto.refresh_from_db()
        self.assertIsNone(konto.fints_zugang)

    def test_konto_ohne_zugang_bleibt_unveraendert_manueller_import(self):
        from apps.accounting.models import Konto
        konto = Konto.objects.get(verein=self.v, name="Barkasse")
        self.assertIsNone(konto.fints_zugang)

    def test_abruf_ohne_tan_importiert_und_erkennt_duplikate(self):
        transaktionen = [_FakeTransaction(date(2026, 3, 15), Decimal("60.00"), "Max Muster",
                                          "DE89370400440532013000", "Mitgliedsbeitrag")]
        fake = _FakeFinTSClient(konten=[self.konto], kontenabruf_ergebnis=transaktionen)
        with patch("fints.client.FinTS3PinTanClient", return_value=fake):
            r = self.client.post(reverse("fints_abrufen", args=[self.zugang.pk]), {"pin": "1234"}, follow=True)
        self.assertContains(r, "1 neue Umsätze importiert")
        self.assertEqual(Bankumsatz.objects.filter(verein=self.v).count(), 1)
        self.assertEqual(Bankumsatz.objects.get(verein=self.v).fints_zugang, self.zugang)
        self.zugang.refresh_from_db()
        self.assertIsNotNone(self.zugang.letzter_abruf)

        # Zweiter Abruf mit denselben Umsaetzen -> Duplikat wird per Pruefsumme erkannt, kein neuer Bankumsatz
        fake2 = _FakeFinTSClient(konten=[self.konto], kontenabruf_ergebnis=transaktionen)
        with patch("fints.client.FinTS3PinTanClient", return_value=fake2):
            r2 = self.client.post(reverse("fints_abrufen", args=[self.zugang.pk]), {"pin": "1234"}, follow=True)
        self.assertContains(r2, "0 neue Umsätze importiert")
        self.assertEqual(Bankumsatz.objects.filter(verein=self.v).count(), 1)

    def test_abruf_mit_tan_ueber_zwei_schritte(self):
        tan_response = _FakeNeedTANResponse(challenge="Bitte die App-TAN bestätigen")
        fake1 = _FakeFinTSClient(konten=[self.konto], kontenabruf_ergebnis=tan_response)
        with patch("fints.client.FinTS3PinTanClient", return_value=fake1), \
             patch("fints.client.NeedTANResponse", _FakeNeedTANResponse), \
             patch("fints.client.NeedRetryResponse", _FakeNeedRetryResponse):
            r1 = self.client.post(reverse("fints_abrufen", args=[self.zugang.pk]), {"pin": "1234"}, follow=True)
            self.assertContains(r1, "TAN erforderlich")
            self.assertContains(r1, "Bitte die App-TAN bestätigen")
            self.assertIn("fints_tan", self.client.session)

            transaktionen = [_FakeTransaction(date(2026, 3, 16), Decimal("25.50"), "Beispiel GmbH",
                                              "DE12500105170648489890", "Vereinsbedarf")]
            fake2 = _FakeFinTSClient(send_tan_ergebnis=transaktionen)
            with patch("fints.client.FinTS3PinTanClient", return_value=fake2):
                r2 = self.client.post(reverse("fints_abrufen", args=[self.zugang.pk]), {"tan": "999999"}, follow=True)
        self.assertContains(r2, "1 neue Umsätze importiert")
        self.assertEqual(Bankumsatz.objects.filter(verein=self.v).count(), 1)
        self.assertEqual(Bankumsatz.objects.get(verein=self.v).fints_zugang, self.zugang)
        self.assertNotIn("fints_tan", self.client.session)

    def test_leere_tan_wird_bei_normalem_verfahren_abgelehnt(self):
        tan_response = _FakeNeedTANResponse(challenge="Bitte TAN eingeben", decoupled=False)
        fake = _FakeFinTSClient(konten=[self.konto], kontenabruf_ergebnis=tan_response)
        with patch("fints.client.FinTS3PinTanClient", return_value=fake), \
             patch("fints.client.NeedTANResponse", _FakeNeedTANResponse), \
             patch("fints.client.NeedRetryResponse", _FakeNeedRetryResponse):
            self.client.post(reverse("fints_abrufen", args=[self.zugang.pk]), {"pin": "1234"})
            r = self.client.post(reverse("fints_abrufen", args=[self.zugang.pk]), {"tan": ""})
        self.assertContains(r, "TAN erforderlich")
        self.assertIn("fints_tan", self.client.session)

    def test_verbindungsfehler_wird_abgefangen(self):
        fake = _FakeFinTSClient(fehler=Exception("Zeitüberschreitung"))
        with patch("fints.client.FinTS3PinTanClient", return_value=fake):
            r = self.client.post(reverse("fints_abrufen", args=[self.zugang.pk]), {"pin": "1234"}, follow=True)
        self.assertContains(r, "fehlgeschlagen")
        self.zugang.refresh_from_db()
        self.assertIn("Zeitüberschreitung", self.zugang.letzte_meldung)
        self.assertNotIn("fints_tan", self.client.session)

    def test_ohne_produkt_id_klare_fehlermeldung(self):
        with self.settings(FINTS_PRODUCT_ID=""):
            r = self.client.get(reverse("fints_abrufen", args=[self.zugang.pk]), follow=True)
        self.assertContains(r, "FinTS-Produkt-ID")

    def test_ohne_add_recht_kein_abruf_aber_liste_lesbar(self):
        User = get_user_model()
        leser = User.objects.create_user("leser", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=leser, rolle=Rolle.objects.get(verein=self.v, name="Kassenprüfer"))
        self.client.logout()
        self.client.login(username="leser", password="pw-Test-12345")
        self.assertEqual(self.client.get(reverse("fints_abrufen", args=[self.zugang.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("fintszugang_list")).status_code, 200)

    def test_kontodaten_abrufen_ohne_tan(self):
        fake = _FakeFinTSClient(konten=[self.konto])
        with patch("fints.client.FinTS3PinTanClient", return_value=fake):
            r = self.client.post(reverse("fints_kontodaten", args=[self.zugang.pk]), {"pin": "1234"})
        self.assertContains(r, "DE02120300000000202051")
        self.assertContains(r, "BYLADEM1001")
        self.assertNotIn("fints_konten_tan", self.client.session)
        # Wurde kein Bankumsatz erzeugt - reine Kontodaten-Abfrage, kein Transaktions-Import.
        self.assertEqual(Bankumsatz.objects.filter(verein=self.v).count(), 0)

    def test_kontodaten_abrufen_mit_tan(self):
        tan_response = _FakeNeedTANResponse(challenge="Bitte TAN eingeben")
        fake1 = _FakeFinTSClient(init_tan_response=tan_response)
        with patch("fints.client.FinTS3PinTanClient", return_value=fake1), \
             patch("fints.client.NeedTANResponse", _FakeNeedTANResponse), \
             patch("fints.client.NeedRetryResponse", _FakeNeedRetryResponse):
            r1 = self.client.post(reverse("fints_kontodaten", args=[self.zugang.pk]), {"pin": "1234"}, follow=True)
            self.assertContains(r1, "TAN erforderlich")
            self.assertIn("fints_konten_tan", self.client.session)

            fake2 = _FakeFinTSClient(konten=[self.konto])
            with patch("fints.client.FinTS3PinTanClient", return_value=fake2):
                r2 = self.client.post(reverse("fints_kontodaten", args=[self.zugang.pk]), {"tan": "999999"}, follow=True)
        self.assertContains(r2, "DE02120300000000202051")
        self.assertNotIn("fints_konten_tan", self.client.session)

    def test_kontodaten_ohne_add_recht_verboten(self):
        User = get_user_model()
        leser = User.objects.create_user("leser2", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=leser, rolle=Rolle.objects.get(verein=self.v, name="Kassenprüfer"))
        self.client.logout()
        self.client.login(username="leser2", password="pw-Test-12345")
        self.assertEqual(self.client.get(reverse("fints_kontodaten", args=[self.zugang.pk])).status_code, 403)

    def test_bankumsaetze_liste_zeigt_abrufknopf_je_zugang(self):
        zweiter = FinTSZugang.objects.create(verein=self.v, bezeichnung="Zweitbank", blz="50010517",
                                             kennung="andere-kennung", bank_url="https://banking.example.org")
        r = self.client.get(reverse("bankumsatz_list"))
        self.assertContains(r, "Umsätze abrufen: Testbank")
        self.assertContains(r, "Umsätze abrufen: Zweitbank")
        self.assertContains(r, reverse("fints_abrufen", args=[self.zugang.pk]))
        self.assertContains(r, reverse("fints_abrufen", args=[zweiter.pk]))

    def test_bankumsaetze_liste_ohne_produkt_id_ohne_abrufknopf(self):
        with self.settings(FINTS_PRODUCT_ID=""):
            r = self.client.get(reverse("bankumsatz_list"))
        self.assertNotContains(r, "Umsätze abrufen:")
