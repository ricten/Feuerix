"""Manuell eingetragene Empfängeranschrift bei Schriftstücken (Anschreiben)."""
from io import BytesIO

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from docx import Document
from pypdf import PdfReader

from apps.core.models import Rolle, Verein, Zugang
from apps.members.models import Mitglied

from .docx_export import schriftstueck_docx
from .models import Schriftstueck
from .pdf import schriftstueck_pdf

PW = "pw-Test-12345"
MANUELL = "Firma Beispiel GmbH\nz. Hd. Frau Meier\nHandwerkerweg 7\n54321 Anderstadt"


def pdf_text(pdf):
    return "\n".join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages)


class AnschriftTests(TestCase):
    def setUp(self):
        self.verein = Verein.objects.create(name="Testverein", kuerzel="test")
        self.m = Mitglied.objects.create(verein=self.verein, anrede="herr", vorname="Max", nachname="Mustermann",
                                         status="aktiv", strasse="Hauptstr. 1", plz="12345", ort="Musterstadt")

    def brief(self, **kw):
        return Schriftstueck.objects.create(verein=self.verein, titel="T", betreff="B", text="<p>{briefanrede}</p>", **kw)

    def test_manuelle_anschrift_ohne_mitglied(self):
        s = self.brief(empfaenger_anschrift=MANUELL)
        self.assertEqual(s.anschrift_zeilen(), MANUELL.split("\n"))
        t = pdf_text(schriftstueck_pdf(s))
        for zeile in MANUELL.split("\n"):
            self.assertIn(zeile, t)
        self.assertIn("Sehr geehrte Damen und Herren,", t)          # neutrale Anrede ohne Mitglied

    def test_manuelle_anschrift_hat_vorrang_vor_mitglied(self):
        s = self.brief(mitglied=self.m, empfaenger_anschrift=MANUELL)
        t = pdf_text(schriftstueck_pdf(s))
        self.assertIn("Handwerkerweg 7", t)
        self.assertNotIn("Hauptstr. 1", t)
        self.assertIn("Sehr geehrter Herr Mustermann,", t)          # persönliche Anrede bleibt, wenn ein Mitglied gewählt ist

    def test_ohne_manuelle_anschrift_wie_bisher(self):
        s = self.brief(mitglied=self.m)
        self.assertEqual(s.anschrift_zeilen(), self.m.anschrift_zeilen())
        self.assertIn("Hauptstr. 1", pdf_text(schriftstueck_pdf(s)))
        self.assertEqual(self.brief().anschrift_zeilen(), [])

    def test_leere_zeilen_und_leerzeichen_werden_ignoriert(self):
        s = self.brief(empfaenger_anschrift="  \n Firma X \n\n  Weg 1  \n")
        self.assertEqual(s.anschrift_zeilen(), ["Firma X", "Weg 1"])

    def test_protokoll_hat_keine_anschrift(self):
        s = self.brief(art="protokoll", empfaenger_anschrift=MANUELL)
        self.assertEqual(s.anschrift_zeilen(), [])
        self.assertNotIn("Handwerkerweg", pdf_text(schriftstueck_pdf(s)))

    def test_word_export(self):
        s = self.brief(empfaenger_anschrift=MANUELL)
        doc = Document(BytesIO(schriftstueck_docx(s)))
        gesamt = "\n".join(p.text for p in doc.paragraphs)
        self.assertIn("Firma Beispiel GmbH", gesamt)
        self.assertIn("54321 Anderstadt", gesamt)


class AnschriftFormularTests(TestCase):
    def setUp(self):
        self.verein = Verein.objects.create(name="Testverein", kuerzel="test")
        admin = get_user_model().objects.create_superuser("admin", password=PW)
        Zugang.objects.create(verein=self.verein, user=admin,
                              rolle=Rolle.objects.get(verein=self.verein, name="Superadministrator"))
        self.client.force_login(admin)

    def test_formular_hat_feld_und_speichert(self):
        r = self.client.get(reverse("schriftstueck_add"))
        self.assertContains(r, 'name="empfaenger_anschrift"')
        self.assertContains(r, "Empfängeranschrift (manuell)")
        r = self.client.post(reverse("schriftstueck_add"), {
            "titel": "T", "art": "brief", "betreff": "B", "datum": "2026-01-01", "status": "entwurf",
            "text": "<p>Hallo</p>", "empfaenger_anschrift": MANUELL})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Schriftstueck.objects.get().empfaenger_anschrift, MANUELL)
