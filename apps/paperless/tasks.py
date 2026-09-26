from celery import shared_task

from .client import PaperlessFehler
from .models import PaperlessVerbindung
from .services import dokument_senden


@shared_task
def senden_task(verbindung_id, dokument_id, erneut=False):
    from apps.documents.models import Ablagedokument
    v = PaperlessVerbindung.objects.get(pk=verbindung_id)
    d = Ablagedokument.objects.get(pk=dokument_id)
    try:
        dokument_senden(v, d, erneut=erneut)
    except PaperlessFehler:
        pass  # Fehlermeldung wurde bereits am Dokument (paperless_fehler) gespeichert


@shared_task
def sammel_senden_task(verbindung_id, dokument_ids, erneut=False):
    for dokument_id in dokument_ids:
        senden_task(verbindung_id, dokument_id, erneut)
