import io
import shutil
import tempfile
import uuid
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image
from pypdf import PdfReader
from reportlab.lib.units import mm

from apps.core.models import Rolle, Verein, Zugang
from apps.inventory.models import Gegenstand, Lagerort, Verleih
from apps.inventory.pdf import (_etikett_layout, _etikett_modus, _logo_platz, etiketten_pdf, logo_schwarzweiss,
                                packliste_pdf)
from apps.members.models import Mitglied

PW = "pw-Test-12345"


class VerleihBasis(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        User = get_user_model()
        admin = User.objects.create_superuser("admin", password=PW)
        Zugang.objects.create(verein=self.v, user=admin, rolle=Rolle.objects.get(verein=self.v,
                                                                                  name="Superadministrator"))
        self.client.login(username="admin", password=PW)
        self.m = Mitglied.objects.create(verein=self.v, vorname="Erika", nachname="Muster", mitgliedsnummer=7)
        self.lager = Lagerort.objects.create(verein=self.v, name="Keller")
        self.zelt = self.gegenstand("Zelt", lagerort=self.lager)
        self.tisch = self.gegenstand("Tisch")
        self.stuhl = self.gegenstand("Stuhl")
        self.bank = self.gegenstand("Bank")
        heute = date.today()
        self.von, self.bis = heute + timedelta(days=1), heute + timedelta(days=3)

    def gegenstand(self, bez, **kw):
        return Gegenstand.objects.create(verein=self.v, bezeichnung=bez, verleihbar=True, **kw)

    def verleih(self, g, vorgang=None, status="reserviert", **kw):
        return Verleih.objects.create(verein=self.v, gegenstand=g, vorgang=vorgang, entleiher=self.m, von=self.von,
                                      bis=self.bis, status=status, **kw)

    def vorgang(self, gegenstaende, status="reserviert"):
        vorgang = uuid.uuid4()
        return vorgang, [self.verleih(g, vorgang, status) for g in gegenstaende]


class UebersichtGruppiertTests(VerleihBasis):
    def test_ein_vorgang_ist_eine_zeile_einzelverleih_bleibt_einzeln(self):
        vorgang, positionen = self.vorgang([self.zelt, self.tisch, self.stuhl])
        einzel = self.verleih(self.bank)
        r = self.client.get(reverse("verleih_list"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.context["zeilen"]), 2)   # Vorgang + Einzelverleih statt 4 Zeilen
        urls = [z["url"] for z in r.context["zeilen"]]
        self.assertIn(reverse("verleih_vorgang_detail", args=[vorgang]), urls)
        self.assertIn(reverse("verleih_detail", args=[einzel.pk]), urls)
        for p in positionen:
            self.assertNotIn(reverse("verleih_detail", args=[p.pk]), urls)

    def test_zeile_zeigt_anzahl_und_gegenstaende(self):
        self.vorgang([self.zelt, self.tisch, self.stuhl])
        r = self.client.get(reverse("verleih_list"))
        self.assertContains(r, "3 Gegenstände: Stuhl, Tisch, Zelt")

    def test_viele_gegenstaende_werden_gekuerzt(self):
        self.vorgang([self.zelt, self.tisch, self.stuhl, self.bank])
        self.assertContains(self.client.get(reverse("verleih_list")), "4 Gegenstände: Bank, Stuhl, Tisch …")

    def test_status_gemeinsam_oder_aufgeschluesselt(self):
        vorgang, pos = self.vorgang([self.zelt, self.tisch])
        self.assertContains(self.client.get(reverse("verleih_list")), "Reserviert")
        pos[0].status = "ausgegeben"
        pos[0].save()
        self.assertContains(self.client.get(reverse("verleih_list")), "1 reserviert, 1 ausgegeben")

    def test_suche_nach_einem_gegenstand_findet_den_ganzen_vorgang_einmal(self):
        self.vorgang([self.zelt, self.tisch, self.stuhl])
        r = self.client.get(reverse("verleih_list"), {"q": "Tisch"})
        self.assertEqual(len(r.context["zeilen"]), 1)

    def test_filter_wirkt_vor_dem_zusammenfassen(self):
        vorgang, pos = self.vorgang([self.zelt, self.tisch, self.stuhl])
        pos[2].status = "ausgegeben"
        pos[2].save()
        r = self.client.get(reverse("verleih_list"), {"status": "ausgegeben"})
        self.assertEqual(len(r.context["zeilen"]), 1)
        self.assertEqual(r.context["zeilen"][0]["url"], reverse("verleih_vorgang_detail", args=[vorgang]))

    def test_vorgaenge_verschiedener_vereine_vermischen_sich_nicht(self):
        self.vorgang([self.zelt, self.tisch])
        anderer = Verein.objects.create(name="Anderer e.V.", kuerzel="anderer")
        g1 = Gegenstand.objects.create(verein=anderer, bezeichnung="Fremd 1", verleihbar=True)
        g2 = Gegenstand.objects.create(verein=anderer, bezeichnung="Fremd 2", verleihbar=True)
        fremd = uuid.uuid4()
        for g in (g1, g2):
            Verleih.objects.create(verein=anderer, gegenstand=g, vorgang=fremd, entleiher_name="X", von=self.von,
                                   bis=self.bis)
        r = self.client.get(reverse("verleih_list"))
        self.assertEqual(len(r.context["zeilen"]), 1)

    def test_export_hat_eine_zeile_je_vorgang(self):
        self.vorgang([self.zelt, self.tisch, self.stuhl])
        r = self.client.get(reverse("verleih_list"), {"export": "csv"})
        zeilen = r.content.decode("utf-8-sig").strip().splitlines()
        self.assertEqual(len(zeilen), 2)   # Kopf + ein Vorgang
        self.assertIn("3 Gegenstände", zeilen[1])

    def test_einzelverleih_zeigt_den_gegenstand(self):
        self.verleih(self.zelt)
        self.assertContains(self.client.get(reverse("verleih_list")), self.zelt.inventarnummer)


class PacklisteTests(VerleihBasis):
    def _text(self, antwort):
        self.assertEqual(antwort.status_code, 200)
        self.assertEqual(antwort["Content-Type"], "application/pdf")
        return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(antwort.content)).pages)

    def test_packliste_zum_vorgang_enthaelt_alle_positionen_mit_ankreuzfeldern(self):
        vorgang, _pos = self.vorgang([self.zelt, self.tisch, self.stuhl])
        text = self._text(self.client.get(reverse("verleih_vorgang_packliste", args=[vorgang])))
        self.assertIn("Packliste", text)
        for g in (self.zelt, self.tisch, self.stuhl):
            self.assertIn(g.inventarnummer, text)
            self.assertIn(g.bezeichnung, text)
        self.assertIn("Erika Muster", text)
        self.assertIn("Keller", text)   # Lagerort
        self.assertEqual(text.count("[ ]"), 6)   # je Position Ausgabe + Rueckgabe
        self.assertIn("Anzahl Positionen: 3", text)
        self.assertIn(f"{self.von:%d.%m.%Y}", text)

    def test_packliste_ist_nach_lagerort_und_name_sortiert(self):
        _vorgang, pos = self.vorgang([self.stuhl, self.zelt, self.tisch])
        pdf = packliste_pdf(pos)
        text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
        # ohne Lagerort zuerst (leer sortiert vorn): Stuhl, Tisch; dann Keller: Zelt
        self.assertLess(text.index("Stuhl"), text.index("Tisch"))
        self.assertLess(text.index("Tisch"), text.index("Zelt"))

    def test_packliste_zum_einzelverleih(self):
        v = self.verleih(self.zelt)
        text = self._text(self.client.get(reverse("verleih_packliste", args=[v.pk])))
        self.assertIn(self.zelt.inventarnummer, text)
        self.assertIn("Anzahl Positionen: 1", text)

    def test_knoepfe_an_vorgang_und_einzelverleih(self):
        vorgang, pos = self.vorgang([self.zelt, self.tisch])
        self.assertContains(self.client.get(reverse("verleih_vorgang_detail", args=[vorgang])), "Packliste drucken")
        self.assertContains(self.client.get(reverse("verleih_detail", args=[pos[0].pk])), "Packliste drucken")

    def test_fremder_vorgang_gibt_404(self):
        self.assertEqual(self.client.get(reverse("verleih_vorgang_packliste", args=[uuid.uuid4()])).status_code, 404)

    def test_ohne_anmeldung_umgeleitet(self):
        vorgang, _ = self.vorgang([self.zelt])
        self.client.logout()
        self.assertEqual(self.client.get(reverse("verleih_vorgang_packliste", args=[vorgang])).status_code, 302)


