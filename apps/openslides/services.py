import re
import secrets
from datetime import date
from html import unescape
from decimal import Decimal, InvalidOperation

from django.db.models import Q
from django.utils import timezone

from apps.core.util import ascii_kennung
from apps.events.models import Anwesenheit, Wahlergebnis
from apps.members.models import Mitglied

from .client import OpenSlidesFehler, OSClient
from .models import OpenSlidesVerbindung

POLL_ABGESCHLOSSEN = ("finished", "published")

ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def benutzername(m):
    n = f"{ascii_kennung(m.vorname)}.{ascii_kennung(m.nachname)}".strip(".")
    return n if len(n) > 2 else f"mitglied{m.mitgliedsnummer}"


def _passwort():
    return "".join(secrets.choice(ALPHABET) for _ in range(12))


def verbindung_oder_none(verein):
    v = OpenSlidesVerbindung.objects.filter(verein=verein).first()
    if v is None or not v.url or not v.benutzername or not v.passwort:
        return None
    return v


def verbindung_testen(v):
    c = OSClient(v)
    c.login()
    return "Anmeldung erfolgreich."


def mitglied_anonymisieren(v, mitglied):
    """Gleicht eine DSGVO-Anonymisierung (apps.members) auf das verknüpfte OpenSlides-Konto ab: Name, Benutzername
    und E-Mail werden überschrieben und das Konto deaktiviert, statt nur zu deaktivieren und den echten Namen dort
    stehen zu lassen."""
    if not mitglied.openslides_user_id:
        return
    c = OSClient(v)
    c.login()
    kennung = mitglied.mitgliedsnummer or mitglied.pk
    c.action("user.update", [{
        # kein "member_number": "" - OpenSlides lehnt einen leeren Wert dafuer ab ("This member_number is
        # forbidden."); die Mitgliedsnummer allein ist ausserdem nicht personenbezogen genug, um sie unbedingt
        # loeschen zu muessen.
        "id": mitglied.openslides_user_id, "first_name": "Anonymisiert", "last_name": f"#{kennung}",
        "username": f"anonym-{mitglied.openslides_user_id}", "email": "", "is_active": False,
    }])


def _superadmin_user_ids(verein):
    from apps.core.models import Zugang
    return set(Zugang.objects.filter(verein=verein, aktiv=True, rolle__ist_superadmin=True)
              .values_list("user_id", flat=True))


def _superadmin_zugaenge_ohne_mitglied(verein):
    """Aktive Superadmin-Benutzerzugänge OHNE eigene Mitgliedsakte - mit Mitgliedsakte bekommen sie ihr Konto
    ohnehin wie jedes andere Mitglied über mitglieder_abgleichen/_im_umfang."""
    from apps.core.models import Zugang
    user_ids = _superadmin_user_ids(verein)
    if not user_ids:
        return []
    mit_mitglied = set(Mitglied.objects.filter(verein=verein, benutzer_id__in=user_ids)
                       .values_list("benutzer_id", flat=True))
    uebrig = user_ids - mit_mitglied
    if not uebrig:
        return []
    return list(Zugang.objects.filter(verein=verein, user_id__in=uebrig).select_related("user"))


def _im_umfang(v):
    qs = Mitglied.objects.filter(verein=v.verein, status="aktiv")
    if v.sync_funktion_id:
        # Funktion ODER ein Tag mit OpenSlides-Gruppe genuegt (Tags verteilen die Rechte); Superadmins (volle
        # Rechte in der Software, siehe apps.core.rechte) bekommen immer ein Konto, unabhaengig vom Sync-Umfang
        qs = qs.filter(
            Q(Q(funktionen__funktion_id=v.sync_funktion_id),
              Q(funktionen__bis__isnull=True) | Q(funktionen__bis__gte=date.today()))
            | Q(tags__openslides_gruppe__gt="")
            | Q(benutzer_id__in=_superadmin_user_ids(v.verein))).distinct()
    return qs


