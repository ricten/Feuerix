"""EXPERIMENTELL: Kontoumsaetze per FinTS abrufen und als Bankumsaetze speichern (Kommandozeile, ohne TAN-Freigabe).

Die Bank-PIN wird NICHT gespeichert, sondern interaktiv abgefragt. Fuer die Nutzung ist eine bei der
Deutschen Kreditwirtschaft registrierte FinTS-Produkt-ID (FINTS_PRODUCT_ID) erforderlich. Banken verlangen
i.d.R. eine TAN-Freigabe (PSD2) - dieser Kommandozeilen-Weg deckt das NICHT ab und schlaegt bei den meisten
Banken fehl. Fuer den ueblichen Fall (TAN erforderlich) bitte stattdessen *Verwaltung > FinTS-Zugaenge* in
der Weboberflaeche nutzen, die den TAN-Dialog abbildet. Dieses Kommando bleibt fuer Banken/Konfigurationen
ohne TAN-Pflicht bzw. fuer Cron-Jobs nuetzlich.
"""
import getpass
import hashlib
from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core.models import Verein
from apps.finance.models import Bankumsatz


class Command(BaseCommand):
    help = "FinTS-Abruf (experimentell)"

    def add_arguments(self, p):
        p.add_argument("--verein", required=True, help="Kuerzel des Vereins")
        p.add_argument("--blz", required=True)
        p.add_argument("--kennung", required=True, help="Online-Banking-Kennung")
        p.add_argument("--url", required=True, help="FinTS-URL der Bank")
        p.add_argument("--tage", type=int, default=60)

    def handle(self, *a, **o):
        try:
            from fints.client import FinTS3PinTanClient
        except ImportError:
            raise CommandError("python-fints ist nicht installiert.")
        if not settings.FINTS_PRODUCT_ID:
            raise CommandError("FINTS_PRODUCT_ID ist nicht gesetzt.")
        verein = Verein.objects.get(kuerzel=o["verein"])
        pin = getpass.getpass("Bank-PIN: ")
        client = FinTS3PinTanClient(o["blz"], o["kennung"], pin, o["url"], product_id=settings.FINTS_PRODUCT_ID)
        if client.init_tan_response:
            raise CommandError("Die Bank verlangt eine TAN-Freigabe - bitte stattdessen Verwaltung > "
                               "FinTS-Zugaenge in der Weboberflaeche nutzen.")
        neu = 0
        for konto in client.get_sepa_accounts():
            for t in client.get_transactions(konto, date.today() - timedelta(days=o["tage"]), date.today()):
                d = t.data
                betrag = d["amount"].amount
                zweck = d.get("purpose") or ""
                iban = d.get("applicant_iban") or ""
                summe = hashlib.sha1(f"{d['date']}|{betrag}|{iban}|{zweck}".encode()).hexdigest()
                if Bankumsatz.objects.filter(verein=verein, pruefsumme=summe).exists():
                    continue
                Bankumsatz.objects.create(verein=verein, buchungsdatum=d["date"], betrag=betrag,
                                          gegenkonto_name=d.get("applicant_name") or "", gegenkonto_iban=iban,
                                          verwendungszweck=zweck, pruefsumme=summe)
                neu += 1
        self.stdout.write(f"{neu} neue Umsaetze importiert.")
