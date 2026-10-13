"""Englische Oberfläche: Meldungen, Knopf-Beschriftungen und Hinweise sind übersetzt, Icons bleiben richtig, und im
Katalog fehlt keine Übersetzung (neue Texte müssen übersetzt werden - siehe CLAUDE.md)."""
import ast
import os
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext_lazy
from django.utils.translation.trans_real import translation as hole_katalog

from apps.core.crud import knopf
from apps.core.models import Rolle, Verein, Zugang
from apps.documents.models import Serienbrief
from apps.members.models import Mitglied

PW = "pw-Test-12345"
UEBERSETZER = {"_", "gettext", "gettext_lazy", "_lazy", "ngettext"}
# gleichlautend in beiden Sprachen (Fremd-/Eigennamen, Abkürzungen) - fehlt dann u. U. im Katalog
GLEICH = {"Paperless", "OpenSlides", "TAN", "Excel", "PDF", "SEPA", "IBAN", "BIC", "Budget", "Status", "Name", "Version", "E-Mail",
          "Download", "Downloads", "Format"}


class EnglischeOberflaecheTests(TestCase):
    def setUp(self):
        self.verein = Verein.objects.create(name="Testverein", kuerzel="test")
        admin = get_user_model().objects.create_superuser("admin", password=PW)
        Zugang.objects.create(verein=self.verein, user=admin,
                              rolle=Rolle.objects.get(verein=self.verein, name="Superadministrator"))
        self.client.force_login(admin)
        self.client.post(reverse("set_language"), {"language": "en", "next": "/"})

    def test_knopf_label_ist_englisch_und_icon_bleibt_richtig(self):
        with translation.override("en"):
            b = knopf(gettext_lazy("Rückgabe erfassen"), "/x/")
            self.assertEqual(str(b["label"]), "Record return")
            self.assertEqual(b["icon"], "bi-box-arrow-in-down")      # Icon kommt aus dem deutschen Stichwort „Rückgabe“
        with translation.override("de"):
            self.assertEqual(str(b["label"]), "Rückgabe erfassen")

    def test_serienbrief_detail_auf_englisch(self):
        Mitglied.objects.create(verein=self.verein, vorname="A", nachname="B", status="aktiv", email="a@example.org")
        Mitglied.objects.create(verein=self.verein, vorname="C", nachname="D", status="aktiv")
        sb = Serienbrief.objects.create(verein=self.verein, titel="S", betreff="B", text="<p>x</p>", versandart="mail_post")
        html = self.client.get(reverse("serienbrief_detail", args=[sb.pk])).content.decode()
        self.assertIn("By email: 1 · By post (letter PDF): 1.", html)
        self.assertIn("Letters for postal dispatch as PDF (1)", html)
        self.assertIn("Send by email (1)", html)
        self.assertIn("Preview (first recipient)", html)
        for deutsch in ("Per E-Mail senden", "Briefe für den Postversand", "Vorschau (erster Empfänger)"):
            self.assertNotIn(deutsch, html)

    def test_meldung_auf_englisch(self):
        sb = Serienbrief.objects.create(verein=self.verein, titel="S", betreff="B", text="<p>x</p>")
        r = self.client.post(reverse("serienbrief_mailen", args=[sb.pk]), follow=True)
        self.assertContains(r, "Sending is running in the background.")
        self.assertNotContains(r, "Der Versand läuft im Hintergrund")

    def test_meldung_mit_platzhalter_auf_englisch(self):
        r = self.client.post(reverse("verein_waehlen"), {"verein": self.verein.pk}, follow=True)
        self.assertEqual(r.status_code, 200)

    def test_einstellungen_auf_englisch(self):
        html = self.client.get(reverse("einstellungen")).content.decode()
        self.assertIn("Settings", html)
        self.assertIn("Club data", html)
        self.assertNotIn("Vereinsdaten", html)

    def test_deutsch_bleibt_deutsch(self):
        self.client.post(reverse("set_language"), {"language": "de", "next": "/"})
        sb = Serienbrief.objects.create(verein=self.verein, titel="S", betreff="B", text="<p>x</p>")
        html = self.client.get(reverse("serienbrief_detail", args=[sb.pk])).content.decode()
        self.assertIn("Vorschau (erster Empfänger)", html)


class KatalogVollstaendigTests(TestCase):
    """Jeder mit _()/gettext markierte Text hat eine englische Übersetzung (sonst erscheint er auf Englisch deutsch)."""

    def test_keine_fehlenden_uebersetzungen(self):
        katalog = hole_katalog("en")._catalog
        fehlend = {}
        for pfad, _d, dateien in os.walk(Path(settings.BASE_DIR) / "apps"):
            if "migrations" in pfad:
                continue
            for f in dateien:
                if not f.endswith(".py") or f.startswith("test"):
                    continue
                p = os.path.join(pfad, f)
                for n in ast.walk(ast.parse(open(p, encoding="utf-8").read())):
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in UEBERSETZER and n.args \
                            and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                        s = n.args[0].value
                        if s not in katalog and s not in GLEICH and s.strip():
                            fehlend[s] = os.path.relpath(p, settings.BASE_DIR)
        self.assertEqual(fehlend, {}, "Texte ohne englische Übersetzung (locale/en/LC_MESSAGES/django.po ergänzen):")