def superadmin_konten_abgleichen(v, client=None):
    """Legt für Superadmin-Benutzerzugänge OHNE eigene Mitgliedsakte ein OpenSlides-Konto an bzw. aktualisiert es
    (mit Mitgliedsakte läuft das über mitglieder_abgleichen, wie bei jedem anderen Mitglied). Wird von
    mitglieder_abgleichen mit aufgerufen. -> (neu, aktualisiert, deaktiviert, [Fehler])."""
    from .models import SuperadminKonto
    c = client or OSClient(v)
    if client is None:
        c.login()
    zugaenge = _superadmin_zugaenge_ohne_mitglied(v.verein)
    ids_umfang = {z.pk for z in zugaenge}
    neu = akt = deaktiviert = 0
    fehler = []
    for z in zugaenge:
        vorname, nachname = z.user.first_name or z.user.get_username(), z.user.last_name or "(Superadmin)"
        try:
            konto = SuperadminKonto.objects.filter(zugang=z).first()
            if konto is None:
                daten = {"first_name": vorname, "last_name": nachname, "is_active": True}
                if z.user.email:
                    daten["email"] = z.user.email
                pw = _passwort()
                daten["default_password"] = pw
                name = f"{ascii_kennung(vorname)}.{ascii_kennung(nachname)}".strip(".") or f"zugang{z.pk}"
                try:
                    uid = c.erstelle("user.create", {**daten, "username": name})
                except OpenSlidesFehler as e:
                    if "username" not in str(e).lower():
                        raise
                    name = f"{name}.{z.pk}"
                    uid = c.erstelle("user.create", {**daten, "username": name})
                SuperadminKonto.objects.create(verein=v.verein, zugang=z, openslides_user_id=uid,
                                               openslides_username=name, openslides_initialpasswort=pw)
                neu += 1
            else:
                daten = {"id": konto.openslides_user_id, "first_name": vorname, "last_name": nachname,
                         "is_active": True}
                if z.user.email:
                    daten["email"] = z.user.email
                c.action("user.update", [daten])
                akt += 1
        except OpenSlidesFehler as e:
            fehler.append(f"{z.user}: {e}")
    for konto in SuperadminKonto.objects.filter(verein=v.verein).exclude(zugang_id__in=ids_umfang):
        try:
            c.action("user.update", [{"id": konto.openslides_user_id, "is_active": False}])
            konto.delete()
            deaktiviert += 1
        except OpenSlidesFehler as e:
            fehler.append(f"{konto.openslides_username} (deaktivieren): {e}")
    return neu, akt, deaktiviert, fehler


def mitglieder_abgleichen(v):
    """Legt für Mitglieder OpenSlides-Konten an, aktualisiert Namen/E-Mail und deaktiviert ausgeschiedene Mitglieder."""
    c = OSClient(v)
    c.login()
    neu = akt = deaktiviert = 0
    fehler = []
    im_umfang = list(_im_umfang(v))
    ids_umfang = {m.pk for m in im_umfang}
    for m in im_umfang:
        try:
            if m.openslides_user_id is None:
                daten = {"first_name": m.vorname, "last_name": m.nachname, "is_active": True,
                         "member_number": f"{v.verein.kuerzel}-{m.mitgliedsnummer}"}
                if m.email:
                    daten["email"] = m.email
                pw = _passwort()
                daten["default_password"] = pw
                name = benutzername(m)
                try:
                    uid = c.erstelle("user.create", {**daten, "username": name})
                except OpenSlidesFehler as e:
                    if "username" not in str(e).lower():
                        raise
                    name = f"{name}.{m.mitgliedsnummer}"
                    uid = c.erstelle("user.create", {**daten, "username": name})
                m.openslides_user_id, m.openslides_username, m.openslides_initialpasswort = uid, name, pw
                m.save(update_fields=["openslides_user_id", "openslides_username", "openslides_initialpasswort", "geaendert"])
                neu += 1
            else:
                daten = {"id": m.openslides_user_id, "first_name": m.vorname, "last_name": m.nachname, "is_active": True}
                if m.email:
                    daten["email"] = m.email
                c.action("user.update", [daten])
                akt += 1
        except OpenSlidesFehler as e:
            fehler.append(f"{m.name}: {e}")
    for m in Mitglied.objects.filter(verein=v.verein, openslides_user_id__isnull=False).exclude(pk__in=ids_umfang):
        try:
            c.action("user.update", [{"id": m.openslides_user_id, "is_active": False}])
            deaktiviert += 1
        except OpenSlidesFehler as e:
            fehler.append(f"{m.name} (deaktivieren): {e}")
    s_neu, s_akt, s_deaktiviert, s_fehler = superadmin_konten_abgleichen(v, client=c)
    neu, akt, deaktiviert = neu + s_neu, akt + s_akt, deaktiviert + s_deaktiviert
    fehler += s_fehler
    info = f"{neu} Konten angelegt, {akt} aktualisiert, {deaktiviert} deaktiviert, {len(fehler)} Fehler."
    if fehler:
        info += "\n" + "\n".join(fehler[:20])
    v.letzter_abgleich_am, v.letzter_abgleich_info = timezone.now(), info
    v.save(update_fields=["letzter_abgleich_am", "letzter_abgleich_info", "geaendert"])
    return info


