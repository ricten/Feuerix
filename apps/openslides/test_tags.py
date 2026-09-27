from datetime import timedelta
from unittest.mock import Mock

from django.test import TestCase
from django.utils import timezone

from apps.core.models import Verein
from apps.events.models import Veranstaltung
from apps.members.models import Mitglied, MitgliedTag

from .client import OpenSlidesFehler
from .models import OpenSlidesVerbindung
from .services import _im_umfang, _versammlungsgruppen, versammlungsrechte_zuweisen


def _client(gruppen=None):
    c = Mock()
    daten = {}
    for gid, name in (gruppen or {1: "Default", 2: "Admin", 3: "Delegates", 4: "Staff"}).items():
        daten[f"group/{gid}/name"] = name
    c.abfragen.return_value = daten
    return c


class Basis(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.verbindung = OpenSlidesVerbindung.objects.create(
            verein=self.v, url="https://os.example.org", benutzername="admin", passwort="x", aktiv=True)
        self.ver = Veranstaltung.objects.create(verein=self.v, titel="JHV", beginn=timezone.now() + timedelta(days=3),
                                                openslides_meeting_id=12)

    def mitglied(self, name, tag=None, konto=True, **kw):
        m = Mitglied.objects.create(verein=self.v, vorname=name, nachname="Test",
                                    openslides_user_id=(100 + Mitglied.objects.count()) if konto else None, **kw)
        if tag:
            m.tags.add(MitgliedTag.objects.get(verein=self.v, name=tag))
        return m


class RechteZuweisenTests(Basis):
    def test_gruppen_der_versammlung_werden_gelesen(self):
        self.assertEqual(_versammlungsgruppen(_client(), 12), {"default": 1, "admin": 2, "delegates": 3, "staff": 4})

    def test_tags_verteilen_gruppen_in_der_versammlung(self):
        vors = self.mitglied("Vera", "1. Vorsitzender")
        schrift = self.mitglied("Sven", "Schriftführer")
        kasse = self.mitglied("Kai", "Kassenwart")
        self.mitglied("Ohne")
        c = _client()
        text = versammlungsrechte_zuweisen(self.verbindung, self.ver, client=c)
        name, eintraege = c.action.call_args.args
        self.assertEqual(name, "user.update")
        zuordnung = {e["id"]: e["group_ids"] for e in eintraege}
        self.assertEqual(zuordnung[vors.openslides_user_id], [2])      # Admin
        self.assertEqual(zuordnung[schrift.openslides_user_id], [4])   # Staff
        self.assertEqual(zuordnung[kasse.openslides_user_id], [3])     # Delegates
        self.assertTrue(all(e["meeting_id"] == 12 for e in eintraege))
        self.assertEqual(len(eintraege), 3)
        self.assertIn("3 Mitglied", text)

    def test_mehrere_tags_ergeben_mehrere_gruppen(self):
        m = self.mitglied("Doppel", "Schriftführer")
        m.tags.add(MitgliedTag.objects.get(verein=self.v, name="Kassenwart"))
        c = _client()
        versammlungsrechte_zuweisen(self.verbindung, self.ver, client=c)
        self.assertEqual(c.action.call_args.args[1][0]["group_ids"], [3, 4])

    def test_mitglied_ohne_konto_wird_gemeldet_nicht_zugewiesen(self):
        self.mitglied("Kein", "Kassenwart", konto=False)
        c = _client()
        text = versammlungsrechte_zuweisen(self.verbindung, self.ver, client=c)
        c.action.assert_not_called()
        self.assertIn("Ohne OpenSlides-Konto", text)

    def test_unbekannte_gruppe_wird_gemeldet(self):
        self.mitglied("Vera", "1. Vorsitzender")
        text = versammlungsrechte_zuweisen(self.verbindung, self.ver, client=_client({1: "Default"}))
        self.assertIn("nicht gefunden: Admin", text)

    def test_nur_aktive_mitglieder(self):
        self.mitglied("Alt", "Schriftführer").__class__.objects.filter(vorname="Alt").update(status="ausgetreten")
        c = _client()
        versammlungsrechte_zuweisen(self.verbindung, self.ver, client=c)
        c.action.assert_not_called()

    def test_ohne_zugeordnete_versammlung_ein_fehler(self):
        self.ver.openslides_meeting_id = None
        with self.assertRaises(OpenSlidesFehler):
            versammlungsrechte_zuweisen(self.verbindung, self.ver, client=_client())

    def test_tag_mit_openslides_gruppe_bringt_mitglied_in_den_abgleich(self):
        from apps.members.models import Funktion
        f = Funktion.objects.create(verein=self.v, name="Wahlleiter")
        self.verbindung.sync_funktion = f
        self.verbindung.save()
        self.mitglied("Tagger", "Kassenwart", konto=False)
        self.mitglied("Keiner")
        namen = set(_im_umfang(self.verbindung).values_list("vorname", flat=True))
        self.assertEqual(namen, {"Tagger"})
