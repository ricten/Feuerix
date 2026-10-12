from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.core import zweifaktor


class Command(BaseCommand):
    help = ("Entsperrt ein wegen Fehlversuchen gesperrtes Konto und setzt auf Wunsch die Zwei-Faktor-Anmeldung "
            "zurück (z. B. wenn Authenticator und Wiederherstellungscodes verloren sind).")

    def add_arguments(self, parser):
        parser.add_argument("benutzername")
        parser.add_argument("--2fa-zuruecksetzen", action="store_true", dest="zf", help="2FA des Kontos löschen")

    def handle(self, *args, **o):
        U = get_user_model()
        try:
            user = U.objects.get(**{U.USERNAME_FIELD: o["benutzername"]})
        except U.DoesNotExist:
            raise CommandError("Benutzer nicht gefunden.")
        zweifaktor.entsperren(user, zweifaktor_zuruecksetzen=o["zf"])
        self.stdout.write(self.style.SUCCESS(
            f"{user} entsperrt" + (", 2FA zurückgesetzt (bei Superadmins Einrichtung bei nächster Anmeldung)." if o["zf"] else ".")))