def meeting_anlegen(v, veranstaltung):
    """Legt eine Versammlung (Meeting) in OpenSlides an und überträgt die Tagesordnung."""
    c = OSClient(v)
    c.login()
    basis = {"name": veranstaltung.titel[:100], "committee_id": v.committee_id, "language": v.sprache,
             "admin_ids": v.admin_ids}
    extra = {"location": veranstaltung.ort[:200] if veranstaltung.ort else None,
             "start_time": int(veranstaltung.beginn.timestamp())}
    if veranstaltung.ende:
        extra["end_time"] = int(veranstaltung.ende.timestamp())
    extra = {k: val for k, val in extra.items() if val is not None}
    try:
        mid = c.erstelle("meeting.create", {**basis, **extra})
    except OpenSlidesFehler:
        mid = c.erstelle("meeting.create", basis)  # ohne optionale Felder erneut versuchen
    veranstaltung.openslides_meeting_id = mid
    veranstaltung.save(update_fields=["openslides_meeting_id", "geaendert"])
    return mid, tagesordnung_uebertragen(v, veranstaltung, client=c)


def tagesordnung_uebertragen(v, veranstaltung, client=None):
    if not veranstaltung.openslides_meeting_id:
        raise OpenSlidesFehler("Die Veranstaltung ist noch keiner OpenSlides-Versammlung zugeordnet.")
    c = client or OSClient(v)
    if client is None:
        c.login()
    n = 0
    for t in veranstaltung.tagesordnung.filter(openslides_topic_id__isnull=True):
        # "topic.create" legt für jedes Thema immer automatisch einen Tagesordnungspunkt an - kein "agenda_create"-Feld nötig
        tid = c.erstelle("topic.create", {"meeting_id": veranstaltung.openslides_meeting_id, "title": t.titel[:250],
                                          "text": t.beschreibung.replace("\n", "<br>")})
        t.openslides_topic_id = tid
        t.save(update_fields=["openslides_topic_id", "geaendert"])
        n += 1
    return n


def _wahlergebnisse_anfrage(meeting_id):
    """Eine einzige verschachtelte Autoupdate-Anfrage, die von der Versammlung über die Wahlen (assignment) und
    deren Wahlgänge (poll) bis zu den Stimmen je Kandidat (option -> poll_candidate_list -> poll_candidate ->
    user) durchtraversiert - nach dem Schema des openslides-autoupdate-service (siehe dessen Dokumentation zu
    verschachtelten relation-list-/generic-relation-Feldern)."""
    kandidat_felder = {
        "poll_candidate_ids": {
            "type": "relation-list", "collection": "poll_candidate",
            "fields": {"user_id": {"type": "relation", "collection": "user",
                                   "fields": {"first_name": None, "last_name": None, "username": None}}},
        },
    }
    # Eine Option einer Wahl verweist je nach Version/Art der Wahl auf eine Kandidatenliste (poll_candidate_list) oder
    # direkt auf einen Benutzer (user) - beide Faelle abfragen (nicht passende Felder liefert der Dienst einfach nicht).
    option_felder = {
        "yes": None, "no": None, "abstain": None,
        "content_object_id": {"type": "generic-relation", "fields": {
            **kandidat_felder, "first_name": None, "last_name": None, "username": None}},
    }
    poll_felder = {
        "title": None, "state": None, "pollmethod": None,
        "option_ids": {"type": "relation-list", "collection": "option", "fields": option_felder},
    }
    assignment_felder = {
        "title": None,
        "poll_ids": {"type": "relation-list", "collection": "poll", "fields": poll_felder},
    }
    return [{"ids": [meeting_id], "collection": "meeting",
            "fields": {"assignment_ids": {"type": "relation-list", "collection": "assignment",
                                          "fields": assignment_felder}}}]


def _kandidat_name(daten, user_id):
    name = f"{daten.get(f'user/{user_id}/first_name', '')} {daten.get(f'user/{user_id}/last_name', '')}".strip()
    return name or daten.get(f"user/{user_id}/username") or f"Nutzer {user_id}"


