from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Rolle, Verein, Zugang


class RollenFortgeschrittenKennzeichnungTests(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.admin = get_user_model().objects.create_superuser("admin", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=self.admin,
                              rolle=Rolle.objects.get(verein=self.v, name="Superadministrator"))
        self.client.login(username="admin", password="pw-Test-12345")

    def test_navigation_kennzeichnet_rollen_als_fortgeschritten(self):
        r = self.client.get(reverse("dashboard"))
        self.assertContains(r, "Rollen (fortgeschritten)")

    def test_rollenliste_zeigt_hinweis_auf_tags(self):
        r = self.client.get(reverse("rolle_list"))
        self.assertContains(r, "Tags vergeben")

    def test_andere_listen_zeigen_keinen_hinweis(self):
        r = self.client.get(reverse("zugang_list"))
        self.assertNotContains(r, "Tags vergeben")
