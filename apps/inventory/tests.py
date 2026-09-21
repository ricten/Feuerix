from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Rolle, Verein, Zugang
from apps.inventory import importer
from apps.inventory.models import Gegenstand
from apps.inventory.pdf import etiketten_pdf

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

    def test_scan_leitet_zum_vorausgefuellten_verleih_start(self):
        g = Gegenstand.objects.create(verein=self.v, bezeichnung="Beamer", verleihbar=True)
        r = self.client.get(reverse("gegenstand_scan", args=[g.inventarnummer]))
        self.assertRedirects(r, reverse("verleih_add") + f"?gegenstand={g.pk}")

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