def _zahl(wert):
    """OpenSlides liefert Stimmen als Dezimalzahl-Text ("8.000000") - fuers Protokoll lesbar: "8" bzw. "0,5"."""
    try:
        d = Decimal(str(wert))
    except InvalidOperation:
        return str(wert)
    text = format(d.normalize(), "f")
    return text.replace(".", ",")


def _stimmen_wert(daten, option_id):
    try:
        return Decimal(str(daten.get(f"option/{option_id}/yes") or 0))
    except InvalidOperation:
        return Decimal(0)


def _stimmen_zeile(daten, option_id, ja_label="Ja"):
    name = None
    coid = daten.get(f"option/{option_id}/content_object_id")
    if coid and coid.startswith("user/"):
        name = _kandidat_name(daten, coid.split("/", 1)[1])
    elif coid and coid.startswith("poll_candidate_list/"):
        pcl_id = coid.split("/", 1)[1]
        for pc_id in daten.get(f"poll_candidate_list/{pcl_id}/poll_candidate_ids") or []:
            uid = daten.get(f"poll_candidate/{pc_id}/user_id")
            if uid:
                name = _kandidat_name(daten, uid)
                break
    teile = []
    for feld, label in (("yes", ja_label), ("no", "Nein"), ("abstain", "Enthaltung")):
        wert = daten.get(f"option/{option_id}/{feld}")
        if wert is not None:
            teile.append(f"{_zahl(wert)} {label}")
    if not name and not teile:
        return None
    return f"{name or 'Option ' + str(option_id)}: {', '.join(teile) if teile else '–'}"


def _poll_felder():
    """Felder einer Abstimmung (poll) fuer Antraege/Themen: Titel, Zustand, Stimmen je Option (Ja/Nein/Enthaltung)
    und die Gesamtzahlen."""
    option_felder = {"yes": None, "no": None, "abstain": None, "text": None}
    return {"title": None, "state": None, "pollmethod": None, "votesvalid": None, "votesinvalid": None,
            "votescast": None, "option_ids": {"type": "relation-list", "collection": "option", "fields": option_felder}}


def _antraege_anfrage(meeting_id):
    """Alle Antraege (motion) der Versammlung samt Abstimmungen und dem in OpenSlides gesetzten Status."""
    nutzer = {"first_name": None, "last_name": None, "username": None}
    antrag_felder = {
        "number": None, "title": None, "text": None, "reason": None,
        # Antragsteller: ab OpenSlides 4.2 ueber meeting_user, davor direkt ueber user - beide abfragen
        "submitter_ids": {"type": "relation-list", "collection": "motion_submitter", "fields": {
            "user_id": {"type": "relation", "collection": "user", "fields": nutzer},
            "meeting_user_id": {"type": "relation", "collection": "meeting_user", "fields": {
                "user_id": {"type": "relation", "collection": "user", "fields": nutzer}}}}},
        "state_id": {"type": "relation", "collection": "motion_state", "fields": {"name": None}},
        "poll_ids": {"type": "relation-list", "collection": "poll", "fields": _poll_felder()},
    }
    return [{"ids": [meeting_id], "collection": "meeting",
            "fields": {"motion_ids": {"type": "relation-list", "collection": "motion", "fields": antrag_felder}}}]


def _themen_anfrage(meeting_id):
    """Alle Themen (topic) der Versammlung samt ihrer Abstimmungen."""
    return [{"ids": [meeting_id], "collection": "meeting",
            "fields": {"topic_ids": {"type": "relation-list", "collection": "topic", "fields": {
                "title": None, "text": None, "poll_ids": {"type": "relation-list", "collection": "poll",
                                            "fields": _poll_felder()}}}}}]


def _klartext(html, maximal=5000):
    """HTML-Text aus OpenSlides (Antragstext, Begruendung) als schlichter Text fuers Protokoll."""
    text = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h[1-6]>|</div>", "\n", html or "")
    text = unescape(re.sub(r"<[^>]+>", "", text))
    text = re.sub(r"[ \t]+\n", "\n", re.sub(r"\n{3,}", "\n\n", text)).strip()
    return text if len(text) <= maximal else text[:maximal].rstrip() + " [...]"


