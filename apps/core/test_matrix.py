"""Berechtigungsmatrix nach der Datenschutzordnung (Manderbach e.V., Stand 09/2026)."""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core import matrix as mx
from apps.core.models import Rolle, Verein, Zugang
from apps.core.rechte import AKTIONEN, MODULE, neue_module_ableiten
from apps.members.models import Mitglied, MitgliedTag

# Originaltabelle der Berechtigungsmatrix (02_Berechtigungsmatrix.docx): 1.V, 2.V, KW, stv.KW, SF, stv.SF
DSO_TABELLE = {
    "stamm": "V V B B V B", "geburt": "L L - - V B", "beitrag": "L L V V - -", "bank": "- - V V - -",
    "zahlung": "L L V V - -", "veranstaltung": "V V L L V B", "teilnehmer": "L L - - V B",
    "komm": "V V L L V B", "rundschreiben": "V V - - V B", "software": "V V V V V B",
    "datenschutz": "V V L L B B", "verletzung": "V V L L L L", "loeschung": "V V V V B B",
}
FUNKTIONEN = ["1. Vorsitzender", "2. Vorsitzender", "Kassenwart", "Stellv. Kassenwart", "Schriftführer",
              "Stellv. Schriftführer"]


def rolle_von(verein, funktion):
    return Rolle.objects.get(verein=verein, name=funktion + mx.DSO_SUFFIX)


