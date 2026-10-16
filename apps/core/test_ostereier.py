"""Versionsname in der Fusszeile und die kleinen Ueberraschungen (Easter Eggs)."""
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Rolle, Verein, Zugang
from .views import ist_floriani


class OsterEiTests(TestCase):
    def setUp(self):
        self.verein = Verein.objects.create(name="Testverein", kuerzel="test")
        admin = get_user_model().objects.create_superuser("admin", password="pw-Test-12345")
        Zugang.objects.create(verein=self.verein, user=admin, rolle=Rolle.objects.get(verein=self.verein, name="Superadministrator"))
        self.client.force_login(admin)

    def test_fusszeile_zeigt_versionsnamen(self):
        from django.conf import settings
        name = (settings.BASE_DIR / "VERSION_NAME").read_text(encoding="utf-8").strip()
        self.assertTrue(name)
        r = self.client.get(reverse("dashboard"))
        self.assertContains(r, 'id="versionsnummer"')
        self.assertContains(r, "\u201e%s\u201c" % name)

    def test_floriani_nur_am_4_mai(self):
        self.assertTrue(ist_floriani(date(2027, 5, 4)))
        self.assertFalse(ist_floriani(date(2027, 5, 5)))
        self.assertFalse(ist_floriani(date(2027, 4, 5)))

    def test_floriani_gruss_auf_der_startseite(self):
        with patch("apps.core.views.ist_floriani", return_value=False):
            self.assertNotContains(self.client.get(reverse("dashboard")), "Heute ist Floriani-Tag")
        with patch("apps.core.views.ist_floriani", return_value=True):
            self.assertContains(self.client.get(reverse("dashboard")), "Heute ist Floriani-Tag")

    def test_konami_und_wasser_skript_ist_eingebunden(self):
        r = self.client.get(reverse("dashboard"))
        self.assertContains(r, "ArrowUp")
        self.assertContains(r, "ei-blaulicht")
