from datetime import date
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Verein
from apps.members.models import Funktion, Mitglied, MitgliedFunktion

from .client import PaperlessClient, PaperlessFehler
from .models import PaperlessBenutzer, PaperlessVerbindung
from .services import mitglied_anonymisieren, vorstand_abgleichen


class Basis(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.verbindung = PaperlessVerbindung.objects.create(
            verein=self.v, url="https://paperless.example.org", api_token="geheim", aktiv=True)
        self.m = Mitglied.objects.create(verein=self.v, vorname="Erika", nachname="Müller", email="e@example.org",
                                         vorstandsmitglied=True)


class MarkerUndFunktionTests(Basis):
    def test_haken_setzt_und_beendet_die_funktion(self):
        f = MitgliedFunktion.objects.get(mitglied=self.m, funktion__name="Vorstandsmitglied")
        self.assertIsNone(f.bis)
        self.assertEqual(f.von, date.today())
        self.m.save()   # kein Duplikat
        self.assertEqual(MitgliedFunktion.objects.filter(mitglied=self.m).count(), 1)
        self.m.vorstandsmitglied = False
        self.m.save()
        f.refresh_from_db()
        self.assertEqual(f.bis, date.today())   # beendet, Verlauf bleibt
        self.m.vorstandsmitglied = True
        self.m.save()
        self.assertEqual(MitgliedFunktion.objects.filter(mitglied=self.m).count(), 2)

    def test_ohne_haken_keine_funktion(self):
        m = Mitglied.objects.create(verein=self.v, vorname="A", nachname="B")
        self.assertFalse(MitgliedFunktion.objects.filter(mitglied=m).exists())

    def test_marker_felder_standardmaessig_aus_und_unabhaengig(self):
        m = Mitglied.objects.create(verein=self.v, vorname="A", nachname="B", einsatzabteilung_aktiv=True)
        self.assertTrue(m.einsatzabteilung_aktiv)
        self.assertFalse(m.alters_ehrenabteilung)
        self.assertFalse(m.vorstandsmitglied)

    def test_funktion_wird_je_verein_angelegt(self):
        anderer = Verein.objects.create(name="Anderer", kuerzel="anderer")
        Mitglied.objects.create(verein=anderer, vorname="X", nachname="Y", vorstandsmitglied=True)
        self.assertEqual(Funktion.objects.filter(name="Vorstandsmitglied").count(), 2)

    def test_import_export_kennen_die_marker(self):
        from apps.members import importer
        csv_inhalt = ("Vorname;Nachname;Vorstandsmitglied;Alters- und Ehrenabteilung;"
                      "Aktives Mitglied der Einsatzabteilung\nAnna;Alt;ja;ja;\nBen;Aktiv;;;x\n").encode("utf-8")
        importer.importieren(self.v, "m.csv", csv_inhalt, testlauf=False, neu_anlegen=True)
        a = Mitglied.objects.get(vorname="Anna")
        b = Mitglied.objects.get(vorname="Ben")
        self.assertEqual((a.vorstandsmitglied, a.alters_ehrenabteilung, a.einsatzabteilung_aktiv), (True, True, False))
        self.assertEqual((b.vorstandsmitglied, b.alters_ehrenabteilung, b.einsatzabteilung_aktiv), (False, False, True))

    def test_liste_zeigt_marker_und_filter(self):
        self.client.force_login(get_user_model().objects.create_superuser("admin", password="pw-Test-12345"))
        Mitglied.objects.create(verein=self.v, vorname="Nur", nachname="Normal")
        r = self.client.get(reverse("mitglied_list") + "?vorstandsmitglied=True")
        self.assertContains(r, "Müller")
        self.assertNotContains(r, "Normal")


def _client_mock(**kw):
    c = Mock()
    c.gruppe_sicherstellen.return_value = 7
    c.benutzer_suchen.return_value = kw.get("vorhanden")
    c.benutzer_anlegen.return_value = 101
    c.benutzer_lesen.return_value = {"groups": [7, 9]}
    return c


class AbgleichTests(Basis):
    def _lauf(self, c):
        with patch("apps.paperless.services.PaperlessClient", return_value=c):
            return vorstand_abgleichen(self.verbindung)

    def test_legt_konto_mit_gruppe_an_ohne_adminrechte(self):
        c = _client_mock()
        info = self._lauf(c)
        daten = c.benutzer_anlegen.call_args.args[0]
        self.assertEqual(daten["username"], "erika.mueller")
        self.assertEqual(daten["groups"], [7])
        self.assertFalse(daten["is_superuser"])
        self.assertFalse(daten["is_staff"])
        self.assertEqual(len(daten["password"]), 14)
        k = PaperlessBenutzer.objects.get(mitglied=self.m)
        self.assertEqual((k.paperless_id, k.angelegt, k.initialpasswort), (101, True, daten["password"]))
        self.assertIn("1 Benutzer angelegt", info)
        c.gruppe_sicherstellen.assert_called_once_with("Vorstand", c.gruppe_sicherstellen.call_args.args[1])

    def test_zweiter_lauf_aktualisiert_statt_neu_anzulegen(self):
        self._lauf(_client_mock())
        c = _client_mock()
        info = self._lauf(c)
        c.benutzer_anlegen.assert_not_called()
        self.assertEqual(c.benutzer_aendern.call_args.args[0], 101)
        self.assertIn("1 aktualisiert", info)

    def test_nur_aktive_vorstandsmitglieder(self):
        Mitglied.objects.create(verein=self.v, vorname="Nur", nachname="Mitglied")
        Mitglied.objects.create(verein=self.v, vorname="Aus", nachname="Getreten", vorstandsmitglied=True,
                                status="ausgetreten")
        c = _client_mock()
        self._lauf(c)
        self.assertEqual(c.benutzer_anlegen.call_count, 1)

    def test_bestehendes_konto_wird_nur_der_gruppe_zugeordnet(self):
        c = _client_mock(vorhanden={"id": 5, "groups": [2]})
        self._lauf(c)
        c.benutzer_anlegen.assert_not_called()
        self.assertEqual(c.benutzer_aendern.call_args.args, (5, {"groups": [2, 7]}))
        k = PaperlessBenutzer.objects.get(mitglied=self.m)
        self.assertFalse(k.angelegt)
        self.assertEqual(k.initialpasswort, "")

    def test_ausgeschiedene_werden_entfernt_angelegte_deaktiviert(self):
        self._lauf(_client_mock())
        self.m.vorstandsmitglied = False
        self.m.save()
        c = _client_mock()
        info = self._lauf(c)
        self.assertEqual(c.benutzer_aendern.call_args.args, (101, {"groups": [9], "is_active": False}))
        self.assertFalse(PaperlessBenutzer.objects.exists())
        self.assertIn("1 aus dem Vorstand entfernt", info)

    def test_uebernommene_konten_werden_nie_deaktiviert(self):
        self._lauf(_client_mock(vorhanden={"id": 5, "groups": []}))
        self.m.vorstandsmitglied = False
        self.m.save()
        c = _client_mock()
        self._lauf(c)
        self.assertEqual(c.benutzer_aendern.call_args.args[1], {"groups": [9]})   # kein is_active

    def test_fehler_bei_einem_mitglied_stoppt_nicht_alle(self):
        Mitglied.objects.create(verein=self.v, vorname="Zweite", nachname="Person", vorstandsmitglied=True)
        c = _client_mock()
        c.benutzer_anlegen.side_effect = [PaperlessFehler("kaputt"), 102]
        info = self._lauf(c)
        self.assertIn("1 Benutzer angelegt", info)
        self.assertIn("1 Fehler", info)
        self.verbindung.refresh_from_db()
        self.assertIn("kaputt", self.verbindung.letzter_abgleich_info)

    def test_anonymisierung_deaktiviert_angelegtes_konto_und_loescht_verknuepfung(self):
        self._lauf(_client_mock())
        c = _client_mock()
        with patch("apps.paperless.services.PaperlessClient", return_value=c):
            mitglied_anonymisieren(self.verbindung, self.m)
        daten = c.benutzer_aendern.call_args.args[1]
        self.assertEqual((daten["first_name"], daten["email"], daten["is_active"]), ("Anonymisiert", "", False))
        self.assertFalse(PaperlessBenutzer.objects.exists())


class ClientTests(Basis):
    @patch("apps.paperless.client.requests.Session.request")
    def test_gruppe_wird_angelegt_wenn_sie_fehlt(self, req):
        def antwort(code, daten):
            r = Mock()
            r.status_code, r.text, r.json = code, "", Mock(return_value=daten)
            return r
        req.side_effect = [antwort(200, {"results": []}), antwort(201, {"id": 4})]
        gid = PaperlessClient(self.verbindung).gruppe_sicherstellen("Vorstand", ["view_document"])
        self.assertEqual(gid, 4)
        self.assertEqual(req.call_args.kwargs["json"], {"name": "Vorstand", "permissions": ["view_document"]})

    @patch("apps.paperless.client.requests.Session.request")
    def test_fehlende_adminrechte_werden_verstaendlich_gemeldet(self, req):
        r = Mock()
        r.status_code, r.text = 403, ""
        req.return_value = r
        with self.assertRaisesRegex(PaperlessFehler, "Administrator"):
            PaperlessClient(self.verbindung).benutzer_suchen("x")


class ViewTests(Basis):
    def setUp(self):
        super().setUp()
        self.client.force_login(get_user_model().objects.create_superuser("admin", password="pw-Test-12345"))

    @patch("apps.paperless.tasks.vorstand_abgleich_task.delay")
    def test_knopf_startet_abgleich(self, delay):
        self.client.post(reverse("paperless_vorstand_abgleich"))
        delay.assert_called_once_with(self.verbindung.pk)

    def test_startpasswoerter_sichtbar_und_loeschbar(self):
        PaperlessBenutzer.objects.create(verein=self.v, mitglied=self.m, paperless_id=1, benutzername="erika.mueller",
                                         initialpasswort="Geheim123")
        self.assertContains(self.client.get(reverse("paperless_einstellungen")), "Geheim123")
        self.client.post(reverse("paperless_vorstand_passwoerter_loeschen"))
        self.assertNotContains(self.client.get(reverse("paperless_einstellungen")), "Geheim123")
