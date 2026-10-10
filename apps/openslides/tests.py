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
        self.assertIn("Max Muster: 8 Ja, 1 Nein, 1 Enthaltung", w.ergebnis)
        self.assertIn("Erika Musterfrau: 3 Ja, 5 Nein, 2 Enthaltung", w.ergebnis)
        self.assertEqual(w.art, "wahl")
        self.assertEqual(w.openslides_poll_id, 45)

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
        self.assertContains(r, "Anwesenheit, Wahlen und Abstimmungen aus OpenSlides übernehmen")

    def test_ohne_meeting_verknuepfung_kein_knopf(self):
        self.ver.openslides_meeting_id = None
        self.ver.save()
        r = self.client.get(reverse("veranstaltung_detail", args=[self.ver.pk]))
        self.assertNotContains(r, "Anwesenheit, Wahlen und Abstimmungen aus OpenSlides übernehmen")

    def test_post_uebernimmt_ergebnisse_und_zeigt_abschnitt(self):
        with patch("apps.openslides.services.OSClient") as MockClient:
            MockClient.return_value.abfragen.return_value = _wahl_antwort()
            r = self.client.post(reverse("veranstaltung_wahlergebnisse", args=[self.ver.pk]), follow=True)
        self.assertContains(r, "1 Wahlergebnis(se), 0 Abstimmung(en) und 0 Anwesende aus OpenSlides übernommen.")
        r2 = self.client.get(reverse("veranstaltung_detail", args=[self.ver.pk]))
        self.assertContains(r2, "Wahlergebnisse (aus OpenSlides)")
        self.assertContains(r2, "1. Vorsitzender")


class SsrfSchutzTests(TestCase):
    """Die OpenSlides-Adresse darf nicht auf interne Dienste (SSRF) zeigen - siehe
    apps.core.util.pruefe_oeffentliche_adresse."""

    def test_interne_adresse_wird_bei_voller_pruefung_abgelehnt(self):
        from django.core.exceptions import ValidationError
        v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        verbindung = OpenSlidesVerbindung(verein=v, url="http://169.254.169.254/", benutzername="bot")
        with self.assertRaises(ValidationError):
            verbindung.clean()


def _antrag_antwort():
    """Simulierte Autoupdate-Antwort fuer Antraege: Antrag A1 mit einer abgeschlossenen Abstimmung (Ja/Nein/
    Enthaltung auf EINER Option ohne Text), Status "beschlossen", dazu eine noch laufende Abstimmung."""
    return {
        "meeting/5/motion_ids": [7],
        "motion/7/number": "A1", "motion/7/title": "Beitragserhöhung", "motion/7/state_id": 3,
        "motion_state/3/name": "beschlossen",
        "motion/7/poll_ids": [60, 61],
        "poll/60/title": "Abstimmung", "poll/60/state": "published", "poll/60/option_ids": [300],
        "poll/60/votesvalid": "12.000000", "poll/60/votesinvalid": "0.000000", "poll/60/votescast": "12.000000",
        "option/300/yes": "9.000000", "option/300/no": "2.000000", "option/300/abstain": "1.000000",
        "poll/61/title": "Läuft noch", "poll/61/state": "started", "poll/61/option_ids": [301],
        "option/301/yes": "1.000000", "option/301/no": "0.000000", "option/301/abstain": "0.000000",
    }


def _thema_antwort():
    return {
        "meeting/5/topic_ids": [9],
        "topic/9/title": "Entlastung des Vorstands",
        "topic/9/poll_ids": [70],
        "poll/70/title": "Abstimmung Entlastung", "poll/70/state": "finished", "poll/70/option_ids": [400],
        "option/400/yes": "10", "option/400/no": "0", "option/400/abstain": "2",
    }


