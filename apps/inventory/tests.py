import uuid
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from reportlab.lib.units import mm

from apps.core.models import Rolle, Verein, Zugang
from apps.events.models import Veranstaltung
from apps.finance.models import Rechnung
from apps.inventory import importer
from apps.inventory.models import Gegenstand, Inventur, Inventurposition, Lagerort, Verleih
from apps.inventory.pdf import _etikett_layout, _etikett_modus, etiketten_pdf
from apps.members.models import Mitglied

CSV = ("Bezeichnung;Hersteller;Zustand;Verleihbar\n"
       "Beamer Epson;Epson;gut;ja\n").encode("utf-8")


class ImportTests(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")

    def test_testlauf_speichert_nichts(self):
        b = importer.importieren(self.v, "i.csv", CSV, testlauf=True)
        self.assertEqual((b["neu"], len(b["fehler"])), (1, 0))
        self.assertEqual(Gegenstand.objects.filter(verein=self.v).count(), 0)

    def test_import_und_aktualisierung(self):
        b = importer.importieren(self.v, "i.csv", CSV, testlauf=False)
        self.assertEqual(b["neu"], 1)
        g = Gegenstand.objects.get(verein=self.v)
        self.assertEqual((g.bezeichnung, g.hersteller, g.verleihbar), ("Beamer Epson", "Epson", True))
        self.assertTrue(g.inventarnummer.startswith("INV-"))
        update = f"Inventarnummer;Bezeichnung;Notizen\n{g.inventarnummer};Beamer Epson;Neu erhalten\n".encode("utf-8")
        b = importer.importieren(self.v, "u.csv", update, testlauf=False)
        self.assertEqual((b["neu"], b["aktualisiert"]), (0, 1))
        g.refresh_from_db()
        self.assertEqual(g.notizen, "Neu erhalten")
        self.assertEqual(g.hersteller, "Epson")  # leere Zelle überschreibt nichts

    def test_fehlerhafte_zeile_wird_gemeldet(self):
        daten = "Bezeichnung;Zustand\nStuhl;gut\n;kaputt\nBank;unbekannt\n".encode("utf-8")
        b = importer.importieren(self.v, "f.csv", daten, testlauf=False)
        self.assertEqual(b["neu"], 1)
        self.assertEqual(len(b["fehler"]), 2)

    def test_unbekannte_kategorie(self):
        daten = "Bezeichnung;Kategorie\nZelt;Gibtsnicht\n".encode("utf-8")
        self.assertEqual(len(importer.importieren(self.v, "a.csv", daten, testlauf=True)["fehler"]), 1)
        b = importer.importieren(self.v, "a.csv", daten, testlauf=False, neu_anlegen=True)
        self.assertEqual((b["neu"], len(b["fehler"])), (1, 0))

    def test_datenbankfehler_in_einer_zeile_bricht_import_nicht_ab(self):
        daten = "Bezeichnung\nFehler\nOk\n".encode("utf-8")
        orig_save = Gegenstand.save

        def kaputt_bei_fehler(self, *a, **kw):
            if self.bezeichnung == "Fehler":
                raise ValueError("simulierter Datenbankfehler")
            return orig_save(self, *a, **kw)

        with patch.object(Gegenstand, "save", kaputt_bei_fehler):
            b = importer.importieren(self.v, "x.csv", daten, testlauf=False)
        self.assertEqual(b["neu"], 1)
        self.assertEqual(len(b["fehler"]), 1)
        self.assertTrue(Gegenstand.objects.filter(verein=self.v, bezeichnung="Ok").exists())
        self.assertFalse(Gegenstand.objects.filter(verein=self.v, bezeichnung="Fehler").exists())


class EtikettenTests(TestCase):
    def test_etiketten_pdf_wird_erzeugt(self):
        v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        g1 = Gegenstand.objects.create(verein=v, bezeichnung="Beamer")
        g2 = Gegenstand.objects.create(verein=v, bezeichnung="Zelt")
        pdf = etiketten_pdf([g1, g2], lambda nr: f"https://example.org/inventar/scan/{nr}/")
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_ohne_eigene_einstellungen_bleibt_es_bei_a4(self):
        from io import BytesIO

        from pypdf import PdfReader
        from reportlab.lib.pagesizes import A4
        v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        g = Gegenstand.objects.create(verein=v, bezeichnung="Beamer")
        pdf = etiketten_pdf([g], lambda nr: f"https://example.org/scan/{nr}/", v)
        box = PdfReader(BytesIO(pdf)).pages[0].mediabox
        self.assertAlmostEqual(float(box.width), A4[0], delta=1)
        self.assertAlmostEqual(float(box.height), A4[1], delta=1)

    def test_1x1_schneidet_die_seite_exakt_auf_die_etikettengroesse_zu(self):
        """Fuer Etikettendrucker mit Endlosrolle (z. B. Dymo LabelWriter 450): bei 1 Spalte x 1 Zeile entspricht
        die PDF-Seite selbst der eingestellten Etikettengroesse statt eines A4-Bogens."""
        from io import BytesIO

        from pypdf import PdfReader
        from reportlab.lib.units import mm
        v = Verein.objects.create(name="Test e.V.", kuerzel="test", etikett_breite_mm=89, etikett_hoehe_mm=28,
                                  etikett_spalten=1, etikett_zeilen=1)
        g = Gegenstand.objects.create(verein=v, bezeichnung="Feuerwehrschlauch")
        pdf = etiketten_pdf([g], lambda nr: f"https://example.org/scan/{nr}/", v)
        box = PdfReader(BytesIO(pdf)).pages[0].mediabox
        self.assertAlmostEqual(float(box.width), 89 * mm, delta=1)
        self.assertAlmostEqual(float(box.height), 28 * mm, delta=1)

    def test_1x1_mit_mehreren_etiketten_erzeugt_eine_seite_je_etikett(self):
        from io import BytesIO

        from pypdf import PdfReader
        v = Verein.objects.create(name="Test e.V.", kuerzel="test", etikett_spalten=1, etikett_zeilen=1)
        g1 = Gegenstand.objects.create(verein=v, bezeichnung="A")
        g2 = Gegenstand.objects.create(verein=v, bezeichnung="B")
        g3 = Gegenstand.objects.create(verein=v, bezeichnung="C")
        pdf = etiketten_pdf([g1, g2, g3], lambda nr: f"https://example.org/scan/{nr}/", v)
        self.assertEqual(len(PdfReader(BytesIO(pdf)).pages), 3)

    def test_eigene_groesse_und_raster_fuer_a4_bogen(self):
        from io import BytesIO

        from pypdf import PdfReader
        v = Verein.objects.create(name="Test e.V.", kuerzel="test", etikett_breite_mm=70, etikett_hoehe_mm=36,
                                  etikett_spalten=2, etikett_zeilen=4)
        gegenstaende = [Gegenstand.objects.create(verein=v, bezeichnung=f"G{i}") for i in range(8)]
        pdf = etiketten_pdf(gegenstaende, lambda nr: f"https://example.org/scan/{nr}/", v)
        # 2 x 4 = 8 Etiketten passen auf eine A4-Seite
        self.assertEqual(len(PdfReader(BytesIO(pdf)).pages), 1)

    def test_lagerort_wird_aufgedruckt_wenn_vorhanden(self):
        from io import BytesIO

        from pypdf import PdfReader

        from apps.inventory.models import Lagerort
        v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        ort = Lagerort.objects.create(verein=v, name="Gerätehaus Dachboden")
        g = Gegenstand.objects.create(verein=v, bezeichnung="Beamer", lagerort=ort)
        pdf = etiketten_pdf([g], lambda nr: f"https://example.org/scan/{nr}/", v)
        text = PdfReader(BytesIO(pdf)).pages[0].extract_text()
        self.assertIn("Gerätehaus Dachboden", text)

    def test_ohne_lagerort_kein_fehler_und_keine_leere_zeile_im_text(self):
        v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        g = Gegenstand.objects.create(verein=v, bezeichnung="Beamer")
        pdf = etiketten_pdf([g], lambda nr: f"https://example.org/scan/{nr}/", v)
        self.assertTrue(pdf.startswith(b"%PDF"))


class EtikettModusTests(TestCase):
    """_etikett_modus() waehlt zwischen gestapelt (QR oben/Text unten), nebeneinander (QR links/Text rechts -
    fuer sehr flache/breite Etiketten) und gedreht (90°, fuer deutlich hoehere als breite Etiketten; danach wird
    erneut geprueft, ob die GEDREHTE Flaeche ihrerseits nebeneinander verlangt)."""

    def test_quadratisches_etikett_wird_gestapelt(self):
        gedreht, nebeneinander, _, _ = _etikett_modus(58 * mm, 40 * mm)
        self.assertFalse(gedreht)
        self.assertFalse(nebeneinander)

    def test_flaches_breites_etikett_wird_nebeneinander_gezeichnet(self):
        # z. B. eine kurze Dymo-Rolle, deutlich breiter als hoch
        gedreht, nebeneinander, zeichenbreite, zeichenhoehe = _etikett_modus(89 * mm, 15 * mm)
        self.assertFalse(gedreht)
        self.assertTrue(nebeneinander)
        self.assertEqual((zeichenbreite, zeichenhoehe), (89 * mm, 15 * mm))

    def test_sehr_schmales_hohes_etikett_wird_gedreht_und_dann_nebeneinander(self):
        # Nach dem Drehen (90°) ist aus 15 x 120 mm eine 120 x 15 mm Flaeche geworden - die ist selbst wieder
        # so flach, dass nebeneinander statt gestapelt sinnvoller ist.
        gedreht, nebeneinander, zeichenbreite, zeichenhoehe = _etikett_modus(15 * mm, 120 * mm)
        self.assertTrue(gedreht)
        self.assertTrue(nebeneinander)
        self.assertEqual((zeichenbreite, zeichenhoehe), (120 * mm, 15 * mm))

    def test_maessig_hohes_etikett_wird_nur_gedreht(self):
        gedreht, nebeneinander, _, _ = _etikett_modus(40 * mm, 58 * mm)
        self.assertTrue(gedreht)
        self.assertFalse(nebeneinander)


class EtikettLayoutTests(TestCase):
    """Regressionsschutz für den Fehler aus einem realen Ausdruck: bei einem schmalen, hohen Etikett blieb
    zwischen QR-Code und Text eine grosse ungenutzte Luecke, weil der Textblock prozentual zur (grossen) Höhe
    berechnet wurde. Jetzt absolute Groessen plus senkrechte Zentrierung von QR-Code und Textbox - sowohl im
    gestapelten als auch im nebeneinander-Modus."""

    def _faelle(self):
        """-> [(breite, hoehe, nebeneinander)] fuer alle praxisrelevanten Faelle."""
        for breite, hoehe in [(58 * mm, 40 * mm), (89 * mm, 28 * mm), (25 * mm, 89 * mm), (10 * mm, 10 * mm),
                              (89 * mm, 15 * mm), (120 * mm, 15 * mm)]:
            _gedreht, nebeneinander, zb, zh = _etikett_modus(breite, hoehe)
            yield zb, zh, nebeneinander

    def test_qr_code_bleibt_innerhalb_des_etiketts(self):
        for breite, hoehe, nebeneinander in self._faelle():
            with self.subTest(breite=breite, hoehe=hoehe, nebeneinander=nebeneinander):
                l = _etikett_layout(breite, hoehe, nebeneinander)
                self.assertGreaterEqual(l["qr_x"], 0)
                self.assertGreaterEqual(l["qr_y"], 0)
                self.assertLessEqual(l["qr_x"] + l["qr_groesse"], breite + 0.5)
                self.assertLessEqual(l["qr_y"] + l["qr_groesse"], hoehe + 0.5)

    def test_textbox_bleibt_innerhalb_des_etiketts(self):
        for breite, hoehe, nebeneinander in self._faelle():
            with self.subTest(breite=breite, hoehe=hoehe, nebeneinander=nebeneinander):
                l = _etikett_layout(breite, hoehe, nebeneinander)
                self.assertGreaterEqual(l["text_unten_y"], 0)
                self.assertLessEqual(l["text_unten_y"] + l["text_hoehe"], hoehe + 0.5)

    def test_gestapelt_zentriert_inhalt_senkrecht_ohne_grosse_luecke(self):
        breite, hoehe = 58 * mm, 40 * mm
        l = _etikett_layout(breite, hoehe, nebeneinander=False)
        frei_oben = hoehe - (l["qr_y"] + l["qr_groesse"])
        self.assertGreater(l["text_unten_y"], 0)
        self.assertLess(frei_oben * 2, hoehe * 0.8)   # kein grosser ungenutzter Rand oben+unten zusammen

    def test_nebeneinander_nutzt_die_volle_hoehe_fuer_den_qr_code(self):
        breite, hoehe = 89 * mm, 15 * mm
        l = _etikett_layout(breite, hoehe, nebeneinander=True)
        # QR-Code soll die kurze Seite (Hoehe) weitgehend ausfuellen, nicht nur einen kleinen zentrierten Teil
        self.assertGreater(l["qr_groesse"], hoehe * 0.7)
        # Text steht rechts vom QR-Code, nicht darunter/darueber
        self.assertGreater(l["text_mitte_x"], l["qr_x"] + l["qr_groesse"])


class ScanTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.verwalter = User.objects.create_user("verwalter", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=self.verwalter,
                              rolle=Rolle.objects.get(verein=self.v, name="Inventarverwalter"))
        self.client.login(username="verwalter", password="pw-Test-12345")

    def test_scan_legt_gegenstand_in_den_warenkorb(self):
        g = Gegenstand.objects.create(verein=self.v, bezeichnung="Beamer", verleihbar=True)
        r = self.client.get(reverse("gegenstand_scan", args=[g.inventarnummer]), follow=True)
        self.assertRedirects(r, reverse("verleih_warenkorb"))
        self.assertContains(r, "Beamer")

    def test_scan_desselben_gegenstands_zweimal_dupliziert_nicht(self):
        g = Gegenstand.objects.create(verein=self.v, bezeichnung="Beamer", verleihbar=True)
        self.client.get(reverse("gegenstand_scan", args=[g.inventarnummer]))
        self.client.get(reverse("gegenstand_scan", args=[g.inventarnummer]))
        korb = self.client.session.get(f"verleih_warenkorb_{self.v.pk}", [])
        self.assertEqual(korb, [g.pk])

    def test_scan_nicht_verleihbarer_gegenstand_zeigt_hinweis(self):
        g = Gegenstand.objects.create(verein=self.v, bezeichnung="Stuhl", verleihbar=False)
        r = self.client.get(reverse("gegenstand_scan", args=[g.inventarnummer]), follow=True)
        self.assertRedirects(r, reverse("gegenstand_detail", args=[g.pk]))
        self.assertContains(r, "nicht als verleihbar markiert")

    def test_scan_fremder_verein_ist_404(self):
        anderer = Verein.objects.create(name="Anderer e.V.", kuerzel="anderer")
        g = Gegenstand.objects.create(verein=anderer, bezeichnung="Beamer", verleihbar=True)
        r = self.client.get(reverse("gegenstand_scan", args=[g.inventarnummer]))
        self.assertEqual(r.status_code, 404)


class WarenkorbTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.verwalter = User.objects.create_user("verwalter", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=self.verwalter,
                              rolle=Rolle.objects.get(verein=self.v, name="Inventarverwalter"))
        self.client.login(username="verwalter", password="pw-Test-12345")
        self.m = Mitglied.objects.create(verein=self.v, vorname="Max", nachname="Muster")
        self.g1 = Gegenstand.objects.create(verein=self.v, bezeichnung="Faltpavillon", verleihbar=True)
        self.g2 = Gegenstand.objects.create(verein=self.v, bezeichnung="Biertischgarnitur", verleihbar=True)

    def test_mehrfach_scannen_sammelt_im_warenkorb(self):
        self.client.get(reverse("gegenstand_scan", args=[self.g1.inventarnummer]))
        r = self.client.get(reverse("gegenstand_scan", args=[self.g2.inventarnummer]), follow=True)
        self.assertContains(r, "Faltpavillon")
        self.assertContains(r, "Biertischgarnitur")

    def test_aus_warenkorb_entfernen(self):
        self.client.get(reverse("gegenstand_scan", args=[self.g1.inventarnummer]))
        self.client.get(reverse("gegenstand_scan", args=[self.g2.inventarnummer]))
        self.client.post(reverse("verleih_warenkorb_entfernen", args=[self.g1.pk]))
        korb = self.client.session.get(f"verleih_warenkorb_{self.v.pk}", [])
        self.assertEqual(korb, [self.g2.pk])

    def test_warenkorb_leeren(self):
        self.client.get(reverse("gegenstand_scan", args=[self.g1.inventarnummer]))
        self.client.post(reverse("verleih_warenkorb_leeren"))
        self.assertNotIn(f"verleih_warenkorb_{self.v.pk}", self.client.session)

    def test_sammelverleih_formular_ist_mit_warenkorb_vorbelegt(self):
        self.client.get(reverse("gegenstand_scan", args=[self.g1.inventarnummer]))
        self.client.get(reverse("gegenstand_scan", args=[self.g2.inventarnummer]))
        r = self.client.get(reverse("verleih_sammel_add"))
        self.assertEqual(set(r.context["form"].initial["gegenstaende"]), {self.g1.pk, self.g2.pk})

    def test_warenkorb_wird_nach_abgeschlossenem_sammelverleih_geleert(self):
        self.client.get(reverse("gegenstand_scan", args=[self.g1.inventarnummer]))
        heute = date.today()
        self.client.post(reverse("verleih_sammel_add"), {
            "gegenstaende": [self.g1.pk], "entleiher": self.m.pk, "von": heute, "bis": heute + timedelta(days=2)})
        self.assertNotIn(f"verleih_warenkorb_{self.v.pk}", self.client.session)


class SammelverleihTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.verwalter = User.objects.create_user("verwalter", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=self.verwalter,
                              rolle=Rolle.objects.get(verein=self.v, name="Inventarverwalter"))
        self.client.login(username="verwalter", password="pw-Test-12345")
        self.m = Mitglied.objects.create(verein=self.v, vorname="Max", nachname="Muster")
        self.g1 = Gegenstand.objects.create(verein=self.v, bezeichnung="Faltpavillon", verleihbar=True, kaution=30)
        self.g2 = Gegenstand.objects.create(verein=self.v, bezeichnung="Biertischgarnitur", verleihbar=True, kaution=20)

    def _formular(self, **overrides):
        heute = date.today()
        daten = {"gegenstaende": [self.g1.pk, self.g2.pk], "entleiher": self.m.pk, "von": heute,
                "bis": heute + timedelta(days=3)}
        daten.update(overrides)
        return daten

    def test_sammelverleih_erstellt_einen_verleih_je_gegenstand_im_selben_vorgang(self):
        r = self.client.post(reverse("verleih_sammel_add"), self._formular())
        self.assertEqual(r.status_code, 302)
        positionen = list(Verleih.objects.filter(verein=self.v, entleiher=self.m))
        self.assertEqual(len(positionen), 2)
        self.assertEqual(positionen[0].vorgang, positionen[1].vorgang)
        self.assertIsNotNone(positionen[0].vorgang)
        for p in positionen:
            self.assertEqual(p.status, "reserviert")
        self.assertRedirects(r, reverse("verleih_vorgang_detail", args=[positionen[0].vorgang]))

    def test_sammelverleih_ohne_gegenstand_zeigt_formularfehler(self):
        r = self.client.post(reverse("verleih_sammel_add"), self._formular(gegenstaende=[]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Verleih.objects.filter(verein=self.v).count(), 0)

    def test_vorgang_ausgeben_und_rueckgabe_wirkt_auf_alle_positionen(self):
        self.client.post(reverse("verleih_sammel_add"), self._formular())
        vorgang = Verleih.objects.filter(verein=self.v).first().vorgang

        r = self.client.post(reverse("verleih_vorgang_ausgeben", args=[vorgang]))
        self.assertRedirects(r, reverse("verleih_vorgang_detail", args=[vorgang]))
        self.assertEqual(Verleih.objects.filter(vorgang=vorgang, status="ausgegeben").count(), 2)

        daten = {f"zustand_{p.pk}": "gut" for p in Verleih.objects.filter(vorgang=vorgang)}
        r = self.client.post(reverse("verleih_vorgang_rueckgabe", args=[vorgang]), daten)
        self.assertEqual(Verleih.objects.filter(vorgang=vorgang, status="zurueckgegeben").count(), 2)

    def test_vorgang_leihschein_pdf(self):
        self.client.post(reverse("verleih_sammel_add"), self._formular())
        vorgang = Verleih.objects.filter(verein=self.v).first().vorgang
        r = self.client.get(reverse("verleih_vorgang_leihschein", args=[vorgang]))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.content.startswith(b"%PDF"))

    def test_sammelverleih_fuer_veranstaltung_ohne_entleiher_ist_gueltig(self):
        """Reserviert der Verein selbst Inventar für eine Veranstaltung, braucht es keinen Entleiher."""
        ver = Veranstaltung.objects.create(verein=self.v, titel="Sommerfest", beginn=timezone.now())
        r = self.client.post(reverse("verleih_sammel_add"),
                             self._formular(entleiher="", veranstaltung=ver.pk))
        self.assertEqual(r.status_code, 302)
        positionen = list(Verleih.objects.filter(verein=self.v, veranstaltung=ver))
        self.assertEqual(len(positionen), 2)
        self.assertIn("Verein selbst", positionen[0].wer)

    def test_sammelformular_wird_durch_veranstaltung_von_bis_aus_querystring_vorbelegt(self):
        ver = Veranstaltung.objects.create(verein=self.v, titel="Sommerfest", beginn=timezone.now())
        r = self.client.get(reverse("verleih_sammel_add") + f"?veranstaltung={ver.pk}&von=2026-07-01&bis=2026-07-03")
        self.assertEqual(r.context["form"].initial["veranstaltung"], str(ver.pk))
        self.assertEqual(r.context["form"].initial["von"], "2026-07-01")

    def test_vorgang_fremder_verein_ist_404(self):
        anderer = Verein.objects.create(name="Anderer e.V.", kuerzel="anderer")
        g = Gegenstand.objects.create(verein=anderer, bezeichnung="Beamer", verleihbar=True)
        m = Mitglied.objects.create(verein=anderer, vorname="A", nachname="B")
        v = Verleih.objects.create(verein=anderer, gegenstand=g, entleiher=m, von=date.today(),
                                   bis=date.today() + timedelta(days=1), vorgang="11111111-1111-1111-1111-111111111111")
        r = self.client.get(reverse("verleih_vorgang_detail", args=[v.vorgang]))
        self.assertEqual(r.status_code, 404)


class RueckgabeTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.verwalter = User.objects.create_user("verwalter", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=self.verwalter,
                              rolle=Rolle.objects.get(verein=self.v, name="Inventarverwalter"))
        self.client.login(username="verwalter", password="pw-Test-12345")
        self.m = Mitglied.objects.create(verein=self.v, vorname="Max", nachname="Muster")
        self.g = Gegenstand.objects.create(verein=self.v, bezeichnung="Beamer", verleihbar=True,
                                           leihgebuehr=Decimal("25"), kaution=Decimal("50"))
        self.verleih = Verleih.objects.create(verein=self.v, gegenstand=self.g, entleiher=self.m, von=date.today(),
                                              bis=date.today() + timedelta(days=2), status="ausgegeben")

    def test_rueckgabeformular_wird_angezeigt(self):
        r = self.client.get(reverse("verleih_rueckgabe", args=[self.verleih.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Beamer")
        self.assertContains(r, "Zurückzahlen")
        self.assertContains(r, "Einbehalten")

    def test_rueckgabe_erstellt_rechnung_fuer_leihgebuehr(self):
        r = self.client.post(reverse("verleih_rueckgabe", args=[self.verleih.pk]),
                             {f"zustand_{self.verleih.pk}": "gut"}, follow=True)
        self.verleih.refresh_from_db()
        self.assertIsNotNone(self.verleih.rechnung_id)
        rechnung = self.verleih.rechnung
        self.assertEqual(rechnung.mitglied_id, self.m.pk)
        self.assertEqual(rechnung.betrag, Decimal("25.00"))
        self.assertContains(r, f"Rechnung {rechnung.nummer}")

    def test_rueckgabe_setzt_zustand_des_gegenstands_auf_defekt(self):
        """Kommt ein Gegenstand defekt zurück, muss das auch am Gegenstand selbst (und damit in der
        Inventar-Übersicht) hinterlegt sein - nicht nur am Verleih-Datensatz."""
        self.client.post(reverse("verleih_rueckgabe", args=[self.verleih.pk]),
                         {f"zustand_{self.verleih.pk}": "defekt", f"kaution_{self.verleih.pk}": "zurueckzahlen"})
        self.g.refresh_from_db()
        self.verleih.refresh_from_db()
        self.assertEqual(self.g.zustand, "defekt")
        self.assertEqual(self.verleih.zustand_bei_rueckgabe, "defekt")
        # Kaution wird NICHT automatisch einbehalten, nur wenn das explizit gewählt wird
        self.assertFalse(self.verleih.kaution_einbehalten)

    def test_rueckgabe_ohne_leihgebuehr_erstellt_keine_rechnung(self):
        g2 = Gegenstand.objects.create(verein=self.v, bezeichnung="Zelt", verleihbar=True, leihgebuehr=Decimal("0"))
        v2 = Verleih.objects.create(verein=self.v, gegenstand=g2, entleiher=self.m, von=date.today(),
                                    bis=date.today() + timedelta(days=1), status="ausgegeben")
        self.client.post(reverse("verleih_rueckgabe", args=[v2.pk]), {f"zustand_{v2.pk}": "gut"})
        v2.refresh_from_db()
        self.assertIsNone(v2.rechnung_id)
        self.assertEqual(Rechnung.objects.filter(verein=self.v).count(), 0)

    def test_rueckgabe_externer_entleiher_erstellt_rechnung_mit_namen(self):
        v3 = Verleih.objects.create(verein=self.v, gegenstand=self.g, entleiher_name="Externe Person",
                                    entleiher_kontakt="Musterstr. 1, 12345 Musterstadt", von=date.today(),
                                    bis=date.today() + timedelta(days=1), status="ausgegeben")
        self.client.post(reverse("verleih_rueckgabe", args=[v3.pk]), {f"zustand_{v3.pk}": "gut"})
        v3.refresh_from_db()
        self.assertIsNotNone(v3.rechnung_id)
        self.assertIsNone(v3.rechnung.mitglied_id)
        self.assertEqual(v3.rechnung.empfaenger_name, "Externe Person")

    def test_kaution_einbehalten_landet_auf_der_rechnung(self):
        r = self.client.post(reverse("verleih_rueckgabe", args=[self.verleih.pk]), {
            f"zustand_{self.verleih.pk}": "defekt", f"kaution_{self.verleih.pk}": "einbehalten"}, follow=True)
        self.verleih.refresh_from_db()
        self.assertTrue(self.verleih.kaution_einbehalten)
        self.assertFalse(self.verleih.kaution_zurueckgezahlt)
        rechnung = self.verleih.rechnung
        self.assertIsNotNone(rechnung)
        # Leihgebühr (25) + einbehaltene Kaution (50)
        self.assertEqual(rechnung.betrag, Decimal("75.00"))
        self.assertEqual(rechnung.positionen.count(), 2)
        self.assertContains(r, f"Rechnung {rechnung.nummer}")
        # Hinweistext beschreibt jetzt "einbehalten", nicht mehr "noch nicht zurückgezahlt"
        detail = self.client.get(reverse("verleih_detail", args=[self.verleih.pk]))
        self.assertContains(detail, "einbehalten und in Rechnung gestellt")

    def test_kaution_als_zurueckgezahlt_markieren(self):
        self.client.post(reverse("verleih_rueckgabe", args=[self.verleih.pk]),
                         {f"zustand_{self.verleih.pk}": "gut", f"kaution_{self.verleih.pk}": "zurueckzahlen"})
        r = self.client.post(reverse("verleih_kaution_zurueckgezahlt", args=[self.verleih.pk]), follow=True)
        self.verleih.refresh_from_db()
        self.assertTrue(self.verleih.kaution_zurueckgezahlt)
        self.assertContains(r, "Kaution als zurückgezahlt markiert")

    def test_vorgang_rueckgabe_erstellt_gemeinsame_rechnung(self):
        vorgang = uuid.uuid4()
        g2 = Gegenstand.objects.create(verein=self.v, bezeichnung="Zelt", verleihbar=True, leihgebuehr=Decimal("10"))
        v2 = Verleih.objects.create(verein=self.v, vorgang=vorgang, gegenstand=g2, entleiher=self.m, von=date.today(),
                                    bis=date.today() + timedelta(days=1), status="ausgegeben")
        self.verleih.vorgang = vorgang
        self.verleih.save(update_fields=["vorgang"])
        self.client.post(reverse("verleih_vorgang_rueckgabe", args=[vorgang]), {
            f"zustand_{self.verleih.pk}": "gut", f"zustand_{v2.pk}": "gut"})
        self.verleih.refresh_from_db()
        v2.refresh_from_db()
        self.assertIsNotNone(self.verleih.rechnung_id)
        self.assertEqual(self.verleih.rechnung_id, v2.rechnung_id)
        self.assertEqual(self.verleih.rechnung.betrag, Decimal("35.00"))
        self.assertEqual(self.verleih.rechnung.positionen.count(), 2)

    def test_vorgang_rueckgabe_in_zwei_schritten_landet_auf_derselben_rechnung(self):
        """Auch wenn die Positionen eines Vorgangs nacheinander (einzeln) statt gemeinsam zurückgenommen werden,
        soll am Ende alles auf einer Rechnung stehen."""
        vorgang = uuid.uuid4()
        g2 = Gegenstand.objects.create(verein=self.v, bezeichnung="Zelt", verleihbar=True, leihgebuehr=Decimal("10"))
        v2 = Verleih.objects.create(verein=self.v, vorgang=vorgang, gegenstand=g2, entleiher=self.m, von=date.today(),
                                    bis=date.today() + timedelta(days=1), status="ausgegeben")
        self.verleih.vorgang = vorgang
        self.verleih.save(update_fields=["vorgang"])
        self.client.post(reverse("verleih_rueckgabe", args=[self.verleih.pk]), {f"zustand_{self.verleih.pk}": "gut"})
        self.client.post(reverse("verleih_rueckgabe", args=[v2.pk]), {f"zustand_{v2.pk}": "gut"})
        self.verleih.refresh_from_db()
        v2.refresh_from_db()
        self.assertEqual(self.verleih.rechnung_id, v2.rechnung_id)
        self.assertEqual(self.verleih.rechnung.betrag, Decimal("35.00"))
        self.assertEqual(self.verleih.rechnung.positionen.count(), 2)

    def test_vorgang_kaution_zurueckgezahlt_bulk(self):
        vorgang = uuid.uuid4()
        self.verleih.vorgang = vorgang
        self.verleih.save(update_fields=["vorgang"])
        self.client.post(reverse("verleih_rueckgabe", args=[self.verleih.pk]),
                         {f"zustand_{self.verleih.pk}": "gut", f"kaution_{self.verleih.pk}": "zurueckzahlen"})
        self.client.post(reverse("verleih_vorgang_kaution_zurueckgezahlt", args=[vorgang]))
        self.verleih.refresh_from_db()
        self.assertTrue(self.verleih.kaution_zurueckgezahlt)

    def test_inventarverwalter_ohne_rechnungsrecht_sieht_keinen_rechnung_link(self):
        """Inventarverwalter hat kein Recht auf "rechnungen" - der Link zur Rechnung darf ihm nicht angezeigt
        werden (er würde beim Klick nur auf einen 403 laufen)."""
        self.client.post(reverse("verleih_rueckgabe", args=[self.verleih.pk]), {f"zustand_{self.verleih.pk}": "gut"})
        self.verleih.refresh_from_db()
        self.assertIsNotNone(self.verleih.rechnung_id)
        r = self.client.get(reverse("verleih_detail", args=[self.verleih.pk]))
        self.assertNotContains(r, "Rechnung ansehen")


class InventurTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.verwalter = User.objects.create_user("verwalter", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=self.verwalter,
                              rolle=Rolle.objects.get(verein=self.v, name="Inventarverwalter"))
        self.client.login(username="verwalter", password="pw-Test-12345")
        self.ort = Lagerort.objects.create(verein=self.v, name="Gerätehaus")
        self.dachboden = Lagerort.objects.create(verein=self.v, name="Dachboden")
        self.g = Gegenstand.objects.create(verein=self.v, bezeichnung="Beamer", lagerort=self.ort)
        self.inv = Inventur.objects.create(verein=self.v, name="Inventur 2026")
        self.p = Inventurposition.objects.filter(inventur=self.inv, gegenstand=self.g).get()

    def test_snapshot_uebernimmt_lagerort_als_soll_wert(self):
        self.assertEqual(self.p.lagerort_text, "Gerätehaus")
        self.assertIsNone(self.p.lagerort_ist_id)

    def test_detailseite_zeigt_auswahlfeld_fuer_lagerort_ist(self):
        r = self.client.get(reverse("inventur_detail", args=[self.inv.pk]))
        self.assertContains(r, "Lagerort (Ist)")
        self.assertContains(r, f'id="position-{self.p.pk}"')
        self.assertContains(r, "Dachboden")

    def test_setzen_speichert_ergebnis_und_lagerort_ist_und_springt_zur_position(self):
        r = self.client.post(reverse("inventurposition_setzen", args=[self.p.pk]),
                             {"ergebnis": "gefunden", "lagerort_ist": self.dachboden.pk})
        self.assertRedirects(r, reverse("inventur_detail", args=[self.inv.pk]) + f"#position-{self.p.pk}")
        self.p.refresh_from_db()
        self.assertEqual(self.p.ergebnis, "gefunden")
        self.assertEqual(self.p.lagerort_ist, self.dachboden)

    def test_nur_speichern_knopf_laesst_ergebnis_unveraendert(self):
        """Der Speichern-Knopf hat kein 'ergebnis' im gültigen Wertebereich - nur der Lagerort (Ist) wird
        aktualisiert, das bisherige Ergebnis bleibt erhalten."""
        self.p.ergebnis = "gefunden"
        self.p.save(update_fields=["ergebnis"])
        self.client.post(reverse("inventurposition_setzen", args=[self.p.pk]),
                         {"ergebnis": "", "lagerort_ist": self.dachboden.pk})
        self.p.refresh_from_db()
        self.assertEqual(self.p.ergebnis, "gefunden")
        self.assertEqual(self.p.lagerort_ist, self.dachboden)

    def test_lagerort_eines_fremden_vereins_wird_ignoriert(self):
        anderer = Verein.objects.create(name="Anderer e.V.", kuerzel="anderer")
        fremder_ort = Lagerort.objects.create(verein=anderer, name="Fremdlager")
        self.client.post(reverse("inventurposition_setzen", args=[self.p.pk]),
                         {"ergebnis": "gefunden", "lagerort_ist": fremder_ort.pk})
        self.p.refresh_from_db()
        self.assertIsNone(self.p.lagerort_ist_id)

    def test_abgeschlossene_inventur_zeigt_lagerort_ist_nur_als_text_ohne_formular(self):
        self.p.lagerort_ist = self.dachboden
        self.p.save(update_fields=["lagerort_ist"])
        self.inv.status = "abgeschlossen"
        self.inv.save(update_fields=["status"])
        r = self.client.get(reverse("inventur_detail", args=[self.inv.pk]))
        self.assertContains(r, "Dachboden")
        self.assertNotContains(r, "name=\"lagerort_ist\"")

    def test_abgeschlossene_inventur_lehnt_setzen_ab(self):
        self.inv.status = "abgeschlossen"
        self.inv.save(update_fields=["status"])
        r = self.client.post(reverse("inventurposition_setzen", args=[self.p.pk]),
                             {"ergebnis": "gefunden", "lagerort_ist": self.dachboden.pk})
        self.assertEqual(r.status_code, 403)
