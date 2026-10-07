from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.core.models import Rolle, Verein, Zugang
from apps.events.models import Veranstaltung
from apps.members.models import Mitglied, MitgliedTag

from .client import OpenSlidesFehler
from .models import OpenSlidesVerbindung, SuperadminKonto
from .services import mitglieder_abgleichen, versammlungsrechte_zuweisen


def _client(gruppen=None):
    c = Mock()
    daten = {}
    for gid, name in (gruppen or {1: "Default", 2: "Admin", 3: "Delegates", 4: "Staff"}).items():
        daten[f"group/{gid}/name"] = name
    c.abfragen.return_value = daten
    c.erstelle.return_value = 999
    return c


class Basis(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.verbindung = OpenSlidesVerbindung.objects.create(
            verein=self.v, url="https://os.example.org", benutzername="admin", passwort="x", aktiv=True)
        self.ver = Veranstaltung.objects.create(verein=self.v, titel="JHV", beginn=timezone.now() + timedelta(days=3),
                                                openslides_meeting_id=12)

    def superadmin_user(self, username="technik", vorname="Tina", nachname="Technik"):
        u = get_user_model().objects.create_user(username, password="pw-Test-12345",
                                                  first_name=vorname, last_name=nachname, email=f"{username}@example.org")
        Zugang.objects.create(verein=self.v, user=u, rolle=Rolle.objects.get(verein=self.v, name="Superadministrator"))
        return u


class KontoAbgleichTests(Basis):
    @patch("apps.openslides.services.OSClient")
    def test_superadmin_ohne_mitgliedsakte_bekommt_konto(self, OSClientMock):
        c = _client()
        OSClientMock.return_value = c
        self.superadmin_user()
        info = mitglieder_abgleichen(self.verbindung)
        konto = SuperadminKonto.objects.get()
        self.assertEqual(konto.openslides_user_id, 999)
        self.assertEqual(konto.openslides_username, "tina.technik")
        self.assertIn("1 Konten angelegt", info)

    @patch("apps.openslides.services.OSClient")
    def test_superadmin_mit_mitgliedsakte_laeuft_ueber_mitglied(self, OSClientMock):
        c = _client()
        OSClientMock.return_value = c
        u = self.superadmin_user()
        m = Mitglied.objects.create(verein=self.v, vorname="Tina", nachname="Technik", benutzer=u)
        mitglieder_abgleichen(self.verbindung)
        m.refresh_from_db()
        self.assertIsNotNone(m.openslides_user_id)
        self.assertFalse(SuperadminKonto.objects.exists())

    @patch("apps.openslides.services.OSClient")
    def test_superadmin_rolle_entzogen_deaktiviert_konto(self, OSClientMock):
        c = _client()
        OSClientMock.return_value = c
        u = self.superadmin_user()
        mitglieder_abgleichen(self.verbindung)
        Zugang.objects.filter(user=u).update(aktiv=False)
        c2 = _client()
        OSClientMock.return_value = c2
        mitglieder_abgleichen(self.verbindung)
        self.assertFalse(SuperadminKonto.objects.exists())
        c2.action.assert_any_call("user.update", [{"id": 999, "is_active": False}])


class KontoAufraeumenSignalTests(Basis):
    """Das OpenSlides-Konto eines Superadmin-Zugangs ohne Mitgliedsakte muss auch dann deaktiviert werden, wenn die
    Verknuepfung per Kaskade verschwindet (Benutzerzugang bzw. der zugrunde liegende Django-User geloescht wird),
    nicht nur beim regulaeren Abgleich."""

    @patch("apps.openslides.client.OSClient")
    def test_zugang_bzw_user_geloescht_deaktiviert_konto(self, OSClientMock):
        c = Mock()
        OSClientMock.return_value = c
        u = self.superadmin_user()
        SuperadminKonto.objects.create(verein=self.v, zugang=Zugang.objects.get(user=u), openslides_user_id=777,
                                       openslides_username="tina.technik")
        u.delete()
        c.action.assert_called_once_with("user.update", [{"id": 777, "is_active": False}])
        self.assertFalse(SuperadminKonto.objects.exists())

    @patch("apps.openslides.client.OSClient")
    def test_ohne_verbindung_bricht_das_loeschen_nicht_ab(self, OSClientMock):
        self.verbindung.delete()
        u = self.superadmin_user()
        z = Zugang.objects.get(user=u)
        SuperadminKonto.objects.create(verein=self.v, zugang=z, openslides_user_id=777, openslides_username="t")
        z.delete()   # darf keine Exception werfen
        OSClientMock.assert_not_called()
        self.assertFalse(SuperadminKonto.objects.exists())


class RechteZuweisenTests(Basis):
    def test_superadmin_mit_mitgliedsakte_bekommt_admin_gruppe(self):
        u = self.superadmin_user()
        m = Mitglied.objects.create(verein=self.v, vorname="Tina", nachname="Technik", benutzer=u,
                                    openslides_user_id=501)
        c = _client()
        text = versammlungsrechte_zuweisen(self.verbindung, self.ver, client=c)
        name, eintraege = c.action.call_args.args
        zuordnung = {e["id"]: e["group_ids"] for e in eintraege}
        self.assertEqual(zuordnung[501], [2])   # Admin
        self.assertIn("1 Mitglied", text)

    def test_superadmin_ohne_mitgliedsakte_bekommt_admin_gruppe(self):
        u = self.superadmin_user()
        SuperadminKonto.objects.create(verein=self.v, zugang=Zugang.objects.get(user=u), openslides_user_id=777,
                                       openslides_username="tina.technik")
        c = _client()
        versammlungsrechte_zuweisen(self.verbindung, self.ver, client=c)
        name, eintraege = c.action.call_args.args
        zuordnung = {e["id"]: e["group_ids"] for e in eintraege}
        self.assertEqual(zuordnung[777], [2])

    def test_superadmin_ohne_konto_wird_gemeldet(self):
        self.superadmin_user()
        c = _client()
        text = versammlungsrechte_zuweisen(self.verbindung, self.ver, client=c)
        self.assertIn("Ohne OpenSlides-Konto", text)

    def test_tags_funktionieren_weiterhin_normal(self):
        m = Mitglied.objects.create(verein=self.v, vorname="Vera", nachname="Vorstand", openslides_user_id=100)
        m.tags.add(MitgliedTag.objects.get(verein=self.v, name="1. Vorsitzender"))
        c = _client()
        versammlungsrechte_zuweisen(self.verbindung, self.ver, client=c)
        name, eintraege = c.action.call_args.args
        self.assertEqual({e["id"]: e["group_ids"] for e in eintraege}[100], [2])
