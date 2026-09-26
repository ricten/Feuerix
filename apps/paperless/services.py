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


# ------------------------------------------------------------------ Vorstands-Abgleich
VORSTAND_RECHTE = [   # Leserechte plus Hochladen/Bearbeiten von Dokumenten; kein Löschen, keine Verwaltung
    "view_document", "add_document", "change_document", "view_tag", "add_tag", "view_correspondent",
    "add_correspondent", "view_documenttype", "add_documenttype", "view_storagepath"]
_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _startpasswort():
    import secrets
    return "".join(secrets.choice(_ALPHABET) for _ in range(14))


def _benutzername(m):
    from apps.openslides.services import benutzername
    return benutzername(m)


def vorstand_abgleichen(v):
    """Legt für aktive Vorstandsmitglieder Paperless-Benutzer an (Gruppe `vorstand_gruppe`), aktualisiert Namen/E-Mail
    und entfernt ausgeschiedene Mitglieder aus der Gruppe (selbst angelegte Konten werden zusätzlich deaktiviert).
    Es werden nie Konten gelöscht und nie Administrator-/Superuser-Rechte vergeben.
    -> Ergebnistext (auch in der Anbindung gespeichert)."""
    from apps.members.models import Mitglied
    from .models import PaperlessBenutzer
    c = PaperlessClient(v)
    gruppe_id = c.gruppe_sicherstellen(v.vorstand_gruppe or "Vorstand", VORSTAND_RECHTE)
    soll = list(Mitglied.objects.filter(verein=v.verein, status="aktiv", vorstandsmitglied=True))
    soll_ids = {m.pk for m in soll}
    neu = akt = entfernt = 0
    fehler = []
    for m in soll:
        try:
            verkn = PaperlessBenutzer.objects.filter(mitglied=m).first()
            if verkn is not None:
                daten = {"first_name": m.vorname, "last_name": m.nachname, "groups": [gruppe_id]}
                if verkn.angelegt:
                    daten["is_active"] = True
                if m.email:
                    daten["email"] = m.email
                c.benutzer_aendern(verkn.paperless_id, daten)
                akt += 1
                continue
            name = _benutzername(m)
            vorhanden = c.benutzer_suchen(name)
            if vorhanden:   # bestehendes Konto nur der Gruppe zuordnen, nie uebernehmen/veraendern/deaktivieren
                gruppen = sorted(set(vorhanden.get("groups") or []) | {gruppe_id})
                c.benutzer_aendern(vorhanden["id"], {"groups": gruppen})
                PaperlessBenutzer.objects.create(verein=v.verein, mitglied=m, paperless_id=vorhanden["id"],
                                                 benutzername=name, angelegt=False)
                akt += 1
                continue
            pw = _startpasswort()
            daten = {"username": name, "password": pw, "first_name": m.vorname, "last_name": m.nachname,
                     "email": m.email or "", "is_active": True, "is_staff": False, "is_superuser": False,
                     "groups": [gruppe_id]}
            uid = c.benutzer_anlegen(daten)
            PaperlessBenutzer.objects.create(verein=v.verein, mitglied=m, paperless_id=uid, benutzername=name,
                                             angelegt=True, initialpasswort=pw)
            neu += 1
        except PaperlessFehler as e:
            fehler.append(f"{m.name}: {e}")
    for verkn in PaperlessBenutzer.objects.filter(verein=v.verein).exclude(mitglied_id__in=soll_ids):
        try:
            aktuell = c.benutzer_lesen(verkn.paperless_id) or {}
            gruppen = [g for g in (aktuell.get("groups") or []) if g != gruppe_id]
            daten = {"groups": gruppen}
            if verkn.angelegt:
                daten["is_active"] = False
            c.benutzer_aendern(verkn.paperless_id, daten)
            verkn.delete()
            entfernt += 1
        except PaperlessFehler as e:
            fehler.append(f"{verkn.benutzername} (entfernen): {e}")
    info = f"{neu} Benutzer angelegt, {akt} aktualisiert, {entfernt} aus dem Vorstand entfernt, {len(fehler)} Fehler."
    if fehler:
        info += "\n" + "\n".join(fehler[:20])
    v.letzter_abgleich_am, v.letzter_abgleich_info = timezone.now(), info
    v.save(update_fields=["letzter_abgleich_am", "letzter_abgleich_info", "geaendert"])
    return info


def mitglied_anonymisieren(v, mitglied):
    """DSGVO-Anonymisierung auf das verknüpfte Paperless-Konto übertragen: Name/E-Mail überschreiben, aus der
    Vorstandsgruppe entfernen; selbst angelegte Konten werden deaktiviert. Die Verknüpfung wird gelöscht."""
    from .models import PaperlessBenutzer
    verkn = PaperlessBenutzer.objects.filter(mitglied=mitglied).first()
    if verkn is None:
        return
    c = PaperlessClient(v)
    if verkn.angelegt:
        c.benutzer_aendern(verkn.paperless_id, {
            "first_name": "Anonymisiert", "last_name": f"#{mitglied.mitgliedsnummer}", "email": "",
            "is_active": False, "groups": []})
    else:
        aktuell = c.benutzer_lesen(verkn.paperless_id) or {}
        gruppen = c.gruppen_ohne(aktuell.get("groups") or [], v.vorstand_gruppe or "Vorstand")
        c.benutzer_aendern(verkn.paperless_id, {"groups": gruppen})
    verkn.delete()
