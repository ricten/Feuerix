"""Layout je Vorlage (Variante B): Briefkopf, Schrift, Raender, Fusszeile der PDFs aus Vorlagen."""
from io import BytesIO

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from pypdf import PdfReader

from apps.core.models import Rolle, Verein, Zugang
from apps.core.pdf import Layout, seiten_pdf
from apps.members.models import Mitglied

from .models import Schriftstueck, Serienbrief, Vorlage
from .pdf import schriftstueck_pdf, serienbrief_pdf

PW = "pw-Test-12345"
SEITE = {"empfaenger": ["Max Mustermann", "Weg 1"], "betreff": "Betreffzeile", "datum": "Datum: 01.01.2026",
         "vor": ["Hallo Welt."]}


def text(pdf):
    return "\n".join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages)


def position(pdf, wort):
    """(x, y) des ersten Textstuecks, das `wort` enthaelt (Seite 1)."""
    treffer = []

    def besuch(t, cm, tm, fd, fs):
        if wort in t and not treffer:
            treffer.append((tm[4] * cm[0] + tm[5] * cm[2] + cm[4], tm[4] * cm[1] + tm[5] * cm[3] + cm[5]))
    PdfReader(BytesIO(pdf)).pages[0].extract_text(visitor_text=besuch)
    return treffer[0]


class LayoutPdfTests(TestCase):
    def setUp(self):
        self.verein = Verein.objects.create(name="Beispielverein e.V.", kuerzel="test", anschrift="Hauptstr. 1",
                                            plz="12345", ort="Musterstadt", email="info@example.org")

    def pdf(self, **kw):
        return seiten_pdf(self.verein, [SEITE], layout=Layout(**kw))

    def test_standardlayout_ist_unveraendert(self):
        a = PdfReader(BytesIO(seiten_pdf(self.verein, [SEITE]))).pages[0].get_contents().get_data()
        b = PdfReader(BytesIO(self.pdf())).pages[0].get_contents().get_data()
        self.assertEqual(a, b)

    def test_briefkopf_varianten(self):
        nur_kopf = dict(fuss="ohne", absenderzeile=False)
        self.assertEqual(text(self.pdf(kopf="voll", **nur_kopf)).count("Beispielverein"), 1)
        self.assertEqual(text(self.pdf(kopf="name", **nur_kopf)).count("Beispielverein"), 1)
        self.assertEqual(text(self.pdf(kopf="logo", **nur_kopf)).count("Beispielverein"), 0)   # ohne Logo-Datei: leer
        self.assertEqual(text(self.pdf(kopf="ohne", **nur_kopf)).count("Beispielverein"), 0)

    def test_absenderzeile_und_fusszeile_abschaltbar(self):
        voll = text(self.pdf(kopf="ohne"))
        self.assertIn("Hauptstr. 1", voll)          # Absenderzeile
        self.assertIn("info@example.org", voll)      # Fusszeile
        self.assertNotIn("Hauptstr. 1", text(self.pdf(kopf="ohne", absenderzeile=False, fuss="ohne")))
        self.assertIn("Hauptstr. 1", text(self.pdf(kopf="ohne", fuss="ohne")))
        self.assertNotIn("info@example.org", text(self.pdf(kopf="ohne", fuss="ohne")))
        nur_seite = text(self.pdf(kopf="ohne", fuss="seitenzahl"))
        self.assertIn("Seite 1", nur_seite)
        self.assertNotIn("info@example.org", nur_seite)

    def test_fusszeile_ohne_vereinsnamen(self):
        kopf_aus = dict(kopf="ohne", absenderzeile=False)
        mit = text(self.pdf(fuss="voll", **kopf_aus))
        ohne = text(self.pdf(fuss="ohne_name", **kopf_aus))
        self.assertIn("Beispielverein", mit)
        self.assertNotIn("Beispielverein", ohne)           # Vereinsname fehlt in der Fusszeile
        self.assertIn("info@example.org", ohne)             # uebrige Angaben bleiben
        self.assertIn("Seite 1", ohne)

    def test_fusszeile_ohne_name_und_ohne_weitere_angaben_zeigt_nur_seitenzahl(self):
        v = Verein.objects.create(name="Demo e.V.", kuerzel="demo")
        pdf = seiten_pdf(v, [SEITE], layout=Layout(kopf="ohne", absenderzeile=False, fuss="ohne_name"))
        t = text(pdf)
        self.assertNotIn("Demo e.V.", t)
        self.assertIn("Seite 1", t)
        self.assertIn("Demo e.V.", text(seiten_pdf(v, [SEITE], layout=Layout(kopf="ohne", absenderzeile=False))))

    def test_absenderzeile_entfaellt_wenn_sie_nur_den_vereinsnamen_enthielte(self):
        v = Verein.objects.create(name="Demo e.V.", kuerzel="demo")          # keine Anschrift hinterlegt
        zaehlt = lambda ver: text(seiten_pdf(ver, [SEITE], layout=Layout())).count(ver.name)  # noqa: E731
        self.assertEqual(zaehlt(v), 2)               # Briefkopf + Fusszeile, keine wiederholende Absenderzeile
        v.anschrift, v.plz, v.ort = "Hauptstr. 1", "12345", "Musterstadt"
        v.save()
        self.assertEqual(zaehlt(v), 3)               # mit Anschrift: Briefkopf + Absenderzeile + Fusszeile

    def test_schriftart_und_groesse(self):
        self.assertIn(b"Times-Roman", self.pdf(schriftart="Times-Roman"))
        self.assertIn(b"Courier", self.pdf(schriftart="Courier"))
        self.assertNotIn(b"Times-Roman", self.pdf())
        self.assertNotIn(b"Courier", self.pdf(schriftart="Unbekannt"))     # ungueltige Schrift -> Standard
        _, y_klein = position(self.pdf(kopf="ohne", schriftgroesse=9), "Hallo")
        _, y_gross = position(self.pdf(kopf="ohne", schriftgroesse=14), "Hallo")
        self.assertNotEqual(y_klein, y_gross)

    def test_raender(self):
        x25, _ = position(self.pdf(kopf="ohne"), "Max")
        x40, _ = position(self.pdf(kopf="ohne", rand_links_mm=40), "Max")
        self.assertGreater(x40, x25 + 30)
        _, y45 = position(self.pdf(kopf="ohne"), "Max")
        _, y70 = position(self.pdf(kopf="ohne", rand_oben_mm=70), "Max")
        self.assertLess(y70, y45 - 40)

    def test_datum_links(self):
        x_rechts, _ = position(self.pdf(kopf="ohne"), "Datum:")
        x_links, _ = position(self.pdf(kopf="ohne", datum_position="links"), "Datum:")
        self.assertLess(x_links, x_rechts - 100)

    def test_logo_links_und_rechts_bauen_ohne_fehler(self):
        for lp in ("rechts", "links"):
            for kopf in ("voll", "name", "logo", "ohne"):
                self.assertTrue(self.pdf(kopf=kopf, logo_position=lp).startswith(b"%PDF"))


