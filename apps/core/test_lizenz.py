from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import lizenz
from .models import Lizenz, Verein

User = get_user_model()
PW = "pw-Test-12345"
ANTWORT = {"lizenz_id": "11111111-2222-3333-4444-555555555555", "token": "tok", "status": "aktiv", "meldung": ""}


def abgelaufen():
    lz = lizenz.laden()
    lz.erster_start = timezone.now() - timedelta(days=31)
    lz.save()


@override_settings(LICENSE_SERVER_URL="https://portal.example.org")
class LizenzTests(TestCase):
    def setUp(self):
        self.verein = Verein.objects.create(name="Testverein", kuerzel="test")
        self.admin = User.objects.create_superuser("admin", password=PW)
        self.user = User.objects.create_user("max", password=PW)

    def test_ohne_server_adresse_keine_pruefung(self):
        with override_settings(LICENSE_SERVER_URL=""):
            abgelaufen()
            self.assertEqual(lizenz.blockiert(), "")
            self.client.force_login(self.user)
            self.assertNotEqual(self.client.get(reverse("nach_login")).status_code, 403)

    def test_probezeit_laeuft_30_tage(self):
        self.assertEqual(lizenz.blockiert(), "")
        self.assertEqual(lizenz.tage_verbleibend(), 30)
        lz = lizenz.laden()
        lz.erster_start = timezone.now() - timedelta(days=29, hours=12)
        lz.save()
        self.assertEqual((lizenz.blockiert(), lizenz.tage_verbleibend()), ("", 1))
        abgelaufen()
        self.assertEqual((lizenz.blockiert(), lizenz.tage_verbleibend()), ("abgelaufen", 0))

    def test_nach_ablauf_zugriff_verweigert(self):
        abgelaufen()
        self.client.force_login(self.user)
        r = self.client.get(reverse("nach_login"))
        self.assertEqual(r.status_code, 403)
        self.assertContains(r, "Lizenz erforderlich", status_code=403)
        self.assertEqual(self.client.get(reverse("lizenz")).status_code, 403)   # nur Superadmin
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.get(reverse("nach_login")), reverse("lizenz"), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("lizenz")).status_code, 200)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("login")).status_code, 200)    # Anmeldung bleibt erreichbar

    def test_registrieren_hebt_sperre_auf_und_sendet_nur_namen(self):
        abgelaufen()
        self.client.force_login(self.admin)
        with patch("apps.core.lizenz._senden", return_value=ANTWORT) as s:
            r = self.client.post(reverse("lizenz"), {"email": "info@example.org"})
        self.assertRedirects(r, reverse("lizenz"), fetch_redirect_response=False)
        pfad, daten = s.call_args.args
        self.assertEqual(pfad, "/lizenz/registrieren/")
        self.assertEqual(daten["vereine"], ["Testverein"])
        self.assertEqual(daten["email"], "info@example.org")
        self.assertEqual(set(daten), {"vereine", "version", "email"})
        lz = lizenz.laden()
        self.assertEqual((lz.token, lz.kontakt_email, str(lz.lizenz_id)), ("tok", "info@example.org", ANTWORT["lizenz_id"]))
        self.assertEqual(lizenz.blockiert(), "")
        self.assertTrue(lizenz.registriert())

    def test_registrieren_fehler_und_ungueltige_mail(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse("lizenz"), {"email": "kaputt"})
        self.assertContains(r, "gültige E-Mail")
        with patch("apps.core.lizenz._senden", side_effect=lizenz.LizenzFehler("Der Lizenzserver ist nicht erreichbar (x).")):
            r = self.client.post(reverse("lizenz"), {"email": "a@example.org"})
        self.assertContains(r, "nicht erreichbar")
        self.assertFalse(lizenz.registriert())

    def test_zugang_aus_env_gilt_als_registriert(self):
        abgelaufen()
        with override_settings(LICENSE_ID="abc", LICENSE_TOKEN="def"):
            self.assertTrue(lizenz.registriert())
            self.assertEqual(lizenz.blockiert(), "")

    def test_pruefen_uebernimmt_sperre(self):
        lz = lizenz.laden()
        lz.lizenz_id, lz.token = ANTWORT["lizenz_id"], "tok"
        lz.save()
        with patch("apps.core.lizenz._senden", return_value={**ANTWORT, "status": "gesperrt", "meldung": "Missbrauch"}):
            lizenz.pruefen()
        self.assertEqual(lizenz.blockiert(), "gesperrt")
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("nach_login")), "Missbrauch", status_code=403)
        with patch("apps.core.lizenz._senden", return_value=ANTWORT):
            lizenz.pruefen()
        self.assertEqual(lizenz.blockiert(), "")

    def test_server_nicht_erreichbar_blockiert_registrierte_nicht(self):
        lz = lizenz.laden()
        lz.lizenz_id, lz.token, lz.status = ANTWORT["lizenz_id"], "tok", "aktiv"
        lz.erster_start = timezone.now() - timedelta(days=400)
        lz.save()
        with patch("apps.core.lizenz._senden", side_effect=lizenz.LizenzFehler("Der Lizenzserver ist nicht erreichbar (x).")):
            lizenz.pruefen()
        self.assertEqual(lizenz.blockiert(), "")
        self.assertIn("nicht erreichbar", lizenz.laden().letzter_fehler)

    def test_unbekannte_lizenz_wird_zur_neuregistrierung(self):
        lz = lizenz.laden()
        lz.lizenz_id, lz.token, lz.status = ANTWORT["lizenz_id"], "tok", "aktiv"
        lz.save()
        with patch("apps.core.lizenz._senden", side_effect=lizenz.LizenzFehler("unbekannt")):
            lizenz.pruefen()
        self.assertFalse(lizenz.registriert())
        self.assertIsNone(lizenz.laden().lizenz_id)

    def test_automatische_registrierung_mit_license_email(self):
        with override_settings(LICENSE_EMAIL="auto@example.org"), \
                patch("apps.core.lizenz._senden", return_value=ANTWORT) as s:
            lizenz.pruefen()
        self.assertEqual(s.call_args.args[1]["email"], "auto@example.org")
        self.assertTrue(lizenz.registriert())

    def test_pruefen_ohne_zugang_und_ohne_email_tut_nichts(self):
        with patch("apps.core.lizenz._senden") as s:
            lizenz.pruefen()
        s.assert_not_called()

    def test_pruefung_faellig_nur_alle_20_stunden(self):
        self.assertTrue(lizenz.pruefung_faellig())
        lz = lizenz.laden()
        lz.letzte_pruefung = timezone.now() - timedelta(hours=2)
        lz.save()
        self.assertFalse(lizenz.pruefung_faellig())
        lz.letzte_pruefung = timezone.now() - timedelta(hours=21)
        lz.save()
        self.assertTrue(lizenz.pruefung_faellig())

    def test_hinweis_nur_fuer_superadmin(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("lizenz"))
        self.assertContains(r, "Verbleibende Probezeit")
        self.assertContains(r, "Testverein")
        lizenz.laden()
        self.client.force_login(self.user)
        self.assertNotContains(self.client.get(reverse("nach_login"), follow=True), "Verbleibende Probezeit")

    def test_task_ruft_pruefen_nur_wenn_faellig(self):
        from .tasks import lizenz_pruefen_task
        with patch("apps.core.lizenz.pruefen") as p:
            lizenz_pruefen_task()
            p.assert_called_once()
            lz = lizenz.laden()
            lz.letzte_pruefung = timezone.now()
            lz.save()
            lizenz_pruefen_task()
            p.assert_called_once()
        self.assertTrue(Lizenz.objects.exists())
