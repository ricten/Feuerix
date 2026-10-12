from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from . import zweifaktor
from .models import ZweiFaktor

User = get_user_model()
PW = "pw-Test-12345"


def aktueller_code(geheimnis, versatz=0):
    import time
    return zweifaktor._code(geheimnis, int(time.time() // zweifaktor.SCHRITT) + versatz)


def zf_aktivieren(user):
    zf = zweifaktor.holen(user)
    zf.geheimnis = zweifaktor.neues_geheimnis()
    zf.save()
    codes = zweifaktor.aktivieren(zf, aktueller_code(zf.geheimnis))
    zf.refresh_from_db()
    return zf, codes


class TotpTests(TestCase):
    def test_rfc6238_testvektor(self):
        # RFC 6238, SHA1, Geheimnis "12345678901234567890", Zeit 59 s -> 94287082 (8-stellig) -> letzte 6 Stellen
        import base64
        g = base64.b32encode(b"12345678901234567890").decode()
        self.assertEqual(zweifaktor._code(g, 59 // 30), "287082")

    def test_toleranz_und_wiederverwendung(self):
        g = zweifaktor.neues_geheimnis()
        z = zweifaktor.totp_pruefen(g, aktueller_code(g, -1))
        self.assertIsNotNone(z)
        self.assertIsNone(zweifaktor.totp_pruefen(g, aktueller_code(g, -1), nach_zeitscheibe=z))
        self.assertIsNone(zweifaktor.totp_pruefen(g, aktueller_code(g, 5)))
        self.assertIsNone(zweifaktor.totp_pruefen(g, "abc"))


class KontosperreTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("max", password=PW)

    def falsch(self, n):
        for _ in range(n):
            self.client.post(reverse("login"), {"username": "max", "password": "falsch"})

    def test_sperre_nach_fuenf_fehlversuchen_ohne_2fa(self):
        self.falsch(4)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.falsch(1)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertTrue(self.user.zweifaktor.gesperrt)
        # auch das richtige Passwort hilft nun nicht mehr
        self.assertFalse(self.client.login(username="max", password=PW))

    def test_erfolgreiche_anmeldung_setzt_zaehler_zurueck(self):
        self.falsch(4)
        self.client.post(reverse("login"), {"username": "max", "password": PW})
        self.assertEqual(ZweiFaktor.objects.get(user=self.user).fehlversuche, 0)
        self.client.logout()
        self.falsch(4)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_mit_aktiver_2fa_keine_kontosperre(self):
        zf_aktivieren(self.user)
        self.falsch(8)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_unbekannter_benutzer_wirft_nichts(self):
        self.client.post(reverse("login"), {"username": "gibtsnicht", "password": "x"})

    def test_befehl_entsperrt(self):
        self.falsch(5)
        call_command("zweifaktor_zuruecksetzen", "max", stdout=StringIO())
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertEqual(self.user.zweifaktor.fehlversuche, 0)
        self.assertTrue(self.client.login(username="max", password=PW))

    def test_befehl_setzt_2fa_zurueck(self):
        zf_aktivieren(self.user)
        call_command("zweifaktor_zuruecksetzen", "max", "--2fa-zuruecksetzen", stdout=StringIO())
        self.assertFalse(ZweiFaktor.objects.get(user=self.user).aktiv)


class AnmeldungTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("max", password=PW)

    def test_einrichten_und_anmelden(self):
        self.client.login(username="max", password=PW)
        r = self.client.get(reverse("zf_einrichten"))
        self.assertContains(r, "data:image/svg+xml")
        geheimnis = ZweiFaktor.objects.get(user=self.user).geheimnis
        # falscher Code
        r = self.client.post(reverse("zf_einrichten"), {"code": "000000"})
        self.assertContains(r, "Der Code ist falsch")
        self.assertFalse(ZweiFaktor.objects.get(user=self.user).aktiv)
        r = self.client.post(reverse("zf_einrichten"), {"code": aktueller_code(geheimnis)})
        self.assertContains(r, "Wiederherstellungscodes")
        self.assertEqual(len(r.context["codes"]), zweifaktor.ANZAHL_CODES)
        self.assertTrue(ZweiFaktor.objects.get(user=self.user).aktiv)
        # neue Sitzung: zweite Stufe wird verlangt
        self.client.logout()
        self.client.login(username="max", password=PW)
        r = self.client.get(reverse("dashboard"))
        self.assertRedirects(r, reverse("zf_pruefen") + "?next=/", fetch_redirect_response=False)
        # Code wurde schon eingeloest -> naechster Zeitschritt noetig
        r = self.client.post(reverse("zf_pruefen"), {"code": aktueller_code(geheimnis, 1)})
        self.assertRedirects(r, reverse("nach_login"), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("nach_login")).status_code, 302)
        self.assertNotIn("zf_pruefen", self.client.get(reverse("nach_login")).url)

    def test_falscher_code_und_auszeit(self):
        zf, _ = zf_aktivieren(self.user)
        self.client.login(username="max", password=PW)
        for _i in range(zweifaktor.MAX_FEHLVERSUCHE):
            r = self.client.post(reverse("zf_pruefen"), {"code": "111111"})
            self.assertContains(r, "Der Code ist falsch")
        r = self.client.post(reverse("zf_pruefen"), {"code": aktueller_code(zf.geheimnis, 1)})
        self.assertContains(r, "Zu viele Fehlversuche")
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("zf_pruefen") + "?next=/",
                             fetch_redirect_response=False)

    def test_wiederherstellungscode_einmalig(self):
        zf, codes = zf_aktivieren(self.user)
        self.client.login(username="max", password=PW)
        r = self.client.post(reverse("zf_pruefen"), {"code": codes[0].upper()})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(len(ZweiFaktor.objects.get(user=self.user).wiederherstellungscodes), zweifaktor.ANZAHL_CODES - 1)
        self.client.logout()
        self.client.login(username="max", password=PW)
        r = self.client.post(reverse("zf_pruefen"), {"code": codes[0]})
        self.assertContains(r, "Der Code ist falsch")

    def test_next_wird_geprueft(self):
        zf_aktivieren(self.user)
        self.client.login(username="max", password=PW)
        r = self.client.post(reverse("zf_pruefen"), {"code": aktueller_code(ZweiFaktor.objects.get(user=self.user).geheimnis, 1),
                                                      "next": "https://boese.example/"})
        self.assertRedirects(r, reverse("nach_login"), fetch_redirect_response=False)

    def test_deaktivieren_braucht_passwort(self):
        zf_aktivieren(self.user)
        self.client.login(username="max", password=PW)
        s = self.client.session
        s["zf_ok"] = True
        s.save()
        self.client.post(reverse("zf_verwalten"), {"aktion": "aus", "passwort": "falsch"})
        self.assertTrue(ZweiFaktor.objects.get(user=self.user).aktiv)
        self.client.post(reverse("zf_verwalten"), {"aktion": "aus", "passwort": PW})
        self.assertFalse(ZweiFaktor.objects.get(user=self.user).aktiv)

    def test_neue_codes_ersetzen_alte(self):
        zf, alt = zf_aktivieren(self.user)
        self.client.login(username="max", password=PW)
        s = self.client.session
        s["zf_ok"] = True
        s.save()
        r = self.client.post(reverse("zf_verwalten"), {"aktion": "codes", "passwort": PW})
        self.assertNotEqual(set(r.context["codes"]), set(alt))
        self.assertEqual(len(ZweiFaktor.objects.get(user=self.user).wiederherstellungscodes), zweifaktor.ANZAHL_CODES)


@override_settings(ZWEIFAKTOR_PFLICHT=True)
class SuperadminPflichtTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", password=PW)
        self.user = User.objects.create_user("max", password=PW)

    def test_superadmin_wird_zur_einrichtung_gezwungen(self):
        self.client.login(username="admin", password=PW)
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("zf_einrichten"), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("zf_einrichten")).status_code, 200)
        r = self.client.post(reverse("logout"))
        self.assertEqual(r.status_code, 302)

    def test_nach_einrichtung_frei_und_nicht_abschaltbar(self):
        self.client.login(username="admin", password=PW)
        self.client.get(reverse("zf_einrichten"))
        g = ZweiFaktor.objects.get(user=self.admin).geheimnis
        self.client.post(reverse("zf_einrichten"), {"code": aktueller_code(g)})
        self.assertNotIn("zwei-faktor", self.client.get(reverse("dashboard")).get("Location", ""))
        self.client.post(reverse("zf_verwalten"), {"aktion": "aus", "passwort": PW})
        self.assertTrue(ZweiFaktor.objects.get(user=self.admin).aktiv)

    def test_normale_benutzer_nicht_betroffen(self):
        self.client.login(username="max", password=PW)
        r = self.client.get(reverse("nach_login"))
        self.assertNotIn("zwei-faktor", r.url)
