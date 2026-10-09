from datetime import date

from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

from .models import Aufgabe

FELD_LABEL = {"titel": "Aufgabe", "status": "Status", "faellig": "Fällig bis", "beschreibung": "Beschreibung",
             "ergebnis": "Ergebnis", "zustaendig_id": "Zuständig (Mitglied)",
             "zustaendig_benutzer_id": "Zuständig (Administrator)", "veranstaltung_id": "Veranstaltung"}
STATUS_LABEL = dict(Aufgabe.STATUS)


def _feldwert(feld, wert):
    if feld == "status":
        return STATUS_LABEL.get(wert, wert)
    return wert if wert not in (None, "") else "–"


def aufgabe_beobachter_benachrichtigen(aufgabe, alt, aendernde_person=None):
    """Informiert alle Beobachter:innen einer Aufgabe per E-Mail über die geänderten Felder (alt -> neu) -
    ausser die Person, die die Änderung selbst vorgenommen hat. Mail-/Netzwerkfehler werden pro Empfänger
    abgefangen, damit ein Fehler nicht die übrigen Benachrichtigungen verhindert."""
    geaendert = {f: (alt[f], getattr(aufgabe, f)) for f in FELD_LABEL if alt.get(f) != getattr(aufgabe, f)}
    if not geaendert:
        return 0
    empfaenger = aufgabe.beobachter.exclude(pk=aendernde_person.pk) if aendernde_person else aufgabe.beobachter.all()
    n = 0
    for b in empfaenger.exclude(email=""):
        zeilen = [f"- {FELD_LABEL[f]}: {_feldwert(f, altw)} → {_feldwert(f, neuw)}" for f, (altw, neuw) in geaendert.items()]
        text = (f"Guten Tag {b.get_full_name() or b.get_username()},\n\ndie Aufgabe \"{aufgabe.titel}\" hat sich "
               f"geändert:\n" + "\n".join(zeilen) + f"\n\nMit freundlichen Grüßen\n{aufgabe.verein.name}")
        try:
            EmailMessage(subject=f"{aufgabe.verein.name}: Aufgabe geändert – {aufgabe.titel}", body=text,
                        from_email=settings.DEFAULT_FROM_EMAIL, to=[b.email]).send()
            n += 1
        except Exception:
            continue
    return n


def aufgabe_beobachter_notiz_benachrichtigen(notiz):
    """Informiert alle Beobachter:innen einer Aufgabe über eine neue Zwischennotiz - ausser der Person, die
    sie geschrieben hat (anhand des gespeicherten Namens, da nur der Benutzername protokolliert wird)."""
    aufgabe = notiz.aufgabe
    empfaenger = aufgabe.beobachter.exclude(username=notiz.erstellt_von) if notiz.erstellt_von else aufgabe.beobachter.all()
    n = 0
    for b in empfaenger.exclude(email=""):
        text = (f"Guten Tag {b.get_full_name() or b.get_username()},\n\nneue Zwischennotiz zur Aufgabe "
               f"\"{aufgabe.titel}\" von {notiz.erstellt_von or 'System'}:\n\n{notiz.text}\n\n"
               f"Mit freundlichen Grüßen\n{aufgabe.verein.name}")
        try:
            EmailMessage(subject=f"{aufgabe.verein.name}: Neue Notiz – {aufgabe.titel}", body=text,
                        from_email=settings.DEFAULT_FROM_EMAIL, to=[b.email]).send()
            n += 1
        except Exception:
            continue
    return n


def aufgaben_faellig_benachrichtigen(verein):
    """Verschickt eine E-Mail an die/den Zuständige(n) einer Aufgabe, sobald ihre Fälligkeit überschritten ist
    (noch nicht erledigt) - je Aufgabe nur einmal (benachrichtigt_am), kein täglicher Spam bei wiederholtem
    Aufruf. Zuständig kann ein Mitglied oder ein Administrator (Benutzer mit Zugang, z. B. ohne eigene
    Mitgliedschaft) sein - Aufgaben ganz ohne Zuständigen oder ohne hinterlegte E-Mail-Adresse werden
    übersprungen (keine Benachrichtigungsmöglichkeit). Netzwerk-/Mailfehler werden pro Aufgabe abgefangen,
    damit ein Fehler nicht die Benachrichtigung der übrigen überfälligen Aufgaben verhindert.
    -> Anzahl verschickter Mails."""
    ueberfaellig = (Aufgabe.objects.filter(verein=verein, faellig__lt=date.today(), benachrichtigt_am__isnull=True)
                    .exclude(status="erledigt")
                    .exclude(zustaendig__isnull=True, zustaendig_benutzer__isnull=True)
                    .select_related("zustaendig", "zustaendig_benutzer", "veranstaltung"))
    n = 0
    for a in ueberfaellig:
        email = a.zustaendig_email
        if not email:
            continue
        text = (f"Guten Tag {a.wer_zustaendig},\n\ndie Aufgabe \"{a.titel}\" war fällig bis "
               f"{a.faellig:%d.%m.%Y} und ist noch nicht erledigt.")
        if a.veranstaltung_id:
            text += f"\nVeranstaltung: {a.veranstaltung.titel}"
        if a.beschreibung:
            text += f"\n\n{a.beschreibung}"
        text += f"\n\nMit freundlichen Grüßen\n{verein.name}"
        try:
            EmailMessage(subject=f"{verein.name}: Aufgabe überfällig – {a.titel}", body=text,
                        from_email=settings.DEFAULT_FROM_EMAIL, to=[email]).send()
        except Exception:
            continue
        a.benachrichtigt_am = timezone.now()
        a.save(update_fields=["benachrichtigt_am"])
        n += 1
    return n
