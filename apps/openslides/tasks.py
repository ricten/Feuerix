from celery import shared_task

from .client import OpenSlidesFehler
from .models import OpenSlidesVerbindung
from .services import mitglieder_abgleichen


@shared_task
def abgleich_task(verbindung_id):
    v = OpenSlidesVerbindung.objects.select_related("verein").get(pk=verbindung_id)
    try:
        mitglieder_abgleichen(v)
    except OpenSlidesFehler as e:
        from django.utils import timezone
        v.letzter_abgleich_am, v.letzter_abgleich_info = timezone.now(), f"Abbruch: {e}"
        v.save(update_fields=["letzter_abgleich_am", "letzter_abgleich_info", "geaendert"])
