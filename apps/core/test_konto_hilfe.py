"""Links auf der Anmeldeseite: Selbstdatenpflege, Passwort vergessen, Anfrage an die Administration (2FA zurücksetzen)."""
import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from . import konto_hilfe, zweifaktor
from .models import Rolle, Verein, Zugang, ZweiFaktorAnfrage

User = get_user_model()
PW = "pw-Test-12345"


class Basis(TestCase):
    def setUp(self):
        self.verein = Verein.objects.create(name="Testverein", kuerzel="test")
        self.admin = User.objects.create_superuser("admin", email="admin@example.org", password=PW)
        Zugang.objects.create(verein=self.verein, user=self.admin, rolle=Rolle.objects.get(verein=self.verein, name="Superadministrator"))
        self.max = User.objects.create_user("max", email="max@example.org", password=PW)
        self.zugang = Zugang.objects.create(verein=self.verein, user=self.max, rolle=Rolle.objects.get(verein=self.verein, name="Superadministrator"))

    def zf_an(self, user):
        zf = zweifaktor.holen(user)
        zf.aktiv = True
        zf.save()


class AnmeldeseiteTests(Basis):
    def test_drei_links_auf_der_anmeldeseite(self):
        r = self.client.get(reverse("login"))
        for name in ("mein_konto", "passwort_vergessen", "zf_anfrage"):
            self.assertContains(r, 'href="%s"' % reverse(name))

    def test_seiten_ohne_anmeldung_erreichbar(self):
        for name in ("passwort_vergessen", "passwort_vergessen_gesendet", "zf_anfrage", "zf_anfrage_fertig", "passwort_neu_fertig"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)


class PasswortVergessenTests(Basis):
    def link(self):
        return re.search(r"https?://\S+/passwort-neu/\S+/", mail.outbox[0].body).group(0)

    def test_link_per_mail_und_neues_passwort(self):
        r = self.client.post(reverse("passwort_vergessen"), {"email": "max@example.org"})
        self.assertRedirects(r, reverse("passwort_vergessen_gesendet"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["max@example.org"])
        pfad = "/" + self.link().split("/", 3)[3]
        r = self.client.get(pfad, follow=True)          # Django leitet auf die Adresse mit "set-password" um
        self.assertContains(r, "Neues Passwort festlegen")
        with patch("apps.core.konto_hilfe.passwortabgleich.abgleichen") as abgleich:
            abgleich.return_value.ok, abgleich.return_value.fehler = [], []
            r = self.client.post(r.request["PATH_INFO"], {"new_password1": "Neu-Pw-98765-xyz", "new_password2": "Neu-Pw-98765-xyz"})
        self.assertRedirects(r, reverse("passwort_neu_fertig"))
        abgleich.assert_called_once()
        self.assertEqual(abgleich.call_args[0][1], "Neu-Pw-98765-xyz")
        self.assertTrue(self.client.login(username="max", password="Neu-Pw-98765-xyz"))

    def test_unbekannte_adresse_gleiche_antwort_ohne_mail(self):
        r = self.client.post(reverse("passwort_vergessen"), {"email": "gibtsnicht@example.org"})
        self.assertRedirects(r, reverse("passwort_vergessen_gesendet"))
        self.assertEqual(len(mail.outbox), 0)

    def test_gesperrtes_konto_bekommt_keinen_link(self):
        self.max.is_active = False
        self.max.save()
        self.client.post(reverse("passwort_vergessen"), {"email": "max@example.org"})
        self.assertEqual(len(mail.outbox), 0)

    def test_link_nur_einmal_verwendbar(self):
        self.client.post(reverse("passwort_vergessen"), {"email": "max@example.org"})
        pfad = "/" + self.link().split("/", 3)[3]
        r = self.client.get(pfad, follow=True)
        ziel = r.request["PATH_INFO"]
        self.client.post(ziel, {"new_password1": "Neu-Pw-98765-xyz", "new_password2": "Neu-Pw-98765-xyz"})
        r = self.client.get(pfad, follow=True)
        self.assertContains(r, "ungültig oder abgelaufen")

    def test_schwaches_passwort_wird_abgelehnt(self):
        self.client.post(reverse("passwort_vergessen"), {"email": "max@example.org"})
        r = self.client.get("/" + self.link().split("/", 3)[3], follow=True)
        r = self.client.post(r.request["PATH_INFO"], {"new_password1": "12345678", "new_password2": "12345678"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(User.objects.get(username="max").check_password(PW))


class ZfAnfrageTests(Basis):
    def test_anfrage_wird_angelegt_und_admins_informiert(self):
        self.zf_an(self.max)
        r = self.client.post(reverse("zf_anfrage"), {"benutzername": "max", "nachricht": "Handy verloren"})
        self.assertRedirects(r, reverse("zf_anfrage_fertig"))
        a = ZweiFaktorAnfrage.objects.get()
        self.assertEqual((a.user, a.nachricht, a.erledigt_am), (self.max, "Handy verloren", None))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("admin@example.org", mail.outbox[0].to)
        self.assertIn("max", mail.outbox[0].subject)
        self.assertIn(reverse("zugang_detail", args=[self.zugang.pk]), mail.outbox[0].body)

    def test_keine_zweite_offene_anfrage(self):
        self.zf_an(self.max)
        for _ in range(3):
            self.client.post(reverse("zf_anfrage"), {"benutzername": "max"})
        self.assertEqual(ZweiFaktorAnfrage.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_unbekannt_oder_ohne_2fa_gleiche_antwort_ohne_eintrag(self):
        for name in ("gibtsnicht", "max"):           # max hat keine aktive 2FA
            r = self.client.post(reverse("zf_anfrage"), {"benutzername": name})
            self.assertRedirects(r, reverse("zf_anfrage_fertig"))
        self.assertEqual(ZweiFaktorAnfrage.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_ohne_empfaengeradresse_bleibt_anfrage_trotzdem_bestehen(self):
        User.objects.filter(is_superuser=True).update(email="")
        self.zf_an(self.max)
        self.assertIsNotNone(konto_hilfe.anfragen("max"))
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(ZWEIFAKTOR_PFLICHT=True)
    def test_angemeldet_ohne_code_kommt_an_die_anfrage_heran(self):
        self.zf_an(self.max)
        self.client.force_login(self.max)
        self.assertEqual(self.client.get(reverse("zf_anfrage")).status_code, 200)

    def test_superadmin_sieht_hinweis_und_zuruecksetzen_erledigt_die_anfrage(self):
        self.zf_an(self.max)
        konto_hilfe.anfragen("max", "Handy weg")
        self.client.force_login(self.admin)
        r = self.client.get(reverse("dashboard"))
        self.assertContains(r, "offene Anfrage, eine Zwei-Faktor-Anmeldung zurückzusetzen")
        r = self.client.get(reverse("zugang_detail", args=[self.zugang.pk]))
        self.assertContains(r, "2FA-Rücksetzung angefragt")
        self.assertContains(r, "Handy weg")
        self.client.post(reverse("benutzer_zf_reset", args=[self.zugang.pk]))
        self.assertIsNotNone(ZweiFaktorAnfrage.objects.get().erledigt_am)
        self.assertNotContains(self.client.get(reverse("dashboard")), "offene Anfrage")
        konto_hilfe.anfragen("max")           # 2FA wurde zurückgesetzt -> keine neue Anfrage mehr möglich
        self.assertEqual(ZweiFaktorAnfrage.objects.count(), 1)
