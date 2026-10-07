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
VORSTAND_LESERECHTE = ["view_document", "view_tag", "view_correspondent", "view_documenttype",
                       "view_storagepath"]
_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _startpasswort():
    import secrets
    return "".join(secrets.choice(_ALPHABET) for _ in range(14))


def _benutzername(m):
    from apps.openslides.services import benutzername
    return benutzername(m)


def _benutzername_zugang(z):
    from apps.core.util import ascii_kennung
    n = f"{ascii_kennung(z.user.first_name)}.{ascii_kennung(z.user.last_name)}".strip(".")
    return n if len(n) > 2 else (ascii_kennung(z.user.get_username()) or f"zugang{z.pk}")


def _superadmin_zugaenge(verein):
    """Aktive Benutzerzugänge mit Rolle "Superadministrator" (Rechte-Bypass, siehe rechte.py) - unabhängig von
    Tags sollen sie automatisch auch Paperless-Zugriff bekommen (Administrator-Gruppe)."""
    from apps.core.models import Zugang
    return list(Zugang.objects.filter(verein=verein, aktiv=True, rolle__ist_superadmin=True).select_related("user"))


def _gruppenbedarf(v):
    """-> ({mitglied_pk: {gruppenname}}, {gruppenname: nur_lesen}, [Mitglieder], [Superadmin-Zugänge ohne
    Mitgliedsakte]) aus den Tags (Paperless-Gruppe) sowie den Superadmin-Benutzerzugängen (bekommen automatisch
    volle Rechte in der Administrator-Gruppe, auch ohne eigenes Tag)."""
    from apps.core.matrix import ADMINISTRATOR
    from apps.members.models import Mitglied, MitgliedTag
    tags = list(MitgliedTag.objects.filter(verein=v.verein).exclude(paperless_gruppe=""))
    gruppen = {}
    for t in tags:   # eine Gruppe ist nur "nur lesen", wenn es alle Tags dazu sind
        gruppen[t.paperless_gruppe] = gruppen.get(t.paperless_gruppe, True) and t.paperless_nur_lesen
    mitglieder = list(Mitglied.objects.filter(verein=v.verein, status="aktiv", tags__in=tags).distinct())
    zuordnung = {m.pk: {t.paperless_gruppe for t in m.tags.all() if t.paperless_gruppe} for m in mitglieder}

    superadmins = _superadmin_zugaenge(v.verein)
    zugang_ohne_mitglied = []
    if superadmins:
        gruppen[ADMINISTRATOR] = False   # volle Rechte, keine Nur-Lesen-Gruppe
        user_ids = {z.user_id for z in superadmins}
        mitglied_je_user = {m.benutzer_id: m for m in
                            Mitglied.objects.filter(verein=v.verein, status="aktiv", benutzer_id__in=user_ids)}
        for z in superadmins:
            m = mitglied_je_user.get(z.user_id)
            if m is not None:
                if m.pk not in zuordnung:
                    zuordnung[m.pk] = set()
                    mitglieder.append(m)
                zuordnung[m.pk].add(ADMINISTRATOR)
            else:
                zugang_ohne_mitglied.append(z)
    return zuordnung, gruppen, mitglieder, zugang_ohne_mitglied


