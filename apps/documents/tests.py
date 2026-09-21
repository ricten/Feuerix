from django.test import TestCase

from apps.core.models import Verein
from apps.documents.docx_export import schriftstueck_docx
from apps.documents.models import Schriftstueck


class DocxExportTests(TestCase):
    def test_schriftstueck_docx_wird_erzeugt(self):
        v = Verein.objects.create(name="Test e.V.", kuerzel="test", akzentfarbe="#C0392B",
                                  unterschrift_1="Erika Musterfrau, 1. Vorsitzende")
        s = Schriftstueck.objects.create(verein=v, titel="Test", art="brief", betreff="Betreff",
                                         text="Text der Nachricht.")
        daten = schriftstueck_docx(s)
        self.assertTrue(daten.startswith(b"PK"))  # .docx ist ein ZIP-Container

    def test_ungueltige_akzentfarbe_faellt_auf_standard_zurueck(self):
        v = Verein.objects.create(name="Test e.V.", kuerzel="test2", akzentfarbe="keine-farbe")
        s = Schriftstueck.objects.create(verein=v, titel="Test", art="brief", betreff="Betreff", text="Text.")
        daten = schriftstueck_docx(s)
        self.assertTrue(daten.startswith(b"PK"))
