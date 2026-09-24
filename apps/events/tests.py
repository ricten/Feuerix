from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.core.models import Rolle, Verein, Zugang
from apps.documents.platzhalter import kontext

from .models import Veranstaltung, Wahlergebnis


class WahlergebnisModelTests(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.ver = Veranstaltung.objects.create(verein=self.v, titel="Mitgliederversammlung 2026",
                                                beginn=timezone.now())

    def test_str_mit_wahlgang(self):
        w = Wahlergebnis.objects.create(verein=self.v, veranstaltung=self.ver, amt="1. Vorsitzender",
                                        wahlgang="Wahlgang 1", ergebnis="Max Muster: 8 Ja")
        self.assertEqual(str(w), "1. Vorsitzender (Wahlgang 1)")

    def test_str_ohne_wahlgang(self):
        w = Wahlergebnis.objects.create(verein=self.v, veranstaltung=self.ver, amt="Kassenwart", ergebnis="...")
        self.assertEqual(str(w), "Kassenwart")


class WahlergebnisPlatzhalterTests(TestCase):
    """{wahlergebnisse} in Vorlagen (z. B. dem Protokoll) muss die aus OpenSlides übernommenen Ergebnisse
    zeigen - das ist der eigentliche "Rückfluss ins Protokoll"."""

    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.ver = Veranstaltung.objects.create(verein=self.v, titel="Mitgliederversammlung 2026",
                                                beginn=timezone.now())

    def test_ohne_wahlergebnisse_zeigt_hinweistext(self):
        ctx = kontext(self.v, veranstaltung=self.ver)
        self.assertIn("keine Wahlergebnisse", ctx["wahlergebnisse"])

    def test_mit_wahlergebnissen_werden_amt_und_stimmen_eingesetzt(self):
        Wahlergebnis.objects.create(verein=self.v, veranstaltung=self.ver, amt="1. Vorsitzender",
                                    wahlgang="Wahlgang 1", ergebnis="Max Muster: 8 Ja, 1 Nein, 1 Enthaltung")
        ctx = kontext(self.v, veranstaltung=self.ver)
        self.assertIn("1. Vorsitzender – Wahlgang 1", ctx["wahlergebnisse"])
        self.assertIn("Max Muster: 8 Ja, 1 Nein, 1 Enthaltung", ctx["wahlergebnisse"])


class WahlergebnisCrudTests(TestCase):
    """Wahlergebnisse werden ausschließlich über den OpenSlides-Rückfluss angelegt - keine manuelle Erfassung."""

    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.ver = Veranstaltung.objects.create(verein=self.v, titel="Mitgliederversammlung 2026",
                                                beginn=timezone.now())
        User = get_user_model()
        self.admin = User.objects.create_superuser("admin", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=self.admin,
                              rolle=Rolle.objects.get(verein=self.v, name="Superadministrator"))
        self.client.login(username="admin", password="pw-Test-12345")

    def test_liste_und_detail_erreichbar(self):
        w = Wahlergebnis.objects.create(verein=self.v, veranstaltung=self.ver, amt="Kassenwart",
                                        ergebnis="Erika Musterfrau: 10 Ja")
        self.assertEqual(self.client.get(reverse("wahlergebnis_list")).status_code, 200)
        r = self.client.get(reverse("wahlergebnis_detail", args=[w.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Erika Musterfrau: 10 Ja")

    def test_keine_add_und_edit_seite(self):
        with self.assertRaises(NoReverseMatch):
            reverse("wahlergebnis_add")
        w = Wahlergebnis.objects.create(verein=self.v, veranstaltung=self.ver, amt="Schriftführer", ergebnis="…")
        with self.assertRaises(NoReverseMatch):
            reverse("wahlergebnis_edit", args=[w.pk])
