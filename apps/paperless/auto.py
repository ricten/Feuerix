"""Automatische Übergabe fertiggestellter Dokumente an Paperless (wenn in der Anbindung aktiviert).

Alle Einstiege sind bewusst fehlertolerant: ein Problem bei Paperless/Broker darf das Fertigstellen (z. B. das
Ausstellen einer Rechnung) niemals verhindern - der Fehler landet stattdessen am Ablage-Dokument.
"""
import logging

from django.db import transaction

from .models import PaperlessVerbindung

log = logging.getLogger(__name__)


def verbindung(verein):
    v = PaperlessVerbindung.objects.filter(verein=verein, aktiv=True, auto_uebergabe=True).first()
    return v if v and v.url and v.api_token else None


def ablage_fertig(dokument):
    """Ein bereits abgelegtes, fertiges Dokument automatisch übergeben."""
    v = verbindung(dokument.verein)
    if v is None or not dokument.datei:
        return False
    from apps.documents.models import Ablagedokument
    from .tasks import senden_task
    Ablagedokument.objects.filter(pk=dokument.pk).update(paperless_status="wartet", paperless_fehler="",
                                                         paperless_info="")

    def starten():
        try:
            senden_task.delay(v.pk, dokument.pk)
        except Exception as e:  # z. B. Broker nicht erreichbar
            log.warning("Automatische Paperless-Übergabe nicht gestartet: %s", e)
            Ablagedokument.objects.filter(pk=dokument.pk).update(
                paperless_status="fehler", paperless_fehler=f"Übergabe konnte nicht gestartet werden: {e}"[:300])
    transaction.on_commit(starten)
    return True


def fertiges_dokument(art, pk, verein):
    """Rechnung ("rechnung") bzw. Zuwendungsbestätigung ("zuwendung") als PDF erzeugen, ablegen und übergeben."""
    if verbindung(verein) is None:
        return False
    from .tasks import fertiges_dokument_task

    def starten():
        try:
            fertiges_dokument_task.delay(art, pk)
        except Exception as e:
            log.warning("Automatische Paperless-Übergabe nicht gestartet: %s", e)
    transaction.on_commit(starten)
    return True