def _png(pfad_name="logo.png"):
    puffer = io.BytesIO()
    Image.new("RGB", (200, 100), (175, 43, 30)).save(puffer, "PNG")
    return pfad_name, ContentFile(puffer.getvalue())


class EtikettLogoTests(TestCase):
    def setUp(self):
        self._media = tempfile.mkdtemp()
        ueb = override_settings(MEDIA_ROOT=self._media)
        ueb.enable()
        self.addCleanup(ueb.disable)
        self.addCleanup(shutil.rmtree, self._media, True)
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.g = Gegenstand.objects.create(verein=self.v, bezeichnung="Zelt")

    def _pdf(self, verein):
        return etiketten_pdf([self.g], lambda nr: f"https://x/{nr}", verein)

    def test_ohne_logo_kein_bild_im_etikett(self):
        self.assertNotIn(b"/Subtype /Image", self._pdf(self.v))

    def test_mit_logo_steht_es_auf_dem_standardetikett(self):
        self.v.logo.save(*_png(), save=True)
        self.assertIn(b"/Subtype /Image", self._pdf(self.v))

    def test_ohne_verein_funktioniert_wie_bisher(self):
        self.assertTrue(etiketten_pdf([self.g], lambda nr: "u").startswith(b"%PDF"))

    def test_platz_fuer_das_logo_nur_wenn_gross_genug(self):
        def platz(b, h):
            gedreht, neben, zb, zh = _etikett_modus(b * mm, h * mm)
            return _logo_platz(_etikett_layout(zb, zh, neben), neben, zb, zh)
        self.assertIsNotNone(platz(58, 40))     # Standard-Etikettenbogen
        self.assertIsNone(platz(25, 25))        # zu klein
        p = platz(58, 40)
        self.assertGreaterEqual(p[2], 7 * mm)
        self.assertGreaterEqual(p[3], 7 * mm)

    def test_logo_liegt_ausserhalb_von_qr_code_und_textfeld(self):
        b, h = 58 * mm, 40 * mm
        layout = _etikett_layout(b, h, False)
        x, y, w, hoehe = _logo_platz(layout, False, b, h)
        self.assertLessEqual(x + w, layout["qr_x"])   # links neben dem QR-Code
        self.assertGreaterEqual(y, layout["text_unten_y"] + layout["text_hoehe"])   # oberhalb des Textfelds
        self.assertLessEqual(y + hoehe, h)

    def test_kleines_etikett_ohne_platz_zeichnet_kein_logo_ohne_fehler(self):
        self.v.logo.save(*_png(), save=True)
        self.v.etikett_spalten, self.v.etikett_zeilen = 1, 1
        self.v.etikett_breite_mm, self.v.etikett_hoehe_mm = 25, 25
        self.assertNotIn(b"/Subtype /Image", self._pdf(self.v))

    def test_breites_flaches_etikett_nebeneinander(self):
        self.v.logo.save(*_png(), save=True)
        self.v.etikett_spalten, self.v.etikett_zeilen = 1, 1
        self.v.etikett_breite_mm, self.v.etikett_hoehe_mm = 89, 36   # z. B. Dymo-Rolle
        self.assertTrue(self._pdf(self.v).startswith(b"%PDF"))   # kein Fehler, mit oder ohne Logo je nach Platz


