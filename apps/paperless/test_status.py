from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Rolle, Verein, Zugang
from apps.documents.models import Ablagedokument

from .client import PaperlessClient
from .models import PaperlessVerbindung
from .services import dokument_senden as service_dokument_senden


def _antwort(status_code=200, json_data=None, text=""):
    r = Mock()
    r.status_code = status_code
    r.text = text
    r.json = Mock(return_value=json_data)
    return r


class LiveStatusTests(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.verbindung = PaperlessVerbindung.objects.create(
            verein=self.v, url="https://paperless.example.org", api_token="geheim", aktiv=True)
        self.user = get_user_model().objects.create_user("schriftfuehrer", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=self.user, rolle=Rolle.objects.get(
            verein=self.v, name="Schriftführer"))
        self.client.force_login(self.user)
        self.dok = Ablagedokument.objects.create(verein=self.v, titel="A", datei=SimpleUploadedFile("a.pdf", b"x"))
        self.url = reverse("ablagedokument_paperless_status", args=[self.dok.pk])

    def _setze(self, **kw):
        Ablagedokument.objects.filter(pk=self.dok.pk).update(**kw)

    def test_laufender_status_pollt_weiter(self):
        self._setze(paperless_status="wartet")
        r = self.client.get(self.url)
        self.assertContains(r, "Warteschlange")
        self.assertContains(r, 'hx-trigger="every 2s"')

    def test_fertig_pollt_nicht_mehr_und_laedt_detailseite_neu(self):
        self._setze(paperless_status="fertig", paperless_info="In Paperless abgelegt (Dokument-ID 5).")
        r = self.client.get(self.url + "?poll=1")
        self.assertNotContains(r, "every 2s")
        self.assertEqual(r["HX-Refresh"], "true")
        self.assertNotIn("HX-Refresh", self.client.get(self.url))   # erstes Laden: kein Neuladen
        self.assertNotIn("HX-Refresh", self.client.get(self.url + "?poll=1&kompakt=1"))

    def test_fehler_wird_angezeigt(self):
        self._setze(paperless_status="fehler", paperless_fehler="Server nicht erreichbar")
        self.assertContains(self.client.get(self.url), "Server nicht erreichbar")

    def test_haengender_auftrag_wird_zum_fehler(self):
        self._setze(paperless_status="wartet", geaendert=timezone.now() - timedelta(minutes=6))
        self.assertContains(self.client.get(self.url), "Worker")
        self.dok.refresh_from_db()
        self.assertEqual(self.dok.paperless_status, "fehler")

    @patch("apps.paperless.client.requests.Session.request")
    def test_uebergeben_fragt_paperless_und_wird_fertig(self, req):
        self._setze(paperless_status="uebergeben", paperless_task_id="t1")
        req.return_value = _antwort(200, [{"status": "SUCCESS", "result": "", "related_document": 55}])
        self.assertContains(self.client.get(self.url), "Dokument-ID 55")
        self.dok.refresh_from_db()
        self.assertEqual(self.dok.paperless_status, "fertig")

    @patch("apps.paperless.client.requests.Session.request")
    def test_paperless_verarbeitung_fehlgeschlagen(self, req):
        self._setze(paperless_status="uebergeben", paperless_task_id="t1")
        req.return_value = _antwort(200, [{"status": "FAILURE", "result": "kaputtes PDF", "related_document": None}])
        self.assertContains(self.client.get(self.url), "kaputtes PDF")

    @patch("apps.paperless.client.requests.Session.request")
    def test_verarbeitung_ohne_bestaetigung_endet_nach_timeout(self, req):
        self._setze(paperless_status="uebergeben", paperless_task_id="t1",
                    paperless_gesendet_am=timezone.now() - timedelta(minutes=11))
        req.return_value = _antwort(200, [{"status": "STARTED", "result": "", "related_document": None}])
        self.assertContains(self.client.get(self.url), "nicht bestätigt")

    @patch("apps.paperless.tasks.senden_task.delay")
    def test_senden_markiert_sofort_als_wartend(self, delay):
        self.client.post(reverse("ablagedokument_paperless_senden", args=[self.dok.pk]))
        self.dok.refresh_from_db()
        self.assertEqual(self.dok.paperless_status, "wartet")

    def test_detailseite_bindet_live_status_ein(self):
        self._setze(paperless_status="wartet")
        r = self.client.get(reverse("ablagedokument_detail", args=[self.dok.pk]))
        self.assertContains(r, self.url)

    def test_status_nur_fuer_eigenen_verein(self):
        anderer = Verein.objects.create(name="Anderer", kuerzel="anderer")
        fremd = Ablagedokument.objects.create(verein=anderer, titel="F", datei=SimpleUploadedFile("f.pdf", b"x"))
        self.assertEqual(self.client.get(reverse("ablagedokument_paperless_status", args=[fremd.pk])).status_code, 404)

    def test_service_setzt_status_uebergeben_bzw_uebersprungen(self):
        with patch.object(PaperlessClient, "dokument_finden", return_value=None), \
             patch.object(PaperlessClient, "dokument_senden", return_value="t"):
            service_dokument_senden(self.verbindung, self.dok)
            self.assertEqual(self.dok.paperless_status, "uebergeben")
            service_dokument_senden(self.verbindung, self.dok)
            self.assertEqual(self.dok.paperless_status, "uebersprungen")

    def _knoepfe(self):
        r = self.client.get(reverse("ablagedokument_detail", args=[self.dok.pk]))
        return "An Paperless senden" in r.content.decode(), "Erneut an Paperless senden" in r.content.decode()

    def test_knoepfe_je_zustand(self):
        # nie gesendet: nur "An Paperless senden"
        self.assertEqual(self._knoepfe(), (True, False))
        # laeuft: keiner
        self._setze(paperless_status="sendet")
        self.assertEqual(self._knoepfe(), (False, False))
        # erfolgreich gesendet: nur "Erneut senden" ("An Paperless senden" ist Teilstring -> genauer pruefen)
        self._setze(paperless_status="fertig", paperless_gesendet_am=timezone.now())
        r = self.client.get(reverse("ablagedokument_detail", args=[self.dok.pk])).content.decode()
        self.assertIn("Erneut an Paperless senden", r)
        self.assertNotIn(">An Paperless senden<", r.replace("> An Paperless senden <", ">An Paperless senden<"))
        # Fehler: wieder normal senden
        self._setze(paperless_status="fehler", paperless_fehler="x")
        self.assertEqual(self._knoepfe(), (True, False))
