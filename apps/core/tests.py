from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.crud import _icon_fuer, _sortierbar, knopf
from apps.core.models import AuditLog, Rolle, Verein, Zugang, naechste_nummer
from apps.members.models import Mitglied


class MandantenTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.v1 = Verein.objects.create(name="Verein A", kuerzel="a")
        self.v2 = Verein.objects.create(name="Verein B", kuerzel="b")
        self.anna = User.objects.create_user("anna", password="pw-Test-12345")
        self.leser = User.objects.create_user("leser", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v1, user=self.anna, rolle=Rolle.objects.get(verein=self.v1, name="Vorstand"))
        Zugang.objects.create(verein=self.v1, user=self.leser, rolle=Rolle.objects.get(verein=self.v1, name="Lesebenutzer"))
        self.m1 = Mitglied.objects.create(verein=self.v1, vorname="Anton", nachname="Eins")
        self.m2 = Mitglied.objects.create(verein=self.v2, vorname="Berta", nachname="Zwei")

    def test_neuer_verein_bekommt_standarddaten(self):
        from apps.accounting.models import Buchungskategorie, Konto
        from apps.documents.models import Ordner, Vorlage
        from apps.members.models import Mitgliedsart
        self.assertTrue(Rolle.objects.filter(verein=self.v2, name="Kassenwart").exists())
        self.assertTrue(Mitgliedsart.objects.filter(verein=self.v2, name="Aktiv").exists())
        self.assertTrue(Vorlage.objects.filter(verein=self.v2, name="Einladung Mitgliederversammlung").exists())
        self.assertTrue(Ordner.objects.filter(verein=self.v2, name="Protokolle").exists())
        self.assertEqual(Konto.objects.filter(verein=self.v2).count(), 2)
        self.assertTrue(Buchungskategorie.objects.filter(verein=self.v2, name="Spenden").exists())

    def test_liste_zeigt_nur_eigenen_verein(self):
        self.client.login(username="anna", password="pw-Test-12345")
        r = self.client.get(reverse("mitglied_list"))
        self.assertContains(r, "Eins")
        self.assertNotContains(r, "Zwei")

    def test_liste_sortierbar_nach_spalte(self):
        Mitglied.objects.create(verein=self.v1, vorname="Zora", nachname="Adler")
        self.client.login(username="anna", password="pw-Test-12345")
        r = self.client.get(reverse("mitglied_list") + "?sort=nachname")
        self.assertLess(r.content.find(b"Adler"), r.content.find(b"Eins"))
        r = self.client.get(reverse("mitglied_list") + "?sort=-nachname")
        self.assertLess(r.content.find(b"Eins"), r.content.find(b"Adler"))

    def test_sortierbar_nur_bei_echten_modellfeldern(self):
        self.assertTrue(_sortierbar(Mitglied, "nachname"))
        self.assertFalse(_sortierbar(Mitglied, "__str__"))
        self.assertFalse(_sortierbar(Mitglied, "diesesfeldgibtesnicht"))

    def test_detail_eines_fremden_vereins_ist_404(self):
        self.client.login(username="anna", password="pw-Test-12345")
        self.assertEqual(self.client.get(reverse("mitglied_detail", args=[self.m1.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("mitglied_detail", args=[self.m2.pk])).status_code, 404)

    def test_detail_zeigt_many_to_many_feld(self):
        from apps.members.models import Abteilung
        a = Abteilung.objects.create(verein=self.v1, name="Löschzug 1")
        self.m1.abteilungen.add(a)
        self.client.login(username="anna", password="pw-Test-12345")
        r = self.client.get(reverse("mitglied_detail", args=[self.m1.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Löschzug 1")

    def test_rechte_werden_geprueft(self):
        self.client.login(username="leser", password="pw-Test-12345")
        self.assertEqual(self.client.get(reverse("mitglied_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("mitglied_add")).status_code, 403)
        self.assertEqual(self.client.get(reverse("auditlog_list")).status_code, 403)

    def test_anmeldung_erforderlich(self):
        r = self.client.get(reverse("mitglied_list"))
        self.assertEqual(r.status_code, 302)

    def test_nummern_je_verein(self):
        self.assertEqual(naechste_nummer(self.v1, "X"), 1)
        self.assertEqual(naechste_nummer(self.v1, "X"), 2)
        self.assertEqual(naechste_nummer(self.v2, "X"), 1)
        self.assertEqual(self.m1.mitgliedsnummer, 1)
        self.assertEqual(self.m2.mitgliedsnummer, 1)

    def test_aenderungen_werden_protokolliert(self):
        self.m1.ort = "Dillenburg"
        self.m1.save()
        self.assertTrue(AuditLog.objects.filter(verein=self.v1, aktion="angelegt", modell="Mitglied").exists())
        log = AuditLog.objects.filter(verein=self.v1, aktion="geaendert", modell="Mitglied").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.aenderungen["Ort"][1], "Dillenburg")

    def test_iban_wird_verschluesselt_gespeichert(self):
        from django.db import connection
        self.m1.iban = "DE89370400440532013000"
        self.m1.save()
        with connection.cursor() as c:
            c.execute("SELECT iban FROM members_mitglied WHERE id = %s", [self.m1.pk])
            roh = c.fetchone()[0]
        self.assertNotIn("DE89", roh)
        self.m1.refresh_from_db()
        self.assertEqual(self.m1.iban, "DE89370400440532013000")

    def test_logo_bleibt_beim_speichern_ohne_neue_datei_erhalten(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.anna.is_superuser = True  # "Verwaltung" (Vereinseinstellungen) hat regulär nur der Superadmin
        self.anna.save()
        self.client.login(username="anna", password="pw-Test-12345")
        logo = SimpleUploadedFile("logo.png", b"\x89PNG\r\n\x1a\n" + b"0" * 20, content_type="image/png")
        self.v1.logo = logo
        self.v1.save()
        self.assertTrue(self.v1.logo)
        daten = {"name": self.v1.name, "zahlungsziel_tage": 14, "uebungsleiter_freibetrag": "3300",
                "ehrenamts_freibetrag": "960", "akzentfarbe": "#1F4E79", "bescheid_art": "freistellung"}
        r = self.client.post(reverse("verein_einstellungen"), daten)
        self.assertEqual(r.status_code, 302)
        self.v1.refresh_from_db()
        self.assertTrue(self.v1.logo)

    def test_briefkopf_pdf_wird_erzeugt(self):
        from apps.core.pdf import brief_pdf
        self.v1.unterschrift_1 = "Max Mustermann, 1. Vorsitzender"
        self.v1.akzentfarbe = "#C0392B"
        pdf = brief_pdf(self.v1, ["Herr", "Max Mustermann", "Musterweg 1", "12345 Musterstadt"], "Testbrief")
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_ungueltige_akzentfarbe_faellt_auf_standard_zurueck(self):
        from apps.core.pdf import brief_pdf
        self.v1.akzentfarbe = "keine-farbe"
        pdf = brief_pdf(self.v1, ["Empfänger"], "Testbrief")
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_fusslinie_verwendet_eigene_akzentfarbe(self):
        from reportlab.lib import colors
        from apps.core.pdf import _akzentfarbe_fuss
        self.v1.akzentfarbe = "#EA580C"
        self.v1.akzentfarbe_fuss = "#005199"
        self.assertEqual(_akzentfarbe_fuss(self.v1), colors.HexColor("#005199"))

    def test_fusslinie_faellt_ohne_eigene_farbe_auf_hauptfarbe_zurueck(self):
        from reportlab.lib import colors
        from apps.core.pdf import _akzentfarbe_fuss
        self.v1.akzentfarbe = "#EA580C"
        self.v1.akzentfarbe_fuss = ""
        self.assertEqual(_akzentfarbe_fuss(self.v1), colors.HexColor("#EA580C"))


class OeffentlicheSeitenTests(TestCase):
    """Impressum und öffentliche Downloads: bewusst ohne Anmeldung erreichbar (Impressum ist Pflicht nach
    § 5 TMG), aber Downloads duerfen NIE ein Dokument ausliefern, das nicht explizit als oeffentlich markiert ist."""

    def setUp(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.documents.models import Ablagedokument
        self.Ablagedokument = Ablagedokument
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test", anschrift="Musterweg 1", plz="12345",
                                       ort="Musterstadt", email="verein@example.org",
                                       impressum_text="Vertretungsberechtigter Vorstand: Max Mustermann")
        self.oeffentlich = Ablagedokument.objects.create(
            verein=self.v, titel="Datenschutzerklärung", kategorie="datenschutz", oeffentlich=True,
            datei=SimpleUploadedFile("datenschutz.pdf", b"%PDF-1.4 Inhalt"))
        self.privat = Ablagedokument.objects.create(
            verein=self.v, titel="Vorstandsprotokoll", kategorie="protokoll", oeffentlich=False,
            datei=SimpleUploadedFile("protokoll.pdf", b"%PDF-1.4 Geheim"))

    def test_impressum_ohne_anmeldung_erreichbar(self):
        r = self.client.get(reverse("impressum", args=[self.v.kuerzel]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Test e.V.")
        self.assertContains(r, "Max Mustermann")

    def test_impressum_unbekannter_verein_ist_404(self):
        r = self.client.get(reverse("impressum", args=["gibt-es-nicht"]))
        self.assertEqual(r.status_code, 404)

    def test_downloads_zeigt_nur_oeffentliche_dokumente(self):
        r = self.client.get(reverse("oeffentliche_dokumente", args=[self.v.kuerzel]))
        self.assertContains(r, "Datenschutzerklärung")
        self.assertNotContains(r, "Vorstandsprotokoll")

    def test_download_oeffentliches_dokument_erlaubt(self):
        r = self.client.get(reverse("oeffentliches_dokument_download", args=[self.v.kuerzel, self.oeffentlich.pk]))
        self.assertEqual(r.status_code, 200)

    def test_download_privates_dokument_ist_404(self):
        """Sicherheitskritisch: ein nicht als oeffentlich markiertes Dokument darf ueber die oeffentliche
        Download-Route unter keinen Umstaenden ausgeliefert werden, auch mit korrekter PK."""
        r = self.client.get(reverse("oeffentliches_dokument_download", args=[self.v.kuerzel, self.privat.pk]))
        self.assertEqual(r.status_code, 404)

    def test_download_fremder_verein_ist_404(self):
        anderer = Verein.objects.create(name="Anderer Verein", kuerzel="anderer")
        r = self.client.get(reverse("oeffentliches_dokument_download", args=[anderer.kuerzel, self.oeffentlich.pk]))
        self.assertEqual(r.status_code, 404)

    def test_footer_verlinkt_impressum_bei_genau_einem_verein(self):
        r = self.client.get(reverse("login"))
        self.assertContains(r, reverse("impressum", args=[self.v.kuerzel]))
        self.assertContains(r, reverse("oeffentliche_dokumente", args=[self.v.kuerzel]))

    def test_footer_listet_mehrere_vereine_einzeln_auf(self):
        zweiter = Verein.objects.create(name="Zweiter Verein", kuerzel="zweiter")
        r = self.client.get(reverse("login"))
        self.assertContains(r, reverse("impressum", args=[self.v.kuerzel]))
        self.assertContains(r, reverse("impressum", args=[zweiter.kuerzel]))

    def test_verein_einstellungen_speichert_impressum(self):
        User = get_user_model()
        admin = User.objects.create_superuser("admin", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=admin,
                              rolle=Rolle.objects.get(verein=self.v, name="Superadministrator"))
        self.client.login(username="admin", password="pw-Test-12345")
        r = self.client.post(reverse("verein_einstellungen"), {
            "name": self.v.name, "impressum_text": "Neuer Impressumstext", "zahlungsziel_tage": 14,
            "uebungsleiter_freibetrag": "3300", "ehrenamts_freibetrag": "960", "akzentfarbe": "#1F4E79",
            "bescheid_art": "freistellung"})
        self.assertEqual(r.status_code, 302)
        self.v.refresh_from_db()
        self.assertEqual(self.v.impressum_text, "Neuer Impressumstext")


class MandantenfaehigkeitGesperrtTests(TestCase):
    """Mandantenfaehigkeit ist aktuell gesperrt: ueber /admin/ laesst sich kein zweiter Verein mehr anlegen,
    solange bereits einer existiert. Die zugrunde liegende Mandantentrennung bleibt unangetastet (siehe
    MandantenTests, die weiterhin mit mehreren Vereinen arbeiten, z. B. fuer bereits laengere bestehende
    Installationen oder interne Tests der Datentrennung)."""

    def setUp(self):
        User = get_user_model()
        self.superuser = User.objects.create_superuser("root", password="pw-Test-12345")
        self.client.login(username="root", password="pw-Test-12345")

    def test_admin_erlaubt_ersten_verein(self):
        from apps.core.admin import VereinAdmin
        self.assertTrue(VereinAdmin(Verein, None).has_add_permission(None))

    def test_admin_verbietet_zweiten_verein(self):
        Verein.objects.create(name="Verein A", kuerzel="a")
        from apps.core.admin import VereinAdmin
        self.assertFalse(VereinAdmin(Verein, None).has_add_permission(None))

    def test_add_formular_im_admin_ist_gesperrt(self):
        Verein.objects.create(name="Verein A", kuerzel="a")
        r = self.client.get(reverse("admin:core_verein_add"))
        self.assertEqual(r.status_code, 403)

    def test_add_formular_im_admin_ohne_bestehenden_verein_erlaubt(self):
        r = self.client.get(reverse("admin:core_verein_add"))
        self.assertEqual(r.status_code, 200)


class WeboberflaechenDesignTests(TestCase):
    """Die Akzentfarbe aus den Vereinseinstellungen wird auch in der Weboberfläche verwendet (Navigation,
    Schaltflächen) - je Verein einstellbar, mit automatisch berechneter, lesbarer Textfarbe."""

    def test_lesbare_textfarbe_bei_dunklem_hintergrund_ist_weiss(self):
        from apps.core.util import lesbare_textfarbe
        self.assertEqual(lesbare_textfarbe("#1F4E79"), "#fff")

    def test_lesbare_textfarbe_bei_hellem_hintergrund_ist_schwarz(self):
        from apps.core.util import lesbare_textfarbe
        self.assertEqual(lesbare_textfarbe("#FFEE00"), "#000")

    def test_lesbare_textfarbe_bei_ungueltigem_wert_stuerzt_nicht_ab(self):
        from apps.core.util import lesbare_textfarbe
        self.assertIn(lesbare_textfarbe("keine-farbe"), ("#000", "#fff"))
        self.assertIn(lesbare_textfarbe(""), ("#000", "#fff"))
        self.assertIn(lesbare_textfarbe(None), ("#000", "#fff"))

    def test_navigation_zeigt_eigene_akzentfarbe_und_icons(self):
        User = get_user_model()
        v = Verein.objects.create(name="Verein A", kuerzel="a", akzentfarbe="#EA580C")
        admin = User.objects.create_superuser("admin", password="pw-Test-12345")
        Zugang.objects.create(verein=v, user=admin, rolle=Rolle.objects.get(verein=v, name="Superadministrator"))
        self.client.login(username="admin", password="pw-Test-12345")
        r = self.client.get(reverse("dashboard"))
        self.assertContains(r, "#EA580C")
        self.assertContains(r, "bi-people")

    def test_login_seite_zeigt_akzentfarbe_des_einzigen_vereins(self):
        Verein.objects.create(name="Verein A", kuerzel="a", akzentfarbe="#EA580C")
        r = self.client.get(reverse("login"))
        self.assertContains(r, "#EA580C")

    def test_knopf_bekommt_automatisch_ein_passendes_icon(self):
        self.assertEqual(knopf("Löschen", "#")["icon"], "bi-trash")
        self.assertEqual(knopf("Import (Excel/CSV)", "#")["icon"], "bi-upload")
        self.assertEqual(knopf("Vollexport (Excel)", "#")["icon"], "bi-download")
        self.assertEqual(knopf("Stornieren", "#")["icon"], "bi-x-circle")
        self.assertEqual(knopf("Zur Veranstaltung", "#")["icon"], "bi-arrow-right-circle")

    def test_icon_fuer_kurzes_symbol_label_liefert_kein_icon(self):
        """Einzelne Symbol-Labels (✓/✗/⚠, z. B. bei der Inventur) sollen kein zusätzliches Icon davor bekommen -
        das wäre doppelt gemoppelt."""
        self.assertIsNone(_icon_fuer("✓"))
        self.assertIsNone(_icon_fuer("✗"))

    def test_unterseite_zeigt_icon_der_eigenen_nav_gruppe(self):
        User = get_user_model()
        v = Verein.objects.create(name="Verein A", kuerzel="a")
        admin = User.objects.create_superuser("admin", password="pw-Test-12345")
        Zugang.objects.create(verein=v, user=admin, rolle=Rolle.objects.get(verein=v, name="Superadministrator"))
        self.client.login(username="admin", password="pw-Test-12345")
        m = Mitglied.objects.create(verein=v, vorname="Anton", nachname="Eins")
        r = self.client.get(reverse("mitglied_detail", args=[m.pk]))
        self.assertContains(r, "bi-people")

    def test_mitglieder_und_inventar_import_liegen_unter_verwaltung(self):
        """Import laeuft in der Regel nur einmalig beim Einrichten des Vereins - deshalb ein Menuepunkt unter
        Verwaltung statt eines Buttons auf der laufend genutzten Liste."""
        User = get_user_model()
        v = Verein.objects.create(name="Verein A", kuerzel="a")
        admin = User.objects.create_superuser("admin", password="pw-Test-12345")
        Zugang.objects.create(verein=v, user=admin, rolle=Rolle.objects.get(verein=v, name="Superadministrator"))
        self.client.login(username="admin", password="pw-Test-12345")
        r = self.client.get(reverse("dashboard"))
        self.assertContains(r, reverse("mitglieder_import"))
        self.assertContains(r, reverse("gegenstand_import"))
        r = self.client.get(reverse("mitglied_list"))
        self.assertNotContains(r, "Import (Excel/CSV)")
        r = self.client.get(reverse("gegenstand_list"))
        self.assertNotContains(r, "Import (Excel/CSV)")


class FeuerixBrandingTests(TestCase):
    """Softwaremarke "Feuerix" (getrennt vom individuellen Vereinsnamen/-logo) - muss auch ohne Anmeldung
    sichtbar sein (Login-Seite), bevor ein Verein aktiv ist."""

    def test_produktname_auf_login_seite_ohne_anmeldung(self):
        r = self.client.get(reverse("login"))
        self.assertContains(r, "Feuerix")
        self.assertContains(r, "branding/icon.svg")

    def test_produktname_im_footer_bei_angemeldetem_verein(self):
        User = get_user_model()
        v = Verein.objects.create(name="Verein A", kuerzel="a")
        admin = User.objects.create_superuser("admin", password="pw-Test-12345")
        Zugang.objects.create(verein=v, user=admin, rolle=Rolle.objects.get(verein=v, name="Superadministrator"))
        self.client.login(username="admin", password="pw-Test-12345")
        r = self.client.get(reverse("dashboard"))
        self.assertContains(r, "Verein A")
        self.assertContains(r, "Feuerix")


class SprachauswahlTests(TestCase):
    """Englische Übersetzung mit Sprachauswahl (oben im Menü bzw. auf dem Anmeldefenster) - Standard bleibt
    Deutsch, nichts ändert sich für Benutzer, die nie umschalten."""

    def setUp(self):
        self.v = Verein.objects.create(name="Verein A", kuerzel="a")

    def test_login_seite_ist_standardmaessig_deutsch(self):
        r = self.client.get(reverse("login"))
        self.assertContains(r, "Anmeldung")
        self.assertContains(r, "Passwort")

    def test_login_seite_zeigt_cookie_hinweis(self):
        r = self.client.get(reverse("login"))
        self.assertContains(r, "technisch notwendige Cookies")
        self.assertContains(r, "cookie-hinweis")

    def test_sprachauswahl_schaltet_login_seite_auf_englisch(self):
        r = self.client.post(reverse("set_language"), {"language": "en", "next": reverse("login")})
        self.assertEqual(r.status_code, 302)
        r = self.client.get(reverse("login"))
        self.assertContains(r, "Sign in")
        self.assertNotContains(r, "Anmeldung")

    def test_sprachauswahl_schaltet_navigation_auf_englisch(self):
        User = get_user_model()
        admin = User.objects.create_superuser("admin", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=admin,
                              rolle=Rolle.objects.get(verein=self.v, name="Superadministrator"))
        self.client.login(username="admin", password="pw-Test-12345")
        self.client.post(reverse("set_language"), {"language": "en", "next": reverse("dashboard")})
        r = self.client.get(reverse("dashboard"))
        self.assertContains(r, 'lang="en"')
        self.assertContains(r, "Members")
        self.assertContains(r, "Log out")
        self.assertContains(r, "Overview")

    def test_ungueltige_sprache_wird_abgelehnt(self):
        r = self.client.post(reverse("set_language"), {"language": "fr", "next": reverse("login")})
        r2 = self.client.get(reverse("login"))
        self.assertContains(r2, "Anmeldung")

    def test_eigenstaendige_unterseiten_sind_ebenfalls_uebersetzt(self):
        """Regressionsschutz: Seiten außerhalb des generischen CRUD-Frameworks (z. B. Jubiläen, Auswertungen)
        wurden im ersten Übersetzungsdurchgang übersehen - genau das hatte der Nutzer gemeldet."""
        User = get_user_model()
        admin = User.objects.create_superuser("admin", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=admin,
                              rolle=Rolle.objects.get(verein=self.v, name="Superadministrator"))
        self.client.login(username="admin", password="pw-Test-12345")
        self.client.post(reverse("set_language"), {"language": "en", "next": reverse("jubilaeen")})
        r = self.client.get(reverse("jubilaeen"))
        self.assertContains(r, "Member")
        self.assertContains(r, "Joined")
        self.assertNotContains(r, "Mitglied<")
        r = self.client.get(reverse("auswertungen"))
        self.assertContains(r, "Membership trend")


class DetailSeitenLayoutTests(TestCase):
    """Detailseiten nutzen bei breiten Bildschirmen eine zweispaltige Sidebar-Ansicht (Felder links, Abschnitte
    rechts) statt einer einzigen langen Spalte - muss sowohl mit als auch ohne Abschnitte funktionieren."""

    def setUp(self):
        User = get_user_model()
        self.v = Verein.objects.create(name="Verein A", kuerzel="a")
        self.admin = User.objects.create_superuser("admin", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=self.admin,
                              rolle=Rolle.objects.get(verein=self.v, name="Superadministrator"))
        self.client.login(username="admin", password="pw-Test-12345")

    def test_seite_mit_abschnitten_zeigt_keinen_platzhalter(self):
        m = Mitglied.objects.create(verein=self.v, vorname="Anton", nachname="Eins")
        r = self.client.get(reverse("mitglied_detail", args=[m.pk]))
        self.assertContains(r, "felder-sidebar")
        self.assertContains(r, "col-xl-4")
        self.assertNotContains(r, "Keine weiteren Angaben.")

    def test_seite_ohne_abschnitte_zeigt_platzhalter(self):
        from apps.members.models import Familie
        fam = Familie.objects.create(verein=self.v, name="Testfamilie")
        r = self.client.get(reverse("familie_detail", args=[fam.pk]))
        self.assertContains(r, "Keine weiteren Angaben.")
