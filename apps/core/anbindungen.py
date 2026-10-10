"""Ist fuer den aktiven Verein eine OpenSlides- bzw. Paperless-Instanz angebunden (Verbindung angelegt UND aktiv)?
Alle Knoepfe, Felder, Spalten und Platzhalter, die nur mit einer solchen Instanz Sinn ergeben, werden nur dann
angezeigt - die Einstellungsseiten (Verwaltung > Anbindung) bleiben immer erreichbar, da man dort die Anbindung
erst herstellt."""
from functools import cached_property


class Anbindungen:
    def __init__(self, verein):
        self.verein = verein

    @cached_property
    def openslides(self):
        if self.verein is None:
            return False
        from apps.openslides.models import OpenSlidesVerbindung
        return OpenSlidesVerbindung.objects.filter(verein=self.verein, aktiv=True).exists()

    @cached_property
    def paperless(self):
        if self.verein is None:
            return False
        from apps.paperless.models import PaperlessVerbindung
        return PaperlessVerbindung.objects.filter(verein=self.verein, aktiv=True).exists()

    def aktiv(self, name):
        return bool(getattr(self, name))


def anbindungen(request):
    """Je Anfrage einmal ermittelt und gemerkt (mehrere Pruefungen pro Seite kosten keine weiteren Abfragen)."""
    if not hasattr(request, "_anbindungen"):
        request._anbindungen = Anbindungen(getattr(request, "verein", None))
    return request._anbindungen
