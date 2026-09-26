from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Rolle, Verein, Zugang
from apps.documents.models import Ablagedokument
from apps.donations.models import Zuwendungsbestaetigung
from apps.finance import services as finance_services
from apps.finance.models import Rechnung, Rechnungsposition

from . import auto
from .client import PaperlessClient
from .models import PaperlessVerbindung
from .services import dokument_senden, dokumenttyp_fuer
from .tasks import fertiges_dokument_task


class Basis(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.verbindung = PaperlessVerbindung.objects.create(
            verein=self.v, url="https://paperless.example.org", api_token="geheim", aktiv=True)
        self.user = get_user_model().objects.create_superuser("admin", password="pw-Test-12345")
        self.client.force_login(self.user)


class DokumenttypTests(Basis):
    def _dok(self, **kw):
        return Ablagedokument.objects.create(verein=self.v, titel="X", datei=SimpleUploadedFile("x.pdf", b"x"), **kw)

    def test_typ_ist_die_art_des_dokuments(self):
        self.assertEqual(dokumenttyp_fuer(self.verbindung, self._dok(kategorie="rechnung")), "Rechnung")

    def test_eigener_typ_hat_vorrang(self):
        self.assertEqual(dokumenttyp_fuer(self.verbindung, self._dok(kategorie="rechnung", dokumenttyp="Eingangsrechnung")),
                         "Eingangsrechnung")

    def test_sonstiges_faellt_auf_den_standard_der_anbindung_zurueck(self):
        self.verbindung.dokumenttyp = "Vereinsunterlage"
        self.assertEqual(dokumenttyp_fuer(self.verbindung, self._dok(kategorie="sonstiges")), "Vereinsunterlage")

    def test_typ_wird_beim_senden_mitgegeben(self):
        d = self._dok(kategorie="protokoll")
        with patch.object(PaperlessClient, "dokument_finden", return_value=None), \
             patch.object(PaperlessClient, "dokument_senden", return_value="t") as senden:
            dokument_senden(self.verbindung, d)
        self.assertEqual(senden.call_args.kwargs["dokumenttyp"], "Protokoll")


class AutoUebergabeTests(Basis):
    @patch("apps.paperless.tasks.fertiges_dokument_task.delay")
    def test_rechnung_wird_automatisch_uebergeben(self, delay):
        with self.captureOnCommitCallbacks(execute=True):
            r = finance_services.rechnung_erstellen(self.v, [("Posten", 1, 10)])
        delay.assert_called_once_with("rechnung", r.pk)

    @patch("apps.paperless.tasks.fertiges_dokument_task.delay")
    def test_nichts_wenn_deaktiviert_oder_ohne_anbindung(self, delay):
        self.verbindung.auto_uebergabe = False
        self.verbindung.save()
        with self.captureOnCommitCallbacks(execute=True):
            finance_services.rechnung_erstellen(self.v, [("Posten", 1, 10)])
        self.verbindung.auto_uebergabe, self.verbindung.aktiv = True, False
        self.verbindung.save()
        with self.captureOnCommitCallbacks(execute=True):
            finance_services.rechnung_erstellen(self.v, [("Posten", 1, 10)])
        delay.assert_not_called()

    @patch("apps.paperless.tasks.fertiges_dokument_task.delay")
    def test_ausstellen_eines_entwurfs_loest_uebergabe_aus(self, delay):
        r = Rechnung.objects.create(verein=self.v, typ="individuell", status="entwurf", datum=date.today(),
                                    empfaenger_name="A")
        Rechnungsposition.objects.create(verein=self.v, rechnung=r, text="P", menge=1, einzelpreis=Decimal("5"))
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("rechnung_ausstellen", args=[r.pk]))
        r.refresh_from_db()
        self.assertEqual(r.status, "offen")
        delay.assert_called_once_with("rechnung", r.pk)

    def test_paperless_problem_verhindert_das_ausstellen_nicht(self):
        with patch("apps.paperless.auto.fertiges_dokument", side_effect=RuntimeError("Broker weg")):
            r = finance_services.rechnung_erstellen(self.v, [("Posten", 1, 10)])
        self.assertEqual(r.status, "offen")

    def test_task_legt_pdf_in_der_ablage_ab_und_uebergibt(self):
        r = finance_services.rechnung_erstellen(self.v, [("Posten", 1, 10)])
        with patch("apps.paperless.tasks.dokument_senden") as senden:
            fertiges_dokument_task("rechnung", r.pk)
        d = Ablagedokument.objects.get(verein=self.v, kategorie="rechnung")
        self.assertIn(r.nummer, d.titel)
        self.assertTrue(d.dateiname.endswith(".pdf"))
        self.assertEqual(d.tags, f"Rechnung, {date.today().year}")
        senden.assert_called_once()
        self.assertEqual(senden.call_args.args[1].pk, d.pk)

    def test_task_faellt_ohne_e_rechnung_auf_normale_pdf_zurueck(self):
        r = finance_services.rechnung_erstellen(self.v, [("Posten", 1, 10)])
        with patch("apps.finance.erechnung.zugferd_pdf", side_effect=ValueError("kaputt")), \
             patch("apps.paperless.tasks.dokument_senden"):
            fertiges_dokument_task("rechnung", r.pk)
        self.assertTrue(Ablagedokument.objects.filter(kategorie="rechnung").exists())

    @patch("apps.paperless.tasks.fertiges_dokument_task.delay")
    def test_zuwendungsbestaetigung_beim_ausstellen(self, delay):
        b = Zuwendungsbestaetigung.objects.create(
            verein=self.v, spender_name="S", spender_anschrift="Weg 1", betrag=Decimal("50"),
            datum_von=date(2026, 1, 1), datum_bis=date(2026, 1, 31))
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("zuwendungsbestaetigung_ausstellen", args=[b.pk]))
        delay.assert_called_once_with("zuwendung", b.pk)

    def test_abgelegtes_dokument_wird_uebergeben_und_als_wartend_markiert(self):
        d = Ablagedokument.objects.create(verein=self.v, titel="P", kategorie="protokoll",
                                          datei=SimpleUploadedFile("p.pdf", b"x"))
        with patch("apps.paperless.tasks.senden_task.delay") as delay:
            with self.captureOnCommitCallbacks(execute=True):
                self.assertTrue(auto.ablage_fertig(d))
        delay.assert_called_once_with(self.verbindung.pk, d.pk)
        d.refresh_from_db()
        self.assertEqual(d.paperless_status, "wartet")

    def test_broker_ausfall_wird_am_dokument_vermerkt(self):
        d = Ablagedokument.objects.create(verein=self.v, titel="P", datei=SimpleUploadedFile("p.pdf", b"x"))
        with patch("apps.paperless.tasks.senden_task.delay", side_effect=OSError("Redis weg")):
            with self.captureOnCommitCallbacks(execute=True):
                auto.ablage_fertig(d)
        d.refresh_from_db()
        self.assertEqual(d.paperless_status, "fehler")
        self.assertIn("Redis weg", d.paperless_fehler)

    @patch("apps.paperless.auto.ablage_fertig")
    def test_schriftstueck_nur_im_status_final(self, fertig):
        from apps.documents.models import Schriftstueck
        for status, erwartet in (("entwurf", 0), ("final", 1)):
            fertig.reset_mock()
            s = Schriftstueck.objects.create(verein=self.v, titel=f"S {status}", art="protokoll", status=status,
                                             text="Text", datum=date.today())
            self.client.post(reverse("schriftstueck_ablegen", args=[s.pk]))
            self.assertEqual(fertig.call_count, erwartet, status)
