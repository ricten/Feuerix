from unittest.mock import patch

from django.test import TestCase

from apps.core.models import Verein
from apps.members.models import Mitglied

from . import services
from .client import OpenSlidesFehler
from .models import OpenSlidesVerbindung


class VerbindungOderNoneTests(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")

    def test_keine_verbindung_angelegt(self):
        self.assertIsNone(services.verbindung_oder_none(self.v))

    def test_unvollstaendige_verbindung(self):
        OpenSlidesVerbindung.objects.create(verein=self.v, url="https://os.example.org")  # ohne Benutzer/Passwort
        self.assertIsNone(services.verbindung_oder_none(self.v))

    def test_vollstaendige_verbindung(self):
        v = OpenSlidesVerbindung.objects.create(verein=self.v, url="https://os.example.org",
                                                benutzername="sync", passwort="geheim")
        self.assertEqual(services.verbindung_oder_none(self.v), v)


class MitgliedAnonymisierenTests(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.verbindung = OpenSlidesVerbindung.objects.create(
            verein=self.v, url="https://os.example.org", benutzername="sync", passwort="geheim")
        self.m = Mitglied.objects.create(verein=self.v, vorname="Erika", nachname="Muster", mitgliedsnummer=7,
                                         openslides_user_id=42, openslides_username="erika.muster")

    def test_ohne_openslides_konto_passiert_nichts(self):
        m2 = Mitglied.objects.create(verein=self.v, vorname="Ohne", nachname="Konto")
        with patch("apps.openslides.services.OSClient") as MockClient:
            services.mitglied_anonymisieren(self.verbindung, m2)
        MockClient.assert_not_called()

    def test_ruft_user_update_mit_anonymisierten_daten_auf(self):
        with patch("apps.openslides.services.OSClient") as MockClient:
            instanz = MockClient.return_value
            services.mitglied_anonymisieren(self.verbindung, self.m)
        instanz.login.assert_called_once()
        name, daten_liste = instanz.action.call_args.args
        self.assertEqual(name, "user.update")
        daten = daten_liste[0]
        self.assertEqual(daten["id"], 42)
        self.assertEqual(daten["first_name"], "Anonymisiert")
        self.assertEqual(daten["last_name"], "#7")
        self.assertEqual(daten["email"], "")
        self.assertEqual(daten["is_active"], False)
        self.assertNotIn("muster", daten["username"].lower())

    def test_fehler_wird_weitergereicht(self):
        with patch("apps.openslides.services.OSClient") as MockClient:
            MockClient.return_value.login.side_effect = OpenSlidesFehler("kaputt")
            with self.assertRaises(OpenSlidesFehler):
                services.mitglied_anonymisieren(self.verbindung, self.m)

    def test_ohne_mitgliedsnummer_faellt_auf_pk_zurueck(self):
        self.m.mitgliedsnummer = None
        self.m.save()
        with patch("apps.openslides.services.OSClient") as MockClient:
            instanz = MockClient.return_value
            services.mitglied_anonymisieren(self.verbindung, self.m)
        daten = instanz.action.call_args.args[1][0]
        self.assertEqual(daten["last_name"], f"#{self.m.pk}")
