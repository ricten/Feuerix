"""Vorschau (eingebettetes PDF) auf den Detailseiten von Rechnung, Zuwendungsbestätigung, Kassenbericht,
Schriftstück und Serienbrief. Feuerix verbietet sonst jedes Einbetten (X_FRAME_OPTIONS=DENY)."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounting.models import Kassenbericht
from apps.core.models import Verein
from apps.documents.models import Schriftstueck, Serienbrief
from apps.donations.models import Zuwendungsbestaetigung
from apps.finance import services as finance_services


class VorschauTests(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.client.force_login(get_user_model().objects.create_superuser("admin", password="pw-Test-12345"))

    def _pruefen(self, detail_name, pdf_name, obj):
        detail = self.client.get(reverse(detail_name, args=[obj.pk]))
        pdf_url = reverse(pdf_name, args=[obj.pk])
        self.assertContains(detail, "<iframe", msg_prefix=detail_name)
        self.assertContains(detail, pdf_url, msg_prefix=detail_name)
        pdf = self.client.get(pdf_url)
        self.assertEqual(pdf.status_code, 200, pdf_name)
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        # nur das eigene Frame ist erlaubt, kein fremdes Einbetten
        self.assertEqual(pdf["X-Frame-Options"], "SAMEORIGIN", pdf_name)

    def test_rechnung(self):
        r = finance_services.rechnung_erstellen(self.v, [("Posten", 1, 10)])
        self._pruefen("rechnung_detail", "rechnung_pdf", r)

    def test_kassenbericht(self):
        b = Kassenbericht.objects.create(verein=self.v, titel="Kassenbericht 2026", von=date(2026, 1, 1),
                                         bis=date(2026, 12, 31))
        self._pruefen("kassenbericht_detail", "kassenbericht_pdf", b)

    def test_zuwendungsbestaetigung(self):
        b = Zuwendungsbestaetigung.objects.create(
            verein=self.v, spender_name="S", spender_anschrift="Weg 1", betrag=Decimal("50"),
            datum_von=date(2026, 1, 1), datum_bis=date(2026, 1, 31))
        self._pruefen("zuwendungsbestaetigung_detail", "zuwendungsbestaetigung_pdf", b)

    def test_schriftstueck(self):
        s = Schriftstueck.objects.create(verein=self.v, titel="Brief", art="brief", text="Hallo", datum=date.today())
        self._pruefen("schriftstueck_detail", "schriftstueck_pdf", s)

    def test_serienbrief(self):
        sb = Serienbrief.objects.create(verein=self.v, titel="Info", betreff="B", text="Text", datum=date.today())
        self.assertContains(self.client.get(reverse("serienbrief_detail", args=[sb.pk])), "<iframe")

    def test_ohne_anmeldung_keine_vorschau(self):
        self.client.logout()
        r = finance_services.rechnung_erstellen(self.v, [("Posten", 1, 10)])
        self.assertEqual(self.client.get(reverse("rechnung_pdf", args=[r.pk])).status_code, 302)
