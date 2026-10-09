from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from datetime import date, timedelta

from apps.core.models import Rolle, Verein, Zugang
from apps.documents.platzhalter import kontext
from apps.members.models import Mitglied, Mitgliedsart

from .models import Anmeldung, Aufgabe, Veranstaltung, Wahlergebnis


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


class AufgabeOhneVeranstaltungTests(TestCase):
    """Aufgaben lassen sich auch unabhaengig von einer Veranstaltung/Sitzung anlegen - z. B. fuer
    allgemeine Vorstandsaufgaben ohne konkreten Termin."""

    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        User = get_user_model()
        self.admin = User.objects.create_superuser("admin", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=self.admin,
                              rolle=Rolle.objects.get(verein=self.v, name="Superadministrator"))
        self.client.login(username="admin", password="pw-Test-12345")

    def test_aufgabe_ohne_veranstaltung_anlegbar(self):
        r = self.client.post(reverse("aufgabe_add"), {"titel": "Vereinsheim-Schlüssel nachmachen lassen",
                                                       "status": "offen"})
        self.assertEqual(r.status_code, 302)
        a = Aufgabe.objects.get(verein=self.v, titel="Vereinsheim-Schlüssel nachmachen lassen")
        self.assertIsNone(a.veranstaltung_id)

    def test_aufgaben_liste_im_menue_verlinkt(self):
        r = self.client.get(reverse("dashboard"))
        self.assertContains(r, reverse("aufgabe_list"))


