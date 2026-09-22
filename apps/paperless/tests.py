from datetime import date
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Rolle, Verein, Zugang
from apps.documents.models import Ablagedokument

from .client import PaperlessClient, PaperlessFehler
from .models import PaperlessVerbindung
from .services import dokument_senden as service_dokument_senden
from .services import verbindung_testen


def _antwort(status_code=200, json_data=None, text=""):
    r = Mock()
    r.status_code = status_code
    r.text = text
    r.json = Mock(return_value=json_data)
    return r


class ClientTests(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.verbindung = PaperlessVerbindung.objects.create(
            verein=self.v, url="https://paperless.example.org", api_token="geheim", aktiv=True)

    @patch("apps.paperless.client.requests.Session.request")
    def test_verbindung_testen_erfolgreich(self, req):
        req.return_value = _antwort(200, {"count": 0, "results": []})
        c = PaperlessClient(self.verbindung)
        self.assertEqual(c.verbindung_testen(), "Verbindung erfolgreich.")
        self.assertEqual(req.call_args.args, ("get", "https://paperless.example.org/api/documents/?page_size=1"))
        self.assertEqual(c.s.headers["Authorization"], "Token geheim")

    @patch("apps.paperless.client.requests.Session.request")
    def test_verbindung_testen_falscher_token(self, req):
        req.return_value = _antwort(401)
        c = PaperlessClient(self.verbindung)
        with self.assertRaises(PaperlessFehler):
            c.verbindung_testen()

    @patch("apps.paperless.client.requests.Session.request")
    def test_id_ermitteln_findet_vorhandenes(self, req):
        req.return_value = _antwort(200, {"count": 1, "results": [{"id": 7, "name": "Stromanbieter"}]})
        c = PaperlessClient(self.verbindung)
        self.assertEqual(c._id_ermitteln("korrespondent", "Stromanbieter"), 7)
        self.assertEqual(req.call_count, 1)  # kein POST noetig

    @patch("apps.paperless.client.requests.Session.request")
    def test_id_ermitteln_legt_neu_an(self, req):
        req.side_effect = [_antwort(200, {"count": 0, "results": []}), _antwort(201, {"id": 42, "name": "Neu"})]
        c = PaperlessClient(self.verbindung)
        self.assertEqual(c._id_ermitteln("dokumenttyp", "Neu"), 42)
        self.assertEqual(req.call_count, 2)
        self.assertEqual(req.call_args.kwargs["json"], {"name": "Neu"})

    @patch("apps.paperless.client.requests.Session.request")
    def test_dokument_senden_erfolgreich(self, req):
        req.side_effect = [
            _antwort(200, {"count": 1, "results": [{"id": 3}]}),  # Korrespondent gefunden
            _antwort(200, {"count": 0, "results": []}),           # Tag nicht gefunden
            _antwort(201, {"id": 9}),                              # Tag angelegt
            _antwort(200, json_data="9c2e6a3e-...-uuid"),          # post_document
        ]
        c = PaperlessClient(self.verbindung)
        task_id = c.dokument_senden("re.pdf", b"%PDF-1.4 ...", titel="Rechnung", erstellt=date(2026, 3, 1),
                                    korrespondent="Stromanbieter", tags=["Ablage"])
        self.assertEqual(task_id, "9c2e6a3e-...-uuid")
        letzter_aufruf = req.call_args
        self.assertEqual(letzter_aufruf.args[1], "https://paperless.example.org/api/documents/post_document/")
        self.assertEqual(letzter_aufruf.kwargs["data"]["correspondent"], 3)
        self.assertEqual(letzter_aufruf.kwargs["data"]["tags"], [9])
        self.assertEqual(letzter_aufruf.kwargs["data"]["title"], "Rechnung")
        self.assertEqual(letzter_aufruf.kwargs["files"]["document"], ("re.pdf", b"%PDF-1.4 ..."))

    @patch("apps.paperless.client.requests.Session.request")
    def test_dokument_senden_fehler_wird_gemeldet(self, req):
        req.return_value = _antwort(400, text="Ungültige Datei")
        c = PaperlessClient(self.verbindung)
        with self.assertRaises(PaperlessFehler):
            c.dokument_senden("x.pdf", b"...")

    @patch("apps.paperless.client.requests.Session.request")
    def test_aufgabe_status(self, req):
        req.return_value = _antwort(200, [{"status": "SUCCESS", "result": "", "related_document": 55}])
        c = PaperlessClient(self.verbindung)
        s = c.aufgabe_status("abc")
        self.assertEqual(s, {"status": "SUCCESS", "ergebnis": "", "dokument_id": 55})

    @patch("apps.paperless.client.requests.Session.request")
    def test_aufgabe_status_unbekannt(self, req):
        req.return_value = _antwort(200, [])
        c = PaperlessClient(self.verbindung)
        self.assertIsNone(c.aufgabe_status("abc"))


class ServiceTests(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.verbindung = PaperlessVerbindung.objects.create(
            verein=self.v, url="https://paperless.example.org", api_token="geheim", aktiv=True)
        self.dok = Ablagedokument.objects.create(
            verein=self.v, titel="Rechnung Strom", datum=date(2026, 3, 1),
            datei=SimpleUploadedFile("re.pdf", b"%PDF-1.4 Inhalt"))

    def test_verbindung_testen_speichert_ergebnis(self):
        with patch.object(PaperlessClient, "verbindung_testen", return_value="Verbindung erfolgreich."):
            verbindung_testen(self.verbindung)
        self.verbindung.refresh_from_db()
        self.assertEqual(self.verbindung.letzter_test, "Verbindung erfolgreich.")

    def test_dokument_senden_erfolgreich_vermerkt_task_id(self):
        with patch.object(PaperlessClient, "dokument_senden", return_value="task-123") as m:
            task_id = service_dokument_senden(self.verbindung, self.dok)
        self.assertEqual(task_id, "task-123")
        self.dok.refresh_from_db()
        self.assertEqual(self.dok.paperless_task_id, "task-123")
        self.assertIsNotNone(self.dok.paperless_gesendet_am)
        self.assertEqual(self.dok.paperless_fehler, "")
        self.assertEqual(m.call_args.kwargs["titel"], "Rechnung Strom")

    def test_dokument_senden_fehler_wird_am_dokument_vermerkt(self):
        with patch.object(PaperlessClient, "dokument_senden", side_effect=PaperlessFehler("Server nicht erreichbar")):
            with self.assertRaises(PaperlessFehler):
                service_dokument_senden(self.verbindung, self.dok)
        self.dok.refresh_from_db()
        self.assertIn("Server nicht erreichbar", self.dok.paperless_fehler)
        self.assertIsNone(self.dok.paperless_gesendet_am)


class ViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.admin = User.objects.create_superuser("admin", password="pw-Test-12345")
        self.schreiber = User.objects.create_user("schriftfuehrer", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=self.schreiber, rolle=Rolle.objects.get(
            verein=self.v, name="Schriftführer"))
        self.dok = Ablagedokument.objects.create(
            verein=self.v, titel="Protokoll", datum=date(2026, 3, 1),
            datei=SimpleUploadedFile("prot.pdf", b"%PDF-1.4 Inhalt"))

    def test_einstellungen_erfordert_anmeldung(self):
        r = self.client.get(reverse("paperless_einstellungen"))
        self.assertEqual(r.status_code, 302)

    def test_einstellungen_speichern(self):
        self.client.login(username="admin", password="pw-Test-12345")
        r = self.client.post(reverse("paperless_einstellungen"), {
            "url": "https://paperless.example.org", "api_token": "geheim-token", "korrespondent": "",
            "dokumenttyp": "", "tags": "", "tls_pruefen": "on", "aktiv": "on"}, follow=True)
        self.assertEqual(r.status_code, 200)
        v = PaperlessVerbindung.objects.get(verein=self.v)
        self.assertEqual(v.api_token, "geheim-token")
        self.assertTrue(v.aktiv)

    def test_test_view_zeigt_fehler_ohne_verbindung(self):
        self.client.login(username="admin", password="pw-Test-12345")
        r = self.client.post(reverse("paperless_test"), follow=True)
        self.assertContains(r, "API-Token")

    def test_dokument_senden_ohne_eingerichtete_verbindung(self):
        self.client.login(username="schriftfuehrer", password="pw-Test-12345")
        r = self.client.post(reverse("ablagedokument_paperless_senden", args=[self.dok.pk]), follow=True)
        self.assertContains(r, "noch nicht eingerichtet")

    @patch("apps.paperless.tasks.senden_task.delay")
    def test_dokument_senden_loest_task_aus(self, delay):
        PaperlessVerbindung.objects.create(verein=self.v, url="https://paperless.example.org",
                                           api_token="geheim", aktiv=True)
        self.client.login(username="schriftfuehrer", password="pw-Test-12345")
        r = self.client.post(reverse("ablagedokument_paperless_senden", args=[self.dok.pk]), follow=True)
        self.assertContains(r, "gesendet")
        v = PaperlessVerbindung.objects.get(verein=self.v)
        delay.assert_called_once_with(v.pk, self.dok.pk)

    def test_dokument_senden_ohne_recht_verboten(self):
        User = get_user_model()
        User.objects.create_user("leser", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=User.objects.get(username="leser"),
                              rolle=Rolle.objects.get(verein=self.v, name="Lesebenutzer"))
        self.client.login(username="leser", password="pw-Test-12345")
        r = self.client.post(reverse("ablagedokument_paperless_senden", args=[self.dok.pk]))
        self.assertEqual(r.status_code, 403)

    def test_sammelversand_seite_zeigt_dokumente(self):
        self.client.login(username="schriftfuehrer", password="pw-Test-12345")
        r = self.client.get(reverse("ablage_paperless_sammelversand"))
        self.assertContains(r, "Protokoll")

    @patch("apps.paperless.tasks.sammel_senden_task.delay")
    def test_sammelversand_post_loest_task_aus(self, delay):
        v = PaperlessVerbindung.objects.create(verein=self.v, url="https://paperless.example.org",
                                               api_token="geheim", aktiv=True)
        dok2 = Ablagedokument.objects.create(verein=self.v, titel="Einladung", datum=date(2026, 3, 2),
                                             datei=SimpleUploadedFile("ein.pdf", b"%PDF-1.4"))
        self.client.login(username="schriftfuehrer", password="pw-Test-12345")
        r = self.client.post(reverse("ablage_paperless_sammelversand"),
                            {"dokumente": [self.dok.pk, dok2.pk]}, follow=True)
        self.assertContains(r, "2 Dokument")
        delay.assert_called_once()
        args = delay.call_args.args
        self.assertEqual(args[0], v.pk)
        self.assertEqual(set(args[1]), {self.dok.pk, dok2.pk})

    def test_paperless_knopf_erscheint_nur_bei_aktiver_verbindung(self):
        self.client.login(username="schriftfuehrer", password="pw-Test-12345")
        r = self.client.get(reverse("ablagedokument_detail", args=[self.dok.pk]))
        self.assertNotContains(r, "An Paperless senden")
        PaperlessVerbindung.objects.create(verein=self.v, url="https://paperless.example.org",
                                           api_token="geheim", aktiv=True)
        r = self.client.get(reverse("ablagedokument_detail", args=[self.dok.pk]))
        self.assertContains(r, "An Paperless senden")
