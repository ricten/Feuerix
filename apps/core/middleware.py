from django.conf import settings
from django.http import HttpResponse

from . import audit
from .models import Verein
from .rechte import RechteKontext


class WartungMiddleware:
    """Waehrend einer Wiederherstellung (Sperrdatei im Sicherungsordner, siehe datensicherung.py) beantwortet sie
    jede Anfrage mit einer Wartungsseite - sonst liefen Seitenaufrufe mitten in den Austausch der Datenbank. Greift
    vor Sitzung und Datenbankzugriff, nutzt also selbst keine Datenbank."""

    SEITE = ("<!doctype html><html lang=\"de\"><head><meta charset=\"utf-8\"><meta http-equiv=\"refresh\" content=\"15\">"
             "<title>Wartung</title></head><body style=\"font-family:sans-serif;max-width:32em;margin:4em auto;"
             "padding:0 1em\"><h2>Wartung</h2><p>Eine Datensicherung wird gerade wiederhergestellt. Die Seite "
             "ist in wenigen Minuten wieder erreichbar und lädt sich selbst neu.</p><p><small>A backup is "
             "being restored. This page will reload automatically.</small></p></body></html>")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from .datensicherung import wartung_aktiv
        if wartung_aktiv() and not request.path.startswith(settings.STATIC_URL):
            return HttpResponse(self.SEITE, status=503, headers={"Retry-After": "30"})
        return self.get_response(request)


class MandantMiddleware:
    """Bestimmt den aktiven Verein (Mandant) und die Rechte des Benutzers darin."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.verein = None
        request.vereine = []
        request.rechte = RechteKontext(request.user, None)
        if request.user.is_authenticated:
            if request.user.is_superuser:
                vereine = list(Verein.objects.filter(aktiv=True))
            else:
                vereine = list(Verein.objects.filter(
                    aktiv=True, zugaenge__user=request.user, zugaenge__aktiv=True).distinct())
            gewaehlt = request.session.get("verein_id")
            verein = next((v for v in vereine if v.pk == gewaehlt), None) or (vereine[0] if vereine else None)
            if verein is not None and gewaehlt != verein.pk:
                request.session["verein_id"] = verein.pk
            request.verein, request.vereine = verein, vereine
            request.rechte = RechteKontext(request.user, verein)
        ip = request.META.get("REMOTE_ADDR")
        if settings.USE_X_FORWARDED_FOR and request.META.get("HTTP_X_FORWARDED_FOR"):
            ip = request.META["HTTP_X_FORWARDED_FOR"].split(",")[0].strip()
        token = audit.kontext_var.set({"user": request.user, "ip": ip, "grund": None})
        try:
            return self.get_response(request)
        finally:
            audit.kontext_var.reset(token)