class AbstimmungenAbrufenTests(TestCase):
    """Alle Abstimmungen (Antraege, Themen) einer OpenSlides-Versammlung ins Protokoll uebernehmen. Die HTTP-
    Abfragen (Wahlen, Antraege, Themen - in dieser Reihenfolge) werden ueber OSClient.abfragen gemockt."""

    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.verbindung = OpenSlidesVerbindung.objects.create(
            verein=self.v, url="https://os.example.org", benutzername="sync", passwort="geheim")
        self.ver = Veranstaltung.objects.create(verein=self.v, titel="Mitgliederversammlung 2026",
                                                beginn=timezone.now(), openslides_meeting_id=5)

    def _abrufen(self, wahlen=None, antraege=None, themen=None):
        with patch("apps.openslides.services.OSClient") as MockClient:
            MockClient.return_value.abfragen.side_effect = [wahlen or {}, antraege or {}, themen or {}]
            return services.wahlergebnisse_abrufen(self.verbindung, self.ver)

    def test_antrag_wird_mit_stimmen_gesamtzahlen_und_status_gespeichert(self):
        self.assertEqual(self._abrufen(antraege=_antrag_antwort()), 1)
        a = Wahlergebnis.objects.get(veranstaltung=self.ver)
        self.assertEqual(a.art, "abstimmung")
        self.assertEqual(a.amt, "Antrag A1: Beitragserhöhung")
        self.assertEqual(a.wahlgang, "Abstimmung")
        self.assertEqual(a.openslides_poll_id, 60)
        self.assertIn("9 Ja, 2 Nein, 1 Enthaltung", a.ergebnis)
        self.assertIn("Gültige Stimmen: 12", a.ergebnis)
        self.assertIn("Status in OpenSlides: beschlossen", a.ergebnis)
        self.assertNotIn("Option", a.ergebnis)

    def test_laufende_abstimmung_wird_uebersprungen(self):
        self._abrufen(antraege=_antrag_antwort())
        self.assertFalse(Wahlergebnis.objects.filter(openslides_poll_id=61).exists())

    def test_thema_wird_uebernommen(self):
        self.assertEqual(self._abrufen(themen=_thema_antwort()), 1)
        t = Wahlergebnis.objects.get(veranstaltung=self.ver)
        self.assertEqual((t.art, t.amt), ("abstimmung", "Thema: Entlastung des Vorstands"))
        self.assertIn("10 Ja, 0 Nein, 2 Enthaltung", t.ergebnis)

    def test_wahlen_und_abstimmungen_zusammen_und_idempotent(self):
        n = self._abrufen(wahlen=_wahl_antwort(), antraege=_antrag_antwort(), themen=_thema_antwort())
        self.assertEqual(n, 3)
        self.assertEqual(Wahlergebnis.objects.filter(art="wahl").count(), 1)
        self.assertEqual(Wahlergebnis.objects.filter(art="abstimmung").count(), 2)
        self._abrufen(antraege=_antrag_antwort())   # erneuter Abruf ersetzt alles
        self.assertEqual(Wahlergebnis.objects.count(), 1)

    def test_fehlerantwort_ohne_daten_ergibt_nichts(self):
        self.assertEqual(self._abrufen(antraege={"message": "kaputt"}, themen={"message": "kaputt"}), 0)

    def test_zahlen_lesbar(self):
        self.assertEqual(services._zahl("8.000000"), "8")
        self.assertEqual(services._zahl("0.500000"), "0,5")
        self.assertEqual(services._zahl("10"), "10")
        self.assertEqual(services._zahl("keine"), "keine")


