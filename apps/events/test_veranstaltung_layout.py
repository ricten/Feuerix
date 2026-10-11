from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Rolle, Verein, Zugang
from apps.events.models import Anmeldung, Kostenposition, Schicht, Veranstaltung

PW = "pw-Test-12345"


class VeranstaltungSeitenaufbauTests(TestCase):
    """Zusammenfassungen und Weitergabe-Links stehen nicht mehr als Hinweiskaesten ganz oben, sondern bei ihrem Inhalt."""

    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        User = get_user_model()
        admin = User.objects.create_superuser("admin", password=PW)
        Zugang.objects.create(verein=self.v, user=admin, rolle=Rolle.objects.get(verein=self.v,
                                                                                  name="Superadministrator"))
        self.client.login(username="admin", password=PW)
        self.ver = Veranstaltung.objects.create(verein=self.v, titel="Sommerfest", beginn=timezone.now(),
                                                anmeldung_erforderlich=True, helfer_eintragung=True,
                                                erwartete_teilnehmer=50)

    def _seite(self):
        return self.client.get(reverse("veranstaltung_detail", args=[self.ver.pk]))

    def test_links_in_eigener_karte_mit_beiden_adressen(self):
        r = self._seite()
        html = r.content.decode()
        self.assertIn("Links zum Weitergeben", html)
        rueck = reverse("veranstaltung_rueckmeldung", args=[self.ver.rueckmeldung_code])
        helfer = reverse("veranstaltung_helfer", args=[self.ver.rueckmeldung_code])
        self.assertIn(f'value="http://testserver{rueck}"', html)
        self.assertIn(f'value="http://testserver{helfer}"', html)
        self.assertNotIn("alert alert-info py-2\">Rückmeldungs-Link", html)   # kein Hinweiskasten mehr
        self.assertIn("data-url=", html)   # Kopieren-Knopf

    def test_ohne_freigaben_keine_links_karte(self):
        self.ver.anmeldung_erforderlich = False
        self.ver.helfer_eintragung = False
        self.ver.save()
        self.assertNotContains(self._seite(), "Links zum Weitergeben")

    def test_nur_ein_link_wenn_nur_eine_funktion_aktiv(self):
        self.ver.helfer_eintragung = False
        self.ver.save()
        r = self._seite()
        self.assertContains(r, "Rückmeldung (Zu-/Absage)")
        self.assertNotContains(r, "Helfer-Selbsteintrag in Schichten")

    def test_budget_zusammenfassung_steht_im_budget_abschnitt_nicht_oben(self):
        Kostenposition.objects.create(verein=self.v, veranstaltung=self.ver, art="einnahme", bezeichnung="Eintritt",
                                      plan_betrag=Decimal("500"), ist_betrag=Decimal("420"))
        Kostenposition.objects.create(verein=self.v, veranstaltung=self.ver, art="ausgabe", bezeichnung="Getränke",
                                      plan_betrag=Decimal("200"), ist_betrag=Decimal("250"))
        r = self._seite()
        abschnitt = r.context["abschnitte"][[a["titel"] for a in r.context["abschnitte"]].index("Budget")]
        self.assertEqual(len(abschnitt["fuss"]), 2)
        self.assertIn("Plan: Einnahmen 500,00 € · Ausgaben 200,00 € · Ergebnis 300,00 €", abschnitt["fuss"][0])
        self.assertIn("Ist: Einnahmen 420,00 € · Ausgaben 250,00 € · Ergebnis 170,00 €", abschnitt["fuss"][1])
        self.assertNotIn("alert-info py-2\">Plan:", r.content.decode())
        self.assertContains(r, "Ergebnis 300,00 €")   # steht auf der Seite (in der Fusszeile des Abschnitts)

    def test_ohne_budgetposten_keine_nullzeilen(self):
        self.assertNotContains(self._seite(), "Plan: Einnahmen")

    def test_zugesagte_personen_beim_abschnitt_anmeldungen(self):
        Anmeldung.objects.create(verein=self.v, veranstaltung=self.ver, name="A", personen=3, status="zugesagt")
        Anmeldung.objects.create(verein=self.v, veranstaltung=self.ver, name="B", personen=2, status="abgesagt")
        r = self._seite()
        self.assertContains(r, "Zugesagte Personen: 3 von erwartet 50")
        titel = [a["titel"] for a in r.context["abschnitte"]]
        fuss = r.context["abschnitte"][titel.index("Anmeldungen")]["fuss"]
        self.assertEqual(fuss, ["Zugesagte Personen: 3 von erwartet 50"])

    def test_offene_schichten_beim_schichtplan(self):
        Schicht.objects.create(verein=self.v, veranstaltung=self.ver, bezeichnung="Theke",
                               beginn=timezone.now() + timedelta(days=1), ende=timezone.now() + timedelta(days=1, hours=3),
                               benoetigt=2)
        r = self._seite()
        titel = [a["titel"] for a in r.context["abschnitte"]]
        self.assertEqual(r.context["abschnitte"][titel.index("Schichtplan")]["fuss"],
                         ["1 Schicht(en) noch nicht voll besetzt.",
                          "1 von 1 Schichten sind für den Selbsteintrag freigegeben."])
        self.assertNotIn("alert-info py-2\">1 Schicht", r.content.decode())