def _antragsteller(daten, antrag_id):
    namen = []
    for sid in daten.get(f"motion/{antrag_id}/submitter_ids") or []:
        uid = daten.get(f"motion_submitter/{sid}/user_id")
        if not uid:
            meeting_user = daten.get(f"motion_submitter/{sid}/meeting_user_id")
            uid = daten.get(f"meeting_user/{meeting_user}/user_id") if meeting_user else None
        if uid and (name := _kandidat_name(daten, uid)) not in namen:
            namen.append(name)
    return ", ".join(namen)


def _antrag_bezeichnung(daten, antrag_id):
    nummer, titel = daten.get(f"motion/{antrag_id}/number"), daten.get(f"motion/{antrag_id}/title") or ""
    bez = f"Antrag {nummer}: {titel}" if nummer else f"Antrag: {titel or antrag_id}"
    status_id = daten.get(f"motion/{antrag_id}/state_id")
    kopf = []
    for label, wert in (("Antragsteller*in", _antragsteller(daten, antrag_id)),
                        ("Antragstext", _klartext(daten.get(f"motion/{antrag_id}/text"))),
                        ("Begründung", _klartext(daten.get(f"motion/{antrag_id}/reason")))):
        if wert:
            kopf.append(f"{label}: {wert}")
    return bez, daten.get(f"motion_state/{status_id}/name") if status_id else None, kopf


def _thema_bezeichnung(daten, thema_id):
    text = _klartext(daten.get(f"topic/{thema_id}/text"))
    return f"Thema: {daten.get(f'topic/{thema_id}/title') or thema_id}", None, [f"Text: {text}"] if text else []


def _erfasst(wert):
    """OpenSlides markiert nicht erfasste Zahlen mit negativen Werten (z. B. -2) - die gehoeren nicht ins Protokoll."""
    if wert in (None, ""):
        return False
    try:
        return Decimal(str(wert)) >= 0
    except InvalidOperation:
        return False


def _abstimmung_zeilen(daten, poll_id):
    """Stimmenverteilung einer Abstimmung als Textzeilen: je Option "Ja/Nein/Enthaltung" (bei Optionen mit Text
    davor der Text), dazu - falls geliefert - gueltige/ungueltige/abgegebene Stimmen."""
    zeilen = []
    for option_id in daten.get(f"poll/{poll_id}/option_ids") or []:
        teile = [f"{_zahl(daten[f'option/{option_id}/{feld}'])} {label}"
                 for feld, label in (("yes", "Ja"), ("no", "Nein"), ("abstain", "Enthaltung"))
                 if _erfasst(daten.get(f"option/{option_id}/{feld}"))]
        if not teile:
            continue
        text = daten.get(f"option/{option_id}/text")
        zeilen.append(f"{text}: {', '.join(teile)}" if text else "Ergebnis: " + ", ".join(teile))
    gesamt = [f"{label}: {_zahl(daten[f'poll/{poll_id}/{feld}'])}"
              for feld, label in (("votesvalid", "Gültige Stimmen"), ("votesinvalid", "Ungültige Stimmen"),
                                  ("votescast", "Abgegebene Stimmen"))
              if _erfasst(daten.get(f"poll/{poll_id}/{feld}"))]
    if zeilen and gesamt:
        zeilen.append(", ".join(gesamt))
    return zeilen


def _abstimmungen_speichern(daten, mid, veranstaltung, sammlung, bezeichnung):
    """Speichert jede abgeschlossene Abstimmung der Antraege bzw. Themen als Abstimmungsergebnis. Ob ein Antrag
    angenommen ist, bestimmt die Software nicht; der in OpenSlides gesetzte Status wird nur als Information
    angehaengt."""
    if not isinstance(daten, dict):
        return 0
    n = 0
    for objekt_id in daten.get(f"meeting/{mid}/{sammlung}_ids") or []:
        bez, status, kopfzeilen = bezeichnung(daten, objekt_id)
        for poll_id in daten.get(f"{sammlung}/{objekt_id}/poll_ids") or []:
            if daten.get(f"poll/{poll_id}/state") not in POLL_ABGESCHLOSSEN:
                continue
            zeilen = _abstimmung_zeilen(daten, poll_id)
            if not zeilen:
                continue
            zeilen = kopfzeilen + zeilen
            if status:
                zeilen.append(f"Status in OpenSlides: {status}")
            Wahlergebnis.objects.create(verein=veranstaltung.verein, veranstaltung=veranstaltung, art="abstimmung",
                                        openslides_poll_id=poll_id, amt=bez[:250],
                                        wahlgang=(daten.get(f"poll/{poll_id}/title") or "")[:250],
                                        ergebnis="\n".join(zeilen))
            n += 1
    return n


