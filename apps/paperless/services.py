import hashlib

from django.utils import timezone

from .client import PaperlessClient, PaperlessFehler


def verbindung_testen(v):
    c = PaperlessClient(v)
    ergebnis = c.verbindung_testen()
    v.letzter_test = ergebnis
    v.save(update_fields=["letzter_test", "geaendert"])
    return ergebnis


def tags_fuer(v, dokument):
    """Standard-Tags der Verbindung plus (falls aktiviert) die Ablage-Kategorie des Dokuments."""
    tags = list(v.tag_liste)
    if v.kategorie_tags:
        tags.append(str(dokument.get_kategorie_display()))
    gesehen, ergebnis = set(), []
    for t in tags:
        if t.lower() not in gesehen:
            gesehen.add(t.lower())
            ergebnis.append(t)
    return ergebnis


def dokument_senden(v, dokument, erneut=False):
    """Lädt ein Ablagedokument zu Paperless hoch und vermerkt Task-ID/Fehler am Dokument.

    Duplikatschutz (außer bei erneut=True): Wurde genau diese Datei (Prüfsumme) schon übergeben, oder kennt
    Paperless sie bereits, wird nichts gesendet. Neue Versionen sind neue Dateien und werden übergeben.
    -> Task-ID, oder None wenn nicht gesendet wurde (Grund steht in dokument.paperless_info)."""
    c = PaperlessClient(v)
    dokument.datei.open("rb")
    try:
        inhalt = dokument.datei.read()
    finally:
        dokument.datei.close()
    summe = hashlib.md5(inhalt, usedforsecurity=False).hexdigest()
    if not erneut:
        if (dokument.paperless_gesendet_am and dokument.paperless_pruefsumme == summe
                and not dokument.paperless_fehler):
            dokument.paperless_info = "Diese Version wurde bereits an Paperless übergeben - nicht erneut gesendet."
            dokument.save(update_fields=["paperless_info", "geaendert"])
            return None
        try:
            vorhanden = c.dokument_finden(summe)
        except PaperlessFehler as e:
            dokument.paperless_fehler = str(e)[:300]
            dokument.save(update_fields=["paperless_fehler", "geaendert"])
            raise
        if vorhanden:
            dokument.paperless_gesendet_am = dokument.paperless_gesendet_am or timezone.now()
            dokument.paperless_pruefsumme = summe
            dokument.paperless_fehler = ""
            dokument.paperless_info = (f"Datei ist in Paperless bereits vorhanden (Dokument-ID {vorhanden}) - "
                                       "nicht erneut gesendet.")
            dokument.save(update_fields=["paperless_gesendet_am", "paperless_pruefsumme", "paperless_fehler",
                                         "paperless_info", "geaendert"])
            return None
    try:
        task_id = c.dokument_senden(dokument.dateiname, inhalt, titel=dokument.titel, erstellt=dokument.datum,
                                    korrespondent=v.korrespondent, dokumenttyp=v.dokumenttyp,
                                    tags=tags_fuer(v, dokument))
    except PaperlessFehler as e:
        dokument.paperless_fehler = str(e)[:300]
        dokument.save(update_fields=["paperless_fehler", "geaendert"])
        raise
    dokument.paperless_task_id = task_id
    dokument.paperless_gesendet_am = timezone.now()
    dokument.paperless_fehler = ""
    dokument.paperless_pruefsumme = summe
    dokument.paperless_info = ""
    dokument.save(update_fields=["paperless_task_id", "paperless_gesendet_am", "paperless_fehler",
                                 "paperless_pruefsumme", "paperless_info", "geaendert"])
    return task_id
