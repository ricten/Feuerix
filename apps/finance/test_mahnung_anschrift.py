"""Manuell eingetragene Empfängeranschrift bei Mahnungen."""
from io import BytesIO

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from pypdf import PdfReader

from apps.core.models import Rolle, Verein, Zugang

from . import services
from .pdf import mahnung_pdf

PW = "pw-Test-12345"


def pdf_text(pdf):
    return "\n".join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages)


class MahnungAnschriftTests(TestCase):
    def setUp(self):
        self.verein = Verein.objects.create(name="Testverein", kuerzel="test")
        self.rechnung = services.rechnung_erstellen(
            self.verein, [("Posten", 1, 10)], empfaenger_name="Erika Rechnung", empfaenger_anschrift="Rechnungsweg 1\n11111 Rechnungsstadt")
        self.mahnung = services.mahnung_erstellen(self.rechnung)

    def test_ohne_manuelle_anschrift_wie_die_rechnung(self):
        t = pdf_text(mahnung_pdf(self.mahnung))
        self.assertIn("Erika Rechnung", t)
        self.assertIn("Rechnungsweg 1", t)

    def test_manuelle_anschrift_hat_vorrang(self):
        self.mahnung.empfaenger_anschrift = "Hans Anders\n  Zustellweg 9 \n\n22222 Zustellstadt"
        self.mahnung.save()
        t = pdf_text(mahnung_pdf(self.mahnung))
        for zeile in ("Hans Anders", "Zustellweg 9", "22222 Zustellstadt"):
            self.assertIn(zeile, t)
        self.assertNotIn("Rechnungsweg 1", t)
        self.assertNotIn("Erika Rechnung", t)

    def test_feld_im_formular_und_speicherbar(self):
        admin = get_user_model().objects.create_superuser("admin", password=PW)
        Zugang.objects.create(verein=self.verein, user=admin,
                              rolle=Rolle.objects.get(verein=self.verein, name="Superadministrator"))
        self.client.force_login(admin)
        r = self.client.get(reverse("mahnung_edit", args=[self.mahnung.pk]))
        self.assertContains(r, 'name="empfaenger_anschrift"')
        daten = {"rechnung": self.rechnung.pk, "stufe": 1, "datum": "2026-01-01", "frist": "2026-02-01", "gebuehr": "0",
                 "empfaenger_anschrift": "Neu Name\nNeue Str. 1"}
        self.assertEqual(self.client.post(reverse("mahnung_edit", args=[self.mahnung.pk]), daten).status_code, 302)
        self.mahnung.refresh_from_db()
        self.assertEqual(self.mahnung.empfaenger_anschrift, "Neu Name\nNeue Str. 1")