class Basis(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")

    def benutzer(self, name, rolle):
        u = get_user_model().objects.create_user(name, password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=u, rolle=rolle)
        return u


class DsoTabelleTests(Basis):
    def test_matrix_entspricht_der_datenschutzordnung(self):
        for bereich, zeile in DSO_TABELLE.items():
            for funktion, stufe in zip(FUNKTIONEN, zeile.split()):
                self.assertEqual(mx.DSO_ROLLEN[funktion + mx.DSO_SUFFIX][bereich], stufe, f"{bereich}/{funktion}")

    def test_neuer_verein_bekommt_sechs_rollen_und_tags(self):
        self.assertEqual(Rolle.objects.filter(verein=self.v, name__endswith=mx.DSO_SUFFIX).count(), 6)
        tags = MitgliedTag.objects.filter(verein=self.v, rolle__isnull=False)
        self.assertEqual(sorted(tags.values_list("name", flat=True)), sorted(FUNKTIONEN + [mx.ADMINISTRATOR]))
        self.assertEqual(mx.dso_anlegen(self.v), (0, 0))   # idempotent

    def test_administrator_hat_volle_rechte_und_zaehlt_nicht_als_pflichtfunktion(self):
        rolle = Rolle.objects.get(verein=self.v, name=mx.ADMINISTRATOR, ist_superadmin=False)
        self.assertTrue(all(v == "V" for v in rolle.matrix.values()))
        self.assertNotIn("Administrator ist nicht besetzt", " ".join(mx.dso_pruefung(self.v)))

    def test_stellvertreter_koennen_die_erstbesetzung_vertreten(self):
        # § 7: stv. Kassenwart = Kassenwart in allen Kassen-Bereichen; stv. Schriftführer bearbeitet die Schriftführung
        self.assertEqual(mx.DSO_ROLLEN["Kassenwart (DSO)"]["bank"], mx.DSO_ROLLEN["Stellv. Kassenwart (DSO)"]["bank"])
        kw = set(rolle_von(self.v, "Kassenwart").rechte)
        stv = set(rolle_von(self.v, "Stellv. Kassenwart").rechte)
        self.assertEqual(kw, stv)
        self.assertLessEqual({"schriftverkehr.change", "veranstaltungen.change"} - {"x"},
                             set(rolle_von(self.v, "Stellv. Schriftführer").rechte))

    def test_bankdaten_nur_kassenwart_und_stellvertreter(self):
        for f in FUNKTIONEN:
            hat = "bankdaten.view" in rolle_von(self.v, f).rechte
            self.assertEqual(hat, f in ("Kassenwart", "Stellv. Kassenwart"), f)

    def test_geburtsdatum_nicht_fuer_kassenwart_nur_lesen_fuer_vorsitz(self):
        self.assertNotIn("geburtsdatum.view", rolle_von(self.v, "Kassenwart").rechte)
        vors = rolle_von(self.v, "1. Vorsitzender").rechte
        self.assertIn("geburtsdatum.view", vors)
        self.assertNotIn("geburtsdatum.change", vors)
        self.assertIn("geburtsdatum.change", rolle_von(self.v, "Schriftführer").rechte)

    def test_loeschen_nur_ueber_die_loeschzeile(self):
        # Kassenwart: Stammdaten nur B, Löschung V -> darf Mitglieder löschen
        self.assertIn("mitglieder.delete", rolle_von(self.v, "Kassenwart").rechte)
        # Schriftführer: Stammdaten V, Löschung B -> darf NICHT löschen
        sf = rolle_von(self.v, "Schriftführer").rechte
        self.assertNotIn("mitglieder.delete", sf)
        self.assertIn("mitglieder.change", sf)
        # Vorsitzende dürfen Beitragsdaten nur lesen, aber (Löschung V) löschen ... nur mit Anzeigerecht
        vors = rolle_von(self.v, "1. Vorsitzender").rechte
        self.assertIn("beitraege.view", vors)
        self.assertNotIn("beitraege.change", vors)
        self.assertIn("beitraege.delete", vors)
        self.assertNotIn("bankdaten.delete", vors)   # ohne Anzeigerecht kein Löschen

    def test_kein_zugriff_wo_die_matrix_keinen_erlaubt(self):
        sf = rolle_von(self.v, "Schriftführer").rechte
        for modul in ("beitraege", "rechnungen", "zahlungen", "bank", "kassenbuch", "spenden", "bankdaten"):
            self.assertFalse([r for r in sf if r.startswith(modul + ".")], modul)
        kw = rolle_von(self.v, "Kassenwart").rechte
        for modul in ("rundschreiben", "teilnehmer", "geburtsdatum"):
            self.assertFalse([r for r in kw if r.startswith(modul + ".")], modul)

    def test_jedes_recht_gehoert_zu_einem_bekannten_modul(self):
        for name, matrix in mx.DSO_ROLLEN.items():
            for r in mx.rechte_aus_matrix(matrix):
                modul, aktion = r.split(".")
                self.assertIn(modul, MODULE)
                self.assertIn(aktion, AKTIONEN)


class MatrixRechnungTests(TestCase):
    def test_rueckrechnung_fuer_selbst_angelegte_rollen(self):
        m = mx.matrix_aus_rechte(["mitglieder.view", "beitraege.view", "beitraege.add", "beitraege.change",
                                  "veranstaltungen.view", "veranstaltungen.add", "veranstaltungen.change",
                                  "veranstaltungen.delete"])
        self.assertEqual((m["stamm"], m["beitrag"], m["veranstaltung"], m["software"]), ("L", "B", "V", "-"))
        self.assertEqual(m[mx.LOESCHUNG], "-")

    def test_gespeicherte_matrix_nur_wenn_sie_zu_den_rechten_passt(self):
        rolle = Rolle(name="X", matrix={"stamm": "V"}, rechte=mx.rechte_aus_matrix({"stamm": "V"}))
        self.assertEqual(mx.matrix_der_rolle(rolle)["stamm"], "V")
        rolle.rechte = ["mitglieder.view"]   # von Hand geändert -> Matrix wird aus den Rechten abgeleitet
        self.assertEqual(mx.matrix_der_rolle(rolle)["stamm"], "L")

    def test_bisheriges_verhalten_bleibt_bei_den_neuen_modulen(self):
        r = neue_module_ableiten(["mitglieder.view", "mitglieder.change", "schriftverkehr.view",
                                  "veranstaltungen.add"])
        for erwartet in ("geburtsdatum.view", "geburtsdatum.change", "bankdaten.view", "bankdaten.change",
                         "rundschreiben.view", "teilnehmer.add"):
            self.assertIn(erwartet, r)
        self.assertNotIn("teilnehmer.view", r)


class MatrixViewTests(Basis):
    def setUp(self):
        super().setUp()
        self.admin = self.benutzer("verwalter", Rolle.objects.get(verein=self.v, name="Superadministrator"))
        self.client.force_login(self.admin)
        self.kw = rolle_von(self.v, "Kassenwart")
        self.sf = rolle_von(self.v, "Schriftführer")

    def _post(self, **aenderungen):
        daten = {}
        for r in Rolle.objects.filter(verein=self.v, ist_superadmin=False):
            for k, wert in mx.matrix_der_rolle(r).items():
                daten[f"m_{r.pk}_{k}"] = wert
        daten.update(aenderungen)
        return self.client.post(reverse("berechtigungsmatrix"), daten)

    def test_seite_zeigt_matrix_mit_allen_rollen_ohne_superadmin(self):
        r = self.client.get(reverse("berechtigungsmatrix"))
        self.assertContains(r, "Datenschutzordnung")
        self.assertContains(r, "Kassenwart (DSO)")
        self.assertContains(r, "Bankverbindungen und SEPA-Mandate")
        self.assertNotContains(r, ">Superadministrator<")
        self.assertContains(r, f'name="m_{self.kw.pk}_bank"')

    def test_zellen_speichern_erzeugt_die_modulrechte(self):
        self._post(**{f"m_{self.sf.pk}_bank": "L", f"m_{self.sf.pk}_beitrag": "B"})
        self.sf.refresh_from_db()
        self.assertIn("bankdaten.view", self.sf.rechte)
        self.assertNotIn("bankdaten.change", self.sf.rechte)
        self.assertIn("beitraege.change", self.sf.rechte)
        self.assertEqual(self.sf.matrix["bank"], "L")

    def test_unveraenderte_rollen_werden_nicht_angefasst(self):
        Rolle.objects.filter(pk=self.kw.pk).update(rechte=["mitglieder.view"], matrix={})
        self._post(**{f"m_{self.sf.pk}_bank": "L"})
        self.kw.refresh_from_db()
        self.assertEqual(self.kw.rechte, ["mitglieder.view"])

    def test_ungueltige_werte_werden_ignoriert(self):
        vorher = list(self.sf.rechte)
        self._post(**{f"m_{self.sf.pk}_bank": "ALLES"})
        self.sf.refresh_from_db()
        self.assertEqual(self.sf.rechte, vorher)

    def test_ohne_verwaltungsrecht_kein_speichern(self):
        lesen = Rolle.objects.create(verein=self.v, name="Nur lesen", rechte=["verwaltung.view"])
        self.client.force_login(self.benutzer("leser", lesen))
        self.assertEqual(self.client.get(reverse("berechtigungsmatrix")).status_code, 200)
        self.assertEqual(self._post(**{f"m_{self.sf.pk}_bank": "V"}).status_code, 403)
        self.sf.refresh_from_db()
        self.assertNotIn("bankdaten.view", self.sf.rechte)

    def test_dso_rollen_nachtraeglich_anlegen(self):
        Rolle.objects.filter(verein=self.v, name__endswith=mx.DSO_SUFFIX).delete()
        MitgliedTag.objects.filter(verein=self.v).delete()
        self.assertContains(self.client.get(reverse("berechtigungsmatrix")), "Rollen und Tags der Datenschutzordnung")
        self.client.post(reverse("berechtigungsmatrix_dso"))
        self.assertEqual(Rolle.objects.filter(verein=self.v, name__endswith=mx.DSO_SUFFIX).count(), 6)

    def test_ohne_anmeldung_gesperrt(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("berechtigungsmatrix")).status_code, 302)


