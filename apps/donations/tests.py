from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Rolle, Verein, Zugang

from .models import Spende, Zuwendungsbestaetigung


class SpendeSperreNachQuittungTests(TestCase):
    """Nach dem Ausstellen einer Zuwendungsbestaetigung muss die verknuepfte Spende unveraenderlich sein -
    sonst zeigt die bereits ausgehaendigte Quittung einen anderen Betrag als die interne Buchhaltung."""

    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        User = get_user_model()
        self.admin = User.objects.create_superuser("admin", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=self.admin,
                              rolle=Rolle.objects.get(verein=self.v, name="Superadministrator"))
        self.client.login(username="admin", password="pw-Test-12345")

    def test_spende_ohne_quittung_bleibt_bearbeitbar(self):
        s = Spende.objects.create(verein=self.v, spender_name="Max Muster", betrag=Decimal("50.00"))
        r = self.client.get(reverse("spende_edit", args=[s.pk]))
        self.assertEqual(r.status_code, 200)
        r = self.client.post(reverse("spende_delete", args=[s.pk]))
        self.assertEqual(r.status_code, 302)

    def test_spende_mit_ausgestellter_quittung_nicht_mehr_bearbeitbar_oder_loeschbar(self):
        b = Zuwendungsbestaetigung.objects.create(verein=self.v, spender_name="Max Muster",
                                                  spender_anschrift="Musterstr. 1, 12345 Musterstadt",
                                                  betrag=Decimal("50.00"), datum_von=date(2026, 1, 1),
                                                  datum_bis=date(2026, 1, 1))
        b.ausstellen()
        s = Spende.objects.create(verein=self.v, spender_name="Max Muster", betrag=Decimal("50.00"),
                                  bestaetigung=b)
        r = self.client.get(reverse("spende_edit", args=[s.pk]))
        self.assertEqual(r.status_code, 403)
        r = self.client.post(reverse("spende_edit", args=[s.pk]), {"betrag": "5.00"})
        self.assertEqual(r.status_code, 403)
        r = self.client.post(reverse("spende_delete", args=[s.pk]))
        self.assertEqual(r.status_code, 403)
        s.refresh_from_db()
        self.assertEqual(s.betrag, Decimal("50.00"))
