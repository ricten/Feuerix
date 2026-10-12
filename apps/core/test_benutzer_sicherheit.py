from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from . import zweifaktor
from .models import AuditLog, Rolle, Verein, Zugang
from .test_zweifaktor import aktueller_code  # noqa: F401

User = get_user_model()
PW = "pw-Test-12345"


class BenutzerSicherheitTests(TestCase):
    def setUp(self):
        self.verein = Verein.objects.create(name="Testverein", kuerzel="test")
        self.admin = User.objects.create_superuser("admin", password=PW)
        self.rolle = Rolle.objects.filter(verein=self.verein).first()
        self.user = User.objects.create_user("max", password=PW)
        self.zugang = Zugang.objects.create(verein=self.verein, user=self.user, rolle=self.rolle)
        self.client.force_login(self.admin)
        s = self.client.session
        s["verein_id"] = self.verein.pk
        s.save()

    def sperren(self):
        for _ in range(5):
            self.client.post(reverse("login"), {"username": "max", "password": "falsch"})
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_detail_zeigt_knoepfe_nur_fuer_superadmin(self):
        r = self.client.get(reverse("zugang_detail", args=[self.zugang.pk]))
        self.assertContains(r, "Passwort neu setzen")
        self.assertContains(r, "nicht eingerichtet")
        self.assertNotContains(r, "2FA zurücksetzen")
        zweifaktor.holen(self.user)
        zf = zweifaktor.holen(self.user)
        zf.geheimnis = zweifaktor.neues_geheimnis()
        zf.save()
        zweifaktor.aktivieren(zf, aktueller_code(zf.geheimnis))
        self.assertContains(self.client.get(reverse("zugang_detail", args=[self.zugang.pk])), "2FA zurücksetzen")

    def test_entsperren(self):
        self.client.logout()
        self.sperren()
        self.client.force_login(self.admin)
        s = self.client.session
        s["verein_id"] = self.verein.pk
        s.save()
        self.assertContains(self.client.get(reverse("zugang_detail", args=[self.zugang.pk])), "Konto entsperren")
        self.client.post(reverse("benutzer_entsperren", args=[self.zugang.pk]))
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertFalse(self.user.zweifaktor.gesperrt)
        self.assertTrue(self.client.login(username="max", password=PW))
        self.assertTrue(AuditLog.objects.filter(user_name="admin", objekt_repr__contains="max").exists())

    def test_zf_zuruecksetzen(self):
        zf = zweifaktor.holen(self.user)
        zf.geheimnis = zweifaktor.neues_geheimnis()
        zf.save()
        zweifaktor.aktivieren(zf, aktueller_code(zf.geheimnis))
        self.client.post(reverse("benutzer_zf_reset", args=[self.zugang.pk]))
        zf.refresh_from_db()
        self.assertFalse(zf.aktiv)
        self.assertEqual(zf.wiederherstellungscodes, [])

    def test_passwort_neu_setzen_entsperrt_und_prueft(self):
        r = self.client.post(reverse("benutzer_passwort", args=[self.zugang.pk]), {"passwort": "abc", "passwort2": "abc"})
        self.assertContains(r, "zu kurz")
        r = self.client.post(reverse("benutzer_passwort", args=[self.zugang.pk]),
                             {"passwort": "Neu-Pw-98765x", "passwort2": "anders"})
        self.assertContains(r, "stimmen nicht überein")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PW))
        self.client.logout()
        self.sperren()
        self.client.force_login(self.admin)
        s = self.client.session
        s["verein_id"] = self.verein.pk
        s.save()
        self.client.post(reverse("benutzer_passwort", args=[self.zugang.pk]),
                         {"passwort": "Neu-Pw-98765x", "passwort2": "Neu-Pw-98765x"})
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertTrue(self.user.check_password("Neu-Pw-98765x"))

    def test_nur_superadmin_und_nicht_fuer_sich_selbst(self):
        normal = User.objects.create_user("norm", password=PW)
        Zugang.objects.create(verein=self.verein, user=normal, rolle=self.rolle)
        self.client.force_login(normal)
        s = self.client.session
        s["verein_id"] = self.verein.pk
        s.save()
        for name in ("benutzer_entsperren", "benutzer_zf_reset"):
            self.assertEqual(self.client.post(reverse(name, args=[self.zugang.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("benutzer_passwort", args=[self.zugang.pk])).status_code, 403)
        eigenes = Zugang.objects.create(verein=self.verein, user=self.admin, rolle=self.rolle)
        self.client.force_login(self.admin)
        s = self.client.session
        s["verein_id"] = self.verein.pk
        s.save()
        self.assertEqual(self.client.post(reverse("benutzer_zf_reset", args=[eigenes.pk])).status_code, 403)

    def test_anderer_verein_nicht_erreichbar(self):
        v2 = Verein.objects.create(name="Anderer", kuerzel="anders")
        u2 = User.objects.create_user("fremd", password=PW)
        z2 = Zugang.objects.create(verein=v2, user=u2, rolle=Rolle.objects.filter(verein=v2).first())
        self.assertEqual(self.client.post(reverse("benutzer_entsperren", args=[z2.pk])).status_code, 404)
