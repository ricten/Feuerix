from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .models import Systemeinstellung


@shared_task
def update_pruefen_task():
    """Prüft die neueste veröffentlichte Version gegen UPDATE_CHECK_URL (Standard: die VERSION-Datei im
    offiziellen Feuerix-Repository) und merkt sie in den Systemeinstellungen vor, damit ein Administrator die
    Update-Benachrichtigung beim nächsten Aufruf sieht. Netzwerkfehler werden bewusst verschluckt - der
    nächste fällige Aufruf versucht es erneut."""
    if not settings.UPDATE_CHECK_URL:
        return
    se = Systemeinstellung.laden()
    se.update_geprueft_am = timezone.now()
    try:
        import requests
        r = requests.get(settings.UPDATE_CHECK_URL, timeout=10)
        r.raise_for_status()
        se.update_verfuegbare_version = r.text.strip()[:20]
    except Exception:
        pass
    # kein update_fields: Systemeinstellung.laden() kann eine noch ungespeicherte Instanz (pk=None) liefern,
    # wenn noch kein Datensatz existiert - update_fields erfordert aber einen bereits existierenden Datensatz.
    se.save()


@shared_task
def datensicherung_task():
    """Fuehrt die Datensicherung sofort aus (Knopf "Jetzt sichern")."""
    from .datensicherung import sicherung_ausfuehren
    sicherung_ausfuehren()


@shared_task
def datensicherung_faellig_task():
    """Wird stuendlich von Celery Beat gestartet und sichert, sobald die eingestellte Uhrzeit des Tages erreicht
    ist und heute noch nicht gesichert wurde."""
    from .datensicherung import faellig, sicherung_ausfuehren
    se = Systemeinstellung.laden()
    if faellig(se):
        sicherung_ausfuehren(se)
