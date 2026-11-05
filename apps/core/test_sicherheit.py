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


class CacheEinstellungTests(TestCase):
    """Gemeinsamer Cache fuer alle Gunicorn-Worker (sonst gilt das Ratenlimit je Worker statt je Server)."""

    def test_cache_nutzt_dieselbe_redis_instanz_aber_datenbank_1(self):
        from config import settings
        for roh, erwartet in (("redis://redis:6379/0", "redis://redis:6379/1"), ("redis://redis:6379", "redis://redis:6379/1"),
                              ("redis://redis:6379/", "redis://redis:6379/1"), ("redis://:geheim@h:6379/5", "redis://:geheim@h:6379/1")):
            self.assertEqual(settings._cache_url(roh), erwartet, roh)
        # cache.clear() darf nie die Celery-Warteschlange (Datenbank 0) leeren
        self.assertNotEqual(settings._cache_url(settings.CELERY_BROKER_URL), settings.CELERY_BROKER_URL)

    def test_im_testlauf_bleibt_es_beim_schnellen_speicher_cache(self):
        from django.conf import settings
        self.assertIn("locmem", settings.CACHES["default"]["BACKEND"])


class SicherheitsHeaderTests(TestCase):
    def _antwort(self, **kw):
        from django.http import HttpResponse
        from django.test import RequestFactory

        from .middleware import SicherheitsHeaderMiddleware
        return SicherheitsHeaderMiddleware(lambda request: HttpResponse("x", **kw))(RequestFactory().get("/"))

    def test_html_bekommt_csp_und_permissions_policy(self):
        a = self._antwort(content_type="text/html; charset=utf-8")
        self.assertIn("frame-ancestors 'self'", a["Content-Security-Policy"])
        self.assertIn("base-uri 'self'", a["Content-Security-Policy"])
        self.assertNotIn("script-src", a["Content-Security-Policy"])        # Inline-Skripte der Anwendung bleiben moeglich
        self.assertNotIn("object-src", a["Content-Security-Policy"])        # koennte den PDF-Betrachter blockieren
        self.assertIn("camera=()", a["Permissions-Policy"])

    def test_dateien_und_pdf_bekommen_kein_csp(self):
        for typ in ("application/pdf", "image/png", "application/octet-stream"):
            a = self._antwort(content_type=typ)
            self.assertFalse(a.has_header("Content-Security-Policy"), typ)
            self.assertTrue(a.has_header("Permissions-Policy"), typ)

    def test_von_der_ansicht_gesetzte_header_bleiben(self):
        from django.http import HttpResponse
        from django.test import RequestFactory

        from .middleware import SicherheitsHeaderMiddleware

        def ansicht(request):
            r = HttpResponse("x", content_type="text/html")
            r.headers["Content-Security-Policy"] = "default-src 'none'"
            return r

        a = SicherheitsHeaderMiddleware(ansicht)(RequestFactory().get("/"))
        self.assertEqual(a["Content-Security-Policy"], "default-src 'none'")

    def test_echte_seiten_tragen_die_header(self):
        r = self.client.get("/login/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("frame-ancestors", r["Content-Security-Policy"])
        self.assertIn("Permissions-Policy", r)
        self.assertEqual(r["X-Frame-Options"], "DENY")                      # bestehender Schutz bleibt


class HaertungsEinstellungenTests(TestCase):
    def test_einstellungen(self):
        from django.conf import settings
        self.assertIs(settings.WHITENOISE_ALLOW_ALL_ORIGINS, False)
        self.assertEqual(settings.LANGUAGE_COOKIE_SAMESITE, "Lax")
        self.assertIn("apps.core.middleware.SicherheitsHeaderMiddleware", settings.MIDDLEWARE)


class PruefskriptTests(TestCase):
    """scripts/sicherheitstest_pruefen.py laeuft nur auf der Testinstanz; hier nur: lesbar und mit Schutzabfrage."""

    def test_skript_ist_gueltiges_python_mit_schutzabfrage(self):
        from pathlib import Path
        pfad = Path(__file__).resolve().parents[2] / "scripts" / "sicherheitstest_pruefen.py"
        text = pfad.read_text(encoding="utf-8")
        compile(text, str(pfad), "exec")
        self.assertIn('kuerzel__in=("pentest-a", "pentest-b")', text)       # weigert sich bei fremden Vereinen
        self.assertIn("SystemExit", text)
        self.assertNotIn("0.0.0.0", text)
        self.assertIn('BASE = "http://127.0.0.1:8000"', text)                # greift nur die lokale Instanz an
