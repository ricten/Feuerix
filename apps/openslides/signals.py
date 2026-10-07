from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import SuperadminKonto


@receiver(pre_delete, sender=SuperadminKonto)
def openslides_konto_deaktivieren(sender, instance, **kwargs):
    """Deaktiviert das verknüpfte OpenSlides-Konto, bevor die Verknüpfung gelöscht wird - auch wenn das über eine
    Kaskade passiert (Benutzerzugang direkt gelöscht statt über den regulären Abgleich, z. B. beim Löschen eines
    Superadmin-Zugangs ohne eigene Mitgliedsakte)."""
    from .client import OpenSlidesFehler, OSClient
    from .models import OpenSlidesVerbindung
    v = OpenSlidesVerbindung.objects.filter(verein_id=instance.verein_id).first()
    if v is None:
        return
    try:
        c = OSClient(v)
        c.login()
        c.action("user.update", [{"id": instance.openslides_user_id, "is_active": False}])
    except OpenSlidesFehler:
        pass
