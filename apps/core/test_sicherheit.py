"""Sicherheits-Haertung: XML-Eingaben (Entity-Angriffe) und HTML von Fremdsystemen."""
from django.test import TestCase

from apps.accounting.erechnung import parse_rechnung
from apps.core.models import Verein
from apps.finance import kontoauszug
from apps.finance.fints_service import _nur_text

ENTITY_BOMBE = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">]>
<Document>&lol2;</Document>"""


class XmlHaertungTests(TestCase):
    def test_erechnung_mit_entity_deklaration_wird_abgelehnt(self):
        self.assertIsNone(parse_rechnung(ENTITY_BOMBE))

    def test_camt_mit_entity_deklaration_wird_abgelehnt(self):
        v = Verein.objects.create(name="Test e.V.", kuerzel="xmltest")
        with self.assertRaises(ValueError):
            kontoauszug.camt053_import(v, ENTITY_BOMBE)


class BankHtmlTests(TestCase):
    def test_nur_text_entfernt_tags_und_skripte_behaelt_zeilenumbrueche(self):
        roh = 'Bitte <b>TAN</b> eingeben<br/>Zeile 2<script>alert(1)</script><img src=x onerror=alert(1)>'
        text = _nur_text(roh)
        self.assertNotIn("<", text)
        self.assertIn("Bitte TAN eingeben\nZeile 2", text)

    def test_nur_text_ohne_wert(self):
        self.assertEqual(_nur_text(None), "")
