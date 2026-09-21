from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Rolle, Verein, Zugang
from apps.inventory import importer
from apps.inventory.models import Gegenstand, Verleih
from apps.inventory.pdf import etiketten_pdf
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

        r = self.client.post(reverse("verleih_vorgang_rueckgabe", args=[vorgang]))
        self.assertEqual(Verleih.objects.filter(vorgang=vorgang, status="zurueckgegeben").count(), 2)

    def test_vorgang_leihschein_pdf(self):
        self.client.post(reverse("verleih_sammel_add"), self._formular())
        vorgang = Verleih.objects.filter(verein=self.v).first().vorgang
        r = self.client.get(reverse("verleih_vorgang_leihschein", args=[vorgang]))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.content.startswith(b"%PDF"))

    def test_vorgang_fremder_verein_ist_404(self):
        anderer = Verein.objects.create(name="Anderer e.V.", kuerzel="anderer")
        g = Gegenstand.objects.create(verein=anderer, bezeichnung="Beamer", verleihbar=True)
        m = Mitglied.objects.create(verein=anderer, vorname="A", nachname="B")
        v = Verleih.objects.create(verein=anderer, gegenstand=g, entleiher=m, von=date.today(),
                                   bis=date.today() + timedelta(days=1), vorgang="11111111-1111-1111-1111-111111111111")
        r = self.client.get(reverse("verleih_vorgang_detail", args=[v.vorgang]))
        self.assertEqual(r.status_code, 404)
