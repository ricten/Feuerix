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
                         ["1 Schicht(en) noch nicht voll besetzt."])
        self.assertNotIn("alert-info py-2\">1 Schicht", r.content.decode())
