from django.test import TestCase

from apps.core.models import Verein
from apps.members import importer
from apps.members.models import Mitglied

CSV = ("Vorname;Nachname;Geburtstag;E-Mail;Mitgliedsart;PLZ\n"
       "Max;Muster;01.02.1980;m@example.org;Aktiv;35683\n").encode("utf-8")


class ImportTests(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")

    def test_testlauf_speichert_nichts(self):
        b = importer.importieren(self.v, "m.csv", CSV, testlauf=True)
        self.assertEqual((b["neu"], len(b["fehler"])), (1, 0))
        self.assertEqual(Mitglied.objects.filter(verein=self.v).count(), 0)

    def test_import_und_aktualisierung(self):
        b = importer.importieren(self.v, "m.csv", CSV, testlauf=False)
        self.assertEqual(b["neu"], 1)
        m = Mitglied.objects.get(verein=self.v)
        self.assertEqual((m.mitgliedsnummer, m.email, str(m.mitgliedsart)), (1, "m@example.org", "Aktiv"))
        update = "Mitgliedsnummer;Vorname;Nachname;Ort;E-Mail\n1;Max;Muster;Dillenburg;\n".encode("utf-8")
        b = importer.importieren(self.v, "u.csv", update, testlauf=False)
        self.assertEqual((b["neu"], b["aktualisiert"]), (0, 1))
        m.refresh_from_db()
        self.assertEqual(m.ort, "Dillenburg")
        self.assertEqual(m.email, "m@example.org")  # leere Zelle überschreibt nichts

    def test_fehlerhafte_zeile_wird_gemeldet(self):
        daten = "Vorname;Nachname;Geburtstag\nEva;;01.01.1990\nAnna;Beispiel;kein-datum\nOk;Person;\n".encode("utf-8")
        b = importer.importieren(self.v, "f.csv", daten, testlauf=False)
        self.assertEqual(b["neu"], 1)
        self.assertEqual(len(b["fehler"]), 2)

    def test_unbekannte_mitgliedsart(self):
        daten = "Vorname;Nachname;Mitgliedsart\nA;B;Gibtsnicht\n".encode("utf-8")
        self.assertEqual(len(importer.importieren(self.v, "a.csv", daten, testlauf=True)["fehler"]), 1)
        b = importer.importieren(self.v, "a.csv", daten, testlauf=False, neu_anlegen=True)
        self.assertEqual((b["neu"], len(b["fehler"])), (1, 0))
