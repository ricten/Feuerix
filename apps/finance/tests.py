import xml.etree.ElementTree as ET
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Rolle, Verein, Zugang
from apps.finance import sepa, services
from apps.finance.models import Beitragsjahr, Rechnung, SepaEinzug, Zahlung
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
