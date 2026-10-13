"""Passwort-Abgleich: dasselbe Passwort in Feuerix, Paperless-ngx und OpenSlides.

Feuerix kennt ein Passwort nur in dem Moment, in dem es gesetzt wird (danach existiert nur der Hash) - der Abgleich laeuft
deshalb bei diesen Ereignissen: Passwort aendern (eigene Seite), Superadmin setzt ein neues Passwort, Verwaltungszugang
einrichten, Benutzer mit Passwort anlegen/aendern. Je Anbindung per Schalter "Passwoerter mit Feuerix abgleichen" aktiv
(Standard: aus). Das Passwort geht nie durch eine Warteschlange (Celery/Redis) - der Abgleich laeuft sofort und mit kurzem
Timeout; Fehler stoppen die Passwortaenderung in Feuerix nie, sie werden gemeldet."""
from django.contrib import messages
from django.db.models import Q
from django.utils.translation import gettext

TIMEOUT = 10


class Ergebnis:
    def __init__(self):
        self.ok = []         # ["Paperless: max.mustermann", ...]
        self.fehler = []     # ["Paperless (max.mustermann): ...", ...]

    def __bool__(self):
        return bool(self.ok or self.fehler)


def abgleichen(user, passwort):
    """Setzt `passwort` in den Paperless-/OpenSlides-Konten des Benutzers (nur bei eingeschaltetem Abgleich der jeweiligen
    Anbindung). Gibt ein Ergebnis zurueck; wirft nie."""
    erg = Ergebnis()
    if not passwort:
        return erg
    try:
        _paperless(user, passwort, erg)
    except Exception as e:     # nie die Passwortaenderung selbst gefaehrden
        erg.fehler.append(f"Paperless: {e}")
    try:
        _openslides(user, passwort, erg)
    except Exception as e:
        erg.fehler.append(f"OpenSlides: {e}")
    return erg


def _paperless(user, passwort, erg):
    from apps.paperless.client import PaperlessClient, PaperlessFehler
    from apps.paperless.models import PaperlessBenutzer, PaperlessVerbindung
    for vb in PaperlessVerbindung.objects.filter(aktiv=True, passwoerter_abgleichen=True).exclude(api_token=""):
        konten = list(PaperlessBenutzer.objects.filter(verein=vb.verein).filter(
            Q(mitglied__benutzer=user) | Q(zugang__user=user)))
        if not konten:
            continue
        client = PaperlessClient(vb, timeout=TIMEOUT)
        for k in konten:
            try:
                client.benutzer_aendern(k.paperless_id, {"password": passwort})
                if k.initialpasswort:
                    k.initialpasswort = ""
                    k.save(update_fields=["initialpasswort", "geaendert"])
                erg.ok.append(f"Paperless: {k.benutzername}")
            except PaperlessFehler as e:
                erg.fehler.append(f"Paperless ({k.benutzername}): {e}")


def _openslides(user, passwort, erg):
    from apps.members.models import Mitglied
    from apps.openslides.client import OpenSlidesFehler, OSClient
    from apps.openslides.models import OpenSlidesVerbindung, SuperadminKonto
    for vb in OpenSlidesVerbindung.objects.filter(aktiv=True, passwoerter_abgleichen=True).exclude(passwort=""):
        ziele = [(m, m.openslides_user_id, m.openslides_username) for m in Mitglied.objects.filter(
            verein=vb.verein, benutzer=user, openslides_user_id__isnull=False)]
        ziele += [(k, k.openslides_user_id, k.openslides_username) for k in SuperadminKonto.objects.filter(
            verein=vb.verein, zugang__user=user)]
        if not ziele:
            continue
        try:
            client = OSClient(vb, timeout=TIMEOUT)
            client.login()
        except OpenSlidesFehler as e:
            erg.fehler.append(f"OpenSlides: {e}")
            continue
        for objekt, uid, name in ziele:
            try:
                client.action("user.set_password", [{"id": uid, "password": passwort, "set_as_default": False}])
                if isinstance(objekt, Mitglied):
                    if objekt.openslides_initialpasswort:
                        objekt.openslides_initialpasswort = ""
                        objekt.save(update_fields=["openslides_initialpasswort", "geaendert"])
                elif objekt.openslides_initialpasswort:
                    objekt.openslides_initialpasswort = ""
                    objekt.save(update_fields=["openslides_initialpasswort", "geaendert"])
                erg.ok.append(f"OpenSlides: {name}")
            except OpenSlidesFehler as e:
                erg.fehler.append(f"OpenSlides ({name}): {e}")


def melden(request, erg):
    """Hinweise zum Abgleich als Meldungen anzeigen (nichts, wenn es keinen Abgleich gab)."""
    if erg.ok:
        messages.success(request, gettext("Das Passwort wurde auch gesetzt in: %(konten)s.") % {"konten": ", ".join(erg.ok)})
    for f in erg.fehler:
        messages.warning(request, gettext("Passwort-Abgleich fehlgeschlagen - %(fehler)s") % {"fehler": f})
