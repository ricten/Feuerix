"""Dateinamen: Rechnungen heißen Rechnungsnummer_Typ_Empfänger, gespeicherte Dateien tragen keine Zufallskennung im Namen."""
import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Rolle, Verein, Zugang
from apps.core.util import anzeige_dateiname, dateiname_bereinigen
from apps.documents.models import Ablagedokument
from apps.documents.services import ablegen
from apps.members.models import Mitglied

from . import services
from .pdf import rechnung_dateiname

PW = "pw-Test-12345"


class DateinameTests(TestCase):
    def setUp(self):
        self.verein = Verein.objects.create(name="Testverein", kuerzel="test")
        self.r = services.rechnung_erstellen(self.verein, [("Posten", 1, 10)], empfaenger_name="Max Mustermann",
                                             empfaenger_anschrift="Weg 1\n12345 Ort")

    def test_namensschema_nummer_typ_empfaenger(self):
        self.assertTrue(self.r.nummer)
        self.assertEqual(rechnung_dateiname(self.r), f"{self.r.nummer}_Individuelle_Rechnung_Max_Mustermann.pdf")
        self.assertEqual(rechnung_dateiname(self.r, "E-Rechnung"),
                         f"{self.r.nummer}_Individuelle_Rechnung_Max_Mustermann_E-Rechnung.pdf")

    def test_entwurf_ohne_nummer(self):
        self.r.nummer = ""
        self.assertEqual(rechnung_dateiname(self.r), "Entwurf_Individuelle_Rechnung_Max_Mustermann.pdf")

    def test_sonderzeichen_und_laenge(self):
        self.r.empfaenger_name = 'Müller / Söhne: "Bau" <GmbH>?'
        n = rechnung_dateiname(self.r)
        self.assertTrue(n.endswith("_Müller_Söhne_Bau_GmbH.pdf"), n)
        for z in '\\/:*?"<>|':
            self.assertNotIn(z, n)
        self.r.empfaenger_name = "A" * 400
        self.assertLessEqual(len(rechnung_dateiname(self.r)), 120 * 4 + 10)
        self.assertLessEqual(len(dateiname_bereinigen("x " * 200)), 120)
        self.assertEqual(dateiname_bereinigen("///"), "Dokument")

    def test_typ_bleibt_deutsch_auch_bei_englischer_oberflaeche(self):
        from django.utils import translation
        with translation.override("en"):
            self.assertIn("Individuelle_Rechnung", rechnung_dateiname(self.r))

    def test_mail_anhang(self):
        m = Mitglied.objects.create(verein=self.verein, vorname="Max", nachname="Mustermann", status="aktiv", email="m@example.org")
        self.r.mitglied = m
        self.r.save()
        services.rechnung_mailen(self.r)
        self.assertEqual(mail.outbox[0].attachments[0][0], rechnung_dateiname(self.r))


class DownloadTests(TestCase):
    def setUp(self):
        self.verein = Verein.objects.create(name="Testverein", kuerzel="test")
        admin = get_user_model().objects.create_superuser("admin", password=PW)
        Zugang.objects.create(verein=self.verein, user=admin, rolle=Rolle.objects.get(verein=self.verein, name="Superadministrator"))
        self.client.force_login(admin)
        self.r = services.rechnung_erstellen(self.verein, [("Posten", 1, 10)], empfaenger_name="Max Mustermann",
                                             empfaenger_anschrift="Weg 1\n12345 Ort")

    def test_pdf_download_name(self):
        r = self.client.get(reverse("rechnung_pdf", args=[self.r.pk]))
        self.assertEqual(r["Content-Disposition"], f'inline; filename="{rechnung_dateiname(self.r)}"')

    def test_erechnung_download_name(self):
        with patch("apps.finance.erechnung.zugferd_pdf", return_value=b"%PDF-1.4 x"):
            r = self.client.get(reverse("rechnung_erechnung", args=[self.r.pk]))
        self.assertEqual(r["Content-Disposition"], f'attachment; filename="{rechnung_dateiname(self.r, "E-Rechnung")}"')

    def test_umlaute_im_namen_werden_korrekt_kodiert(self):
        self.r.empfaenger_name = "Jörg Müller"
        self.r.save()
        r = self.client.get(reverse("rechnung_pdf", args=[self.r.pk]))
        self.assertIn("filename*=utf-8''", r["Content-Disposition"])
        self.assertIn("J%C3%B6rg_M%C3%BCller", r["Content-Disposition"])


class AblageDateinameTests(TestCase):
    def setUp(self):
        self.verein = Verein.objects.create(name="Testverein", kuerzel="test")

    def test_gespeicherter_name_hat_keine_kennung_im_dateinamen(self):
        d = ablegen(self.verein, "Rechnung", "rechnung", "RE-2026-0001_Rechnung_Max.pdf", b"%PDF-1.4")
        self.assertEqual(os.path.basename(d.datei.name), "RE-2026-0001_Rechnung_Max.pdf")
        self.assertEqual(d.dateiname, "RE-2026-0001_Rechnung_Max.pdf")
        ordner = os.path.basename(os.path.dirname(d.datei.name))
        self.assertRegex(ordner, r"^[0-9a-f]{12}$")           # die Kennung steht im Ordner

    def test_gleicher_name_zweimal_ohne_suffix(self):
        a = ablegen(self.verein, "A", "rechnung", "gleich.pdf", b"%PDF-1.4 a")
        b = ablegen(self.verein, "B", "rechnung", "gleich.pdf", b"%PDF-1.4 b")
        self.assertEqual((a.dateiname, b.dateiname), ("gleich.pdf", "gleich.pdf"))
        self.assertNotEqual(a.datei.name, b.datei.name)

    def test_alte_dateien_mit_kennung_werden_ohne_angezeigt(self):
        self.assertEqual(anzeige_dateiname("1/ablagedokument/0123456789ab_Beleg.pdf"), "Beleg.pdf")
        self.assertEqual(anzeige_dateiname("abc_Beleg.pdf"), "abc_Beleg.pdf")           # kein Treffer -> unveraendert
        self.assertEqual(anzeige_dateiname("1/x/Ohne.pdf"), "Ohne.pdf")
        self.assertEqual(anzeige_dateiname(""), "")
        alt = Ablagedokument.objects.create(verein=self.verein, titel="Alt", kategorie="rechnung", datei="1/ablagedokument/0123456789ab_Alt.pdf",
                                            ordner=ablegen(self.verein, "X", "rechnung", "x.pdf", b"x").ordner)
        self.assertEqual(alt.dateiname, "Alt.pdf")

    def test_automatische_ablage_der_rechnung(self):
        from apps.paperless.tasks import fertiges_dokument_task
        r = services.rechnung_erstellen(self.verein, [("Posten", 1, 10)], empfaenger_name="Max Mustermann")
        with patch("apps.paperless.auto.verbindung", return_value=None):
            fertiges_dokument_task("rechnung", r.pk)
        d = Ablagedokument.objects.get(titel__contains=r.nummer)
        self.assertEqual(d.dateiname, rechnung_dateiname(r))
