"""NUR FÜR EINE TESTINSTANZ: legt zwei Vereine und Testkonten für einen Sicherheitstest an (Rechte- und
Mandantentrennung, ZAP/Burp). Siehe docs/SICHERHEITSTEST.md.

Je Verein gibt es ein paar Mitglieder (eines mit IBAN), dazu Konten mit unterschiedlichen Rechten:

* pt_admin_a  - Rolle "Administrator" in Verein A (volle Rechte, aber kein Superuser)
* pt_lesen_a  - nur Anzeigen-Rechte in Verein A (ohne Verwaltung/Änderungsprotokoll)
* pt_kasse_a  - nur Kassenbuch in Verein A
* pt_admin_b  - Rolle "Administrator" in Verein B (zweiter Mandant: darf nichts aus A sehen)

Aus Sicherheitsgründen weigert sich der Befehl, wenn schon andere Vereine existieren (also auf einer Produktivinstanz),
und braucht --testinstanz als ausdrückliche Bestätigung.

Aufruf:  python manage.py sicherheitstest_vorbereiten --testinstanz [--zuruecksetzen]
"""
import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.core.matrix import ADMINISTRATOR
from apps.core.models import Rolle, Verein, Zugang
from apps.core.rechte import MODULE
from apps.members.models import Mitglied

KUERZEL = {"A": "pentest-a", "B": "pentest-b"}
MARKE = "[Sicherheitstest]"
# Module, die ein reiner Leser nicht sehen soll (Verwaltung = Benutzer/Rollen, Änderungsprotokoll)
OHNE_LESEN = {"verwaltung", "audit"}


class Command(BaseCommand):
    help = "NUR FÜR TESTINSTANZEN: zwei Vereine und Testkonten für den Sicherheitstest anlegen."

    def add_arguments(self, parser):
        parser.add_argument("--testinstanz", action="store_true",
                            help="Bestätigung, dass dies eine Testinstanz ohne echte Daten ist")
        parser.add_argument("--zuruecksetzen", action="store_true",
                            help="Vorhandene Testkonten und -vereine zuerst entfernen")

    def handle(self, *args, **opts):
        if not opts["testinstanz"]:
            raise CommandError("Nur für Testinstanzen. Zur Bestätigung --testinstanz angeben.")
        fremde = Verein.objects.exclude(kuerzel__in=KUERZEL.values())
        if fremde.exists():
            raise CommandError("Abbruch: Es gibt Vereine, die nicht zum Sicherheitstest gehören "
                               f"({', '.join(fremde.values_list('kuerzel', flat=True)[:5])}). "
                               "Dieser Befehl gehört nur auf eine leere Testinstanz.")
        User = get_user_model()
        if User.objects.filter(username__startswith="pt_").exists():
            if not opts["zuruecksetzen"]:
                raise CommandError("Die Testkonten gibt es schon. Mit --zuruecksetzen Passwörter und Daten erneuern.")
            # Die Vereine bleiben (viele Stammdaten daran sind geschützt); Konten und Testmitglieder werden neu angelegt.
            User.objects.filter(username__startswith="pt_").delete()
            Mitglied.objects.filter(verein__kuerzel__in=KUERZEL.values(), notizen=MARKE).delete()
            Rolle.objects.filter(verein__kuerzel__in=KUERZEL.values(), name__endswith="(Test)").delete()

        verein = {k: Verein.objects.get_or_create(kuerzel=kz, defaults={"name": f"Sicherheitstest Verein {k} e.V."})[0]
                  for k, kz in KUERZEL.items()}
        mitglieder = {k: self._mitglieder(v, k) for k, v in verein.items()}

        lesen = Rolle.objects.create(verein=verein["A"], name="Nur Lesen (Test)", rechte=sorted(
            f"{m}.view" for m in MODULE if m not in OHNE_LESEN))
        kasse = Rolle.objects.create(verein=verein["A"], name="Nur Kassenbuch (Test)", rechte=["kassenbuch.view", "kassenbuch.add"])
        konten = [
            ("pt_admin_a", verein["A"], Rolle.objects.get(verein=verein["A"], name=ADMINISTRATOR)),
            ("pt_lesen_a", verein["A"], lesen),
            ("pt_kasse_a", verein["A"], kasse),
            ("pt_admin_b", verein["B"], Rolle.objects.get(verein=verein["B"], name=ADMINISTRATOR)),
        ]
        ausgabe = []
        for name, v, rolle in konten:
            pw = secrets.token_urlsafe(12)
            user = User.objects.create_user(name, f"{name}@example.invalid", pw)
            Zugang.objects.create(verein=v, user=user, rolle=rolle)
            ausgabe.append((name, pw, v.kuerzel, rolle.name))

        w = self.stdout.write
        w(self.style.SUCCESS("Testvereine und Testkonten angelegt. Diese Passwörter werden nur jetzt angezeigt:\n"))
        for name, pw, kz, rolle in ausgabe:
            w(f"  {name:<12} {pw:<18} Verein {kz:<10} Rolle {rolle}")
        w("\nMitglieds-IDs für die Mandantentrennung (Verein A darf die von B nie sehen und umgekehrt):")
        for k, liste in mitglieder.items():
            w(f"  Verein {k}: " + ", ".join(f"{m.pk}" + (" (mit IBAN)" if m.iban else "") for m in liste))
        w("\nWeiter: docs/SICHERHEITSTEST.md")

    def _mitglieder(self, verein, k):
        liste = []
        for i, (vor, nach) in enumerate([("Erika", "Muster"), ("Max", "Beispiel"), ("Tina", "Test")], start=1):
            liste.append(Mitglied.objects.create(
                verein=verein, vorname=vor, nachname=f"{nach}-{k}", email=f"{vor.lower()}.{k.lower()}@example.invalid",
                iban="DE02120300000000202051" if i == 1 else "", notizen=MARKE))
        return liste