class TagesordnungNurBeiVersammlungenTests(TestCase):
    """Die Tagesordnung gibt es nur bei Versammlungen und Sitzungen."""

    def setUp(self):
        from apps.events.models import Tagesordnungspunkt
        self.TOP = Tagesordnungspunkt
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        User = get_user_model()
        admin = User.objects.create_superuser("admin", password=PW)
        Zugang.objects.create(verein=self.v, user=admin, rolle=Rolle.objects.get(verein=self.v,
                                                                                  name="Superadministrator"))
        self.client.login(username="admin", password=PW)

    def _veranstaltung(self, art):
        return Veranstaltung.objects.create(verein=self.v, titel=f"Test {art}", art=art, beginn=timezone.now())

    def _titel(self, ver):
        r = self.client.get(reverse("veranstaltung_detail", args=[ver.pk]))
        return [a["titel"] for a in r.context["abschnitte"]], r

    def test_versammlung_und_sitzung_zeigen_tagesordnung_und_standardknopf(self):
        for art in ("versammlung", "sitzung"):
            titel, r = self._titel(self._veranstaltung(art))
            self.assertIn("Tagesordnung", titel, art)
            self.assertContains(r, "Standard-Tagesordnung")

    def test_andere_arten_blenden_tagesordnung_und_knopf_aus(self):
        for art in ("fest", "ausflug", "schulung", "sonstiges"):
            titel, r = self._titel(self._veranstaltung(art))
            self.assertNotIn("Tagesordnung", titel, art)
            self.assertNotContains(r, "Standard-Tagesordnung")

    def test_bereits_erfasste_punkte_bleiben_trotzdem_sichtbar(self):
        fest = self._veranstaltung("fest")
        self.TOP.objects.create(verein=self.v, veranstaltung=fest, position=1, titel="Begrüßung")
        titel, r = self._titel(fest)
        self.assertIn("Tagesordnung", titel)
        self.assertContains(r, "Begrüßung")

    def test_reihenfolge_der_abschnitte_bleibt_sinnvoll_ohne_tagesordnung(self):
        titel, _ = self._titel(self._veranstaltung("fest"))
        self.assertEqual(titel[:4], ["Aufgaben", "Anmeldungen", "Schichtplan", "Budget"])
        titel, _ = self._titel(self._veranstaltung("versammlung"))
        self.assertEqual(titel[:5], ["Tagesordnung", "Aufgaben", "Anmeldungen", "Schichtplan", "Budget"])

    def test_art_wird_geaendert_dann_verschwindet_die_leere_tagesordnung(self):
        ver = self._veranstaltung("versammlung")
        self.assertIn("Tagesordnung", self._titel(ver)[0])
        ver.art = "fest"
        ver.save()
        self.assertNotIn("Tagesordnung", self._titel(ver)[0])

    def test_openslides_knoepfe_nur_bei_versammlung_oder_vorhandener_verknuepfung(self):
        from apps.openslides.models import OpenSlidesVerbindung
        OpenSlidesVerbindung.objects.create(verein=self.v, url="https://os.example.org", benutzername="s",
                                            passwort="p", aktiv=True)
        self.assertContains(self.client.get(reverse("veranstaltung_detail", args=[self._veranstaltung("versammlung").pk])),
                            "In OpenSlides anlegen")
        fest = self._veranstaltung("fest")
        self.assertNotContains(self.client.get(reverse("veranstaltung_detail", args=[fest.pk])), "In OpenSlides anlegen")
        fest.openslides_meeting_id = 5
        fest.save()
        self.assertContains(self.client.get(reverse("veranstaltung_detail", args=[fest.pk])),
                            "Tagesordnung nach OpenSlides übertragen")