class FeldRechteTests(Basis):
    def setUp(self):
        super().setUp()
        self.m = Mitglied.objects.create(verein=self.v, vorname="Erika", nachname="Muster",
                                         geburtsdatum=date(1980, 2, 1), iban="DE02120300000000202051",
                                         kontoinhaber="Erika Muster")

    def _als(self, funktion):
        self.client.force_login(self.benutzer("u-" + funktion.replace(" ", "").replace(".", ""),
                                              rolle_von(self.v, funktion)))

    def test_kassenwart_sieht_bank_aber_kein_geburtsdatum(self):
        self._als("Kassenwart")
        r = self.client.get(reverse("mitglied_detail", args=[self.m.pk]))
        self.assertContains(r, "DE02")
        self.assertNotContains(r, "01.02.1980")
        form = self.client.get(reverse("mitglied_edit", args=[self.m.pk])).context["form"]
        self.assertIn("iban", form.fields)
        self.assertNotIn("geburtsdatum", form.fields)

    def test_vorsitz_sieht_geburtsdatum_nur_lesend_und_keine_bankdaten(self):
        self._als("1. Vorsitzender")
        r = self.client.get(reverse("mitglied_detail", args=[self.m.pk]))
        self.assertContains(r, "01.02.1980")
        self.assertNotContains(r, "DE02")
        form = self.client.get(reverse("mitglied_edit", args=[self.m.pk])).context["form"]
        self.assertTrue(form.fields["geburtsdatum"].disabled)
        self.assertNotIn("iban", form.fields)

    def test_schreibgeschuetzte_felder_lassen_sich_nicht_per_post_aendern(self):
        self._als("1. Vorsitzender")
        self.client.post(reverse("mitglied_edit", args=[self.m.pk]), {
            "vorname": "Erika", "nachname": "Neu", "status": "aktiv", "zahlungsart": "ueberweisung",
            "geburtsdatum": "01.01.2000", "iban": "DE00"})
        self.m.refresh_from_db()
        self.assertEqual(self.m.nachname, "Neu")
        self.assertEqual(self.m.geburtsdatum, date(1980, 2, 1))
        self.assertEqual(self.m.iban, "DE02120300000000202051")

    def test_export_und_auskunft_ohne_geschuetzte_felder(self):
        self._als("Schriftführer")   # darf Geburtsdatum, aber keine Bankdaten
        r = self.client.get(reverse("mitglieder_export") + "?format=csv&bank=1")
        text = r.content.decode("utf-8", "replace")
        self.assertIn("Geburtsdatum", text)
        self.assertNotIn("IBAN", text)
        self.assertNotIn("DE02120300000000202051", text)
        auskunft = self.client.get(reverse("mitglied_export", args=[self.m.pk])).content.decode("utf-8")
        self.assertNotIn("DE02120300000000202051", auskunft)
        self.assertIn("1980", auskunft)

    def test_kassenwart_export_ohne_geburtsdatum_aber_mit_bank(self):
        self._als("Kassenwart")
        text = self.client.get(reverse("mitglieder_export") + "?format=csv&bank=1").content.decode("utf-8", "replace")
        self.assertNotIn("Geburtsdatum", text)
        self.assertIn("DE02120300000000202051", text)

    def test_import_ignoriert_gesperrte_spalten(self):
        from apps.members import importer
        inhalt = "Vorname;Nachname;Geburtsdatum;IBAN\nNeu;Person;01.01.1990;DE0012\n".encode("utf-8")
        bericht = importer.importieren(self.v, "m.csv", inhalt, testlauf=False, neu_anlegen=True,
                                       gesperrte_felder={"geburtsdatum", "iban"})
        m = Mitglied.objects.get(vorname="Neu")
        self.assertIsNone(m.geburtsdatum)
        self.assertEqual(m.iban, "")
        self.assertTrue(any("ohne Berechtigung" in w for w in bericht["warnungen"]))


