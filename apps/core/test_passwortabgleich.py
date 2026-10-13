"""Passwort-Abgleich (Feuerix → Paperless/OpenSlides) und Anzeige des Administrator-Zugangs."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from apps.core import passwortabgleich
from apps.core.models import AuditLog, Rolle, Verein, Zugang
from apps.members.models import Mitglied
from apps.openslides.client import OpenSlidesFehler
from apps.openslides.models import OpenSlidesVerbindung
from apps.paperless.client import PaperlessFehler
from apps.paperless.models import PaperlessBenutzer, PaperlessVerbindung

User = get_user_model()
PW = "pw-Test-12345"


class Basis(TestCase):
    def setUp(self):
        self.verein = Verein.objects.create(name="Testverein", kuerzel="test")
        self.user = User.objects.create_user("max", password=PW)
        self.m = Mitglied.objects.create(verein=self.verein, vorname="Max", nachname="Mustermann", status="aktiv",
                                         benutzer=self.user, openslides_user_id=7, openslides_username="max.mustermann",
                                         openslides_initialpasswort="altos")
        self.pl = PaperlessVerbindung.objects.create(verein=self.verein, url="https://paperless.example.org", api_token="tok",
                                                     aktiv=True, passwoerter_abgleichen=True)
        PaperlessBenutzer.objects.create(verein=self.verein, mitglied=self.m, paperless_id=3, benutzername="max",
                                         initialpasswort="altpl")
        self.os = OpenSlidesVerbindung.objects.create(verein=self.verein, url="https://os.example.org", benutzername="sync",
                                                      passwort="geheim", aktiv=True, passwoerter_abgleichen=True)


class AbgleichTests(Basis):
    def lauf(self, user=None, pw="Neu-Pw-98765x"):
        with patch("apps.paperless.client.PaperlessClient.benutzer_aendern") as pl, \
                patch("apps.openslides.client.OSClient.login") as login, \
                patch("apps.openslides.client.OSClient.action") as aktion:
            erg = passwortabgleich.abgleichen(user or self.user, pw)
        return erg, pl, login, aktion

    def test_setzt_passwort_in_beiden_systemen_und_loescht_startpasswoerter(self):
        erg, pl, login, aktion = self.lauf()
        pl.assert_called_once_with(3, {"password": "Neu-Pw-98765x"})
        aktion.assert_called_once_with("user.set_password", [{"id": 7, "password": "Neu-Pw-98765x", "set_as_default": False}])
        self.assertEqual(sorted(erg.ok), ["OpenSlides: max.mustermann", "Paperless: max"])
        self.assertEqual(erg.fehler, [])
        self.m.refresh_from_db()
        self.assertEqual(self.m.openslides_initialpasswort, "")
        self.assertEqual(PaperlessBenutzer.objects.get().initialpasswort, "")

    def test_ohne_schalter_oder_inaktiv_passiert_nichts(self):
        PaperlessVerbindung.objects.update(passwoerter_abgleichen=False)
        OpenSlidesVerbindung.objects.update(aktiv=False)
        erg, pl, login, aktion = self.lauf()
        pl.assert_not_called()
        aktion.assert_not_called()
        self.assertFalse(erg)
        self.m.refresh_from_db()
        self.assertEqual(self.m.openslides_initialpasswort, "altos")

    def test_benutzer_ohne_verknuepfte_konten(self):
        fremd = User.objects.create_user("fremd", password=PW)
        erg, pl, login, aktion = self.lauf(user=fremd)
        pl.assert_not_called()
        aktion.assert_not_called()
        self.assertFalse(erg)

    def test_leeres_passwort_wird_nie_gesetzt(self):
        erg, pl, login, aktion = self.lauf(pw="")
        pl.assert_not_called()
        self.assertFalse(erg)

    def test_fehler_werden_gesammelt_und_nie_geworfen(self):
        with patch("apps.paperless.client.PaperlessClient.benutzer_aendern", side_effect=PaperlessFehler("HTTP 400: zu einfach")), \
                patch("apps.openslides.client.OSClient.login", side_effect=OpenSlidesFehler("nicht erreichbar")):
            erg = passwortabgleich.abgleichen(self.user, "Neu-Pw-98765x")
        self.assertEqual(erg.ok, [])
        self.assertEqual(len(erg.fehler), 2)
        self.assertIn("zu einfach", erg.fehler[0])
        self.m.refresh_from_db()
        self.assertEqual(self.m.openslides_initialpasswort, "altos")        # nichts gesetzt -> Startpasswort bleibt

    def test_unerwartete_ausnahme_wird_abgefangen(self):
        with patch("apps.paperless.client.PaperlessClient.benutzer_aendern", side_effect=RuntimeError("kaputt")):
            erg = passwortabgleich.abgleichen(self.user, "x")
        self.assertTrue(any("kaputt" in f for f in erg.fehler))

    def test_superadmin_ohne_mitglied_ueber_zugang(self):
        admin = User.objects.create_superuser("root", password=PW)
        z = Zugang.objects.create(verein=self.verein, user=admin, rolle=Rolle.objects.get(verein=self.verein, name="Superadministrator"))
        PaperlessBenutzer.objects.create(verein=self.verein, zugang=z, paperless_id=9, benutzername="root")
        erg, pl, login, aktion = self.lauf(user=admin)
        pl.assert_called_once_with(9, {"password": "Neu-Pw-98765x"})


class HakenTests(Basis):
    """Die Stellen, an denen ein Passwort gesetzt wird, rufen den Abgleich auf."""

    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser("root", password=PW)
        self.rolle = Rolle.objects.get(verein=self.verein, name="Superadministrator")
        Zugang.objects.create(verein=self.verein, user=self.admin, rolle=self.rolle)

    def test_eigenes_passwort_aendern(self):
        self.client.force_login(self.user)
        with patch("apps.core.passwortabgleich.abgleichen", return_value=passwortabgleich.Ergebnis()) as ab:
            r = self.client.post(reverse("password_change"), {"old_password": PW, "new_password1": "Neu-Pw-98765x",
                                                              "new_password2": "Neu-Pw-98765x"})
        self.assertEqual(r.status_code, 302)
        ab.assert_called_once()
        self.assertEqual(ab.call_args.args[1], "Neu-Pw-98765x")
        self.assertEqual(ab.call_args.args[0].pk, self.user.pk)

    def test_falsche_eingabe_loest_keinen_abgleich_aus(self):
        self.client.force_login(self.user)
        with patch("apps.core.passwortabgleich.abgleichen") as ab:
            self.client.post(reverse("password_change"), {"old_password": "falsch", "new_password1": "Neu-Pw-98765x",
                                                          "new_password2": "Neu-Pw-98765x"})
        ab.assert_not_called()

    def test_meldungen_nach_abgleich(self):
        self.client.force_login(self.user)
        with patch("apps.paperless.client.PaperlessClient.benutzer_aendern"), \
                patch("apps.openslides.client.OSClient.login"), patch("apps.openslides.client.OSClient.action"):
            r = self.client.post(reverse("password_change"), {"old_password": PW, "new_password1": "Neu-Pw-98765x",
                                                              "new_password2": "Neu-Pw-98765x"}, follow=True)
        self.assertContains(r, "Das Passwort wurde auch gesetzt in: ")
        self.assertContains(r, "Paperless: max")

    def test_admin_setzt_passwort_in_benutzerverwaltung(self):
        z = Zugang.objects.create(verein=self.verein, user=self.user, rolle=self.rolle)
        self.client.force_login(self.admin)
        s = self.client.session
        s["verein_id"] = self.verein.pk
        s.save()
        with patch("apps.core.passwortabgleich.abgleichen", return_value=passwortabgleich.Ergebnis()) as ab:
            self.client.post(reverse("benutzer_passwort", args=[z.pk]),
                             {"passwort": "Neu-Pw-98765x", "passwort2": "Neu-Pw-98765x"})
        ab.assert_called_once()
        self.assertEqual(ab.call_args.args[0].pk, self.user.pk)

    def test_benutzer_mit_passwort_anlegen(self):
        self.client.force_login(self.admin)
        s = self.client.session
        s["verein_id"] = self.verein.pk
        s.save()
        daten = {"username": "neu", "rolle": self.rolle.pk, "passwort": "Neu-Pw-98765x", "aktiv": "on"}
        with patch("apps.core.passwortabgleich.abgleichen", return_value=passwortabgleich.Ergebnis()) as ab:
            r = self.client.post(reverse("zugang_add"), daten)
        self.assertEqual(r.status_code, 302)
        ab.assert_called_once()
        self.assertEqual((ab.call_args.args[0].username, ab.call_args.args[1]), ("neu", "Neu-Pw-98765x"))

    def test_verwaltungszugang_einrichten(self):
        self.m.email = "max@example.org"
        self.m.benutzer = None
        self.m.save()
        self.client.force_login(self.admin)
        s = self.client.session
        s["verein_id"] = self.verein.pk
        s.save()
        with patch("apps.core.passwortabgleich.abgleichen", return_value=passwortabgleich.Ergebnis()) as ab, \
                patch("apps.members.verwaltungszugang._zugangsdaten_mailen"):
            self.client.post(reverse("mitglied_verwaltungszugang_einrichten", args=[self.m.pk]), {"rolle": self.rolle.pk})
        ab.assert_called_once()
        self.assertEqual(ab.call_args.args[0].username, "max@example.org")


class AdminZugangTests(Basis):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser("root", password=PW)
        Zugang.objects.create(verein=self.verein, user=self.admin, rolle=Rolle.objects.get(verein=self.verein, name="Superadministrator"))
        self.client.force_login(self.admin)
        s = self.client.session
        s["verein_id"] = self.verein.pk
        s.save()
        self.pl.admin_benutzer, self.pl.admin_passwort = "admin", "Geheimes-Admin-PW"
        self.pl.save()

    def test_formular_zeigt_felder_nur_superadmins(self):
        r = self.client.get(reverse("paperless_einstellungen"))
        for name in ("admin_benutzer", "admin_passwort", "passwoerter_abgleichen"):
            self.assertContains(r, f'name="{name}"')
        self.assertNotContains(r, "Geheimes-Admin-PW")                # nie im Formular
        lesen = Rolle.objects.create(verein=self.verein, name="Paperless-Admin", rechte=["paperless.view", "paperless.change"])
        u = User.objects.create_user("pl", password=PW)
        Zugang.objects.create(verein=self.verein, user=u, rolle=lesen)
        self.client.force_login(u)
        s = self.client.session
        s["verein_id"] = self.verein.pk
        s.save()
        r = self.client.get(reverse("paperless_einstellungen"))
        self.assertEqual(r.status_code, 200)
        for name in ("admin_benutzer", "admin_passwort", "passwoerter_abgleichen"):
            self.assertNotContains(r, f'name="{name}"')
        self.assertNotContains(r, "paperless_admin_anzeigen")

    def test_nicht_superadmin_kann_nichts_ueberschreiben(self):
        lesen = Rolle.objects.create(verein=self.verein, name="Paperless-Admin", rechte=["paperless.view", "paperless.change"])
        u = User.objects.create_user("pl", password=PW)
        Zugang.objects.create(verein=self.verein, user=u, rolle=lesen)
        self.client.force_login(u)
        s = self.client.session
        s["verein_id"] = self.verein.pk
        s.save()
        self.client.post(reverse("paperless_einstellungen"), {
            "url": "https://paperless.example.org", "aktiv": "on", "tls_pruefen": "on", "kategorie_tags": "on",
            "auto_uebergabe": "on", "vorstand_gruppe": "Vorstand", "admin_passwort": "Angriff", "passwoerter_abgleichen": "on"})
        self.pl.refresh_from_db()
        self.assertEqual(self.pl.admin_passwort, "Geheimes-Admin-PW")
        self.assertTrue(self.pl.passwoerter_abgleichen)       # unveraendert (war schon an) - nicht per POST aenderbar
        self.assertEqual(self.client.post(reverse("paperless_admin_anzeigen"), {"passwort": PW}).status_code, 403)

    def test_speichern_verschluesselt_und_leer_behaelt(self):
        daten = {"url": "https://paperless.example.org", "aktiv": "on", "tls_pruefen": "on", "kategorie_tags": "on",
                 "auto_uebergabe": "on", "vorstand_gruppe": "Vorstand", "admin_benutzer": "admin2", "admin_passwort": "Neues-Admin-PW"}
        self.client.post(reverse("paperless_einstellungen"), daten)
        self.pl.refresh_from_db()
        self.assertEqual((self.pl.admin_benutzer, self.pl.admin_passwort), ("admin2", "Neues-Admin-PW"))
        with connection.cursor() as c:
            c.execute("select admin_passwort from paperless_paperlessverbindung")
            roh = c.fetchone()[0]
        self.assertNotIn("Neues-Admin-PW", roh)                 # in der Datenbank verschluesselt
        daten["admin_passwort"] = ""
        self.client.post(reverse("paperless_einstellungen"), daten)
        self.pl.refresh_from_db()
        self.assertEqual(self.pl.admin_passwort, "Neues-Admin-PW")

    def test_anzeigen_nach_passwortbestaetigung(self):
        r = self.client.post(reverse("paperless_admin_anzeigen"), {"passwort": PW})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Geheimes-Admin-PW")
        self.assertContains(r, "admin")
        self.assertIn("no-store", r["Cache-Control"])
        eintrag = AuditLog.objects.filter(modell__icontains="Paperless-Verbindung").latest("zeit")
        self.assertEqual(eintrag.user_name, "root")
        self.assertIn("angezeigt", str(eintrag.aenderungen))
        self.assertNotIn("Geheimes-Admin-PW", str(eintrag.aenderungen))      # Passwort selbst nie im Protokoll

    def test_falsches_passwort_zeigt_nichts(self):
        r = self.client.post(reverse("paperless_admin_anzeigen"), {"passwort": "falsch"}, follow=True)
        self.assertNotContains(r, "Geheimes-Admin-PW")
        self.assertContains(r, "Das Passwort ist falsch.")

    def test_ohne_gespeichertes_passwort(self):
        self.pl.admin_passwort = ""
        self.pl.save()
        r = self.client.post(reverse("paperless_admin_anzeigen"), {"passwort": PW}, follow=True)
        self.assertContains(r, "Es ist noch kein Administrator-Zugang gespeichert.")

    def test_nur_per_post(self):
        self.assertEqual(self.client.get(reverse("paperless_admin_anzeigen")).status_code, 405)

    def test_openslides_genauso(self):
        self.os.admin_benutzer, self.os.admin_passwort = "superadmin", "OS-Super-PW"
        self.os.save()
        r = self.client.post(reverse("openslides_admin_anzeigen"), {"passwort": PW})
        self.assertContains(r, "OS-Super-PW")
        self.assertContains(r, "superadmin")
        html = self.client.get(reverse("openslides_einstellungen")).content.decode()
        self.assertIn("openslides_admin_anzeigen", html.replace("/openslides/admin-zugang/", "openslides_admin_anzeigen"))
        self.assertNotIn("OS-Super-PW", html)
