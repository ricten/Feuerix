"""Administrator-Zugang einer angebundenen Instanz (Paperless/OpenSlides) anzeigen - nur Superadmins, nach erneuter Eingabe des
eigenen Feuerix-Passworts (laeuft ueber authenticate(): Fehlversuche zaehlen wie bei der Anmeldung und werden von der
Sperre erfasst). Jede Anzeige steht im Aenderungsprotokoll; die Seite wird nie zwischengespeichert."""
from django.contrib import messages
from django.contrib.auth import authenticate
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.utils.translation import gettext

from . import audit


def anzeigen(request, verbindung, titel, zurueck_name):
    if not request.user.is_superuser:
        raise PermissionDenied
    if verbindung is None or not verbindung.admin_passwort:
        messages.error(request, gettext("Es ist noch kein Administrator-Zugang gespeichert."))
        return redirect(zurueck_name)
    pw = request.POST.get("passwort", "")
    if authenticate(request, username=request.user.get_username(), password=pw) is None:
        messages.error(request, gettext("Das Passwort ist falsch."))
        return redirect(zurueck_name)
    audit._schreiben(verbindung, "geaendert", {gettext("Sicherheit"): [None, "Administrator-Passwort angezeigt"]})
    antwort = render(request, "core/zugangsdaten_anzeigen.html", {
        "titel": titel, "benutzer": verbindung.admin_benutzer, "passwort": verbindung.admin_passwort,
        "adresse": verbindung.url, "zurueck": zurueck_name})
    antwort["Cache-Control"] = "no-store, private"
    return antwort