class AufgabenBenachrichtigungTests(TestCase):
    """Ueberfaellige Aufgaben (Faelligkeit in der Vergangenheit, nicht erledigt) loesen einmalig eine
    E-Mail an die/den Zustaendige(n) aus - kein taeglicher Spam bei wiederholtem Aufruf."""

    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        art = Mitgliedsart.objects.get(verein=self.v, name="Aktiv")
        self.m = Mitglied.objects.create(verein=self.v, vorname="Max", nachname="Muster", mitgliedsart=art,
                                         eintrittsdatum=date(2015, 1, 1), email="max@example.org")

    def test_ueberfaellige_aufgabe_wird_einmalig_gemailt(self):
        from .services import aufgaben_faellig_benachrichtigen
        a = Aufgabe.objects.create(verein=self.v, titel="Kassenbericht vorbereiten", zustaendig=self.m,
                                   faellig=date.today() - timedelta(days=1))
        n = aufgaben_faellig_benachrichtigen(self.v)
        self.assertEqual(n, 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Kassenbericht vorbereiten", mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to, ["max@example.org"])
        a.refresh_from_db()
        self.assertIsNotNone(a.benachrichtigt_am)
        # Zweiter Aufruf darf dieselbe Aufgabe nicht nochmal verschicken.
        n2 = aufgaben_faellig_benachrichtigen(self.v)
        self.assertEqual(n2, 0)
        self.assertEqual(len(mail.outbox), 1)

    def test_nicht_ueberfaellige_aufgabe_wird_nicht_gemailt(self):
        from .services import aufgaben_faellig_benachrichtigen
        Aufgabe.objects.create(verein=self.v, titel="Noch Zeit", zustaendig=self.m,
                               faellig=date.today() + timedelta(days=5))
        self.assertEqual(aufgaben_faellig_benachrichtigen(self.v), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_erledigte_aufgabe_wird_nicht_gemailt(self):
        from .services import aufgaben_faellig_benachrichtigen
        Aufgabe.objects.create(verein=self.v, titel="Erledigt", zustaendig=self.m, status="erledigt",
                               faellig=date.today() - timedelta(days=1))
        self.assertEqual(aufgaben_faellig_benachrichtigen(self.v), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_aufgabe_ohne_email_wird_uebersprungen(self):
        from .services import aufgaben_faellig_benachrichtigen
        self.m.email = ""
        self.m.save()
        Aufgabe.objects.create(verein=self.v, titel="Keine Mailadresse", zustaendig=self.m,
                               faellig=date.today() - timedelta(days=1))
        self.assertEqual(aufgaben_faellig_benachrichtigen(self.v), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_dashboard_stoesst_pruefung_an(self):
        User = get_user_model()
        admin = User.objects.create_superuser("admin", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=admin,
                              rolle=Rolle.objects.get(verein=self.v, name="Superadministrator"))
        self.client.login(username="admin", password="pw-Test-12345")
        Aufgabe.objects.create(verein=self.v, titel="Kassenbericht vorbereiten", zustaendig=self.m,
                               faellig=date.today() - timedelta(days=1))
        self.v.refresh_from_db()
        self.assertIsNone(self.v.aufgaben_geprueft_am)
        self.client.get(reverse("dashboard"))
        self.assertEqual(len(mail.outbox), 1)
        self.v.refresh_from_db()
        self.assertIsNotNone(self.v.aufgaben_geprueft_am)
        # Zweiter Seitenaufruf direkt danach loest die Pruefung nicht nochmal aus (zu kurzes Intervall).
        self.client.get(reverse("dashboard"))
        self.assertEqual(len(mail.outbox), 1)


class MeineAufgabenDashboardTests(TestCase):
    """Dem angemeldeten Benutzer (ueber sein verknuepftes Mitglied) werden die eigenen offenen Aufgaben auf
    der Startseite angezeigt - ueberfaellige optisch hervorgehoben."""

    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        art = Mitgliedsart.objects.get(verein=self.v, name="Aktiv")
        User = get_user_model()
        self.user = User.objects.create_user("max", password="pw-Test-12345")
        self.m = Mitglied.objects.create(verein=self.v, vorname="Max", nachname="Muster", mitgliedsart=art,
                                         eintrittsdatum=date(2015, 1, 1), benutzer=self.user)
        Zugang.objects.create(verein=self.v, user=self.user,
                              rolle=Rolle.objects.get(verein=self.v, name="Superadministrator"))
        self.client.login(username="max", password="pw-Test-12345")

    def test_eigene_offene_aufgabe_wird_angezeigt(self):
        Aufgabe.objects.create(verein=self.v, titel="Meine Aufgabe", zustaendig=self.m, status="offen")
        r = self.client.get(reverse("dashboard"))
        self.assertContains(r, "Meine Aufgabe")

    def test_erledigte_aufgabe_wird_nicht_angezeigt(self):
        Aufgabe.objects.create(verein=self.v, titel="Erledigte Aufgabe", zustaendig=self.m, status="erledigt")
        r = self.client.get(reverse("dashboard"))
        self.assertNotContains(r, "Erledigte Aufgabe")

    def test_fremde_aufgabe_wird_nicht_angezeigt(self):
        anderer = Mitglied.objects.create(verein=self.v, vorname="Erika", nachname="Musterfrau",
                                          mitgliedsart=Mitgliedsart.objects.get(verein=self.v, name="Aktiv"),
                                          eintrittsdatum=date(2015, 1, 1))
        Aufgabe.objects.create(verein=self.v, titel="Fremde Aufgabe", zustaendig=anderer, status="offen")
        r = self.client.get(reverse("dashboard"))
        self.assertNotContains(r, "Fremde Aufgabe")


class AufgabeFaelligkeitsStufeTests(TestCase):
    """Rot: unter 2 Tage (inkl. ueberfaellig), gelb: 2 bis unter 10 Tage, gruen: ab 10 Tagen."""

    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")

    def test_ueberfaellig_ist_rot(self):
        a = Aufgabe.objects.create(verein=self.v, titel="X", faellig=date.today() - timedelta(days=1))
        self.assertEqual(a.faelligkeits_stufe, "rot")

    def test_ein_tag_ist_rot(self):
        a = Aufgabe.objects.create(verein=self.v, titel="X", faellig=date.today() + timedelta(days=1))
        self.assertEqual(a.faelligkeits_stufe, "rot")

    def test_zwei_tage_ist_gelb(self):
        a = Aufgabe.objects.create(verein=self.v, titel="X", faellig=date.today() + timedelta(days=2))
        self.assertEqual(a.faelligkeits_stufe, "gelb")

    def test_neun_tage_ist_gelb(self):
        a = Aufgabe.objects.create(verein=self.v, titel="X", faellig=date.today() + timedelta(days=9))
        self.assertEqual(a.faelligkeits_stufe, "gelb")

    def test_zehn_tage_ist_gruen(self):
        a = Aufgabe.objects.create(verein=self.v, titel="X", faellig=date.today() + timedelta(days=10))
        self.assertEqual(a.faelligkeits_stufe, "gruen")

    def test_ohne_faelligkeit_ist_none(self):
        a = Aufgabe.objects.create(verein=self.v, titel="X")
        self.assertIsNone(a.faelligkeits_stufe)

    def test_erledigt_ist_none(self):
        a = Aufgabe.objects.create(verein=self.v, titel="X", faellig=date.today() - timedelta(days=5),
                                   status="erledigt", ergebnis="Fertig.")
        self.assertIsNone(a.faelligkeits_stufe)


class MeineAufgabenKachelfarbeTests(TestCase):
    """Die Kachel "Meine Aufgaben" eskaliert erst auf Gelb, sobald mindestens zwei Aufgaben mindestens gelb
    sind (rot zaehlt dabei mit), und auf Rot erst ab mindestens zwei roten Aufgaben - eine einzelne knapp
    fällige Aufgabe allein soll die ganze Kachel nicht grell machen."""

    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        art = Mitgliedsart.objects.get(verein=self.v, name="Aktiv")
        User = get_user_model()
        self.user = User.objects.create_user("max", password="pw-Test-12345")
        self.m = Mitglied.objects.create(verein=self.v, vorname="Max", nachname="Muster", mitgliedsart=art,
                                         eintrittsdatum=date(2015, 1, 1), benutzer=self.user)
        Zugang.objects.create(verein=self.v, user=self.user,
                              rolle=Rolle.objects.get(verein=self.v, name="Superadministrator"))
        self.client.login(username="max", password="pw-Test-12345")

    def _aufgabe(self, titel, tage):
        return Aufgabe.objects.create(verein=self.v, titel=titel, zustaendig=self.m,
                                      faellig=date.today() + timedelta(days=tage))

    def test_ohne_dringende_aufgaben_ist_unauffaellig(self):
        self._aufgabe("Weit weg", 30)
        r = self.client.get(reverse("dashboard"))
        self.assertNotContains(r, "border-danger")
        self.assertNotContains(r, "border-warning")

    def test_eine_einzelne_rote_aufgabe_eskaliert_nicht(self):
        self._aufgabe("Knapp dran", 1)
        r = self.client.get(reverse("dashboard"))
        self.assertNotContains(r, "border-danger")

    def test_zwei_rote_aufgaben_eskalieren_auf_rot(self):
        self._aufgabe("Knapp dran 1", 1)
        self._aufgabe("Knapp dran 2", -1)
        r = self.client.get(reverse("dashboard"))
        self.assertContains(r, "border-danger")

    def test_zwei_gelbe_aufgaben_eskalieren_auf_gelb(self):
        self._aufgabe("Bald faellig 1", 3)
        self._aufgabe("Bald faellig 2", 5)
        r = self.client.get(reverse("dashboard"))
        self.assertContains(r, "border-warning")

    def test_eine_rote_und_eine_gelbe_aufgabe_eskalieren_auf_gelb(self):
        self._aufgabe("Knapp dran", 1)
        self._aufgabe("Bald faellig", 5)
        r = self.client.get(reverse("dashboard"))
        self.assertNotContains(r, "border-danger")
        self.assertContains(r, "border-warning")

    def test_zeilen_sind_einzeln_eingefaerbt_auch_ohne_eskalation(self):
        self._aufgabe("Knapp dran", 1)
        self._aufgabe("Weit weg", 30)
        r = self.client.get(reverse("dashboard"))
        self.assertNotContains(r, "border-danger")  # Kachel bleibt unauffaellig (nur 1 rote Aufgabe)
        self.assertContains(r, "list-group-item-danger")  # die Zeile selbst ist trotzdem rot markiert


class AufgabeErgebnisPflichtTests(TestCase):
    """Beim Abschliessen (Status 'Erledigt') muss ein Ergebnis eingetragen sein - wie bei einem Ticketsystem
    ein Abschlusskommentar."""

    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        User = get_user_model()
        self.admin = User.objects.create_superuser("admin", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=self.admin,
                              rolle=Rolle.objects.get(verein=self.v, name="Superadministrator"))
        self.client.login(username="admin", password="pw-Test-12345")
        self.a = Aufgabe.objects.create(verein=self.v, titel="Flyer entwerfen", status="offen")

    def test_erledigt_ohne_ergebnis_wird_abgelehnt(self):
        r = self.client.post(reverse("aufgabe_edit", args=[self.a.pk]), {"titel": self.a.titel,
                                                                         "status": "erledigt"})
        self.assertEqual(r.status_code, 200)
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, "offen")

    def test_erledigt_mit_ergebnis_wird_gespeichert(self):
        r = self.client.post(reverse("aufgabe_edit", args=[self.a.pk]), {"titel": self.a.titel,
                                                                         "status": "erledigt",
                                                                         "ergebnis": "Flyer ist fertig und gedruckt."})
        self.assertEqual(r.status_code, 302)
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, "erledigt")
        self.assertEqual(self.a.ergebnis, "Flyer ist fertig und gedruckt.")

    def test_status_offen_braucht_kein_ergebnis(self):
        r = self.client.post(reverse("aufgabe_edit", args=[self.a.pk]), {"titel": self.a.titel,
                                                                         "status": "arbeit"})
        self.assertEqual(r.status_code, 302)
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, "arbeit")


class AufgabeErledigenKnopfTests(TestCase):
    """Schnell-Erledigen-Knopf auf der Aufgaben-Detailseite - Eingabefeld fuer das Pflicht-Ergebnis statt
    Umweg ueber das Bearbeiten-Formular."""

    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        User = get_user_model()
        self.admin = User.objects.create_superuser("admin", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=self.admin,
                              rolle=Rolle.objects.get(verein=self.v, name="Superadministrator"))
        self.client.login(username="admin", password="pw-Test-12345")
        self.a = Aufgabe.objects.create(verein=self.v, titel="Flyer entwerfen", status="offen")

    def test_formular_erscheint_nur_wenn_nicht_bereits_erledigt(self):
        r = self.client.get(reverse("aufgabe_detail", args=[self.a.pk]))
        self.assertContains(r, "Als erledigt markieren")
        self.a.status, self.a.ergebnis = "erledigt", "Fertig."
        self.a.save()
        r = self.client.get(reverse("aufgabe_detail", args=[self.a.pk]))
        self.assertNotContains(r, "Als erledigt markieren")

    def test_ohne_ergebnis_wird_abgelehnt(self):
        r = self.client.post(reverse("aufgabe_erledigen", args=[self.a.pk]), {"ergebnis": ""}, follow=True)
        self.assertContains(r, "Bitte ein Ergebnis eintragen.")
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, "offen")

    def test_mit_ergebnis_wird_erledigt(self):
        r = self.client.post(reverse("aufgabe_erledigen", args=[self.a.pk]),
                             {"ergebnis": "Flyer ist fertig und gedruckt."})
        self.assertRedirects(r, reverse("aufgabe_detail", args=[self.a.pk]))
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, "erledigt")
        self.assertEqual(self.a.ergebnis, "Flyer ist fertig und gedruckt.")

    def test_ohne_schreibrecht_verweigert(self):
        leser = get_user_model().objects.create_user("leser", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=leser,
                              rolle=Rolle.objects.create(verein=self.v, name="Leser", rechte=["veranstaltungen.view"]))
        self.client.login(username="leser", password="pw-Test-12345")
        r = self.client.post(reverse("aufgabe_erledigen", args=[self.a.pk]), {"ergebnis": "Fertig."})
        self.assertEqual(r.status_code, 403)
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, "offen")