def wahlergebnisse_abrufen(v, veranstaltung):
    """Ruft alle Wahlen (assignment) sowie alle Abstimmungen zu Anträgen (motion) und Themen (topic) der
    verknüpften OpenSlides-Versammlung ab und speichert die Stimmenverteilung je abgeschlossenem Wahlgang bzw.
    jeder abgeschlossenen Abstimmung - ersetzt zuvor abgerufene Ergebnisse dieser Veranstaltung vollständig
    (idempotent bei erneutem Abruf). Wer gewählt ist bzw. ob ein Antrag angenommen ist, wird bewusst NICHT
    automatisch bestimmt (siehe Wahlergebnis-Modell). Gibt die Gesamtzahl der gespeicherten Ergebnisse zurück."""
    if not veranstaltung.openslides_meeting_id:
        raise OpenSlidesFehler("Die Veranstaltung ist noch keiner OpenSlides-Versammlung zugeordnet.")
    c = OSClient(v)
    c.login()
    mid = veranstaltung.openslides_meeting_id
    daten = c.abfragen(_wahlergebnisse_anfrage(mid))
    Wahlergebnis.objects.filter(verein=veranstaltung.verein, veranstaltung=veranstaltung).delete()
    n = 0
    for assignment_id in daten.get(f"meeting/{mid}/assignment_ids") or []:
        amt = daten.get(f"assignment/{assignment_id}/title") or f"Wahl {assignment_id}"
        for poll_id in daten.get(f"assignment/{assignment_id}/poll_ids") or []:
            if daten.get(f"poll/{poll_id}/state") not in POLL_ABGESCHLOSSEN:
                continue
            # Wahlmethode "Y" = jede Person erhaelt nur Stimmen (kein Ja/Nein/Enthaltung je Person)
            ja_label = "Stimmen" if daten.get(f"poll/{poll_id}/pollmethod") == "Y" else "Ja"
            optionen = sorted(daten.get(f"poll/{poll_id}/option_ids") or [],
                              key=lambda oid: _stimmen_wert(daten, oid), reverse=True)   # meiste Stimmen zuerst
            zeilen = [z for z in (_stimmen_zeile(daten, oid, ja_label) for oid in optionen) if z]
            if not zeilen:
                continue
            Wahlergebnis.objects.create(verein=veranstaltung.verein, veranstaltung=veranstaltung, amt=amt,
                                        wahlgang=daten.get(f"poll/{poll_id}/title") or "", art="wahl",
                                        openslides_poll_id=poll_id, ergebnis="\n".join(zeilen))
            n += 1
    for sammlung, anfrage, bezeichnung in (("motion", _antraege_anfrage, _antrag_bezeichnung),
                                           ("topic", _themen_anfrage, _thema_bezeichnung)):
        n += _abstimmungen_speichern(c.abfragen(anfrage(mid)), mid, veranstaltung, sammlung, bezeichnung)
    return n


def anwesenheit_abrufen(v, veranstaltung):
    """Holt die in OpenSlides als "anwesend" markierten Personen der verknuepften Versammlung und speichert sie als
    Anwesenheit der Veranstaltung (ersetzt den zuvor abgerufenen Stand vollstaendig). Mitglieder werden ueber ihr
    verknuepftes OpenSlides-Konto (Abgleich) zugeordnet, alle anderen als Gast mit dem Namen aus OpenSlides.
    Gibt die Zahl der Anwesenden zurueck."""
    if not veranstaltung.openslides_meeting_id:
        raise OpenSlidesFehler("Die Veranstaltung ist noch keiner OpenSlides-Versammlung zugeordnet.")
    c = OSClient(v)
    c.login()
    mid = veranstaltung.openslides_meeting_id
    daten = c.abfragen([{"ids": [mid], "collection": "meeting", "fields": {
        "present_user_ids": {"type": "relation-list", "collection": "user",
                             "fields": {"first_name": None, "last_name": None, "username": None}}}}])
    if not isinstance(daten, dict) or daten.get("success") is False or daten.get("message"):
        raise OpenSlidesFehler(f"Anwesenheit konnte nicht abgerufen werden: {str(daten)[:200]}")
    user_ids = daten.get(f"meeting/{mid}/present_user_ids") or []
    mitglieder = {m.openslides_user_id: m for m in
                  Mitglied.objects.filter(verein=veranstaltung.verein, openslides_user_id__in=user_ids)}
    Anwesenheit.objects.filter(verein=veranstaltung.verein, veranstaltung=veranstaltung).delete()
    for uid in user_ids:
        m = mitglieder.get(uid)
        Anwesenheit.objects.create(verein=veranstaltung.verein, veranstaltung=veranstaltung, mitglied=m,
                                   name="" if m else _kandidat_name(daten, uid)[:200], openslides_user_id=uid)
    return len(user_ids)


