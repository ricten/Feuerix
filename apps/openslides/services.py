import re
import secrets
import unicodedata
from datetime import date

from django.db.models import Q
from django.utils import timezone

from apps.members.models import Mitglied

from .client import OpenSlidesFehler, OSClient
from .models import OpenSlidesVerbindung

ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _ascii(s):
    s = s.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9._-]", "", s.replace(" ", "-"))


def benutzername(m):
    n = f"{_ascii(m.vorname)}.{_ascii(m.nachname)}".strip(".")
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


def _im_umfang(v):
    qs = Mitglied.objects.filter(verein=v.verein, status="aktiv")
    if v.sync_funktion_id:
        qs = qs.filter(Q(funktionen__funktion_id=v.sync_funktion_id),
                       Q(funktionen__bis__isnull=True) | Q(funktionen__bis__gte=date.today())).distinct()
    return qs


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