class AufgabenNotizTests(TestCase):
    """Zwischennotizen zu einer Aufgabe - wie ein Ticket-Verlauf, mit Zeitpunkt und Benutzer."""

    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        User = get_user_model()
        self.admin = User.objects.create_superuser("admin", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=self.admin,
                              rolle=Rolle.objects.get(verein=self.v, name="Superadministrator"))
        self.client.login(username="admin", password="pw-Test-12345")
        self.a = Aufgabe.objects.create(verein=self.v, titel="Flyer entwerfen", status="offen")

    def test_notiz_hinzufuegen_und_auf_der_aufgabenseite_sichtbar(self):
        r = self.client.post(reverse("aufgabenotiz_add"), {"aufgabe": self.a.pk,
                                                             "text": "Entwurf an die Druckerei geschickt."})
        self.assertEqual(r.status_code, 302)
        notiz = self.a.notizen.get()
        self.assertEqual(notiz.text, "Entwurf an die Druckerei geschickt.")
        self.assertEqual(notiz.erstellt_von, "admin")
        r = self.client.get(reverse("aufgabe_detail", args=[self.a.pk]))
        self.assertContains(r, "Entwurf an die Druckerei geschickt.")
        self.assertContains(r, "admin")

    def test_mehrere_notizen_in_zeitlicher_reihenfolge(self):
        self.client.post(reverse("aufgabenotiz_add"), {"aufgabe": self.a.pk, "text": "Erste Notiz"})
        self.client.post(reverse("aufgabenotiz_add"), {"aufgabe": self.a.pk, "text": "Zweite Notiz"})
        texte = list(self.a.notizen.values_list("text", flat=True))
        self.assertEqual(texte, ["Erste Notiz", "Zweite Notiz"])

    def test_notiz_nicht_nachtraeglich_bearbeitbar(self):
        notiz = self.a.notizen.create(verein=self.v, text="Erste Notiz", erstellt_von="admin")
        with self.assertRaises(NoReverseMatch):
            reverse("aufgabenotiz_edit", args=[notiz.pk])


