"""Versandart bei Serienbriefen/Einladungen: E-Mail an Mitglieder mit Adresse, alle übrigen per Post."""
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader

from apps.core.models import Rolle, Verein, Zugang
from apps.events.models import Veranstaltung
from apps.members.models import Mitglied

from .models import Serienbrief, Vorlage
from .tasks import serienbrief_mailen_task

PW = "pw-Test-12345"


def seiten(antwort):
    return len(PdfReader(BytesIO(antwort.content)).pages)


class VersandartTests(TestCase):
    def setUp(self):
        self.verein = Verein.objects.create(name="Testverein", kuerzel="test")
        self.admin = get_user_model().objects.create_superuser("admin", password=PW)
        Zugang.objects.create(verein=self.verein, user=self.admin,
                              rolle=Rolle.objects.get(verein=self.verein, name="Superadministrator"))
        self.client.force_login(self.admin)
        for i, email in enumerate(["a@example.org", "b@example.org", "", ""]):
            Mitglied.objects.create(verein=self.verein, vorname=f"V{i}", nachname=f"N{i}", status="aktiv", email=email)

    def sb(self, **kw):
        return Serienbrief.objects.create(verein=self.verein, titel="Einladung", betreff="Einladung",
                                          text="{briefanrede}\n\nbitte kommen.", **kw)

    def test_empfaengerkreise_je_versandart(self):
        for art, mail_n, post_n in (("beides", 2, 4), ("mail_post", 2, 2), ("post", 0, 4), ("mail", 2, 0)):
            sb = self.sb(versandart=art)
            self.assertEqual((sb.mail_empfaenger().count(), sb.post_empfaenger().count()), (mail_n, post_n), art)

    def test_pdf_fuer_post_enthaelt_nur_die_ohne_email(self):
        sb = self.sb(versandart="mail_post")
        r = self.client.get(reverse("serienbrief_pdf", args=[sb.pk]) + "?alle=1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(seiten(r), 2)
        sb.versandart = "post"
        sb.save()
        self.assertEqual(seiten(self.client.get(reverse("serienbrief_pdf", args=[sb.pk]) + "?alle=1")), 4)

    def test_vorschau_funktioniert_auch_wenn_alle_per_mail(self):
        sb = self.sb(versandart="mail")
        self.assertEqual(seiten(self.client.get(reverse("serienbrief_pdf", args=[sb.pk]))), 1)

    def test_mailversand_nur_an_mail_empfaenger(self):
        sb = self.sb(versandart="mail_post")
        serienbrief_mailen_task(sb.pk)
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ["a@example.org", "b@example.org"])
        sb.refresh_from_db()
        self.assertIn("2 versendet", sb.versand_info)
        self.assertIn("per Post", sb.versand_info)

    def test_bei_nur_post_wird_nichts_gemailt(self):
        sb = self.sb(versandart="post")
        serienbrief_mailen_task(sb.pk)
        self.assertEqual(len(mail.outbox), 0)

    def test_detailseite_zeigt_zaehler_und_versandweg(self):
        sb = self.sb(versandart="mail_post")
        r = self.client.get(reverse("serienbrief_detail", args=[sb.pk]))
        self.assertContains(r, "Per E-Mail: 2 · Per Post (Brief-PDF): 2")
        self.assertContains(r, "Briefe für den Postversand als PDF (2)")
        self.assertContains(r, "Per E-Mail senden (2)")
        self.assertContains(r, ">Post<")
        sb.versandart = "post"
        sb.save()
        self.assertNotContains(self.client.get(reverse("serienbrief_detail", args=[sb.pk])), "Per E-Mail senden")

    def test_ablegen_nutzt_nur_postempfaenger(self):
        sb = self.sb(versandart="mail_post")
        self.client.post(reverse("serienbrief_ablegen", args=[sb.pk]))
        sb.refresh_from_db()
        self.assertIn("2 Briefe (Post)", sb.ablage.beschreibung)

    def test_einladung_aus_veranstaltung_standard_mail_und_post(self):
        Vorlage.objects.create(verein=self.verein, name="Einladung", art="einladung", text="x", ist_standard=True)
        v = Veranstaltung.objects.create(verein=self.verein, titel="JHV", art="versammlung", beginn=timezone.now())
        self.client.post(reverse("veranstaltung_schriftstueck", args=[v.pk, "serienbrief"]))
        self.assertEqual(Serienbrief.objects.get(veranstaltung=v).versandart, "mail_post")
