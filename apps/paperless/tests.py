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
from .services import tags_fuer, verbindung_testen


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
        with patch.object(PaperlessClient, "dokument_finden", return_value=None), \
             patch.object(PaperlessClient, "dokument_senden", return_value="task-123") as m:
            task_id = service_dokument_senden(self.verbindung, self.dok)
        self.assertEqual(task_id, "task-123")
        self.dok.refresh_from_db()
        self.assertEqual(self.dok.paperless_task_id, "task-123")
        self.assertIsNotNone(self.dok.paperless_gesendet_am)
        self.assertEqual(self.dok.paperless_fehler, "")
        self.assertEqual(m.call_args.kwargs["titel"], "Rechnung Strom")

    def test_dokument_senden_fehler_wird_am_dokument_vermerkt(self):
        with patch.object(PaperlessClient, "dokument_finden", return_value=None), \
             patch.object(PaperlessClient, "dokument_senden", side_effect=PaperlessFehler("Server nicht erreichbar")):
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
        delay.assert_called_once_with(v.pk, self.dok.pk, False)

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


class DuplikatUndTagTests(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.verbindung = PaperlessVerbindung.objects.create(
            verein=self.v, url="https://paperless.example.org", api_token="geheim", aktiv=True, tags="Ablage")
        self.dok = Ablagedokument.objects.create(
            verein=self.v, titel="Protokoll JHV", kategorie="protokoll", datum=date(2026, 3, 1),
            datei=SimpleUploadedFile("p.pdf", b"%PDF-1.4 Inhalt"))

    def _senden(self, **kw):
        with patch.object(PaperlessClient, "dokument_finden", return_value=kw.get("vorhanden")) as finden, \
             patch.object(PaperlessClient, "dokument_senden", return_value="task-1") as senden:
            ergebnis = service_dokument_senden(self.verbindung, self.dok, erneut=kw.get("erneut", False))
        return ergebnis, finden, senden

    def test_neue_dokumente_bekommen_art_und_jahr_als_tags_vorbelegt(self):
        self.assertEqual(self.dok.tags, "Protokoll, 2026")
        _, _, senden = self._senden()
        self.assertEqual(senden.call_args.kwargs["tags"], ["Ablage", "Protokoll", "2026"])

    def test_eigene_tags_haben_vorrang_vor_der_vorbelegung(self):
        self.dok.tags = "Wichtig, Vorstand"
        self.assertEqual(tags_fuer(self.verbindung, self.dok), ["Ablage", "Wichtig", "Vorstand"])

    def test_dokumente_ohne_tags_fallen_auf_art_und_jahr_zurueck_abschaltbar(self):
        self.dok.tags = ""
        self.assertEqual(tags_fuer(self.verbindung, self.dok), ["Ablage", "Protokoll", "2026"])
        self.verbindung.kategorie_tags = False
        self.assertEqual(tags_fuer(self.verbindung, self.dok), ["Ablage"])

    def test_tags_ohne_doppelte(self):
        self.verbindung.tags = "protokoll, Ablage"
        self.assertEqual(tags_fuer(self.verbindung, self.dok), ["protokoll", "Ablage", "2026"])

    def test_gesetzte_tags_werden_beim_anlegen_nicht_ueberschrieben(self):
        d = Ablagedokument.objects.create(verein=self.v, titel="X", tags="Nur-Das",
                                          datei=SimpleUploadedFile("x.pdf", b"x"))
        self.assertEqual(d.tags, "Nur-Das")

    def test_gleiche_version_wird_nicht_zweimal_uebergeben(self):
        self.assertEqual(self._senden()[0], "task-1")
        ergebnis, finden, senden = self._senden()
        self.assertIsNone(ergebnis)
        senden.assert_not_called()
        finden.assert_not_called()   # lokale Pruefung reicht, kein unnoetiger API-Aufruf
        self.dok.refresh_from_db()
        self.assertIn("bereits an Paperless übergeben", self.dok.paperless_info)

    def test_geaenderte_datei_wird_uebergeben(self):
        self._senden()
        self.dok.datei.save("p.pdf", SimpleUploadedFile("p.pdf", b"%PDF-1.4 ANDERER Inhalt"))
        ergebnis, _, senden = self._senden()
        self.assertEqual(ergebnis, "task-1")
        senden.assert_called_once()

    def test_in_paperless_vorhandene_datei_wird_uebernommen_nicht_gesendet(self):
        ergebnis, _, senden = self._senden(vorhanden=42)
        self.assertIsNone(ergebnis)
        senden.assert_not_called()
        self.dok.refresh_from_db()
        self.assertIsNotNone(self.dok.paperless_gesendet_am)
        self.assertIn("Dokument-ID 42", self.dok.paperless_info)

    def test_erneut_ueberspringt_die_pruefung(self):
        self._senden()
        ergebnis, finden, senden = self._senden(erneut=True)
        self.assertEqual(ergebnis, "task-1")
        finden.assert_not_called()

    def test_fehlgeschlagener_versand_wird_wiederholt(self):
        with patch.object(PaperlessClient, "dokument_finden", return_value=None), \
             patch.object(PaperlessClient, "dokument_senden", side_effect=PaperlessFehler("weg")):
            with self.assertRaises(PaperlessFehler):
                service_dokument_senden(self.verbindung, self.dok)
        self.assertEqual(self._senden()[0], "task-1")

    @patch("apps.paperless.client.requests.Session.request")
    def test_client_dokument_finden(self, req):
        req.return_value = _antwort(200, {"results": [{"id": 7}]})
        self.assertEqual(PaperlessClient(self.verbindung).dokument_finden("abc"), 7)
        self.assertEqual(req.call_args.kwargs["params"]["checksum__iexact"], "abc")
        req.return_value = _antwort(200, {"results": []})
        self.assertIsNone(PaperlessClient(self.verbindung).dokument_finden("abc"))
        req.return_value = _antwort(500, text="x")
        with self.assertRaises(PaperlessFehler):
            PaperlessClient(self.verbindung).dokument_finden("abc")


class UebersichtHakenTests(TestCase):
    def test_haken_nur_bei_uebergebenen_dokumenten(self):
        from django.utils import timezone
        from apps.core.crud import wert
        v = Verein.objects.create(name="T e.V.", kuerzel="t")
        d = Ablagedokument.objects.create(verein=v, titel="A", datei=SimpleUploadedFile("a.pdf", b"x"))
        self.assertEqual(wert(d, "paperless_uebergeben"), "–")
        d.paperless_gesendet_am = timezone.now()
        self.assertEqual(wert(d, "paperless_uebergeben"), "✓")
        d.paperless_fehler = "Fehler"
        self.assertEqual(wert(d, "paperless_uebergeben"), "–")