class AufgabeZustaendigAdministratorTests(TestCase):
    """'Zuständig' kann neben einem Mitglied auch ein Administrator (Benutzer mit Zugang, z. B. ohne eigene
    Mitgliedschaft - externe Kassenprüfung o. ä.) sein."""

    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        User = get_user_model()
        self.admin = User.objects.create_superuser("admin", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=self.admin,
                              rolle=Rolle.objects.get(verein=self.v, name="Superadministrator"))
        self.pruefer = User.objects.create_user("pruefer", password="pw-Test-12345", first_name="Erika",
                                                last_name="Pruefer", email="pruefer@example.org")
        Zugang.objects.create(verein=self.v, user=self.pruefer,
                              rolle=Rolle.objects.get(verein=self.v, name="Superadministrator"))
        self.client.login(username="admin", password="pw-Test-12345")

    def test_administrator_erscheint_in_der_auswahl(self):
        r = self.client.get(reverse("aufgabe_add"))
        self.assertContains(r, "pruefer")

    def test_aufgabe_administrator_zuweisbar(self):
        r = self.client.post(reverse("aufgabe_add"), {"titel": "Kassenprüfung", "status": "offen",
                                                       "zustaendig_benutzer": self.pruefer.pk})
        self.assertEqual(r.status_code, 302)
        a = Aufgabe.objects.get(titel="Kassenprüfung")
        self.assertEqual(a.zustaendig_benutzer_id, self.pruefer.pk)
        self.assertIsNone(a.zustaendig_id)
        self.assertEqual(a.wer_zustaendig, "Erika Pruefer")

    def test_nicht_mitglied_und_administrator_gleichzeitig(self):
        art = Mitgliedsart.objects.get(verein=self.v, name="Aktiv")
        m = Mitglied.objects.create(verein=self.v, vorname="Max", nachname="Muster", mitgliedsart=art,
                                    eintrittsdatum=date(2015, 1, 1))
        r = self.client.post(reverse("aufgabe_add"), {"titel": "Doppelt", "status": "offen",
                                                       "zustaendig": m.pk, "zustaendig_benutzer": self.pruefer.pk})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Aufgabe.objects.filter(titel="Doppelt").exists())

    def test_benutzer_ohne_zugang_zu_diesem_verein_nicht_waehlbar(self):
        User = get_user_model()
        anderer_verein = Verein.objects.create(name="Anderer e.V.", kuerzel="anderer")
        fremder = User.objects.create_user("fremder", password="pw-Test-12345")
        Zugang.objects.create(verein=anderer_verein, user=fremder,
                              rolle=Rolle.objects.get(verein=anderer_verein, name="Superadministrator"))
        self.client.post(reverse("verein_waehlen"), {"verein": self.v.pk})  # Kontext explizit auf self.v fixieren
        r = self.client.get(reverse("aufgabe_add"))
        self.assertNotContains(r, "fremder")

    def test_ueberfaellige_aufgabe_fuer_administrator_wird_gemailt(self):
        from django.core import mail
        from .services import aufgaben_faellig_benachrichtigen
        Aufgabe.objects.create(verein=self.v, titel="Kassenprüfung", zustaendig_benutzer=self.pruefer,
                               faellig=date.today() - timedelta(days=1))
        n = aufgaben_faellig_benachrichtigen(self.v)
        self.assertEqual(n, 1)
        self.assertEqual(mail.outbox[0].to, ["pruefer@example.org"])

    def test_meine_aufgaben_zeigt_aufgaben_des_administrators_ohne_mitgliedschaft(self):
        Aufgabe.objects.create(verein=self.v, titel="Kassenprüfung", zustaendig_benutzer=self.pruefer,
                               status="offen")
        self.client.logout()
        self.client.login(username="pruefer", password="pw-Test-12345")
        r = self.client.get(reverse("dashboard"))
        self.assertContains(r, "Kassenprüfung")


