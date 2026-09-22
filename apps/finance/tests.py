import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounting import erechnung as erechnung_import
from apps.core.models import Rolle, Verein, Zugang
from apps.finance import erechnung, kontoauszug, sepa, services
from apps.finance.models import Bankumsatz, Beitragsjahr, Rechnung, Rechnungsposition, SepaEinzug, Zahlung
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

    def test_xml_enthaelt_kernfelder(self):
        xml_bytes = erechnung.xrechnung_xml(self.r)
        root = ET.fromstring(xml_bytes)
        self.assertTrue(root.tag.endswith("Invoice"))
        ns = {"cbc": erechnung.CBC_NS, "cac": erechnung.CAC_NS}
        self.assertEqual(root.find("cbc:ID", ns).text, self.r.nummer)
        self.assertEqual(root.find("cbc:IssueDate", ns).text, "2026-03-01")
        self.assertEqual(root.find("cac:LegalMonetaryTotal/cbc:PayableAmount", ns).text, f"{self.r.betrag:.2f}")
        zeilen = root.findall("cac:InvoiceLine", ns)
        self.assertEqual(len(zeilen), 2)
        self.assertEqual(root.find("cac:AccountingSupplierParty//cbc:RegistrationName", ns).text, self.v.name)
        self.assertEqual(root.find("cac:AccountingCustomerParty//cbc:RegistrationName", ns).text,
                         "Beispiel Handwerk GmbH")
        self.assertEqual(root.find("cac:PaymentMeans/cac:PayeeFinancialAccount/cbc:ID", ns).text, self.v.iban)

    def test_entwurf_ohne_nummer_bekommt_platzhalter(self):
        entwurf = Rechnung.objects.create(verein=self.v, typ="individuell", status="entwurf",
                                          empfaenger_name="Max Muster", datum=date(2026, 3, 1))
        xml_bytes = erechnung.xrechnung_xml(entwurf)
        root = ET.fromstring(xml_bytes)
        ns = {"cbc": erechnung.CBC_NS}
        self.assertEqual(root.find("cbc:ID", ns).text, f"ENTWURF-{entwurf.pk}")

    def test_roundtrip_mit_dem_e_rechnung_importer_lesbar(self):
        """Die eigene Ausgabe muss vom bestehenden E-Rechnung-Import (apps.accounting.erechnung) wieder
        korrekt eingelesen werden koennen - Symmetrie zwischen Erstellen und Lesen."""
        xml_bytes = erechnung.xrechnung_xml(self.r)
        d = erechnung_import.parse_rechnung(xml_bytes)
        self.assertEqual(d["format"], "XRechnung (UBL)")
        self.assertEqual(d["nummer"], self.r.nummer)
        self.assertEqual(d["datum"], date(2026, 3, 1))
        self.assertEqual(d["betrag"], self.r.betrag)
        self.assertEqual(d["verkaeufer"], self.v.name)
        self.assertEqual(d["waehrung"], "EUR")


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

    def test_download_liefert_xml(self):
        r = self.client.get(reverse("rechnung_erechnung", args=[self.r.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/xml")
        self.assertIn(self.r.nummer, r["Content-Disposition"])
        self.assertIn(self.r.nummer.encode(), r.content)

    def test_entwurf_wird_abgelehnt(self):
        entwurf = Rechnung.objects.create(verein=self.v, typ="individuell", status="entwurf",
                                          empfaenger_name="Max Muster", datum=date(2026, 3, 1))
        r = self.client.get(reverse("rechnung_erechnung", args=[entwurf.pk]), follow=True)
        self.assertContains(r, "noch keine Rechnungsnummer")

    def test_detailseite_zeigt_knopf_nur_bei_ausgestellter_rechnung(self):
        entwurf = Rechnung.objects.create(verein=self.v, typ="individuell", status="entwurf",
                                          empfaenger_name="Max Muster", datum=date(2026, 3, 1))
        r1 = self.client.get(reverse("rechnung_detail", args=[entwurf.pk]))
        self.assertNotContains(r1, "E-Rechnung (XML)")
        r2 = self.client.get(reverse("rechnung_detail", args=[self.r.pk]))
        self.assertContains(r2, "E-Rechnung (XML)")