def _versammlungsgruppen(c, meeting_id):
    """-> {gruppenname_klein: gruppen_id} der Versammlung (Autoupdate-Abfrage)."""
    daten = c.abfragen([{"ids": [meeting_id], "collection": "meeting",
                         "fields": {"group_ids": {"type": "relation-list", "collection": "group",
                                                  "fields": {"name": None}}}}])
    gruppen = {}
    for schluessel, wert in (daten or {}).items():
        teile = str(schluessel).split("/")
        if len(teile) == 3 and teile[0] == "group" and teile[2] == "name" and wert:
            gruppen[str(wert).strip().lower()] = int(teile[1])
    return gruppen


SUPERADMIN_GRUPPE = "Admin"


def versammlungsrechte_zuweisen(v, veranstaltung, client=None):
    """Weist Mitgliedern anhand ihrer Tags (Feld „OpenSlides-Gruppe“) die Gruppe in der Versammlung der
    Veranstaltung zu. Superadministratoren (mit oder ohne eigene Mitgliedsakte) bekommen dort zusätzlich
    automatisch die Gruppe "Admin", unabhängig von Tags. Nur Mitglieder/Zugänge mit OpenSlides-Konto; ohne Konto
    werden sie gemeldet. Vorhandene weitere Gruppen in der Versammlung bleiben unberührt.
    -> Ergebnistext."""
    from .models import SuperadminKonto
    if not veranstaltung.openslides_meeting_id:
        raise OpenSlidesFehler("Die Veranstaltung ist noch keiner OpenSlides-Versammlung zugeordnet.")
    c = client or OSClient(v)
    if client is None:
        c.login()
    mid = veranstaltung.openslides_meeting_id
    gruppen = _versammlungsgruppen(c, mid)
    eintraege, ohne_konto, unbekannt = [], [], set()
    superadmin_user_ids = _superadmin_user_ids(v.verein)
    qs = Mitglied.objects.filter(
        Q(verein=v.verein, status="aktiv")
        & (Q(tags__openslides_gruppe__gt="") | Q(benutzer_id__in=superadmin_user_ids))).distinct()
    for m in qs:
        namen = {t.openslides_gruppe.strip() for t in m.tags.all() if t.openslides_gruppe}
        if m.benutzer_id in superadmin_user_ids:
            namen.add(SUPERADMIN_GRUPPE)
        ids = []
        for n in sorted(namen):
            if n.lower() in gruppen:
                ids.append(gruppen[n.lower()])
            else:
                unbekannt.add(n)
        if not ids:
            continue
        if m.openslides_user_id is None:
            ohne_konto.append(m.name)
            continue
        eintraege.append({"id": m.openslides_user_id, "meeting_id": mid, "group_ids": sorted(set(ids))})
    for z in _superadmin_zugaenge_ohne_mitglied(v.verein):
        if SUPERADMIN_GRUPPE.lower() not in gruppen:
            unbekannt.add(SUPERADMIN_GRUPPE)
            continue
        konto = SuperadminKonto.objects.filter(zugang=z).first()
        if konto is None:
            ohne_konto.append(str(z.user))
            continue
        eintraege.append({"id": konto.openslides_user_id, "meeting_id": mid,
                          "group_ids": [gruppen[SUPERADMIN_GRUPPE.lower()]]})
    if eintraege:
        c.action("user.update", eintraege)
    text = f"{len(eintraege)} Mitglied(er) mit Rechten in der Versammlung."
    if ohne_konto:
        text += f" Ohne OpenSlides-Konto (bitte „Mitglieder abgleichen“): {', '.join(ohne_konto[:10])}."
    if unbekannt:
        text += f" Gruppe(n) in der Versammlung nicht gefunden: {', '.join(sorted(unbekannt))}."
    return text
