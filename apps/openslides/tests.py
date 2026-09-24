from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Rolle, Verein, Zugang
from apps.events.models import Veranstaltung, Wahlergebnis
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


def _wahl_antwort():
    """Simulierte Autoupdate-Antwort: eine Wahl ("1. Vorsitzender") mit einem abgeschlossenen Wahlgang und
    zwei Kandidaten (Max Muster, Erika Musterfrau) - nach dem Datenmodell aus openslides-meta (assignment ->
    poll -> option -> poll_candidate_list -> poll_candidate -> user)."""
    return {
        "meeting/5/assignment_ids": [12],
        "assignment/12/title": "1. Vorsitzender",
        "assignment/12/poll_ids": [45],
        "poll/45/title": "Wahlgang 1",
        "poll/45/state": "published",
        "poll/45/option_ids": [100, 101],
        "option/100/yes": "8.000000", "option/100/no": "1.000000", "option/100/abstain": "1.000000",
        "option/100/content_object_id": "poll_candidate_list/7",
        "poll_candidate_list/7/poll_candidate_ids": [200],
        "poll_candidate/200/user_id": 42,
        "user/42/first_name": "Max", "user/42/last_name": "Muster",
        "option/101/yes": "3.000000", "option/101/no": "5.000000", "option/101/abstain": "2.000000",
        "option/101/content_object_id": "poll_candidate_list/8",
        "poll_candidate_list/8/poll_candidate_ids": [201],
        "poll_candidate/201/user_id": 43,
        "user/43/first_name": "Erika", "user/43/last_name": "Musterfrau",
    }


class WahlergebnisseAbrufenTests(TestCase):
    """Rückfluss der Wahlergebnisse aus OpenSlides (assignment/poll/option/poll_candidate/user) ins Protokoll -
    die eigentliche HTTP-Abfrage wird über OSClient.abfragen gemockt, da keine echte Instanz erreichbar ist."""

    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.verbindung = OpenSlidesVerbindung.objects.create(
            verein=self.v, url="https://os.example.org", benutzername="sync", passwort="geheim")
        self.ver = Veranstaltung.objects.create(verein=self.v, titel="Mitgliederversammlung 2026",
                                                beginn=timezone.now(), openslides_meeting_id=5)

    def test_ohne_meeting_id_wird_abgelehnt(self):
        self.ver.openslides_meeting_id = None
        self.ver.save()
        with self.assertRaises(OpenSlidesFehler):
            services.wahlergebnisse_abrufen(self.verbindung, self.ver)

    def test_speichert_ergebnis_je_wahlgang(self):
        with patch("apps.openslides.services.OSClient") as MockClient:
            MockClient.return_value.abfragen.return_value = _wahl_antwort()
            n = services.wahlergebnisse_abrufen(self.verbindung, self.ver)
        self.assertEqual(n, 1)
        w = Wahlergebnis.objects.get(verein=self.v, veranstaltung=self.ver)
        self.assertEqual(w.amt, "1. Vorsitzender")
        self.assertEqual(w.wahlgang, "Wahlgang 1")
        self.assertIn("Max Muster: 8.000000 Ja, 1.000000 Nein, 1.000000 Enthaltung", w.ergebnis)
        self.assertIn("Erika Musterfrau: 3.000000 Ja, 5.000000 Nein, 2.000000 Enthaltung", w.ergebnis)

    def test_nicht_abgeschlossene_wahl_wird_uebersprungen(self):
        antwort = _wahl_antwort()
        antwort["poll/45/state"] = "started"
        with patch("apps.openslides.services.OSClient") as MockClient:
            MockClient.return_value.abfragen.return_value = antwort
            n = services.wahlergebnisse_abrufen(self.verbindung, self.ver)
        self.assertEqual(n, 0)
        self.assertFalse(Wahlergebnis.objects.filter(veranstaltung=self.ver).exists())

    def test_erneuter_abruf_ersetzt_alte_ergebnisse(self):
        Wahlergebnis.objects.create(verein=self.v, veranstaltung=self.ver, amt="Veraltet", wahlgang="",
                                    ergebnis="nicht mehr aktuell")
        with patch("apps.openslides.services.OSClient") as MockClient:
            MockClient.return_value.abfragen.return_value = _wahl_antwort()
            services.wahlergebnisse_abrufen(self.verbindung, self.ver)
        ergebnisse = Wahlergebnis.objects.filter(veranstaltung=self.ver)
        self.assertEqual(ergebnisse.count(), 1)
        self.assertFalse(ergebnisse.filter(amt="Veraltet").exists())


class VeranstaltungWahlergebnisseViewTests(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        OpenSlidesVerbindung.objects.create(verein=self.v, url="https://os.example.org", benutzername="sync",
                                            passwort="geheim", aktiv=True)
        self.ver = Veranstaltung.objects.create(verein=self.v, titel="Mitgliederversammlung 2026",
                                                beginn=timezone.now(), openslides_meeting_id=5)
        User = get_user_model()
        self.admin = User.objects.create_superuser("admin", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=self.admin, rolle=Rolle.objects.get(verein=self.v,
                                                                                       name="Superadministrator"))
        self.client.login(username="admin", password="pw-Test-12345")

    def test_knopf_erscheint_wenn_meeting_verknuepft(self):
        r = self.client.get(reverse("veranstaltung_detail", args=[self.ver.pk]))
        self.assertContains(r, "Wahlergebnisse aus OpenSlides übernehmen")

    def test_ohne_meeting_verknuepfung_kein_knopf(self):
        self.ver.openslides_meeting_id = None
        self.ver.save()
        r = self.client.get(reverse("veranstaltung_detail", args=[self.ver.pk]))
        self.assertNotContains(r, "Wahlergebnisse aus OpenSlides übernehmen")

    def test_post_uebernimmt_ergebnisse_und_zeigt_abschnitt(self):
        with patch("apps.openslides.services.OSClient") as MockClient:
            MockClient.return_value.abfragen.return_value = _wahl_antwort()
            r = self.client.post(reverse("veranstaltung_wahlergebnisse", args=[self.ver.pk]), follow=True)
        self.assertContains(r, "1 Wahlergebnis(se) aus OpenSlides übernommen.")
        r2 = self.client.get(reverse("veranstaltung_detail", args=[self.ver.pk]))
        self.assertContains(r2, "Wahlergebnisse (aus OpenSlides)")
        self.assertContains(r2, "1. Vorsitzender")
