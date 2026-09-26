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


@shared_task
def fertiges_dokument_task(art, pk):
    """Erzeugt das PDF eines fertiggestellten Dokuments (Rechnung/Zuwendungsbestätigung), legt es in der Ablage
    ab und übergibt es an Paperless."""
    from apps.documents.services import ablegen
    if art == "rechnung":
        from apps.finance.erechnung import zugferd_pdf
        from apps.finance.models import Rechnung
        from apps.finance.pdf import rechnung_pdf
        obj = Rechnung.objects.get(pk=pk)
        try:
            pdf = zugferd_pdf(obj)   # E-Rechnung (ZUGFeRD/Factur-X), sonst normale PDF-Rechnung
        except Exception:
            pdf = rechnung_pdf(obj)
        titel, kat, datum, name = f"{obj.get_typ_display()} {obj.nummer}", "rechnung", obj.datum, obj.nummer
    elif art == "zuwendung":
        from apps.donations.models import Zuwendungsbestaetigung
        from apps.donations.pdf import zuwendungsbestaetigung_pdf
        obj = Zuwendungsbestaetigung.objects.get(pk=pk)
        pdf = zuwendungsbestaetigung_pdf(obj)
        titel, kat, datum, name = f"Zuwendungsbestätigung {obj.nummer}", "zuwendung", obj.ausgestellt_am, obj.nummer
    else:
        return
    d = ablegen(obj.verein, titel, kat, f"{name}.pdf", pdf, datum=datum)
    from . import auto
    v = auto.verbindung(obj.verein)
    if v is None:
        return
    try:
        dokument_senden(v, d)
    except PaperlessFehler:
        pass  # Fehler steht am Ablage-Dokument
