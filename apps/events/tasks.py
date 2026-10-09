from celery import shared_task

from apps.core.models import Verein

from .services import aufgaben_faellig_benachrichtigen


@shared_task
def aufgaben_faellig_benachrichtigen_task(verein_id):
    aufgaben_faellig_benachrichtigen(Verein.objects.get(pk=verein_id))