class ModulTrennungTests(Basis):
    def test_kassenwart_darf_keine_serienbriefe_und_teilnehmer(self):
        self.client.force_login(self.benutzer("kw", rolle_von(self.v, "Kassenwart")))
        self.assertEqual(self.client.get(reverse("serienbrief_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("anmeldung_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("schriftstueck_list")).status_code, 200)   # Kommunikation: Lesen

    def test_schriftfuehrer_darf_beides(self):
        self.client.force_login(self.benutzer("sf", rolle_von(self.v, "Schriftführer")))
        self.assertEqual(self.client.get(reverse("serienbrief_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("anmeldung_list")).status_code, 200)


class TagRolleTests(Basis):
    def setUp(self):
        super().setUp()
        self.u = get_user_model().objects.create_user("erika", password="pw-Test-12345")
        self.m = Mitglied.objects.create(verein=self.v, vorname="Erika", nachname="Muster", benutzer=self.u)
        self.lese = Rolle.objects.create(verein=self.v, name="Ausgangsrolle", rechte=[])
        self.z = Zugang.objects.create(verein=self.v, user=self.u, rolle=self.lese)
        self.kw_tag = MitgliedTag.objects.get(verein=self.v, name="Kassenwart")
        self.sf_tag = MitgliedTag.objects.get(verein=self.v, name="Schriftführer")

    def test_tag_verteilt_die_rolle(self):
        self.m.tags.add(self.kw_tag)
        self.z.refresh_from_db()
        self.assertEqual(self.z.rolle, rolle_von(self.v, "Kassenwart"))
        self.assertTrue(self.z.aktiv)

    def test_wechsel_der_funktion_wechselt_die_rolle(self):
        self.m.tags.add(self.kw_tag)
        self.m.tags.remove(self.kw_tag)
        self.m.tags.add(self.sf_tag)
        self.z.refresh_from_db()
        self.assertEqual(self.z.rolle, rolle_von(self.v, "Schriftführer"))

    def test_funktionsende_entzieht_die_rechte(self):   # § 17
        self.m.tags.add(self.kw_tag)
        self.m.tags.remove(self.kw_tag)
        self.z.refresh_from_db()
        self.assertFalse(self.z.aktiv)
        self.assertTrue(Zugang.objects.filter(pk=self.z.pk).exists())   # nie gelöscht

    def test_austritt_entzieht_die_rechte(self):
        self.m.tags.add(self.kw_tag)
        self.m.status = "ausgetreten"
        self.m.save()
        self.z.refresh_from_db()
        self.assertFalse(self.z.aktiv)

    def test_nicht_verwaltete_rolle_bleibt_ohne_tag_unberuehrt(self):
        self.m.tags.clear()
        self.z.refresh_from_db()
        self.assertTrue(self.z.aktiv)
        self.assertEqual(self.z.rolle, self.lese)

    def test_superadministrator_wird_nie_veraendert(self):
        self.z.rolle = Rolle.objects.get(verein=self.v, name="Superadministrator")
        self.z.save()
        self.m.tags.add(self.kw_tag)
        self.m.tags.remove(self.kw_tag)
        self.z.refresh_from_db()
        self.assertTrue(self.z.aktiv)
        self.assertTrue(self.z.rolle.ist_superadmin)

    def test_tag_seite_verteilt_an_alle_traeger(self):
        self.kw_tag.mitglieder.add(self.m)   # umgekehrte Richtung
        self.z.refresh_from_db()
        self.assertEqual(self.z.rolle, rolle_von(self.v, "Kassenwart"))


class PruefungTests(Basis):
    def test_hinweise_zu_besetzung_und_zu_vielen_personen(self):
        hinweise = " ".join(mx.dso_pruefung(self.v))
        self.assertIn("nicht besetzt", hinweise)
        t = MitgliedTag.objects.get(verein=self.v, name="Kassenwart")
        for i in range(2):
            Mitglied.objects.create(verein=self.v, vorname=f"K{i}", nachname="W").tags.add(t)
        self.assertIn("mehrfach besetzt", " ".join(mx.dso_pruefung(self.v)))
        for i, tag in enumerate(MitgliedTag.objects.filter(verein=self.v, rolle__isnull=False)):
            Mitglied.objects.create(verein=self.v, vorname=f"X{i}", nachname="Y").tags.add(tag)
        self.assertIn("§ 6", " ".join(mx.dso_pruefung(self.v)))

    def test_zugang_ohne_funktion_wird_gemeldet(self):
        u = get_user_model().objects.create_user("ohne", password="pw-Test-12345")
        Zugang.objects.create(verein=self.v, user=u, rolle=rolle_von(self.v, "Kassenwart"))
        self.assertIn("§ 17", " ".join(mx.dso_pruefung(self.v)))
