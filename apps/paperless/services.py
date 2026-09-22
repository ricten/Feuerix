from django.utils import timezone

from .client import PaperlessClient, PaperlessFehler


def verbindung_testen(v):
    c = PaperlessClient(v)
    ergebnis = c.verbindung_testen()
    v.letzter_test = ergebnis
    v.save(update_fields=["letzter_test", "geaendert"])
    return ergebnis


def dokument_senden(v, dokument):
    """Lädt ein Ablagedokument zu Paperless hoch und vermerkt Task-ID/Fehler am Dokument."""
    c = PaperlessClient(v)
    dokument.datei.open("rb")
    try:
        inhalt = dokument.datei.read()
    finally:
        dokument.datei.close()
    try:
        task_id = c.dokument_senden(dokument.dateiname, inhalt, titel=dokument.titel, erstellt=dokument.datum,
                                    korrespondent=v.korrespondent, dokumenttyp=v.dokumenttyp, tags=v.tag_liste)
    except PaperlessFehler as e:
        dokument.paperless_fehler = str(e)[:300]
        dokument.save(update_fields=["paperless_fehler", "geaendert"])
        raise
    dokument.paperless_task_id = task_id
    dokument.paperless_gesendet_am = timezone.now()
    dokument.paperless_fehler = ""
    dokument.save(update_fields=["paperless_task_id", "paperless_gesendet_am", "paperless_fehler", "geaendert"])
    return task_id
