import hashlib
from datetime import timedelta

from django.utils import timezone

from .client import PaperlessClient, PaperlessFehler


def verbindung_testen(v):
    c = PaperlessClient(v)
    ergebnis = c.verbindung_testen()
    v.letzter_test = ergebnis
    v.save(update_fields=["letzter_test", "geaendert"])
    return ergebnis


def tags_fuer(v, dokument):
    """Standard-Tags der Verbindung plus die Tags des Dokuments (ohne eigene Tags: Art und Jahr, falls aktiviert)."""
    tags = list(v.tag_liste) + dokument.tag_liste
    if not dokument.tag_liste and v.kategorie_tags:
        tags += dokument.standard_tags
    gesehen, ergebnis = set(), []
    for t in tags:
        if t.lower() not in gesehen:
            gesehen.add(t.lower())
            ergebnis.append(t)
    return ergebnis


def dokumenttyp_fuer(v, dokument):
    """Eigener Dokumenttyp des Dokuments, sonst dessen Art (Kategorie); nur bei "Sonstiges" der Standard der Anbindung."""
    if dokument.dokumenttyp:
        return dokument.dokumenttyp
    if dokument.kategorie != "sonstiges":
        return str(dokument.get_kategorie_display())
    return v.dokumenttyp


def dokument_senden(v, dokument, erneut=False):
    """Lädt ein Ablagedokument zu Paperless hoch und vermerkt Task-ID/Fehler am Dokument.

    Duplikatschutz (außer bei erneut=True): Wurde genau diese Datei (Prüfsumme) schon übergeben, oder kennt
    Paperless sie bereits, wird nichts gesendet. Neue Versionen sind neue Dateien und werden übergeben.
    -> Task-ID, oder None wenn nicht gesendet wurde (Grund steht in dokument.paperless_info)."""
    c = PaperlessClient(v)
    dokument.paperless_status = "sendet"
    dokument.save(update_fields=["paperless_status", "geaendert"])
    try:
        dokument.datei.open("rb")
        try:
            inhalt = dokument.datei.read()
        finally:
            dokument.datei.close()
    except OSError as e:
        dokument.paperless_fehler, dokument.paperless_status = f"Datei nicht lesbar: {e}"[:300], "fehler"
        dokument.save(update_fields=["paperless_fehler", "paperless_status", "geaendert"])
        raise PaperlessFehler(dokument.paperless_fehler)
    summe = hashlib.md5(inhalt, usedforsecurity=False).hexdigest()
    if not erneut:
        if (dokument.paperless_gesendet_am and dokument.paperless_pruefsumme == summe
                and not dokument.paperless_fehler):
            dokument.paperless_info = "Diese Version wurde bereits an Paperless übergeben - nicht erneut gesendet."
            dokument.paperless_status = "uebersprungen"
            dokument.save(update_fields=["paperless_info", "paperless_status", "geaendert"])
            return None
        try:
            vorhanden = c.dokument_finden(summe)
        except PaperlessFehler as e:
            dokument.paperless_fehler, dokument.paperless_status = str(e)[:300], "fehler"
            dokument.save(update_fields=["paperless_fehler", "paperless_status", "geaendert"])
            raise
        if vorhanden:
            dokument.paperless_status = "uebersprungen"
            dokument.paperless_gesendet_am = dokument.paperless_gesendet_am or timezone.now()
            dokument.paperless_pruefsumme = summe
            dokument.paperless_fehler = ""
            dokument.paperless_info = (f"Datei ist in Paperless bereits vorhanden (Dokument-ID {vorhanden}) - "
                                       "nicht erneut gesendet.")
            dokument.save(update_fields=["paperless_gesendet_am", "paperless_pruefsumme", "paperless_fehler",
                                         "paperless_info", "paperless_status", "geaendert"])
            return None
    tags = tags_fuer(v, dokument)
    try:
        task_id = c.dokument_senden(dokument.dateiname, inhalt, titel=dokument.titel, erstellt=dokument.datum,
                                    korrespondent=v.korrespondent, dokumenttyp=dokumenttyp_fuer(v, dokument),
                                    tags=tags)
    except PaperlessFehler as e:
        dokument.paperless_fehler, dokument.paperless_status = str(e)[:300], "fehler"
        dokument.save(update_fields=["paperless_fehler", "paperless_status", "geaendert"])
        raise
    dokument.paperless_task_id = task_id
    dokument.paperless_gesendet_am = timezone.now()
    dokument.paperless_fehler = ""
    dokument.paperless_pruefsumme = summe
    dokument.paperless_info = ""
    dokument.paperless_status = "uebergeben"
    dokument.paperless_tags = ", ".join(tags)
    dokument.save(update_fields=["paperless_task_id", "paperless_gesendet_am", "paperless_fehler",
                                 "paperless_pruefsumme", "paperless_info", "paperless_status", "paperless_tags",
                                 "geaendert"])
    return task_id


AKTIV = ("wartet", "sendet", "uebergeben")
VERARBEITUNG_TIMEOUT_MIN = 10


def status_aktualisieren(v, dokument):
    """Fragt bei laufender Verarbeitung in Paperless den Status der Aufgabe ab (SUCCESS/FAILURE) und
    aktualisiert das Dokument. Nach VERARBEITUNG_TIMEOUT_MIN ohne Ergebnis endet die Abfrage."""
    if not dokument.paperless_status and dokument.paperless_gesendet_am and not dokument.paperless_fehler:
        dokument.paperless_status = "uebergeben"   # vor Einfuehrung des Live-Status uebergeben
    if dokument.paperless_status != "uebergeben":
        return dokument
    c = PaperlessClient(v)
    s = None
    if dokument.paperless_task_id:
        try:
            s = c.aufgabe_status(dokument.paperless_task_id)
        except PaperlessFehler:
            s = None
    if not (s and s["status"] in ("SUCCESS", "FAILURE")) and dokument.paperless_pruefsumme:
        # Zuverlaessiger Gegencheck unabhaengig von der Aufgaben-API: liegt die Datei (Pruefsumme) schon in Paperless?
        try:
            gefunden = c.dokument_finden(dokument.paperless_pruefsumme)
        except PaperlessFehler:
            gefunden = None
        if gefunden:
            s = {"status": "SUCCESS", "ergebnis": "", "dokument_id": gefunden}
    if s and s["status"] == "SUCCESS":
        dokument.paperless_status = "fertig"
        dokument.paperless_info = (f"In Paperless abgelegt (Dokument-ID {s['dokument_id']})."
                                   if s.get("dokument_id") else "In Paperless abgelegt.")
    elif s and s["status"] == "FAILURE":
        dokument.paperless_status = "fehler"
        dokument.paperless_fehler = f"Paperless konnte das Dokument nicht verarbeiten: {s['ergebnis']}"[:300]
    elif (dokument.paperless_gesendet_am
          and timezone.now() - dokument.paperless_gesendet_am > timedelta(minutes=VERARBEITUNG_TIMEOUT_MIN)):
        dokument.paperless_status = "fertig"
        dokument.paperless_info = "Übergeben - die Verarbeitung in Paperless wurde nicht bestätigt (bitte dort prüfen)."
    else:
        return dokument
    dokument.save(update_fields=["paperless_status", "paperless_info", "paperless_fehler", "geaendert"])
    return dokument