class AufgabenListeTests(TestCase):
    """Die Aufgaben-Liste sortiert standardmaessig nach der Aufgabe selbst (nicht nach der oft leeren
    Veranstaltung) und markiert bald faellige/ueberfaellige Zeilen farblich - ohne Gruen fuer unkritische."""

    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        User = get_user_model()
        self.admin = User.objects.create_superuser("admin", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=self.admin,
                              rolle=Rolle.objects.get(verein=self.v, name="Superadministrator"))
        self.client.login(username="admin", password="pw-Test-12345")

    def test_liste_standardmaessig_alphabetisch_nach_aufgabe_sortiert(self):
        Aufgabe.objects.create(verein=self.v, titel="Zebra-Aufgabe")
        Aufgabe.objects.create(verein=self.v, titel="Apfel-Aufgabe")
        Aufgabe.objects.create(verein=self.v, titel="Mango-Aufgabe")
        r = self.client.get(reverse("aufgabe_list"))
        inhalt = r.content.decode()
        self.assertLess(inhalt.index("Apfel-Aufgabe"), inhalt.index("Mango-Aufgabe"))
        self.assertLess(inhalt.index("Mango-Aufgabe"), inhalt.index("Zebra-Aufgabe"))

    def test_ueberfaellige_zeile_ist_rot(self):
        Aufgabe.objects.create(verein=self.v, titel="Zu spaet", faellig=date.today() - timedelta(days=1))
        r = self.client.get(reverse("aufgabe_list"))
        self.assertContains(r, "table-danger")
        self.assertNotContains(r, "table-warning")

    def test_bald_faellige_zeile_ist_gelb(self):
        Aufgabe.objects.create(verein=self.v, titel="Bald faellig", faellig=date.today() + timedelta(days=5))
        r = self.client.get(reverse("aufgabe_list"))
        self.assertContains(r, "table-warning")
        self.assertNotContains(r, "table-danger")

    def test_weit_entfernte_faelligkeit_ohne_markierung(self):
        Aufgabe.objects.create(verein=self.v, titel="Viel Zeit", faellig=date.today() + timedelta(days=30))
        r = self.client.get(reverse("aufgabe_list"))
        self.assertNotContains(r, "table-danger")
        self.assertNotContains(r, "table-warning")
