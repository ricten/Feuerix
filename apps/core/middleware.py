from django.conf import settings

from . import audit
from .models import Verein
from .rechte import RechteKontext


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