class ProtokollAbstimmungenViewTests(TestCase):
    def setUp(self):
        from apps.documents.models import Schriftstueck
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        OpenSlidesVerbindung.objects.create(verein=self.v, url="https://os.example.org", benutzername="sync",
                                            passwort="geheim", aktiv=True)
        self.ver = Veranstaltung.objects.create(verein=self.v, titel="Mitgliederversammlung 2026",
                                                beginn=timezone.now(), openslides_meeting_id=5)
        self.s = Schriftstueck.objects.create(verein=self.v, titel="Protokoll MV", art="protokoll",
                                              veranstaltung=self.ver, text="Beginn der Sitzung.")
        User = get_user_model()
        self.admin = User.objects.create_superuser("admin", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=self.admin, rolle=Rolle.objects.get(verein=self.v,
                                                                                       name="Superadministrator"))
        self.client.login(username="admin", password="pw-Test-12345")
        self.url = reverse("schriftstueck_abstimmungen", args=[self.s.pk])

    def _post(self, **antworten):
        with patch("apps.openslides.services.OSClient") as MockClient:
            MockClient.return_value.abfragen.side_effect = [antworten.get("wahlen", {}),
                                                            antworten.get("antraege", {}),
                                                            antworten.get("themen", {}),
                                                            antworten.get("anwesenheit", {})]
            return self.client.post(self.url, follow=True)

    def test_knopf_nur_bei_protokoll_mit_verknuepfter_versammlung(self):
        self.assertContains(self.client.get(reverse("schriftstueck_detail", args=[self.s.pk])),
                            "Anwesenheit, Abstimmungen und Wahlen aus OpenSlides einfügen")
        self.ver.openslides_meeting_id = None
        self.ver.save()
        self.assertNotContains(self.client.get(reverse("schriftstueck_detail", args=[self.s.pk])),
                               "Anwesenheit, Abstimmungen und Wahlen aus OpenSlides einfügen")

    def test_fuegt_abschnitte_ein_und_platzhalter_zeigen_ergebnis(self):
        r = self._post(antraege=_antrag_antwort(), wahlen=_wahl_antwort())
        self.assertContains(r, "1 Wahlergebnis(se), 1 Abstimmung(en) und 0 Anwesende aus OpenSlides übernommen.")
        self.s.refresh_from_db()
        self.assertIn("{abstimmungen}", self.s.text)
        self.assertIn("{wahlergebnisse}", self.s.text)
        self.assertTrue(self.s.text.startswith("Beginn der Sitzung."))
        ctx = self.s.kontext()
        from apps.documents.platzhalter import ersetzen
        ausgefuellt = ersetzen(self.s.text, ctx)
        self.assertIn("Antrag A1: Beitragserhöhung", ausgefuellt)
        self.assertIn("9 Ja, 2 Nein, 1 Enthaltung", ausgefuellt)
        self.assertIn("1. Vorsitzender", ausgefuellt)

    def test_erneuter_klick_verdoppelt_nichts_und_behaelt_eigene_ergaenzungen(self):
        self._post(antraege=_antrag_antwort())
        self.s.refresh_from_db()
        self.s.text += "\nEigene Ergänzung."
        self.s.save()
        text_vorher = self.s.text
        r = self._post(antraege=_antrag_antwort())
        self.assertContains(r, "Platzhalter bereits")
        self.s.refresh_from_db()
        self.assertEqual(self.s.text, text_vorher)
        self.assertEqual(self.s.text.count("{abstimmungen}"), 1)

    def test_ohne_ergebnisse_warnung_und_text_unveraendert(self):
        r = self._post()
        self.assertContains(r, "Keine abgeschlossenen Wahlen oder Abstimmungen und keine Anwesenden")
        self.s.refresh_from_db()
        self.assertEqual(self.s.text, "Beginn der Sitzung.")

    def test_abgelehnt_ohne_verknuepfung_oder_fremdes_protokoll(self):
        self.ver.openslides_meeting_id = None
        self.ver.save()
        r = self.client.post(self.url, follow=True)
        self.assertContains(r, "Nur für Protokolle")

    def test_nur_mit_rechten(self):
        User = get_user_model()
        User.objects.create_user("anna", password="pw-Test-12345")
        self.client.login(username="anna", password="pw-Test-12345")
        self.assertIn(self.client.post(self.url).status_code, (302, 403))
        self.s.refresh_from_db()
        self.assertEqual(self.s.text, "Beginn der Sitzung.")


