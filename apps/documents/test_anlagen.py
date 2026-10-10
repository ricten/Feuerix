import io

from django.test import TestCase
from django.utils import timezone
from pypdf import PdfReader

from apps.core.models import Verein
from apps.documents import anlagen
from apps.documents.models import Schriftstueck
from apps.documents.pdf import schriftstueck_pdf
from apps.events.models import Anwesenheit, Veranstaltung, Wahlergebnis
from apps.members.models import Mitglied


class AnlagenBasis(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.ver = Veranstaltung.objects.create(verein=self.v, titel="Mitgliederversammlung 2026",
                                                beginn=timezone.now())

    def abstimmung(self, amt, details, wahlgang="Abstimmung"):
        return Wahlergebnis.objects.create(
            verein=self.v, veranstaltung=self.ver, art="abstimmung", amt=amt, wahlgang=wahlgang, details=details,
            ergebnis="\n".join(f"{a}: {b}" for a, b in details))

    def wahl(self, amt, details, wahlgang="Wahlgang"):
        return Wahlergebnis.objects.create(
            verein=self.v, veranstaltung=self.ver, art="wahl", amt=amt, wahlgang=wahlgang, details=details,
            ergebnis="\n".join(f"{a}: {b}" for a, b in details))

    def gast(self, name):
        return Anwesenheit.objects.create(verein=self.v, veranstaltung=self.ver, name=name)


class AnlagenAufbauTests(AnlagenBasis):
    def test_ohne_daten_keine_anlagen(self):
        self.assertEqual(anlagen.anlagen(self.ver), [])
        self.assertEqual(anlagen.anlagen_nummern(self.ver), {})
        self.assertEqual(anlagen.anlagen(None), [])

    def test_nummern_sind_fortlaufend_nur_fuer_vorhandene(self):
        self.wahl("Kassenwart", [["A", "3 Stimmen"]])
        self.assertEqual(anlagen.anlagen_nummern(self.ver), {"wahl": 1})
        self.gast("Gast")
        self.assertEqual(anlagen.anlagen_nummern(self.ver), {"anwesenheit": 1, "wahl": 2})
        self.abstimmung("Antrag 1", [["Ergebnis", "1 Ja"]])
        self.assertEqual(anlagen.anlagen_nummern(self.ver), {"anwesenheit": 1, "abstimmung": 2, "wahl": 3})

    def test_alle_wahlen_stehen_in_einer_anlage_je_wahl_ein_block(self):
        self.wahl("1. Vorsitzender", [["Max Muster", "8 Stimmen"], ["Erika Musterfrau", "3 Stimmen"]])
        self.wahl("Kassenwart", [["Hans Kasse", "10 Stimmen"]])
        liste = anlagen.anlagen(self.ver)
        self.assertEqual(len(liste), 1)
        a = liste[0]
        self.assertEqual(a["titel"], "Anlage 1: Wahlergebnisse")
        self.assertEqual([b["titel"] for b in a["bloecke"]], ["1. Vorsitzender – Wahlgang", "Kassenwart – Wahlgang"])
        erster = a["bloecke"][0]
        self.assertEqual(erster["zeilen"], [["Kandidat*in", "Stimmen"], ["Max Muster", "8 Stimmen"],
                                            ["Erika Musterfrau", "3 Stimmen"]])
        self.assertIn("Gewählt:", erster["nach"][0])

    def test_alle_abstimmungen_in_einer_anlage_text_als_absaetze_zahlen_als_tabelle(self):
        self.abstimmung("Antrag A1: Beitragserhöhung", [
            ["Antragsteller*in", "Christina Peters"], ["Antragstext", "erhöhung beitrag"],
            ["Begründung", "kein geld in der kasse"], ["Ergebnis", "10 Ja, 5 Nein, 2 Enthaltung"],
            ["Gültige Stimmen", "17"], ["Status in OpenSlides", "angenommen"]])
        self.abstimmung("Thema: Entlastung", [["Ergebnis", "10 Ja, 0 Nein, 2 Enthaltung"]])
        a = anlagen.anlagen(self.ver)[0]
        self.assertEqual(a["titel"], "Anlage 1: Abstimmungen")
        self.assertEqual(len(a["bloecke"]), 2)
        antrag = a["bloecke"][0]
        self.assertEqual(antrag["absaetze"], ["Antragsteller*in: Christina Peters", "Antragstext: erhöhung beitrag",
                                              "Begründung: kein geld in der kasse",
                                              "Status in OpenSlides: angenommen"])
        self.assertEqual(antrag["zeilen"], [["Ergebnis", "Wert"], ["Ergebnis", "10 Ja, 5 Nein, 2 Enthaltung"],
                                            ["Gültige Stimmen", "17"]])
        self.assertIn("angenommen", antrag["nach"][0])
        self.assertIn("abgelehnt", antrag["nach"][0])

    def test_aeltere_eintraege_ohne_details_zeigen_den_gespeicherten_text(self):
        Wahlergebnis.objects.create(verein=self.v, veranstaltung=self.ver, art="wahl", amt="Alt", ergebnis="X: 1 Ja")
        block = anlagen.anlagen(self.ver)[0]["bloecke"][0]
        self.assertEqual(block["absaetze"], ["X: 1 Ja"])
        self.assertNotIn("zeilen", block)

    def test_teilnehmerliste_alphabetisch_mit_mitglied_oder_gast(self):
        m = Mitglied.objects.create(verein=self.v, vorname="Erika", nachname="Muster", mitgliedsnummer=7)
        Anwesenheit.objects.create(verein=self.v, veranstaltung=self.ver, mitglied=m)
        self.gast("Zoe Gast")
        self.gast("Adam Gast")
        a = anlagen.anlagen(self.ver)[0]
        zeilen = a["tabellen"][0]["zeilen"]
        self.assertEqual(zeilen[0], ["Nr.", "Name", "Mitglied / Gast"])
        self.assertEqual([z[1:] for z in zeilen[1:]], [["Adam Gast", "Gast"], ["Erika Muster", "Mitglied"],
                                                       ["Zoe Gast", "Gast"]])
        self.assertIn("3", a["vor"][1])

    def test_datum_im_kopf(self):
        self.gast("A")
        self.assertIn("Samstag, 10.10.2026", anlagen.anlagen(self.ver, "Samstag, 10.10.2026")[0]["vor"][0])


class AnlagenImPdfTests(AnlagenBasis):
    def _pdf_text(self, s):
        pdf = PdfReader(io.BytesIO(schriftstueck_pdf(s)))
        return len(pdf.pages), "\n".join(p.extract_text() for p in pdf.pages)

    def _protokoll(self, art="protokoll", ver=True):
        return Schriftstueck.objects.create(verein=self.v, titel="Protokoll", art=art, text="Beginn.",
                                            veranstaltung=self.ver if ver else None)

    def test_jede_anlage_beginnt_auf_eigener_seite(self):
        self.gast("Gast Eins")
        self.abstimmung("Antrag A1", [["Ergebnis", "1 Ja"]])
        self.wahl("Kassenwart", [["Hans Kasse", "10 Stimmen"]])
        seiten, text = self._pdf_text(self._protokoll())
        self.assertEqual(seiten, 4)
        self.assertLess(text.index("Anlage 1: Teilnehmerliste"), text.index("Anlage 2: Abstimmungen"))
        self.assertLess(text.index("Anlage 2: Abstimmungen"), text.index("Anlage 3: Wahlergebnisse"))

    def test_ohne_daten_nur_das_protokoll(self):
        seiten, text = self._pdf_text(self._protokoll())
        self.assertEqual(seiten, 1)
        self.assertNotIn("Anlage", text)

    def test_nur_protokolle_bekommen_anlagen(self):
        self.gast("Gast Eins")
        seiten, text = self._pdf_text(self._protokoll(art="einladung"))
        self.assertEqual((seiten, "Anlage" in text), (1, False))
        seiten, text = self._pdf_text(self._protokoll(ver=False))
        self.assertEqual(seiten, 1)

    def test_sehr_langer_antragstext_bricht_ueber_mehrere_seiten_um(self):
        self.abstimmung("Antrag A1", [["Antragstext", "Absatz mit vielen Worten. " * 400],
                                      ["Ergebnis", "1 Ja"]])
        seiten, text = self._pdf_text(self._protokoll())
        self.assertGreaterEqual(seiten, 3)   # Protokoll + mehrseitige Anlage, ohne Fehler
        self.assertIn("Anlage 1: Abstimmungen", text)

    def test_verweis_statt_doppeltem_block_im_protokolltext(self):
        self.wahl("Kassenwart", [["Hans Kasse", "10 Stimmen"]])
        s = self._protokoll()
        s.text = "Wahlen:\n{wahlergebnisse}"
        s.save()
        seiten, text = self._pdf_text(s)
        self.assertIn("Wahlergebnisse: siehe Anlage 1 (Wahlergebnisse)", text)
        self.assertEqual(text.count("Hans Kasse"), 1)   # nur in der Anlage, nicht zusaetzlich im Fliesstext
