from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.html import escape

from .hilfe import DOKUMENTE


class HilfeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("u", password="pw-Test-12345")
        self.client.login(username="u", password="pw-Test-12345")

    def test_erfordert_anmeldung(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("hilfe")).status_code, 302)

    def test_liste_zeigt_alle_dokumente(self):
        r = self.client.get(reverse("hilfe"))
        for slug, sprachen in DOKUMENTE.items():
            self.assertContains(r, escape(sprachen["de"][1]))
            self.assertContains(r, reverse("hilfe_dokument", args=[slug]))

    def test_handbuch_wird_als_html_gerendert(self):
        r = self.client.get(reverse("hilfe_dokument", args=["handbuch"]))
        self.assertContains(r, "<h1")
        self.assertContains(r, "<h2")

    def test_interner_verweis_zeigt_auf_hilfe_seite_nicht_auf_md_datei(self):
        r = self.client.get(reverse("hilfe_dokument", args=["handbuch"]))
        self.assertContains(r, reverse("hilfe_dokument", args=["selbstdatenpflege"]))
        self.assertNotContains(r, "SELBSTDATENPFLEGE.md")

    def test_unbekanntes_dokument_404(self):
        self.assertEqual(self.client.get(reverse("hilfe_dokument", args=["nichtvorhanden"])).status_code, 404)

    def test_nav_zeigt_hilfe_unabhaengig_von_rechten(self):
        from apps.core.models import Rolle, Verein, Zugang
        v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        Zugang.objects.create(verein=v, user=self.user, rolle=Rolle.objects.create(verein=v, name="Leer", rechte=[]))
        r = self.client.get(reverse("dashboard"))
        self.assertContains(r, reverse("hilfe"))


class HilfeZweisprachigTests(TestCase):
    """Jedes Dokument liegt deutsch und englisch vor; die Hilfe-Seite zeigt die zur Oberflaechen-Sprache
    passende Fassung, umschaltbar über den normalen Sprachauswahl-Mechanismus (set_language)."""

    def setUp(self):
        self.user = get_user_model().objects.create_user("u", password="pw-Test-12345")
        self.client.login(username="u", password="pw-Test-12345")

    def _sprache_setzen(self, code):
        self.client.post(reverse("set_language"), {"language": code})

    def test_englische_oberflaeche_zeigt_englische_titel_und_dateien_existieren(self):
        self._sprache_setzen("en")
        r = self.client.get(reverse("hilfe"))
        for slug, sprachen in DOKUMENTE.items():
            self.assertContains(r, escape(sprachen["en"][1]))

    def test_englisches_handbuch_wird_gerendert_mit_englischem_titel(self):
        self._sprache_setzen("en")
        r = self.client.get(reverse("hilfe_dokument", args=["handbuch"]))
        self.assertContains(r, "<h1")
        self.assertContains(r, escape(DOKUMENTE["handbuch"]["en"][1]))
        self.assertContains(r, "Club software")   # englischer Fliesstext, nicht nur der Titel

    def test_deutsches_handbuch_bleibt_deutsch_ohne_sprachumschaltung(self):
        r = self.client.get(reverse("hilfe_dokument", args=["handbuch"]))
        self.assertContains(r, escape(DOKUMENTE["handbuch"]["de"][1]))
        self.assertContains(r, "Vereinssoftware")

    def test_interner_verweis_bleibt_in_der_gewaehlten_sprache(self):
        self._sprache_setzen("en")
        r = self.client.get(reverse("hilfe_dokument", args=["handbuch"]))
        # Link fuehrt weiterhin auf die Hilfe-Seite (sprachunabhaengiger Slug), nicht auf die rohe .md-Datei
        self.assertContains(r, reverse("hilfe_dokument", args=["selbstdatenpflege"]))
        self.assertNotContains(r, "SELBSTDATENPFLEGE.en.md")
        self.assertNotContains(r, "SELBSTDATENPFLEGE.md")

    def test_alle_dokumente_haben_eine_vorhandene_deutsche_und_englische_datei(self):
        from django.conf import settings
        for slug, sprachen in DOKUMENTE.items():
            for sprache, (dateiname, _titel) in sprachen.items():
                pfad = settings.BASE_DIR / "docs" / dateiname
                self.assertTrue(pfad.exists(), f"{dateiname} ({sprache}) fehlt für Dokument '{slug}'")
