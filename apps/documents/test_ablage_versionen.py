import importlib
from datetime import date

from django.apps import apps as echte_apps
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Rolle, Verein, Zugang
from apps.documents import services
from apps.documents.models import Ablagedokument, Schriftstueck
from apps.events.models import Veranstaltung

PW = "pw-Test-12345"


class AblageVersionenBasis(TestCase):
    def setUp(self):
        self.v = Verein.objects.create(name="Test e.V.", kuerzel="test")
        self.ver1 = Veranstaltung.objects.create(verein=self.v, titel="Mitgliederversammlung", beginn=timezone.now())
        self.ver2 = Veranstaltung.objects.create(verein=self.v, titel="Mitgliederversammlung", beginn=timezone.now())
        User = get_user_model()
        admin = User.objects.create_superuser("admin", password=PW)
        Zugang.objects.create(verein=self.v, user=admin, rolle=Rolle.objects.get(verein=self.v,
                                                                                  name="Superadministrator"))
        self.client.login(username="admin", password=PW)

    def protokoll(self, ver, datum):
        return Schriftstueck.objects.create(verein=self.v, titel="Protokoll Mitgliederversammlung", art="protokoll",
                                            veranstaltung=ver, text="Text", datum=datum)

    def ablegen_per_knopf(self, s):
        self.client.post(reverse("schriftstueck_ablegen", args=[s.pk]))
        s.refresh_from_db()
        return s.ablage


class ProtokolleMitGleichemTitelTests(AblageVersionenBasis):
    """Regression: das Protokoll der Sitzung vom 10.10. wurde als "Version 2" des Protokolls vom 30.9. abgelegt."""

    def test_protokolle_verschiedener_sitzungen_sind_getrennte_dokumente(self):
        alt = self.ablegen_per_knopf(self.protokoll(self.ver1, date(2026, 9, 30)))
        neu = self.ablegen_per_knopf(self.protokoll(self.ver2, date(2026, 10, 10)))
        self.assertEqual((alt.version, neu.version), (1, 1))
        self.assertNotEqual(alt.pk, neu.pk)
        self.assertEqual(Ablagedokument.objects.filter(titel="Protokoll Mitgliederversammlung").count(), 2)
        alt.refresh_from_db()
        self.assertEqual(alt.version, 1)   # das fruehere Protokoll bleibt unveraendert

    def test_gleicher_titel_ohne_veranstaltung_wird_auch_getrennt_abgelegt(self):
        a = self.ablegen_per_knopf(self.protokoll(None, date(2026, 9, 30)))
        b = self.ablegen_per_knopf(self.protokoll(None, date(2026, 10, 10)))
        self.assertEqual((a.version, b.version), (1, 1))

    def test_erneutes_ablegen_desselben_protokolls_ergibt_eine_neue_version(self):
        s = self.protokoll(self.ver1, date(2026, 9, 30))
        erste = self.ablegen_per_knopf(s)
        zweite = self.ablegen_per_knopf(s)
        self.assertEqual((erste.version, zweite.version), (1, 2))
        dritte = self.ablegen_per_knopf(s)
        self.assertEqual(dritte.version, 3)

    def test_neue_version_des_zweiten_protokolls_zaehlt_nur_dessen_versionen(self):
        self.ablegen_per_knopf(self.protokoll(self.ver1, date(2026, 9, 30)))
        s2 = self.protokoll(self.ver2, date(2026, 10, 10))
        self.assertEqual(self.ablegen_per_knopf(s2).version, 1)
        self.assertEqual(self.ablegen_per_knopf(s2).version, 2)


class ModellVersionierungTests(AblageVersionenBasis):
    def _doc(self, ver, **kw):
        return services.ablegen(self.v, "Satzung", "sonstiges", "satzung.pdf", b"%PDF-1.4", veranstaltung=ver, **kw)

    def test_gleicher_titel_und_veranstaltung_zaehlt_hoch(self):
        self.assertEqual([self._doc(self.ver1).version for _ in range(3)], [1, 2, 3])

    def test_andere_veranstaltung_beginnt_bei_eins(self):
        self._doc(self.ver1)
        self.assertEqual(self._doc(self.ver2).version, 1)

    def test_manueller_upload_ohne_veranstaltung_bleibt_wie_bisher_versioniert(self):
        self.assertEqual([self._doc(None).version for _ in range(2)], [1, 2])

    def test_erste_version_erzwingt_version_eins(self):
        self._doc(None)
        self.assertEqual(self._doc(None, erste_version=True).version, 1)

    def test_neue_version_hochladen_gibt_die_veranstaltung_weiter(self):
        d = self._doc(self.ver1)
        r = self.client.get(reverse("ablagedokument_detail", args=[d.pk]))
        self.assertContains(r, f"veranstaltung={self.ver1.pk}")


class MigrationVersionenTrennenTests(AblageVersionenBasis):
    def _angelegt(self, titel, ver, version):
        d = services.ablegen(self.v, titel, "protokoll", "x.pdf", b"%PDF-1.4", veranstaltung=ver, erste_version=True)
        Ablagedokument.objects.filter(pk=d.pk).update(version=version)
        return d.pk

    def test_falsch_gezaehlte_versionen_werden_je_veranstaltung_neu_nummeriert(self):
        migration = importlib.import_module("apps.documents.migrations.0009_versionen_je_veranstaltung")
        a = self._angelegt("Protokoll", self.ver1, 1)       # 30.9.
        b = self._angelegt("Protokoll", self.ver2, 2)       # 10.10. - war faelschlich "Version 2" von a
        c = self._angelegt("Protokoll", self.ver2, 3)       # echte zweite Version des 10.10.-Protokolls
        ohne1 = self._angelegt("Beleg", None, 1)
        ohne2 = self._angelegt("Beleg", None, 2)
        migration.versionen_trennen(echte_apps, None)
        version = lambda pk: Ablagedokument.objects.get(pk=pk).version
        self.assertEqual([version(a), version(b), version(c)], [1, 1, 2])
        self.assertEqual([version(ohne1), version(ohne2)], [1, 2])   # ohne Veranstaltung unveraendert

    def test_unproblematische_dokumente_bleiben_unberuehrt(self):
        migration = importlib.import_module("apps.documents.migrations.0009_versionen_je_veranstaltung")
        a = self._angelegt("Satzung", self.ver1, 1)
        b = self._angelegt("Satzung", self.ver1, 2)
        migration.versionen_trennen(echte_apps, None)
        self.assertEqual([Ablagedokument.objects.get(pk=pk).version for pk in (a, b)], [1, 2])
