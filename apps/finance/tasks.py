from celery import shared_task

from .models import Rechnung
from .services import rechnung_mailen


@shared_task
def rechnung_mailen_task(rechnung_id):
    r = Rechnung.objects.select_related("mitglied", "verein").get(pk=rechnung_id)
    if r.versendet_am is None:
        rechnung_mailen(r)
