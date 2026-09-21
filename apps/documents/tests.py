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

    def test_fusslinie_verwendet_eigene_akzentfarbe(self):
        from docx.shared import RGBColor
        from apps.documents.docx_export import _farbe_fuss
        v = Verein.objects.create(name="Test e.V.", kuerzel="test3", akzentfarbe="#EA580C",
                                  akzentfarbe_fuss="#005199")
        self.assertEqual(_farbe_fuss(v), RGBColor.from_string("005199"))

    def test_fusslinie_faellt_ohne_eigene_farbe_auf_hauptfarbe_zurueck(self):
        from docx.shared import RGBColor
        from apps.documents.docx_export import _farbe_fuss
        v = Verein.objects.create(name="Test e.V.", kuerzel="test4", akzentfarbe="#EA580C")
        self.assertEqual(_farbe_fuss(v), RGBColor.from_string("EA580C"))

    def test_schriftstueck_docx_mit_logo_ohne_tabelle(self):
        import base64
        import zipfile
        from io import BytesIO
        from django.core.files.uploadedfile import SimpleUploadedFile
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
        v = Verein.objects.create(name="Test e.V.", kuerzel="test5",
                                  logo=SimpleUploadedFile("logo.png", png, content_type="image/png"))
        s = Schriftstueck.objects.create(verein=v, titel="Test", art="brief", betreff="Betreff", text="Text.")
        daten = schriftstueck_docx(s)
        with zipfile.ZipFile(BytesIO(daten)) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        self.assertNotIn("<w:tbl>", xml)
        self.assertIn("wp:anchor", xml)