def _anwesenheit_antwort():
    """Simulierte Autoupdate-Antwort: zwei als anwesend markierte Personen - ein Mitglied (OpenSlides-Konto 42) und
    ein Gast ohne Mitgliedskonto."""
    return {
        "meeting/5/present_user_ids": [42, 99],
        "user/42/first_name": "Erika", "user/42/last_name": "OS-Name-wird-nicht-gebraucht",
        "user/99/first_name": "Gast", "user/99/last_name": "Besucher",
    }


class AnwesenheitAbrufenTests(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.verbindung = OpenSlidesVerbindung.objects.create(
            verein=self.v, url="https://os.example.org", benutzername="sync", passwort="geheim")
        self.ver = Veranstaltung.objects.create(verein=self.v, titel="Mitgliederversammlung 2026",
                                                beginn=timezone.now(), openslides_meeting_id=5)
        self.m = Mitglied.objects.create(verein=self.v, vorname="Erika", nachname="Muster", mitgliedsnummer=7,
                                         openslides_user_id=42, openslides_username="erika.muster")

    def _abrufen(self, antwort):
        with patch("apps.openslides.services.OSClient") as MockClient:
            MockClient.return_value.abfragen.return_value = antwort
            return services.anwesenheit_abrufen(self.verbindung, self.ver)

    def test_mitglied_wird_zugeordnet_gast_behaelt_namen(self):
        from apps.events.models import Anwesenheit
        self.assertEqual(self._abrufen(_anwesenheit_antwort()), 2)
        mitglied = Anwesenheit.objects.get(openslides_user_id=42)
        self.assertEqual(mitglied.mitglied, self.m)
        self.assertEqual(mitglied.name, "")   # Name wird nicht kopiert (DSGVO-Anonymisierung wirkt)
        self.assertEqual(mitglied.wer, "Erika Muster")
        gast = Anwesenheit.objects.get(openslides_user_id=99)
        self.assertIsNone(gast.mitglied)
        self.assertEqual(gast.wer, "Gast Besucher")

    def test_mitglied_eines_anderen_vereins_wird_nicht_zugeordnet(self):
        from apps.events.models import Anwesenheit
        anderer = Verein.objects.create(name="Anderer e.V.", kuerzel="anderer")
        Mitglied.objects.create(verein=anderer, vorname="Fremd", nachname="Person", mitgliedsnummer=1,
                                openslides_user_id=99)
        self._abrufen(_anwesenheit_antwort())
        self.assertIsNone(Anwesenheit.objects.get(openslides_user_id=99).mitglied)

    def test_erneuter_abruf_ersetzt_den_stand(self):
        from apps.events.models import Anwesenheit
        self._abrufen(_anwesenheit_antwort())
        self._abrufen({"meeting/5/present_user_ids": [42], "user/42/first_name": "Erika"})
        self.assertEqual(Anwesenheit.objects.filter(veranstaltung=self.ver).count(), 1)

    def test_niemand_anwesend_ist_kein_fehler(self):
        from apps.events.models import Anwesenheit
        self._abrufen(_anwesenheit_antwort())
        self.assertEqual(self._abrufen({"meeting/5/present_user_ids": []}), 0)
        self.assertFalse(Anwesenheit.objects.exists())

    def test_fehlerantwort_loescht_nichts_und_wird_gemeldet(self):
        from apps.events.models import Anwesenheit
        self._abrufen(_anwesenheit_antwort())
        with self.assertRaises(OpenSlidesFehler):
            self._abrufen({"success": False, "message": "Kein Zugriff"})
        self.assertEqual(Anwesenheit.objects.count(), 2)

    def test_ohne_meeting_wird_abgelehnt(self):
        self.ver.openslides_meeting_id = None
        self.ver.save()
        with self.assertRaises(OpenSlidesFehler):
            services.anwesenheit_abrufen(self.verbindung, self.ver)

    def test_platzhalter_anwesenheit_und_anzahl(self):
        from apps.documents.platzhalter import kontext
        self.verbindung.aktiv = True
        self.verbindung.save()
        ctx = kontext(self.v, veranstaltung=self.ver)
        self.assertEqual(ctx["anwesenheit_anzahl"], "[Anzahl]")
        self.assertIn("keine Anwesenheit", ctx["anwesenheit"])
        self._abrufen(_anwesenheit_antwort())
        ctx = kontext(self.v, veranstaltung=self.ver)
        self.assertEqual(ctx["anwesenheit_anzahl"], "2")
        self.assertEqual(ctx["anwesenheit"], "- Erika Muster\n- Gast Besucher")

    def test_anonymisiertes_mitglied_erscheint_anonymisiert(self):
        from apps.documents.platzhalter import kontext
        self._abrufen(_anwesenheit_antwort())
        self.m.vorname, self.m.nachname = "Anonymisiert", "#7"
        self.m.save()
        self.assertIn("Anonymisiert #7", kontext(self.v, veranstaltung=self.ver)["anwesenheit"])
        self.assertNotIn("Erika", kontext(self.v, veranstaltung=self.ver)["anwesenheit"])


class ProtokollAnwesenheitViewTests(ProtokollAbstimmungenViewTests):
    """Der Knopf am Protokoll fuegt zusaetzlich die Anwesenheitsliste ein (erbt Einrichtung und Hilfsmethode)."""

    def test_anwesenheit_wird_abgerufen_und_abschnitt_eingefuegt(self):
        r = self._post(anwesenheit=_anwesenheit_antwort(), antraege=_antrag_antwort())
        self.assertContains(r, "1 Abstimmung(en) und 2 Anwesende aus OpenSlides übernommen.")
        self.s.refresh_from_db()
        self.assertIn("{anwesenheit}", self.s.text)
        from apps.documents.platzhalter import ersetzen
        text = ersetzen(self.s.text, self.s.kontext())
        self.assertIn("- Gast Besucher", text)

    def test_veranstaltung_zeigt_abschnitt_anwesenheit(self):
        self._post(anwesenheit=_anwesenheit_antwort())
        r = self.client.get(reverse("veranstaltung_detail", args=[self.ver.pk]))
        self.assertContains(r, "Anwesenheit (aus OpenSlides)")
        self.assertContains(r, "Gast Besucher")


class LoginFehlerHinweisTests(TestCase):
    """Fehlermeldung beim Anmelden: bei Proxy-Fehlern (leere Antwort) ein konkreter Suchhinweis."""

    def _login(self, status, text=""):
        from types import SimpleNamespace
        from .client import OSClient
        v = SimpleNamespace(url="https://os.example.org", tls_pruefen=True, benutzername="u", passwort="p")
        c = OSClient(v)
        antwort = SimpleNamespace(status_code=status, text=text, headers={}, json=lambda: {})
        with patch.object(c.s, "post", return_value=antwort):
            with self.assertRaises(OpenSlidesFehler) as ctx:
                c.login()
        return str(ctx.exception)

    def test_502_nennt_ursache_und_befehle_statt_leerer_antwort(self):
        meldung = self._login(502)
        self.assertIn("HTTP 502).", meldung)
        self.assertIn("docker compose ps", meldung)
        self.assertNotIn("): ", meldung)   # keine leere Antwort hinter dem Doppelpunkt

    def test_antworttext_wird_weiter_angezeigt(self):
        self.assertIn("HTTP 400): kaputt", self._login(400, "kaputt"))

    def test_zugangsdaten_und_adresse_hinweise(self):
        self.assertIn("technischen Benutzers", self._login(403, "verboten"))
        self.assertIn("OpenSlides-Startseite", self._login(404, "nicht da"))