class VorgangKopfTests(VerleihBasis):
    def test_kopfkarte_mit_entleiher_zeitraum_positionen_und_summen(self):
        vorgang = uuid.uuid4()
        for g, gebuehr, kaution in ((self.zelt, "10.00", "50.00"), (self.tisch, "5.50", "0")):
            self.verleih(g, vorgang, leihgebuehr=gebuehr, kaution=kaution)
        r = self.client.get(reverse("verleih_vorgang_detail", args=[vorgang]))
        for erwartet in ("Erika Muster", f"{self.von:%d.%m.%Y} – {self.bis:%d.%m.%Y}", "Positionen", "Leihgebühr gesamt",
                         "15,50", "Kaution gesamt", "50,00"):
            self.assertContains(r, erwartet)

    def test_kopfkarte_ohne_gebuehr_ohne_summenzeilen(self):
        vorgang, _ = self.vorgang([self.zelt, self.tisch])
        r = self.client.get(reverse("verleih_vorgang_detail", args=[vorgang]))
        self.assertNotContains(r, "Leihgebühr gesamt")
        self.assertNotContains(r, "Kaution gesamt")


class EtikettLogoGroesseUndFarbeTests(TestCase):
    def setUp(self):
        self._media = tempfile.mkdtemp()
        ueb = override_settings(MEDIA_ROOT=self._media)
        ueb.enable()
        self.addCleanup(ueb.disable)
        self.addCleanup(shutil.rmtree, self._media, True)
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.g = Gegenstand.objects.create(verein=self.v, bezeichnung="Zelt")

    def _farbiges_logo(self, modus="RGB", farbe=(175, 43, 30)):
        puffer = io.BytesIO()
        Image.new(modus, (200, 100), farbe).save(puffer, "PNG")
        self.v.logo.save("logo.png", ContentFile(puffer.getvalue()), save=True)
        return self.v.logo.path

    def test_logo_wird_in_graustufen_umgewandelt(self):
        bild = logo_schwarzweiss(self._farbiges_logo())
        self.assertEqual(bild.mode, "L")   # kein Farbkanal mehr

    def test_transparenz_wird_weiss_nicht_schwarz(self):
        bild = logo_schwarzweiss(self._farbiges_logo("RGBA", (0, 0, 0, 0)))   # komplett durchsichtig
        self.assertEqual(bild.getpixel((10, 10)), 255)

    def test_unlesbare_datei_gibt_none(self):
        self.assertIsNone(logo_schwarzweiss("/gibt/es/nicht.png"))

    def test_pdf_enthaelt_graustufenbild_ohne_farbbild(self):
        self._farbiges_logo()
        pdf = etiketten_pdf([self.g], lambda nr: "u", self.v)
        self.assertIn(b"/Subtype /Image", pdf)
        self.assertIn(b"/DeviceGray", pdf)
        self.assertNotIn(b"/DeviceRGB", pdf.split(b"/Subtype /Image")[1].split(b"endobj")[0])   # das Bild selbst

    def test_mit_logo_sitzt_der_qr_code_rechts_und_das_logo_hat_viel_platz(self):
        b, h = 58 * mm, 40 * mm
        ohne = _etikett_layout(b, h, False)
        mit = _etikett_layout(b, h, False, mit_logo=True)
        self.assertGreater(mit["qr_x"], ohne["qr_x"])            # QR-Code nach rechts gerueckt
        self.assertEqual(mit["qr_groesse"], ohne["qr_groesse"])
        x, y, w, hoehe = _logo_platz(mit, False, b, h)
        self.assertGreaterEqual(w, 20 * mm)                      # deutlich mehr als zuvor (ca. 13 mm)
        self.assertLessEqual(x + w, mit["qr_x"])                 # nichts ueberlappt den QR-Code

    def test_qr_code_ist_groesser_geworden(self):
        l = _etikett_layout(58 * mm, 40 * mm, False)
        self.assertGreaterEqual(l["qr_groesse"], 23.5 * mm)

    def test_ohne_platz_bleibt_der_qr_code_mittig(self):
        self._farbiges_logo()
        self.v.etikett_spalten, self.v.etikett_zeilen = 1, 1
        self.v.etikett_breite_mm, self.v.etikett_hoehe_mm = 25, 25
        self.assertNotIn(b"/Subtype /Image", etiketten_pdf([self.g], lambda nr: "u", self.v))
