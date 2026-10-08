from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from datetime import date, timedelta

from apps.core.models import Rolle, Verein, Zugang
from apps.documents.platzhalter import kontext

from .models import Anmeldung, Veranstaltung, Wahlergebnis


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


class VeranstaltungInventarTests(TestCase):
    """Die Schaltfläche "Inventar reservieren" muss direkt zur Mehrfachauswahl (Sammelverleih) führen - ein
    Entleiher ist hier nicht nötig, da der Verein selbst reserviert."""

    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.ver = Veranstaltung.objects.create(verein=self.v, titel="Sommerfest 2026", beginn=timezone.now())
        User = get_user_model()
        self.admin = User.objects.create_superuser("admin", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=self.admin,
                              rolle=Rolle.objects.get(verein=self.v, name="Superadministrator"))
        self.client.login(username="admin", password="pw-Test-12345")

    def test_inventar_reservieren_knopf_verweist_auf_sammelauswahl(self):
        r = self.client.get(reverse("veranstaltung_detail", args=[self.ver.pk]))
        self.assertContains(r, reverse("verleih_sammel_add") + f"?veranstaltung={self.ver.pk}")


class RueckmeldungTests(TestCase):
    """Öffentliche Zu-/Absage zu einer Veranstaltung mit Rückmeldepflicht - ohne Anmeldung, über einen
    nicht erratbaren Link."""

    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.ver = Veranstaltung.objects.create(verein=self.v, titel="Sommerfest 2026", beginn=timezone.now(),
                                                anmeldung_erforderlich=True)

    def test_hinweis_mit_rueckmeldungs_link_auf_der_veranstaltungsseite(self):
        User = get_user_model()
        admin = User.objects.create_superuser("admin", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=admin, rolle=Rolle.objects.get(verein=self.v, name="Superadministrator"))
        self.client.login(username="admin", password="pw-Test-12345")
        r = self.client.get(reverse("veranstaltung_detail", args=[self.ver.pk]))
        self.assertContains(r, reverse("veranstaltung_rueckmeldung", args=[self.ver.rueckmeldung_code]))

    def test_veranstaltung_ohne_anmeldepflicht_hat_keinen_hinweis(self):
        self.ver.anmeldung_erforderlich = False
        self.ver.save(update_fields=["anmeldung_erforderlich"])
        User = get_user_model()
        admin = User.objects.create_superuser("admin2", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=admin, rolle=Rolle.objects.get(verein=self.v, name="Superadministrator"))
        self.client.login(username="admin2", password="pw-Test-12345")
        r = self.client.get(reverse("veranstaltung_detail", args=[self.ver.pk]))
        self.assertNotContains(r, "Rückmeldungs-Link")

    def test_oeffentliche_seite_ohne_anmeldung_erreichbar(self):
        r = self.client.get(reverse("veranstaltung_rueckmeldung", args=[self.ver.rueckmeldung_code]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Sommerfest 2026")

    def test_zusage_wird_gespeichert(self):
        url = reverse("veranstaltung_rueckmeldung", args=[self.ver.rueckmeldung_code])
        r = self.client.post(url, {"name": "Erika Musterfrau", "personen": "2", "status": "zugesagt",
                                   "bemerkung": "Bringe Kuchen mit"})
        self.assertEqual(r.status_code, 200)
        a = Anmeldung.objects.get(verein=self.v, veranstaltung=self.ver, name="Erika Musterfrau")
        self.assertEqual(a.status, "zugesagt")
        self.assertEqual(a.personen, 2)
        self.assertEqual(a.bemerkung, "Bringe Kuchen mit")
        self.assertIsNone(a.mitglied_id)

    def test_absage_wird_gespeichert(self):
        url = reverse("veranstaltung_rueckmeldung", args=[self.ver.rueckmeldung_code])
        self.client.post(url, {"name": "Max Mustermann", "personen": "1", "status": "abgesagt"})
        a = Anmeldung.objects.get(verein=self.v, veranstaltung=self.ver, name="Max Mustermann")
        self.assertEqual(a.status, "abgesagt")

    def test_erneute_ruckmeldung_aktualisiert_statt_duplikat(self):
        """Antwortet dieselbe Person nochmal (z. B. Meinung geändert), wird die bestehende Anmeldung
        aktualisiert statt eine zweite anzulegen."""
        url = reverse("veranstaltung_rueckmeldung", args=[self.ver.rueckmeldung_code])
        self.client.post(url, {"name": "Max Mustermann", "personen": "1", "status": "zugesagt"})
        self.client.post(url, {"name": "Max Mustermann", "personen": "3", "status": "abgesagt"})
        positionen = Anmeldung.objects.filter(verein=self.v, veranstaltung=self.ver, name="Max Mustermann")
        self.assertEqual(positionen.count(), 1)
        self.assertEqual(positionen.first().status, "abgesagt")
        self.assertEqual(positionen.first().personen, 3)

    def test_ohne_namen_wird_fehlermeldung_gezeigt(self):
        url = reverse("veranstaltung_rueckmeldung", args=[self.ver.rueckmeldung_code])
        r = self.client.post(url, {"name": "", "personen": "1", "status": "zugesagt"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Anmeldung.objects.filter(verein=self.v, veranstaltung=self.ver).count(), 0)

    def test_nach_anmeldeschluss_keine_rueckmeldung_mehr_moeglich(self):
        self.ver.anmeldeschluss = date.today() - timedelta(days=1)
        self.ver.save(update_fields=["anmeldeschluss"])
        url = reverse("veranstaltung_rueckmeldung", args=[self.ver.rueckmeldung_code])
        r = self.client.post(url, {"name": "Zu spät", "personen": "1", "status": "zugesagt"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "abgelaufen")
        self.assertEqual(Anmeldung.objects.filter(verein=self.v, veranstaltung=self.ver).count(), 0)

    def test_unbekannter_code_ist_404(self):
        r = self.client.get(reverse("veranstaltung_rueckmeldung", args=["00000000-0000-0000-0000-000000000000"]))
        self.assertEqual(r.status_code, 404)

    def test_veranstaltung_ohne_anmeldepflicht_liefert_404_fuer_rueckmeldungsseite(self):
        self.ver.anmeldung_erforderlich = False
        self.ver.save(update_fields=["anmeldung_erforderlich"])
        r = self.client.get(reverse("veranstaltung_rueckmeldung", args=[self.ver.rueckmeldung_code]))
        self.assertEqual(r.status_code, 404)
