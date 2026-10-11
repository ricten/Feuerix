import io
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader

from apps.core.models import Rolle, Verein, Zugang
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
        self.assertContains(r, "Helfer-Link zum Weitergeben")

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