class VorlagenLayoutTests(TestCase):
    def setUp(self):
        self.verein = Verein.objects.create(name="Beispielverein e.V.", kuerzel="test")
        self.admin = get_user_model().objects.create_superuser("admin", password=PW)
        Zugang.objects.create(verein=self.verein, user=self.admin,
                              rolle=Rolle.objects.get(verein=self.verein, name="Superadministrator"))
        self.client.force_login(self.admin)

    def test_layout_aus_vorlage(self):
        v = Vorlage.objects.create(verein=self.verein, name="Eigen", text="x", layout_kopf="ohne", layout_schriftart="Courier",
                                   layout_schriftgroesse=12, layout_rand_links=30, layout_fuss="seitenzahl",
                                   layout_absenderzeile=False, layout_datum_position="links")
        lay = Layout.von_vorlage(v)
        self.assertEqual((lay.kopf, lay.schriftart, lay.schriftgroesse, lay.fuss, lay.absenderzeile, lay.datum_position),
                         ("ohne", "Courier", 12.0, "seitenzahl", False, "links"))
        self.assertEqual(Layout.von_vorlage(None).kopf, "voll")

    def test_schriftstueck_und_serienbrief_nutzen_vorlagenlayout(self):
        v = Vorlage.objects.create(verein=self.verein, name="Courier", text="x", layout_schriftart="Courier")
        s = Schriftstueck.objects.create(verein=self.verein, titel="A", betreff="B", text="Text", vorlage=v)
        self.assertIn(b"Courier", schriftstueck_pdf(s))
        s_ohne = Schriftstueck.objects.create(verein=self.verein, titel="A2", betreff="B", text="Text")
        self.assertNotIn(b"Courier", schriftstueck_pdf(s_ohne))
        m = Mitglied.objects.create(verein=self.verein, vorname="A", nachname="B", status="aktiv")
        sb = Serienbrief.objects.create(verein=self.verein, titel="S", betreff="B", text="Text", vorlage=v)
        self.assertIn(b"Courier", serienbrief_pdf(sb, [m]))

    def test_formular_zeigt_layout_abschnitte_und_prueft_werte(self):
        r = self.client.get(reverse("vorlage_add"))
        self.assertContains(r, "Layout: Briefkopf und Seite")
        self.assertContains(r, "Layout: Schrift und Ränder")
        daten = {"name": "N", "art": "brief", "text": "x", "layout_kopf": "voll", "layout_logo_position": "rechts",
                 "layout_datum_position": "rechts", "layout_fuss": "voll", "layout_schriftart": "Helvetica",
                 "layout_schriftgroesse": "30", "layout_rand_links": "25", "layout_rand_rechts": "10",
                 "layout_rand_oben": "45", "layout_rand_unten": "28", "layout_absenderzeile": "on", "aktiv": "on"}
        r = self.client.post(reverse("vorlage_add"), daten)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Vorlage.objects.filter(name="N").exists())
        daten["layout_schriftgroesse"] = "11"
        r = self.client.post(reverse("vorlage_add"), daten)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Vorlage.objects.get(name="N").layout_schriftgroesse, 11)

    def test_vorschau_pdf(self):
        v = Vorlage.objects.create(verein=self.verein, name="Vorschau", betreff="Betreff {verein}", text="Hallo {verein}",
                                   layout_kopf="ohne")
        r = self.client.get(reverse("vorlage_vorschau", args=[v.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        t = text(r.content)
        self.assertIn("Max Mustermann", t)
        self.assertIn("Hallo Beispielverein e.V.", t)
        self.assertContains(self.client.get(reverse("vorlage_detail", args=[v.pk])), "Layout-Vorschau (PDF)")

    def test_vorschau_nur_im_eigenen_verein(self):
        v2 = Verein.objects.create(name="Anderer", kuerzel="anders")
        fremd = Vorlage.objects.create(verein=v2, name="Fremd", text="x")
        s = self.client.session
        s["verein_id"] = self.verein.pk
        s.save()
        self.assertEqual(self.client.get(reverse("vorlage_vorschau", args=[fremd.pk])).status_code, 404)


class DetailMitVorschauTests(TestCase):
    """Detailseiten mit PDF-Vorschau: Vorschau rechts neben den Feldern, seitenbreit und ohne Seitenleiste."""

    def setUp(self):
        self.verein = Verein.objects.create(name="Beispielverein e.V.", kuerzel="test")
        admin = get_user_model().objects.create_superuser("admin", password=PW)
        Zugang.objects.create(verein=self.verein, user=admin,
                              rolle=Rolle.objects.get(verein=self.verein, name="Superadministrator"))
        self.client.force_login(admin)

    def test_schriftstueck_detail_mit_nebeneinander_layout(self):
        s = Schriftstueck.objects.create(verein=self.verein, titel="Mein Brief", betreff="B", text="<p>x</p>")
        html = self.client.get(reverse("schriftstueck_detail", args=[s.pk])).content.decode()
        self.assertIn("vorschau-sticky", html)
        self.assertIn('class="vorschau-pdf"', html)
        self.assertIn("#view=FitH&amp;navpanes=0", html)
        self.assertIn("col-xl-5", html)
        self.assertIn("Mein Brief", html)                         # Felder stehen links
        self.assertLess(html.index("Mein Brief"), html.index("vorschau-pdf"))
        self.assertEqual(html.count("<iframe"), 1)

    def test_serienbrief_detail_zeigt_empfaengerliste_links_neben_der_vorschau(self):
        from apps.members.models import Mitglied
        Mitglied.objects.create(verein=self.verein, vorname="A", nachname="B", status="aktiv")
        sb = Serienbrief.objects.create(verein=self.verein, titel="Rundbrief", betreff="B", text="<p>x</p>")
        html = self.client.get(reverse("serienbrief_detail", args=[sb.pk])).content.decode()
        self.assertIn("Empfängerliste", html)
        self.assertLess(html.index("Empfängerliste"), html.index("vorschau-pdf"))

    def test_seiten_ohne_vorschau_behalten_das_alte_layout(self):
        v = Vorlage.objects.create(verein=self.verein, name="V", text="<p>x</p>")
        html = self.client.get(reverse("vorlage_detail", args=[v.pk])).content.decode()
        self.assertIn("vorschau-pdf", html)                        # Vorlage hat die Layout-Vorschau
        from apps.members.models import Abteilung
        a = Abteilung.objects.create(verein=self.verein, name="Zug 1")
        html = self.client.get(reverse("abteilung_detail", args=[a.pk])).content.decode()
        self.assertNotIn("vorschau-pdf", html)
        self.assertIn("col-xl-4", html)
