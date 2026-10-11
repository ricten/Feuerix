import io
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader

from apps.core.models import Rolle, Verein, Zugang
from apps.events.helfer import finde_mitglied
from apps.events.models import Schicht, Schichteinsatz, Veranstaltung
from apps.events.pdf import schichtplan_pdf
from apps.members.models import Mitglied

PW = "pw-Test-12345"


class SchichtBasis(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        User = get_user_model()
        admin = User.objects.create_superuser("admin", password=PW)
        Zugang.objects.create(verein=self.v, user=admin, rolle=Rolle.objects.get(verein=self.v,
                                                                                  name="Superadministrator"))
        # feste Uhrzeit (10:00), damit die Tests unabhaengig von der Tageszeit des Testlaufs sind
        self.beginn = (timezone.localtime() + timedelta(days=5)).replace(hour=10, minute=0, second=0, microsecond=0)
        self.ver = Veranstaltung.objects.create(verein=self.v, titel="Sommerfest", beginn=self.beginn, ort="Festplatz",
                                                helfer_eintragung=True)
        self.aufbau = self.schicht("Aufbau", 0, 3, benoetigt=3)
        self.theke = self.schicht("Theke", 4, 8, benoetigt=2)
        self.m = Mitglied.objects.create(verein=self.v, vorname="Erika", nachname="Muster", mitgliedsnummer=7)

    def schicht(self, name, ab_h, bis_h, benoetigt=1, ver=None):
        return Schicht.objects.create(verein=self.v, veranstaltung=ver or self.ver, bezeichnung=name,
                                      beginn=self.beginn + timedelta(hours=ab_h), ende=self.beginn + timedelta(hours=bis_h),
                                      benoetigt=benoetigt)

    def einsatz(self, schicht, **kw):
        return Schichteinsatz.objects.create(verein=self.v, schicht=schicht, **kw)

    def anmelden(self):
        self.client.login(username="admin", password=PW)


class ModellTests(SchichtBasis):
    def test_einsatz_braucht_mitglied_oder_name(self):
        with self.assertRaises(ValidationError):
            Schichteinsatz(verein=self.v, schicht=self.aufbau).full_clean()
        Schichteinsatz(verein=self.v, schicht=self.aufbau, name="Gast Eins").full_clean()
        Schichteinsatz(verein=self.v, schicht=self.aufbau, mitglied=self.m).full_clean()

    def test_wer_und_helferliste_mit_mitglied_und_gast(self):
        self.einsatz(self.aufbau, mitglied=self.m)
        self.einsatz(self.aufbau, name="Anton Gast")
        self.assertEqual(self.aufbau.helfer_namen, ["Anton Gast", "Erika Muster"])   # alphabetisch
        self.assertEqual(self.aufbau.helfer, "Anton Gast, Erika Muster")
        self.assertEqual(self.aufbau.besetzung, "2/3")
        self.assertEqual(self.aufbau.freie_plaetze, 1)
        self.assertEqual(self.theke.helfer, "–")

    def test_volle_schicht_nimmt_niemanden_mehr_auf(self):
        self.einsatz(self.theke, name="A")
        self.einsatz(self.theke, name="B")
        with self.assertRaises(ValidationError):
            Schichteinsatz(verein=self.v, schicht=self.theke, name="C").full_clean()
        self.assertEqual(self.theke.freie_plaetze, 0)


class SchichtplanPdfTests(SchichtBasis):
    def _text(self, v=None):
        pdf = PdfReader(io.BytesIO(schichtplan_pdf(v or self.ver)))
        return "\n".join(p.extract_text() for p in pdf.pages)

    def test_alle_eingeteilten_je_schicht_mit_kontakt_und_freien_plaetzen(self):
        self.einsatz(self.aufbau, mitglied=self.m)
        self.einsatz(self.aufbau, name="Anton Gast", kontakt="0170 123")
        self.einsatz(self.theke, name="Berta Helfer")
        text = self._text()
        for erwartet in ("Schichtplan", "Sommerfest", "Festplatz", "Aufbau", "Theke", "Erika Muster", "Anton Gast (0170 123)",
                         "Berta Helfer", "Besetzung 2/3", "Besetzung 1/2"):
            self.assertIn(erwartet, text)
        self.assertIn("_" * 34, text)   # offene Plaetze als Schreiblinien
        self.assertIn("handschriftlich", text)

    def test_komplett_besetzt_ohne_schreiblinien_und_hinweis(self):
        for n in ("A", "B", "C"):
            self.einsatz(self.aufbau, name=n)
        for n in ("D", "E"):
            self.einsatz(self.theke, name=n)
        text = self._text()
        self.assertNotIn("_" * 34, text)
        self.assertNotIn("handschriftlich", text)

    def test_nach_tagen_gegliedert(self):
        self.schicht("Abbau", 30, 33)   # am Folgetag
        text = self._text()
        self.assertEqual(sum(1 for t in ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
                             if t in text.split("Eingeteilte Helfer")[1]), 2)

    def test_ohne_schichten_funktioniert_es(self):
        leer = Veranstaltung.objects.create(verein=self.v, titel="Leer", beginn=self.beginn)
        self.assertIn("noch keine Schichten", self._text(leer))

    def test_ansicht_nur_angemeldet_und_nur_eigener_verein(self):
        url = reverse("veranstaltung_schichtplan_pdf", args=[self.ver.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.anmelden()
        antwort = self.client.get(url)
        self.assertEqual((antwort.status_code, antwort["Content-Type"]), (200, "application/pdf"))
        anderer = Verein.objects.create(name="Anderer e.V.", kuerzel="anderer")
        fremd = Veranstaltung.objects.create(verein=anderer, titel="Fremd", beginn=self.beginn)
        self.assertEqual(self.client.get(reverse("veranstaltung_schichtplan_pdf", args=[fremd.pk])).status_code, 404)


class OberflaecheTests(SchichtBasis):
    def setUp(self):
        super().setUp()
        self.anmelden()

    def test_schicht_zeigt_alle_eingeteilten_mit_kontakt_und_freien_plaetzen(self):
        self.einsatz(self.aufbau, mitglied=self.m)
        self.einsatz(self.aufbau, name="Anton Gast", kontakt="0170 123", selbst_eingetragen=True)
        r = self.client.get(reverse("schicht_detail", args=[self.aufbau.pk]))
        for erwartet in ("Eingeteilte Helfer", "Erika Muster", "Anton Gast", "0170 123", "1 von 3 Plätzen noch frei",
                         "Schichtplan der Veranstaltung drucken"):
            self.assertContains(r, erwartet)

    def test_veranstaltung_zeigt_pdf_knopf_und_helfer_link(self):
        r = self.client.get(reverse("veranstaltung_detail", args=[self.ver.pk]))
        self.assertContains(r, "Schichtplan drucken (PDF)")
        self.assertContains(r, reverse("veranstaltung_schichtplan_pdf", args=[self.ver.pk]))
        self.assertContains(r, reverse("veranstaltung_helfer", args=[self.ver.rueckmeldung_code]))
        self.assertContains(r, "Links zum Weitergeben")
        self.assertContains(r, "Helfer-Selbsteintrag in Schichten")

    def test_ohne_schichten_kein_pdf_knopf_ohne_freigabe_kein_link(self):
        ohne = Veranstaltung.objects.create(verein=self.v, titel="Ohne", beginn=self.beginn)
        r = self.client.get(reverse("veranstaltung_detail", args=[ohne.pk]))
        self.assertNotContains(r, "Schichtplan drucken")
        self.assertNotContains(r, "Helfer-Link")

    def test_schichtplan_abschnitt_zeigt_helfer_namen_auch_von_gaesten(self):
        self.einsatz(self.theke, name="Berta Helfer")
        self.assertContains(self.client.get(reverse("veranstaltung_detail", args=[self.ver.pk])), "Berta Helfer")

    def test_helfer_manuell_als_gast_eintragen(self):
        r = self.client.post(reverse("schichteinsatz_add"), {"schicht": self.theke.pk, "name": "Manuell Gast",
                                                             "kontakt": "123", "bemerkung": ""})
        self.assertEqual(r.status_code, 302)
        e = Schichteinsatz.objects.get(name="Manuell Gast")
        self.assertFalse(e.selbst_eingetragen)
        self.assertIsNone(e.mitglied)

    def test_manueller_eintrag_ohne_mitglied_und_name_wird_abgelehnt(self):
        r = self.client.post(reverse("schichteinsatz_add"), {"schicht": self.theke.pk, "name": "", "kontakt": "",
                                                             "bemerkung": ""})
        self.assertEqual(r.status_code, 200)   # Formular mit Fehler
        self.assertFalse(Schichteinsatz.objects.exists())


class OeffentlicheEintragungTests(SchichtBasis):
    def setUp(self):
        super().setUp()
        self.url = reverse("veranstaltung_helfer", args=[self.ver.rueckmeldung_code])

    def _post(self, **daten):
        return self.client.post(self.url, daten)

    def test_seite_ohne_anmeldung_erreichbar_mit_schichten_und_freien_plaetzen(self):
        self.einsatz(self.aufbau, name="Geheim Name")
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Aufbau")
        self.assertContains(r, "Theke")
        self.assertContains(r, "2 Plätze frei")   # Aufbau: 3 benoetigt, 1 vergeben
        self.assertNotContains(r, "Geheim Name")  # keine Namen anderer Helfer

    def test_nicht_freigegeben_oder_falscher_code_gibt_404(self):
        self.ver.helfer_eintragung = False
        self.ver.save()
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.ver.helfer_eintragung = True
        self.ver.save()
        import uuid
        self.assertEqual(self.client.get(reverse("veranstaltung_helfer", args=[uuid.uuid4()])).status_code, 404)

    def test_eintragen_legt_selbst_eingetragenen_einsatz_an(self):
        r = self._post(name="  Max   Muster ", kontakt="max@example.org", schicht=[self.aufbau.pk, self.theke.pk])
        self.assertContains(r, "Danke, Sie sind eingetragen")
        e = Schichteinsatz.objects.filter(name="Max Muster")
        self.assertEqual(e.count(), 2)
        self.assertTrue(all(x.selbst_eingetragen and x.kontakt == "max@example.org" and x.mitglied is None for x in e))
        self.assertEqual(self.aufbau.einsaetze.count(), 1)

    def test_doppelte_eintragung_derselben_person_wird_verhindert(self):
        self._post(name="Max Muster", schicht=[self.aufbau.pk])
        r = self._post(name="max muster", schicht=[self.aufbau.pk])
        self.assertContains(r, "bereits eingetragen")
        self.assertEqual(self.aufbau.einsaetze.count(), 1)

    def test_volle_schicht_wird_nicht_ueberbucht(self):
        self.einsatz(self.theke, name="A")
        self.einsatz(self.theke, name="B")
        r = self._post(name="Zu Spaet", schicht=[self.theke.pk, self.aufbau.pk])
        self.assertContains(r, "inzwischen voll")
        self.assertEqual(self.theke.einsaetze.count(), 2)
        self.assertEqual(self.aufbau.einsaetze.filter(name="Zu Spaet").count(), 1)   # die freie klappt trotzdem

    def test_ohne_name_oder_ohne_schicht_gibt_fehler_und_legt_nichts_an(self):
        self.assertContains(self._post(name="", schicht=[self.aufbau.pk]), "Bitte Ihren Namen angeben")
        self.assertContains(self._post(name="Max"), "mindestens eine Schicht")
        self.assertFalse(Schichteinsatz.objects.exists())

    def test_spam_falle_und_ungueltige_ids(self):
        self._post(name="Bot", website="http://spam", schicht=[self.aufbau.pk])
        self._post(name="Max", schicht=["abc"])
        self.assertFalse(Schichteinsatz.objects.exists())

    def test_schicht_einer_anderen_veranstaltung_wird_ignoriert(self):
        andere = Veranstaltung.objects.create(verein=self.v, titel="Andere", beginn=self.beginn)
        fremd = self.schicht("Fremd", 0, 2, ver=andere)
        self._post(name="Max", schicht=[fremd.pk])
        self.assertFalse(Schichteinsatz.objects.exists())

    def test_vergangene_schichten_werden_nicht_angezeigt_und_nicht_gebucht(self):
        alt = Schicht.objects.create(verein=self.v, veranstaltung=self.ver, bezeichnung="Gestern",
                                     beginn=timezone.now() - timedelta(days=2), ende=timezone.now() - timedelta(days=1),
                                     benoetigt=2)
        self.assertNotContains(self.client.get(self.url), "Gestern")
        self._post(name="Max", schicht=[alt.pk])
        self.assertFalse(alt.einsaetze.exists())

    def test_abgesagte_veranstaltung_ist_geschlossen(self):
        self.ver.status = "abgesagt"
        self.ver.save()
        self.assertContains(self.client.get(self.url), "geschlossen")
        self._post(name="Max", schicht=[self.aufbau.pk])
        self.assertFalse(Schichteinsatz.objects.exists())

    def test_eintragung_erscheint_im_schichtplan_pdf(self):
        self._post(name="Max Muster", kontakt="0151 999", schicht=[self.aufbau.pk])
        pdf = PdfReader(io.BytesIO(schichtplan_pdf(self.ver)))
        text = "\n".join(p.extract_text() for p in pdf.pages)
        self.assertIn("Max Muster (0151 999)", text)


class MitgliedFindenTests(SchichtBasis):
    def test_name_in_beliebiger_reihenfolge_schreibweise_und_mit_komma(self):
        for name in ("Erika Muster", "muster erika", "Muster, Erika", "  ERIKA   MUSTER "):
            self.assertEqual(finde_mitglied(self.v.pk, name), self.m, name)

    def test_umlaute_in_beiden_schreibweisen(self):
        m = Mitglied.objects.create(verein=self.v, vorname="Jürgen", nachname="Müller", mitgliedsnummer=9)
        for name in ("Jürgen Müller", "Juergen Mueller", "jurgen muller"[:0] + "Müller Jürgen"):
            self.assertEqual(finde_mitglied(self.v.pk, name), m, name)

    def test_bindestrich_nachname(self):
        m = Mitglied.objects.create(verein=self.v, vorname="Anna", nachname="Meier-Schmidt", mitgliedsnummer=10)
        self.assertEqual(finde_mitglied(self.v.pk, "Anna Meier Schmidt"), m)
        self.assertEqual(finde_mitglied(self.v.pk, "Anna Meier-Schmidt"), m)

    def test_unbekannt_oder_nur_teil_des_namens_ergibt_none(self):
        self.assertIsNone(finde_mitglied(self.v.pk, "Erika"))
        self.assertIsNone(finde_mitglied(self.v.pk, "Erika Beispiel"))
        self.assertIsNone(finde_mitglied(self.v.pk, ""))

    def test_ausgetretene_und_andere_vereine_zaehlen_nicht(self):
        self.m.status = "ausgetreten"
        self.m.save()
        self.assertIsNone(finde_mitglied(self.v.pk, "Erika Muster"))
        anderer = Verein.objects.create(name="Anderer e.V.", kuerzel="anderer")
        Mitglied.objects.create(verein=anderer, vorname="Fremd", nachname="Person", mitgliedsnummer=1)
        self.assertIsNone(finde_mitglied(self.v.pk, "Fremd Person"))

    def test_gleicher_name_zweimal_nur_mit_passender_nummer_eindeutig(self):
        zweiter = Mitglied.objects.create(verein=self.v, vorname="Erika", nachname="Muster", mitgliedsnummer=8)
        self.assertIsNone(finde_mitglied(self.v.pk, "Erika Muster"))           # nicht raten
        self.assertIsNone(finde_mitglied(self.v.pk, "Erika Muster", 99))        # falsche Nummer
        self.assertEqual(finde_mitglied(self.v.pk, "Erika Muster", 8), zweiter)
        self.assertEqual(finde_mitglied(self.v.pk, "Erika Muster", 7), self.m)

    def test_ruhende_mitglieder_werden_gefunden(self):
        self.m.status = "ruhend"
        self.m.save()
        self.assertEqual(finde_mitglied(self.v.pk, "Erika Muster"), self.m)


class SelbsteintragAlsMitgliedTests(SchichtBasis):
    def setUp(self):
        super().setUp()
        self.m.mobil, self.m.email = "0171 555", "erika@example.org"
        self.m.save()
        self.url = reverse("veranstaltung_helfer", args=[self.ver.rueckmeldung_code])

    def _post(self, **daten):
        return self.client.post(self.url, daten)

    def test_kaestchen_und_nummernfeld_sind_auf_der_seite(self):
        r = self.client.get(self.url)
        self.assertContains(r, "Ich bin Mitglied im Verein")
        self.assertContains(r, 'name="mitglied"')
        self.assertContains(r, 'name="mitgliedsnummer"')

    def test_mitglied_wird_zugeordnet_und_name_nicht_kopiert(self):
        r = self._post(name="Muster, Erika", mitglied="ja", schicht=[self.aufbau.pk])
        self.assertContains(r, "Danke, Sie sind eingetragen")
        e = Schichteinsatz.objects.get()
        self.assertEqual(e.mitglied, self.m)
        self.assertEqual(e.name, "")   # Name kommt aus der Mitgliedsakte (Anonymisierung wirkt)
        self.assertTrue(e.selbst_eingetragen and e.mitglied_angegeben)
        self.assertEqual(e.wer, "Erika Muster")
        self.assertEqual(e.zuordnung, "Mitglied")

    def test_oeffentliche_seite_verraet_nicht_ob_ein_mitglied_gefunden_wurde(self):
        gefunden = self._post(name="Erika Muster", mitglied="ja", schicht=[self.aufbau.pk]).content.decode()
        unbekannt = self._post(name="Unbekannt Person", mitglied="ja", schicht=[self.theke.pk]).content.decode()
        for seite in (gefunden, unbekannt):
            self.assertNotIn("0171 555", seite)
            self.assertNotIn("erika@example.org", seite)
            self.assertNotIn("1 Mitglied", seite)
        self.assertNotIn("Mitgliedsakte erkannt", gefunden)

    def test_ohne_kaestchen_bleibt_es_ein_gast_auch_bei_passendem_namen(self):
        self._post(name="Erika Muster", schicht=[self.aufbau.pk])
        e = Schichteinsatz.objects.get()
        self.assertIsNone(e.mitglied)
        self.assertEqual((e.name, e.mitglied_angegeben), ("Erika Muster", False))

    def test_kaestchen_aber_nicht_gefunden_bleibt_gast_mit_hinweis_zur_zuordnung(self):
        self._post(name="Unbekannt Person", mitglied="ja", schicht=[self.aufbau.pk])
        e = Schichteinsatz.objects.get()
        self.assertIsNone(e.mitglied)
        self.assertTrue(e.mitglied_angegeben)
        self.assertIn("bitte zuordnen", e.zuordnung)

    def test_zwei_gleichnamige_mitglieder_ohne_nummer_werden_nicht_geraten(self):
        Mitglied.objects.create(verein=self.v, vorname="Erika", nachname="Muster", mitgliedsnummer=8)
        self._post(name="Erika Muster", mitglied="ja", schicht=[self.aufbau.pk])
        self.assertIsNone(Schichteinsatz.objects.get().mitglied)
        self._post(name="Erika Muster", mitglied="ja", mitgliedsnummer="8", schicht=[self.theke.pk])
        zugeordnet = Schichteinsatz.objects.get(schicht=self.theke)
        self.assertEqual(zugeordnet.mitglied.mitgliedsnummer, 8)

    def test_ungueltige_mitgliedsnummer_stoert_nicht(self):
        self._post(name="Erika Muster", mitglied="ja", mitgliedsnummer="abc", schicht=[self.aufbau.pk])
        self.assertEqual(Schichteinsatz.objects.get().mitglied, self.m)

    def test_doppelte_eintragung_des_mitglieds_wird_verhindert(self):
        self._post(name="Erika Muster", mitglied="ja", schicht=[self.aufbau.pk])
        r = self._post(name="Muster Erika", mitglied="ja", schicht=[self.aufbau.pk])   # andere Schreibweise
        self.assertContains(r, "bereits eingetragen")
        self.assertEqual(Schichteinsatz.objects.count(), 1)

    def test_angegebener_kontakt_wird_beibehalten(self):
        self._post(name="Erika Muster", mitglied="ja", kontakt="privat 123", schicht=[self.aufbau.pk])
        self.assertEqual(Schichteinsatz.objects.get().kontakt, "privat 123")


class MitgliedskontaktSichtbarkeitTests(SchichtBasis):
    def setUp(self):
        super().setUp()
        self.m.mobil, self.m.telefon, self.m.email = "0171 555", "030 111", "erika@example.org"
        self.m.save()
        self.e = self.einsatz(self.aufbau, mitglied=self.m, selbst_eingetragen=True, mitglied_angegeben=True)

    def test_kontakt_anzeige_prioritaet_und_vorrang_des_angegebenen(self):
        self.assertEqual(self.e.kontakt_anzeige(False), "")
        self.assertEqual(self.e.kontakt_anzeige(True), "0171 555")   # Mobil vor Telefon vor E-Mail
        self.m.mobil = ""
        self.assertEqual(self.e.kontakt_anzeige(True), "030 111")
        self.m.telefon = ""
        self.assertEqual(self.e.kontakt_anzeige(True), "erika@example.org")
        self.e.kontakt = "angegeben"
        self.assertEqual(self.e.kontakt_anzeige(True), "angegeben")

    def test_pdf_nimmt_mitgliedskontakt_nur_auf_wunsch(self):
        def text(**kw):
            return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(schichtplan_pdf(self.ver, **kw))).pages)
        self.assertNotIn("0171 555", text())
        self.assertIn("Erika Muster (0171 555)", text(mit_mitgliedskontakt=True))

    def test_schichtseite_mit_recht_zeigt_mitgliedskontakt_ohne_recht_nicht(self):
        self.anmelden()
        r = self.client.get(reverse("schicht_detail", args=[self.aufbau.pk]))
        self.assertContains(r, "0171 555")
        self.assertContains(r, "Mitglied")
        User = get_user_model()
        u = User.objects.create_user("lena", password=PW)
        Zugang.objects.create(verein=self.v, user=u, rolle=Rolle.objects.create(
            verein=self.v, name="Nur Veranstaltungen", rechte=["veranstaltungen.view"]))
        self.client.login(username="lena", password=PW)
        r = self.client.get(reverse("schicht_detail", args=[self.aufbau.pk]))
        self.assertContains(r, "Erika Muster")
        self.assertNotContains(r, "0171 555")

    def test_pdf_ansicht_gibt_kontakt_nur_mit_mitglieder_recht_aus(self):
        url = reverse("veranstaltung_schichtplan_pdf", args=[self.ver.pk])
        self.anmelden()
        text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(self.client.get(url).content)).pages)
        self.assertIn("0171 555", text)
        User = get_user_model()
        u = User.objects.create_user("lena", password=PW)
        Zugang.objects.create(verein=self.v, user=u, rolle=Rolle.objects.create(
            verein=self.v, name="Nur Veranstaltungen", rechte=["veranstaltungen.view"]))
        self.client.login(username="lena", password=PW)
        text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(self.client.get(url).content)).pages)
        self.assertNotIn("0171 555", text)
        self.assertIn("Erika Muster", text)

    def test_zuordnung_nachtraeglich_durch_die_verwaltung(self):
        gast = self.einsatz(self.theke, name="Erika M.", mitglied_angegeben=True, selbst_eingetragen=True)
        self.anmelden()
        r = self.client.post(reverse("schichteinsatz_edit", args=[gast.pk]),
                             {"schicht": self.theke.pk, "mitglied": self.m.pk, "name": "", "kontakt": "", "bemerkung": ""})
        self.assertEqual(r.status_code, 302)
        gast.refresh_from_db()
        self.assertEqual(gast.zuordnung, "Mitglied")


