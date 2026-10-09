"""Benachrichtigt die Beobachter:innen einer Aufgabe per E-Mail ueber relevante Aenderungen - unabhaengig
vom Speicherweg (Bearbeiten-Formular, Schnell-Erledigen-Knopf, zukuenftiger Code), da auf Datenbankebene
(pre_save/post_save) statt in einzelnen Views gehakt wird."""
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.core.audit import kontext_var

from .models import Aufgabe
from .services import FELD_LABEL, aufgabe_beobachter_benachrichtigen


def _aktueller_benutzer():
    k = kontext_var.get()
    user = k.get("user") if k else None
    return user if user is not None and getattr(user, "is_authenticated", False) else None


@receiver(pre_save, sender=Aufgabe)
def _aufgabe_vor_speichern(sender, instance, raw=False, **kw):
    instance._beobachter_alt = None
    if not raw and instance.pk:
        instance._beobachter_alt = Aufgabe.objects.filter(pk=instance.pk).values(*FELD_LABEL).first()


@receiver(post_save, sender=Aufgabe)
def _aufgabe_nach_speichern(sender, instance, created, raw=False, **kw):
    if raw or created:
        return
    alt = getattr(instance, "_beobachter_alt", None)
    if alt is None or not instance.beobachter.exists():
        return
    aufgabe_beobachter_benachrichtigen(instance, alt, _aktueller_benutzer())