def vorstand_abgleichen(v):
    """Gleicht Paperless-Benutzer anhand der Tags der Mitglieder ab: Träger eines Tags mit Paperless-Gruppe erhalten
    ein Konto (ohne Administrator-Rechte) in den Gruppen ihrer Tags; wer keine solchen Tags mehr hat, wird aus den
    verwalteten Gruppen entfernt (selbst angelegte Konten zusätzlich deaktiviert). Gruppen, die nicht durch Tags
    verwaltet werden, bleiben unberührt. Zusätzlich bekommen alle Superadministratoren automatisch ein Konto in
    der Administrator-Gruppe (mit oder ohne eigene Mitgliedsakte) - unabhängig von Tags. Es werden nie Konten
    gelöscht.
    -> Ergebnistext (auch in der Anbindung gespeichert)."""
    from apps.core.matrix import ADMINISTRATOR

    from .models import PaperlessBenutzer
    c = PaperlessClient(v)
    zuordnung, gruppen, soll, superadmin_zugaenge = _gruppenbedarf(v)
    benoetigt = set().union(*zuordnung.values()) if zuordnung else set()
    if superadmin_zugaenge:
        benoetigt.add(ADMINISTRATOR)
    ids = {name: c.gruppe_sicherstellen(name, VORSTAND_LESERECHTE if lesen else VORSTAND_RECHTE)
           for name, lesen in gruppen.items() if name in benoetigt}
    verwaltet = set(ids.values())
    for name in gruppen:   # nicht benoetigte Gruppen nur nachschlagen (nicht anlegen), um Mitglieder korrekt zu entfernen
        if name not in ids:
            gid = c.gruppe_finden(name)
            if gid:
                verwaltet.add(gid)
    soll_ids = {m.pk for m in soll}
    neu = akt = entfernt = 0
    fehler = []

    def ziel_gruppen(aktuell, m):
        return sorted((set(aktuell) - verwaltet) | {ids[n] for n in zuordnung[m.pk]})

    for m in soll:
        try:
            verkn = PaperlessBenutzer.objects.filter(mitglied=m).first()
            if verkn is not None:
                aktuell = (c.benutzer_lesen(verkn.paperless_id) or {}).get("groups") or []
                daten = {"first_name": m.vorname, "last_name": m.nachname, "groups": ziel_gruppen(aktuell, m)}
                if verkn.angelegt:
                    daten["is_active"] = True
                if m.email:
                    daten["email"] = m.email
                c.benutzer_aendern(verkn.paperless_id, daten)
                akt += 1
                continue
            name = _benutzername(m)
            vorhanden = c.benutzer_suchen(name)
            if vorhanden:   # bestehendes Konto nur den Gruppen zuordnen, nie uebernehmen/veraendern/deaktivieren
                c.benutzer_aendern(vorhanden["id"], {"groups": ziel_gruppen(vorhanden.get("groups") or [], m)})
                PaperlessBenutzer.objects.create(verein=v.verein, mitglied=m, paperless_id=vorhanden["id"],
                                                 benutzername=name, angelegt=False)
                akt += 1
                continue
            pw = _startpasswort()
            daten = {"username": name, "password": pw, "first_name": m.vorname, "last_name": m.nachname,
                     "email": m.email or "", "is_active": True, "is_staff": False, "is_superuser": False,
                     "groups": ziel_gruppen([], m)}
            uid = c.benutzer_anlegen(daten)
            PaperlessBenutzer.objects.create(verein=v.verein, mitglied=m, paperless_id=uid, benutzername=name,
                                             angelegt=True, initialpasswort=pw)
            neu += 1
        except PaperlessFehler as e:
            fehler.append(f"{m.name}: {e}")
    for verkn in PaperlessBenutzer.objects.filter(verein=v.verein, mitglied_id__isnull=False).exclude(
            mitglied_id__in=soll_ids):
        try:
            aktuell = (c.benutzer_lesen(verkn.paperless_id) or {}).get("groups") or []
            daten = {"groups": sorted(set(aktuell) - verwaltet)}
            if verkn.angelegt:
                daten["is_active"] = False
            c.benutzer_aendern(verkn.paperless_id, daten)
            verkn.delete()
            entfernt += 1
        except PaperlessFehler as e:
            fehler.append(f"{verkn.benutzername} (entfernen): {e}")

    # Superadmin-Zugänge ohne eigene Mitgliedsakte: gleiche Logik, Name/E-Mail vom Benutzerkonto statt vom Mitglied
    admin_gruppen_ids = sorted({ids[ADMINISTRATOR]}) if ADMINISTRATOR in ids else []
    superadmin_ids = {z.pk for z in superadmin_zugaenge}
    for z in superadmin_zugaenge:
        vorname, nachname, email = z.user.first_name or z.user.get_username(), z.user.last_name or "(Superadmin)", z.user.email
        try:
            verkn = PaperlessBenutzer.objects.filter(zugang=z).first()
            if verkn is not None:
                aktuell = (c.benutzer_lesen(verkn.paperless_id) or {}).get("groups") or []
                daten = {"first_name": vorname, "last_name": nachname,
                         "groups": sorted((set(aktuell) - verwaltet) | set(admin_gruppen_ids))}
                if verkn.angelegt:
                    daten["is_active"] = True
                if email:
                    daten["email"] = email
                c.benutzer_aendern(verkn.paperless_id, daten)
                akt += 1
                continue
            name = _benutzername_zugang(z)
            vorhanden = c.benutzer_suchen(name)
            if vorhanden:
                c.benutzer_aendern(vorhanden["id"], {
                    "groups": sorted((set(vorhanden.get("groups") or []) - verwaltet) | set(admin_gruppen_ids))})
                PaperlessBenutzer.objects.create(verein=v.verein, zugang=z, paperless_id=vorhanden["id"],
                                                 benutzername=name, angelegt=False)
                akt += 1
                continue
            pw = _startpasswort()
            daten = {"username": name, "password": pw, "first_name": vorname, "last_name": nachname,
                     "email": email or "", "is_active": True, "is_staff": False, "is_superuser": False,
                     "groups": admin_gruppen_ids}
            uid = c.benutzer_anlegen(daten)
            PaperlessBenutzer.objects.create(verein=v.verein, zugang=z, paperless_id=uid, benutzername=name,
                                             angelegt=True, initialpasswort=pw)
            neu += 1
        except PaperlessFehler as e:
            fehler.append(f"{z.user}: {e}")
    for verkn in PaperlessBenutzer.objects.filter(verein=v.verein, zugang_id__isnull=False).exclude(
            zugang_id__in=superadmin_ids):
        try:
            aktuell = (c.benutzer_lesen(verkn.paperless_id) or {}).get("groups") or []
            daten = {"groups": sorted(set(aktuell) - verwaltet)}
            if verkn.angelegt:
                daten["is_active"] = False
            c.benutzer_aendern(verkn.paperless_id, daten)
            verkn.delete()
            entfernt += 1
        except PaperlessFehler as e:
            fehler.append(f"{verkn.benutzername} (entfernen): {e}")

    info = f"{neu} Benutzer angelegt, {akt} aktualisiert, {entfernt} ohne Tag entfernt, {len(fehler)} Fehler."
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
        gruppen = c.gruppen_ohne(aktuell.get("groups") or [], _verwaltete_gruppennamen(v))
        c.benutzer_aendern(verkn.paperless_id, {"groups": gruppen})
    verkn.delete()


def _verwaltete_gruppennamen(v):
    from apps.members.models import MitgliedTag
    return set(MitgliedTag.objects.filter(verein=v.verein).exclude(paperless_gruppe="").values_list(
        "paperless_gruppe", flat=True))
