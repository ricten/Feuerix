from datetime import date

from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

from .models import Aufgabe


def aufgaben_faellig_benachrichtigen(verein):
    """Verschickt eine E-Mail an die/den Zuständige(n) einer Aufgabe, sobald ihre Fälligkeit überschritten ist
    (noch nicht erledigt) - je Aufgabe nur einmal (benachrichtigt_am), kein täglicher Spam bei wiederholtem
    Aufruf. Aufgaben ohne Zuständigen oder ohne hinterlegte E-Mail-Adresse werden übersprungen (keine
    Benachrichtigungsmöglichkeit). Netzwerk-/Mailfehler werden pro Aufgabe abgefangen, damit ein Fehler nicht
    die Benachrichtigung der übrigen überfälligen Aufgaben verhindert. -> Anzahl verschickter Mails."""
    ueberfaellig = (Aufgabe.objects.filter(verein=verein, faellig__lt=date.today(), benachrichtigt_am__isnull=True)
                    .exclude(status="erledigt").exclude(zustaendig__isnull=True).exclude(zustaendig__email="")
                    .select_related("zustaendig", "veranstaltung"))
    n = 0
    for a in ueberfaellig:
        text = (f"Guten Tag {a.zustaendig.name},\n\ndie Aufgabe \"{a.titel}\" war fällig bis "
               f"{a.faellig:%d.%m.%Y} und ist noch nicht erledigt.")
        if a.veranstaltung_id:
            text += f"\nVeranstaltung: {a.veranstaltung.titel}"
        if a.beschreibung:
            text += f"\n\n{a.beschreibung}"
        text += f"\n\nMit freundlichen Grüßen\n{verein.name}"
        try:
            EmailMessage(subject=f"{verein.name}: Aufgabe überfällig – {a.titel}", body=text,
                        from_email=settings.DEFAULT_FROM_EMAIL, to=[a.zustaendig.email]).send()
        except Exception:
            continue
        a.benachrichtigt_am = timezone.now()
        a.save(update_fields=["benachrichtigt_am"])
        n += 1
    return n