class SchichtFreigabeTests(SchichtBasis):
    """Nur bestimmte Schichten fuer die Selbsteintragung freigeben."""

    def setUp(self):
        super().setUp()
        self.url = reverse("veranstaltung_helfer", args=[self.ver.rueckmeldung_code])
        self.theke.selbsteintrag = False   # nur der Aufbau ist freigegeben
        self.theke.save()

    def test_neue_und_bestehende_schichten_sind_standardmaessig_freigegeben(self):
        neu = self.schicht("Abbau", 9, 11)
        self.assertTrue(neu.selbsteintrag)
        self.assertTrue(self.aufbau.selbsteintrag)

    def test_oeffentliche_seite_zeigt_nur_freigegebene_schichten(self):
        r = self.client.get(self.url)
        self.assertContains(r, "Aufbau")
        self.assertNotContains(r, "Theke")

    def test_nicht_freigegebene_schicht_ist_nicht_buchbar(self):
        r = self.client.post(self.url, {"name": "Max Muster", "schicht": [self.theke.pk]})
        self.assertContains(r, "nicht (mehr) zur Eintragung freigegeben")
        self.assertFalse(self.theke.einsaetze.exists())

    def test_freigegebene_wird_gebucht_auch_wenn_eine_gesperrte_mitgewaehlt_wurde(self):
        r = self.client.post(self.url, {"name": "Max Muster", "schicht": [self.aufbau.pk, self.theke.pk]})
        self.assertContains(r, "Danke, Sie sind eingetragen")
        self.assertEqual(self.aufbau.einsaetze.count(), 1)
        self.assertEqual(self.theke.einsaetze.count(), 0)

    def test_ohne_freigegebene_schichten_hinweis_statt_formular(self):
        self.aufbau.selbsteintrag = False
        self.aufbau.save()
        r = self.client.get(self.url)
        self.assertContains(r, "keine Schichten zur Eintragung offen")
        self.assertNotContains(r, 'name="schicht"')

    def test_verwaltung_kann_gesperrte_schicht_trotzdem_besetzen(self):
        self.anmelden()
        r = self.client.post(reverse("schichteinsatz_add"), {"schicht": self.theke.pk, "name": "Von Hand",
                                                             "kontakt": "", "bemerkung": ""})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.theke.einsaetze.count(), 1)

    def test_freigabe_am_schichtformular(self):
        self.anmelden()
        r = self.client.post(reverse("schicht_edit", args=[self.theke.pk]), {
            "veranstaltung": self.ver.pk, "bezeichnung": "Theke",
            "beginn": self.theke.beginn.strftime("%Y-%m-%dT%H:%M"), "ende": self.theke.ende.strftime("%Y-%m-%dT%H:%M"),
            "benoetigt": 2, "selbsteintrag": "on"})
        self.assertEqual(r.status_code, 302)
        self.theke.refresh_from_db()
        self.assertTrue(self.theke.selbsteintrag)

    def test_veranstaltungsseite_zeigt_spalte_zaehlung_und_sammelknoepfe(self):
        self.anmelden()
        r = self.client.get(reverse("veranstaltung_detail", args=[self.ver.pk]))
        self.assertContains(r, "Selbsteintrag")
        self.assertContains(r, "1 von 2 Schichten sind für den Selbsteintrag freigegeben.")
        self.assertContains(r, "Alle Schichten für Selbsteintrag freigeben")
        self.assertContains(r, "Alle Schichten für Selbsteintrag sperren")

    def test_ohne_helfer_eintragung_keine_freigabe_elemente(self):
        self.anmelden()
        self.ver.helfer_eintragung = False
        self.ver.save()
        r = self.client.get(reverse("veranstaltung_detail", args=[self.ver.pk]))
        self.assertNotContains(r, "für den Selbsteintrag freigegeben")
        self.assertNotContains(r, "Alle Schichten für Selbsteintrag")

    def test_alle_freigeben_und_alle_sperren(self):
        self.anmelden()
        self.client.post(reverse("veranstaltung_schichten_freigabe", args=[self.ver.pk, "alle"]))
        self.assertEqual(self.ver.schichten.filter(selbsteintrag=True).count(), 2)
        self.client.post(reverse("veranstaltung_schichten_freigabe", args=[self.ver.pk, "keine"]))
        self.assertEqual(self.ver.schichten.filter(selbsteintrag=True).count(), 0)

    def test_sammelaktion_nur_per_post_mit_recht_und_im_eigenen_verein(self):
        url = reverse("veranstaltung_schichten_freigabe", args=[self.ver.pk, "alle"])
        self.anmelden()
        self.assertEqual(self.client.get(url).status_code, 405)                       # nur POST
        self.assertEqual(self.client.post(reverse("veranstaltung_schichten_freigabe",
                                                  args=[self.ver.pk, "unsinn"])).status_code, 403)
        anderer = Verein.objects.create(name="Anderer e.V.", kuerzel="anderer")
        fremd = Veranstaltung.objects.create(verein=anderer, titel="Fremd", beginn=self.beginn)
        self.assertEqual(self.client.post(reverse("veranstaltung_schichten_freigabe",
                                                  args=[fremd.pk, "alle"])).status_code, 404)
        User = get_user_model()
        u = User.objects.create_user("lena", password=PW)
        Zugang.objects.create(verein=self.v, user=u, rolle=Rolle.objects.create(
            verein=self.v, name="Nur Lesen", rechte=["veranstaltungen.view"]))
        self.client.login(username="lena", password=PW)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.theke.refresh_from_db()
        self.assertFalse(self.theke.selbsteintrag)
