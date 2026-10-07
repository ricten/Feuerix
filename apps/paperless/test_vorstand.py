from datetime import date
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Rolle, Verein, Zugang
from apps.members.models import Funktion, Mitglied, MitgliedFunktion, MitgliedTag

from .client import PaperlessClient, PaperlessFehler
from .models import PaperlessBenutzer, PaperlessVerbindung
from .services import mitglied_anonymisieren, vorstand_abgleichen


class Basis(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.verbindung = PaperlessVerbindung.objects.create(
            verein=self.v, url="https://paperless.example.org", api_token="geheim", aktiv=True)
        self.beisitzer_tag = MitgliedTag.objects.get(verein=self.v, name="Beisitzer")
        self.m = Mitglied.objects.create(verein=self.v, vorname="Erika", nachname="Müller", email="e@example.org")
        self.m.tags.add(self.beisitzer_tag)


class MarkerUndFunktionTests(Basis):
    def test_haken_setzt_und_beendet_die_funktion(self):
        f = MitgliedFunktion.objects.get(mitglied=self.m, funktion__name="Beisitzer")
        self.assertIsNone(f.bis)
        self.assertEqual(f.von, date.today())
        self.assertTrue(self.m.vorstandsmitglied)
        self.m.save()   # kein Duplikat
        self.assertEqual(MitgliedFunktion.objects.filter(mitglied=self.m).count(), 1)
        self.m.tags.remove(self.beisitzer_tag)
        self.m.refresh_from_db()
        self.assertFalse(self.m.vorstandsmitglied)
        f.refresh_from_db()
        self.assertEqual(f.bis, date.today())   # beendet, Verlauf bleibt
        self.m.tags.add(self.beisitzer_tag)
        self.assertEqual(MitgliedFunktion.objects.filter(mitglied=self.m).count(), 2)

    def test_ohne_tag_keine_funktion(self):
        m = Mitglied.objects.create(verein=self.v, vorname="A", nachname="B")
        self.assertFalse(MitgliedFunktion.objects.filter(mitglied=m).exists())
        self.assertFalse(m.vorstandsmitglied)

    def test_marker_felder_standardmaessig_aus_und_unabhaengig(self):
        m = Mitglied.objects.create(verein=self.v, vorname="A", nachname="B", einsatzabteilung_aktiv=True)
        self.assertTrue(m.einsatzabteilung_aktiv)
        self.assertFalse(m.alters_ehrenabteilung)
        self.assertFalse(m.vorstandsmitglied)

    def test_dso_tag_zaehlt_ebenfalls_als_vorstandsmitglied(self):
        kw_tag = MitgliedTag.objects.get(verein=self.v, name="Kassenwart")
        m = Mitglied.objects.create(verein=self.v, vorname="Kai", nachname="Kasse")
        m.tags.add(kw_tag)
        self.assertTrue(m.vorstandsmitglied)

    def test_funktion_wird_je_verein_angelegt(self):
        anderer = Verein.objects.create(name="Anderer", kuerzel="anderer")
        tag = MitgliedTag.objects.get(verein=anderer, name="Beisitzer")
        m = Mitglied.objects.create(verein=anderer, vorname="X", nachname="Y")
        m.tags.add(tag)
        self.assertEqual(Funktion.objects.filter(name="Beisitzer").count(), 2)

    def test_import_ignoriert_die_abgeleitete_spalte_vorstandsmitglied(self):
        from apps.members import importer
        csv_inhalt = ("Vorname;Nachname;Vorstandsmitglied;Alters- und Ehrenabteilung;"
                      "Aktives Mitglied der Einsatzabteilung\nAnna;Alt;ja;ja;\nBen;Aktiv;;;x\n").encode("utf-8")
        bericht = importer.importieren(self.v, "m.csv", csv_inhalt, testlauf=False, neu_anlegen=True)
        a = Mitglied.objects.get(vorname="Anna")
        b = Mitglied.objects.get(vorname="Ben")
        # vorstandsmitglied wird aus Tags abgeleitet - die CSV-Spalte wird ignoriert (nie manuell gesetzt)
        self.assertEqual((a.vorstandsmitglied, a.alters_ehrenabteilung, a.einsatzabteilung_aktiv), (False, True, False))
        self.assertEqual((b.vorstandsmitglied, b.alters_ehrenabteilung, b.einsatzabteilung_aktiv), (False, False, True))
        self.assertTrue(any("automatisch aus Tags abgeleitet" in w for w in bericht["warnungen"]))

    def test_liste_zeigt_marker_und_filter(self):
        self.client.force_login(get_user_model().objects.create_superuser("admin", password="pw-Test-12345"))
        Mitglied.objects.create(verein=self.v, vorname="Nur", nachname="Normal")
        r = self.client.get(reverse("mitglied_list") + "?vorstandsmitglied=True")
        self.assertContains(r, "Müller")
        self.assertNotContains(r, "Normal")


def _client_mock(**kw):
    c = Mock()
    c.gruppe_sicherstellen.return_value = 7
    c.gruppe_finden.return_value = 7   # bekannte, aber nicht benoetigte Gruppen werden nur nachgeschlagen
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
        ausgetreten = Mitglied.objects.create(verein=self.v, vorname="Aus", nachname="Getreten",
                                              status="ausgetreten")
        ausgetreten.tags.add(self.beisitzer_tag)
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
        self.m.tags.remove(self.beisitzer_tag)
        c = _client_mock()
        info = self._lauf(c)
        self.assertEqual(c.benutzer_aendern.call_args.args, (101, {"groups": [9], "is_active": False}))
        self.assertFalse(PaperlessBenutzer.objects.exists())
        self.assertIn("1 ohne Tag entfernt", info)

    def test_uebernommene_konten_werden_nie_deaktiviert(self):
        self._lauf(_client_mock(vorhanden={"id": 5, "groups": []}))
        self.m.tags.remove(self.beisitzer_tag)
        c = _client_mock()
        self._lauf(c)
        self.assertEqual(c.benutzer_aendern.call_args.args[1], {"groups": [9]})   # kein is_active

    def test_fehler_bei_einem_mitglied_stoppt_nicht_alle(self):
        zweite = Mitglied.objects.create(verein=self.v, vorname="Zweite", nachname="Person")
        zweite.tags.add(self.beisitzer_tag)
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


class SuperadminAbgleichTests(Basis):
    def _superadmin_user(self, username="technik"):
        u = get_user_model().objects.create_user(username, password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=u, rolle=Rolle.objects.get(verein=self.v, name="Superadministrator"))
        return u

    def _lauf(self, c):
        with patch("apps.paperless.services.PaperlessClient", return_value=c):
            return vorstand_abgleichen(self.verbindung)

    def test_superadmin_mit_mitgliedsakte_bekommt_administrator_gruppe(self):
        u = self._superadmin_user()
        self.m.benutzer = u
        self.m.save(update_fields=["benutzer"])
        c = _client_mock()
        self._lauf(c)
        daten = c.benutzer_anlegen.call_args.args[0]
        self.assertEqual(daten["groups"], [7])   # Beisitzer (Vorstand) + Administrator -> dieselbe gemockte ID
        self.assertTrue(PaperlessBenutzer.objects.filter(mitglied=self.m).exists())
        namen = {call.args[0] for call in c.gruppe_sicherstellen.call_args_list}
        self.assertIn("Administrator", namen)

    def test_superadmin_ohne_mitgliedsakte_bekommt_eigenes_konto(self):
        u = self._superadmin_user("technik")
        u.first_name, u.last_name, u.email = "Tina", "Technik", "tina@example.org"
        u.save()
        c = _client_mock()
        info = self._lauf(c)
        konto = PaperlessBenutzer.objects.get(zugang__user=u)
        self.assertEqual(konto.benutzername, "tina.technik")
        self.assertIn("2 Benutzer angelegt", info)   # Erika (Beisitzer) + Tina (Superadmin)

    def test_superadmin_rolle_entzogen_entfernt_konto_ohne_mitgliedsakte(self):
        u = self._superadmin_user()
        self._lauf(_client_mock())
        Zugang.objects.filter(user=u).update(aktiv=False)
        c = _client_mock()
        info = self._lauf(c)
        self.assertFalse(PaperlessBenutzer.objects.filter(zugang__user=u).exists())
        self.assertIn("1 ohne Tag entfernt", info)


class KontoAufraeumenSignalTests(Basis):
    """Das verknuepfte Paperless-Konto muss auch dann aufgeraeumt werden, wenn die Verknuepfung nicht ueber den
    regulaeren Abgleich, sondern per Kaskade verschwindet (Mitglied oder - haeufigster Fall - ein kompletter
    Benutzerzugang samt Django-User geloescht wird, z. B. ein Superadmin-Zugang)."""

    def test_mitglied_geloescht_deaktiviert_angelegtes_konto(self):
        PaperlessBenutzer.objects.create(verein=self.v, mitglied=self.m, paperless_id=55, benutzername="erika.mueller",
                                         angelegt=True, initialpasswort="geheim")
        c = Mock()
        with patch("apps.paperless.client.PaperlessClient", return_value=c):
            self.m.delete()
        c.benutzer_aendern.assert_called_once_with(55, {"is_active": False})
        self.assertFalse(PaperlessBenutzer.objects.exists())

    def test_uebernommenes_konto_wird_nur_aus_gruppen_entfernt_nicht_deaktiviert(self):
        PaperlessBenutzer.objects.create(verein=self.v, mitglied=self.m, paperless_id=56, benutzername="erika.mueller",
                                         angelegt=False)
        c = Mock()
        c.benutzer_lesen.return_value = {"groups": [1, 2]}
        c.gruppen_ohne.return_value = [1]
        with patch("apps.paperless.client.PaperlessClient", return_value=c):
            self.m.delete()
        c.benutzer_aendern.assert_called_once_with(56, {"groups": [1]})

    def test_zugang_bzw_user_geloescht_deaktiviert_superadmin_konto(self):
        u = get_user_model().objects.create_user("technik", password="pw-Test-12345")
        z = Zugang.objects.create(verein=self.v, user=u,
                                  rolle=Rolle.objects.get(verein=self.v, name="Superadministrator"))
        PaperlessBenutzer.objects.create(verein=self.v, zugang=z, paperless_id=77, benutzername="technik",
                                         angelegt=True, initialpasswort="geheim")
        c = Mock()
        with patch("apps.paperless.client.PaperlessClient", return_value=c):
            u.delete()   # Zugang kaskadiert mit, PaperlessBenutzer ebenso - das Signal muss trotzdem feuern
        c.benutzer_aendern.assert_called_once_with(77, {"is_active": False})
        self.assertFalse(PaperlessBenutzer.objects.exists())

    def test_ohne_verbindung_bricht_das_loeschen_nicht_ab(self):
        self.verbindung.delete()
        PaperlessBenutzer.objects.create(verein=self.v, mitglied=self.m, paperless_id=55, benutzername="erika.mueller",
                                         angelegt=True)
        self.m.delete()   # darf keine Exception werfen
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
