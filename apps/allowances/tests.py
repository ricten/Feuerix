from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Rolle, Verein, Zugang
from apps.members.models import Mitglied, Mitgliedsart

from .models import Aufwandsentschaedigung


class NegativerBetragValidierungTests(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        art = Mitgliedsart.objects.get(verein=self.v, name="Aktiv")
        self.m = Mitglied.objects.create(verein=self.v, vorname="Max", nachname="Muster", mitgliedsart=art,
                                         eintrittsdatum=date(2015, 1, 1))
        User = get_user_model()
        self.admin = User.objects.create_superuser("admin", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=self.admin,
                              rolle=Rolle.objects.get(verein=self.v, name="Superadministrator"))
        self.client.login(username="admin", password="pw-Test-12345")

    def test_negativer_betrag_wird_abgelehnt(self):
        self.client.post(reverse("aufwandsentschaedigung_add"), {
            "empfaenger": self.m.pk, "art": "aufwandsersatz", "datum": date.today(), "betrag": "-20.00",
            "taetigkeit": "Fahrtkosten"})
        self.assertEqual(Aufwandsentschaedigung.objects.filter(empfaenger=self.m).count(), 0)
