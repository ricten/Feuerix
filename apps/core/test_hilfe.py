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
        for slug, (_, titel) in DOKUMENTE.items():
            self.assertContains(r, escape(titel))
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
