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

    @patch("apps.paperless.client.requests.Session.request")
    def test_bestaetigung_ueber_pruefsumme_wenn_aufgaben_api_nichts_liefert(self, req):
        self._setze(paperless_status="uebergeben", paperless_task_id="t1", paperless_pruefsumme="abc123",
                    paperless_gesendet_am=timezone.now())
        req.side_effect = [_antwort(200, []),                          # Aufgabe unbekannt
                           _antwort(200, {"results": [{"id": 77}]})]   # Datei per Pruefsumme gefunden
        self.assertContains(self.client.get(self.url), "Dokument-ID 77")
        self.dok.refresh_from_db()
        self.assertEqual(self.dok.paperless_status, "fertig")

    @patch("apps.paperless.client.requests.Session.request")
    def test_aufgaben_api_mit_paginierter_antwort(self, req):
        req.return_value = _antwort(200, {"results": [{"status": "success", "result": "", "related_document": 5}]})
        self.assertEqual(PaperlessClient(self.verbindung).aufgabe_status("t")["status"], "SUCCESS")

    @patch("apps.paperless.client.requests.Session.request")
    def test_alte_uebergaben_ohne_status_werden_nachtraeglich_bestaetigt(self, req):
        self._setze(paperless_status="", paperless_pruefsumme="abc", paperless_gesendet_am=timezone.now())
        req.side_effect = [_antwort(200, {"results": [{"id": 9}]})]
        r = self.client.get(reverse("ablagedokument_detail", args=[self.dok.pk]))
        self.assertContains(r, self.url)   # Live-Status wird auch fuer Altbestand eingebunden
        self.assertContains(self.client.get(self.url), "Dokument-ID 9")

    def test_pruefsumme_ist_in_der_detailansicht_sichtbar(self):
        self._setze(paperless_pruefsumme="deadbeef" * 4)
        self.assertContains(self.client.get(reverse("ablagedokument_detail", args=[self.dok.pk])), "deadbeef")

    def test_uebergebene_tags_werden_am_dokument_gemerkt_und_angezeigt(self):
        self.verbindung.tags = "Ablage"
        self.verbindung.save()
        with patch.object(PaperlessClient, "dokument_finden", return_value=None), \
             patch.object(PaperlessClient, "dokument_senden", return_value="t"):
            service_dokument_senden(self.verbindung, self.dok)
        self.dok.refresh_from_db()
        self.assertEqual(self.dok.paperless_tags, "Ablage, " + self.dok.tags.replace(", ", ", "))
        r = self.client.get(reverse("ablagedokument_detail", args=[self.dok.pk]))
        self.assertContains(r, "Tags in Paperless")
        self.assertContains(r, self.dok.paperless_tags)

    def test_sammelversand_zeigt_tags_als_badges(self):
        r = self.client.get(reverse("ablage_paperless_sammelversand"))
        self.assertContains(r, "badge")


class VorschauTests(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.user = get_user_model().objects.create_user("schriftfuehrer", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=self.user, rolle=Rolle.objects.get(
            verein=self.v, name="Schriftführer"))
        self.client.force_login(self.user)

    def _dok(self, name, inhalt=b"%PDF-1.4 x", verein=None):
        return Ablagedokument.objects.create(verein=verein or self.v, titel=name,
                                             datei=SimpleUploadedFile(name, inhalt))

    def test_pdf_vorschau_inline_und_im_eigenen_frame_erlaubt(self):
        d = self._dok("a.pdf")
        r = self.client.get(reverse("ablagedokument_vorschau", args=[d.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertTrue(r["Content-Disposition"].startswith("inline"))
        self.assertEqual(r["X-Frame-Options"], "SAMEORIGIN")
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")

    def test_bild_vorschau(self):
        d = self._dok("b.PNG", b"\x89PNG")
        self.assertEqual(self.client.get(reverse("ablagedokument_vorschau", args=[d.pk]))["Content-Type"], "image/png")

    def test_keine_vorschau_fuer_aktive_oder_unbekannte_typen(self):
        for name in ("x.svg", "x.html", "x.docx"):
            d = self._dok(name, b"<script>alert(1)</script>")
            self.assertEqual(self.client.get(reverse("ablagedokument_vorschau", args=[d.pk])).status_code, 404, name)

    def test_fremder_verein_und_ohne_anmeldung(self):
        anderer = Verein.objects.create(name="Anderer", kuerzel="anderer")
        fremd = self._dok("f.pdf", verein=anderer)
        self.assertEqual(self.client.get(reverse("ablagedokument_vorschau", args=[fremd.pk])).status_code, 404)
        self.client.logout()
        d = self._dok("g.pdf")
        self.assertEqual(self.client.get(reverse("ablagedokument_vorschau", args=[d.pk])).status_code, 302)

    def test_detailseite_zeigt_vorschau_nur_bei_passendem_typ(self):
        pdf, docx = self._dok("a.pdf"), self._dok("a.docx")
        self.assertContains(self.client.get(reverse("ablagedokument_detail", args=[pdf.pk])), "<iframe")
        self.assertNotContains(self.client.get(reverse("ablagedokument_detail", args=[docx.pk])), "<iframe")
