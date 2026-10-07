from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import PaperlessBenutzer


@receiver(pre_delete, sender=PaperlessBenutzer)
def paperless_konto_aufraeumen(sender, instance, **kwargs):
    """Räumt das verknüpfte Paperless-Konto auf, bevor die Verknüpfung gelöscht wird - auch wenn das über eine
    Kaskade passiert (Mitglied oder Benutzerzugang direkt gelöscht statt über den regulären Abgleich, z. B. beim
    Löschen eines Superadmin-Zugangs). Selbst angelegte Konten werden deaktiviert, übernommene nur aus den
    verwalteten Gruppen entfernt (wie beim regulären Abgleich: nie verändert/deaktiviert)."""
    from .client import PaperlessClient, PaperlessFehler
    from .models import PaperlessVerbindung
    from .services import _verwaltete_gruppennamen
    v = PaperlessVerbindung.objects.filter(verein_id=instance.verein_id).first()
    if v is None:
        return
    c = PaperlessClient(v)
    try:
        if instance.angelegt:
            c.benutzer_aendern(instance.paperless_id, {"is_active": False})
        else:
            aktuell = c.benutzer_lesen(instance.paperless_id) or {}
            c.benutzer_aendern(instance.paperless_id,
                               {"groups": c.gruppen_ohne(aktuell.get("groups") or [], _verwaltete_gruppennamen(v))})
    except PaperlessFehler:
        pass
