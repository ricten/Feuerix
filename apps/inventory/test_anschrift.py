"""Manuell eingetragene Anschrift des Entleihers auf dem Leihschein."""
import uuid
from datetime import date, timedelta
from io import BytesIO

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from pypdf import PdfReader

from apps.core.models import Rolle, Verein, Zugang
from apps.members.models import Mitglied

from .models import Gegenstand, Verleih
from .pdf import leihschein_pdf, leihschein_sammel_pdf

PW = "pw-Test-12345"


def pdf_text(pdf):
    return "\n".join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages)


class LeihscheinAnschriftTests(TestCase):
    def setUp(self):
        self.verein = Verein.objects.create(name="Testverein", kuerzel="test")
        self.g = Gegenstand.objects.create(verein=self.verein, bezeichnung="Beamer", verleihbar=True)
        self.m = Mitglied.objects.create(verein=self.verein, vorname="Max", nachname="Mustermann", status="aktiv",
                                         strasse="Hauptstr. 1", plz="12345", ort="Musterstadt")
        self.heute = date.today()

    def verleih(self, **kw):
        return Verleih.objects.create(verein=self.verein, gegenstand=self.g, von=self.heute,
                                      bis=self.heute + timedelta(days=2), **kw)

    def test_manuelle_anschrift_extern(self):
        v = self.verein
        vl = self.verleih(entleiher_name="Schützenverein", entleiher_kontakt="info@example.org",
                          entleiher_anschrift="Schützenverein Musterdorf\nZielweg 3\n99999 Musterdorf")
        self.assertEqual(vl.anschrift_zeilen(), ["Schützenverein Musterdorf", "Zielweg 3", "99999 Musterdorf"])
        t = pdf_text(leihschein_pdf(vl))
        self.assertIn("Zielweg 3", t)
        self.assertNotIn("info@example.org", t)
        self.assertIsNotNone(v)

    def test_manuelle_anschrift_hat_vorrang_vor_mitglied(self):
        vl = self.verein and self.verleih(entleiher=self.m, entleiher_anschrift="Anderer Name\nAndere Str. 5\n54321 Anderswo")
        t = pdf_text(leihschein_pdf(vl))
        self.assertIn("Andere Str. 5", t)
        self.assertNotIn("Hauptstr. 1", t)

    def test_ohne_manuelle_anschrift_wie_bisher(self):
        vl = self.verleih(entleiher=self.m)
        self.assertEqual(vl.anschrift_zeilen(), self.m.anschrift_zeilen())
        self.assertIn("Hauptstr. 1", pdf_text(leihschein_pdf(vl)))
        extern = self.verleih(entleiher_name="Firma X", entleiher_kontakt="0123 456")
        self.assertEqual(extern.anschrift_zeilen(), ["Firma X", "0123 456"])

    def test_sammelleihschein_nutzt_anschrift_der_ersten_position(self):
        g2 = Gegenstand.objects.create(verein=self.verein, bezeichnung="Laptop", verleihbar=True)
        vorgang = uuid.uuid4()
        v1 = self.verleih(entleiher_name="Verein Y", entleiher_anschrift="Verein Y\nVereinsweg 8\n10101 Ort", vorgang=vorgang)
        v2 = Verleih.objects.create(verein=self.verein, gegenstand=g2, von=self.heute, bis=self.heute + timedelta(days=2),
                                    entleiher_name="Verein Y", entleiher_anschrift=v1.entleiher_anschrift, vorgang=vorgang)
        self.assertIn("Vereinsweg 8", pdf_text(leihschein_sammel_pdf([v1, v2])))


class VerleihFormularAnschriftTests(TestCase):
    def setUp(self):
        self.verein = Verein.objects.create(name="Testverein", kuerzel="test")
        admin = get_user_model().objects.create_superuser("admin", password=PW)
        Zugang.objects.create(verein=self.verein, user=admin,
                              rolle=Rolle.objects.get(verein=self.verein, name="Superadministrator"))
        self.client.force_login(admin)
        self.g = Gegenstand.objects.create(verein=self.verein, bezeichnung="Beamer", verleihbar=True)

    def test_einzelverleih_formular(self):
        r = self.client.get(reverse("verleih_add"))
        self.assertContains(r, 'name="entleiher_anschrift"')
        heute = date.today()
        r = self.client.post(reverse("verleih_add"), {
            "gegenstand": self.g.pk, "entleiher_name": "Extern", "von": heute, "bis": heute + timedelta(days=1),
            "entleiher_anschrift": "Extern GmbH\nWeg 1\n12345 Ort", "kaution_zurueckgezahlt": ""})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Verleih.objects.get().entleiher_anschrift, "Extern GmbH\nWeg 1\n12345 Ort")

    def test_sammelverleih_formular_gibt_anschrift_weiter(self):
        r = self.client.get(reverse("verleih_sammel_add"))
        self.assertContains(r, 'name="entleiher_anschrift"')
        heute = date.today()
        r = self.client.post(reverse("verleih_sammel_add"), {
            "gegenstaende": [self.g.pk], "entleiher_name": "Extern", "von": heute, "bis": heute + timedelta(days=1),
            "entleiher_anschrift": "Extern GmbH\nWeg 1\n12345 Ort"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Verleih.objects.get().entleiher_anschrift, "Extern GmbH\nWeg 1\n12345 Ort")
