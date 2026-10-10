from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Rolle, Verein, Zugang
from apps.documents.models import Ablagedokument, Vorlage
from apps.documents.platzhalter import PLATZHALTER, ersetzen, kontext
from apps.documents.services import standardvorlagen_anlegen
from apps.documents.vorlagen_defaults import STANDARDVORLAGEN
from apps.events.models import Tagesordnungspunkt, Veranstaltung
from apps.members.models import Mitglied
from apps.openslides.models import OpenSlidesVerbindung
from apps.paperless.models import PaperlessVerbindung

PW = "pw-Test-12345"


class AnbindungenBasis(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        User = get_user_model()
        self.admin = User.objects.create_superuser("admin", password=PW)
        Zugang.objects.create(verein=self.v, user=self.admin, rolle=Rolle.objects.get(verein=self.v,
                                                                                       name="Superadministrator"))
        self.client.login(username="admin", password=PW)
        self.ver = Veranstaltung.objects.create(verein=self.v, titel="MV", beginn=timezone.now(),
                                                openslides_meeting_id=5)
        self.m = Mitglied.objects.create(verein=self.v, vorname="Erika", nachname="Muster", mitgliedsnummer=7,
                                         openslides_user_id=42, openslides_username="erika.muster")

    def os_anbinden(self, aktiv=True):
        return OpenSlidesVerbindung.objects.create(verein=self.v, url="https://os.example.org", benutzername="s",
                                                   passwort="p", aktiv=aktiv)

    def pl_anbinden(self, aktiv=True):
        return PaperlessVerbindung.objects.create(verein=self.v, url="https://pl.example.org", api_token="t",
                                                  aktiv=aktiv)


class OpenSlidesSichtbarkeitTests(AnbindungenBasis):
    def test_veranstaltung_ohne_anbindung_keine_openslides_elemente(self):
        r = self.client.get(reverse("veranstaltung_detail", args=[self.ver.pk]))
        self.assertNotContains(r, "OpenSlides")

    def test_veranstaltung_mit_anbindung_zeigt_knoepfe_und_hinweis(self):
        self.os_anbinden()
        r = self.client.get(reverse("veranstaltung_detail", args=[self.ver.pk]))
        self.assertContains(r, "Tagesordnung nach OpenSlides übertragen")
        self.assertContains(r, "OpenSlides-Versammlung Nr. 5 ist verknüpft")

    def test_inaktive_verbindung_zaehlt_als_nicht_angebunden(self):
        self.os_anbinden(aktiv=False)
        r = self.client.get(reverse("veranstaltung_detail", args=[self.ver.pk]))
        self.assertNotContains(r, "OpenSlides")

    def test_tagesordnung_spalte_nur_mit_anbindung(self):
        Tagesordnungspunkt.objects.create(verein=self.v, veranstaltung=self.ver, position=1, titel="Begrüßung",
                                          openslides_topic_id=9)
        self.assertNotContains(self.client.get(reverse("veranstaltung_detail", args=[self.ver.pk])),
                               "OpenSlides-Themen-ID")
        self.os_anbinden()
        self.assertContains(self.client.get(reverse("veranstaltung_detail", args=[self.ver.pk])),
                            "OpenSlides-Themen-ID")

    def test_mitglied_detail_zeigt_openslides_konto_nur_mit_anbindung(self):
        url = reverse("mitglied_detail", args=[self.m.pk])
        r = self.client.get(url)
        self.assertNotContains(r, "OpenSlides")
        self.assertNotContains(r, "erika.muster")
        self.os_anbinden()
        r = self.client.get(url)
        self.assertContains(r, "OpenSlides-Konto-ID")
        self.assertContains(r, "erika.muster")

    def test_tags_liste_spalte_openslides_gruppe(self):
        self.assertNotContains(self.client.get(reverse("mitgliedtag_list")), "OpenSlides-Gruppe")
        self.os_anbinden()
        self.assertContains(self.client.get(reverse("mitgliedtag_list")), "OpenSlides-Gruppe")

    def test_tag_formular_ohne_anbindung_ohne_gruppenfelder(self):
        # (die Rechte-Matrix des Formulars listet bewusst alle Rechte-Module, daher nur die Gruppenfelder pruefen)
        r = self.client.get(reverse("mitgliedtag_add"))
        self.assertNotContains(r, 'name="openslides_gruppe"')
        self.assertNotContains(r, 'name="paperless_gruppe"')
        self.assertNotContains(r, 'name="paperless_nur_lesen"')
        self.os_anbinden()
        self.pl_anbinden()
        r = self.client.get(reverse("mitgliedtag_add"))
        self.assertContains(r, 'name="openslides_gruppe"')
        self.assertContains(r, 'name="paperless_gruppe"')

    def test_platzhalter_hilfe(self):
        r = self.client.get(reverse("platzhalter_hilfe"))
        for schluessel in ("openslides_url", "wahlergebnisse", "abstimmungen", "anwesenheit"):
            self.assertNotContains(r, "&#123;" + schluessel + "&#125;")
        self.assertContains(r, "&#123;veranstaltung&#125;")
        self.os_anbinden()
        r = self.client.get(reverse("platzhalter_hilfe"))
        for schluessel in ("openslides_url", "wahlergebnisse", "abstimmungen", "anwesenheit"):
            self.assertContains(r, "&#123;" + schluessel + "&#125;")

    def test_einstellungsseite_bleibt_immer_erreichbar(self):
        self.assertEqual(self.client.get(reverse("openslides_einstellungen")).status_code, 200)
        self.assertEqual(self.client.get(reverse("paperless_einstellungen")).status_code, 200)


class VorlagenOhneOpenSlidesTests(AnbindungenBasis):
    def test_zugangsdaten_vorlage_nur_mit_anbindung(self):
        name = "Zugangsdaten OpenSlides (Mitgliederversammlung online)"
        self.assertFalse(Vorlage.objects.filter(verein=self.v, name=name).exists())
        self.os_anbinden()
        standardvorlagen_anlegen(self.v)
        self.assertTrue(Vorlage.objects.filter(verein=self.v, name=name).exists())

    def test_standardprotokoll_erwaehnt_openslides_nirgends(self):
        protokoll = next(d for d in STANDARDVORLAGEN if d["name"] == "Protokoll Mitgliederversammlung")
        ausgefuellt = ersetzen(protokoll["text"], kontext(self.v, veranstaltung=self.ver))
        self.assertNotIn("OpenSlides", ausgefuellt)
        self.assertNotIn("keine ", ausgefuellt.split("Tagesordnung:")[0])
        for ueberschrift in ("Anwesenheitsliste", "Abstimmungen", "Wahlergebnisse"):   # leer -> samt Ueberschrift weg
            self.assertNotIn(ueberschrift, ausgefuellt)

    def test_platzhalterliste_bleibt_vollstaendig_im_code(self):
        # nur die Anzeige wird gefiltert, nicht PLATZHALTER selbst
        namen = {n for _t, eintraege in PLATZHALTER for n, _b in eintraege}
        self.assertTrue({"openslides_url", "anwesenheit", "abstimmungen"} <= namen)


class PaperlessSichtbarkeitTests(AnbindungenBasis):
    def setUp(self):
        super().setUp()
        self.d = Ablagedokument.objects.create(verein=self.v, titel="Satzung", kategorie="sonstiges",
                                               datei="x/y.pdf", tags="Satzung, 2026",
                                               paperless_status="uebergeben")

    def test_ablage_liste_ohne_anbindung_ohne_paperless_spalten(self):
        r = self.client.get(reverse("ablagedokument_list"))
        self.assertNotContains(r, "Paperless")
        self.assertNotContains(r, ">Tags<")

    def test_ablage_liste_mit_anbindung(self):
        self.pl_anbinden()
        r = self.client.get(reverse("ablagedokument_list"))
        self.assertContains(r, "Paperless")
        self.assertContains(r, "Tags")

    def test_ablage_formular_ohne_anbindung_ohne_paperless_felder(self):
        r = self.client.get(reverse("ablagedokument_add"))
        self.assertNotContains(r, "Paperless")
        self.assertNotContains(r, 'name="tags"')
        self.assertNotContains(r, 'name="dokumenttyp"')
        self.pl_anbinden()
        r = self.client.get(reverse("ablagedokument_add"))
        self.assertContains(r, 'name="tags"')
        self.assertContains(r, 'name="dokumenttyp"')

    def test_ablage_detail_ohne_anbindung_ohne_paperless_felder(self):
        url = reverse("ablagedokument_detail", args=[self.d.pk])
        self.assertNotContains(self.client.get(url), "Paperless")
        self.pl_anbinden()
        self.assertContains(self.client.get(url), "Paperless-Hinweis")

    def test_anlegen_ohne_anbindung_funktioniert_weiter(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        r = self.client.post(reverse("ablagedokument_add"), {
            "titel": "Neu", "kategorie": "sonstiges", "datum": "2026-10-10",
            "datei": SimpleUploadedFile("a.pdf", b"%PDF-1.4 x")})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Ablagedokument.objects.filter(titel="Neu").exists())

    def test_sammelversand_knopf_nur_mit_anbindung(self):
        self.assertNotContains(self.client.get(reverse("ablagedokument_list")), "Sammelversand")
        self.pl_anbinden()
        self.assertContains(self.client.get(reverse("ablagedokument_list")), "Sammelversand")
