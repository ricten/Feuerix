from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TenantModel
from apps.core.util import upload_pfad


class Jubilaeumsregel(TenantModel):
    jahre = models.PositiveIntegerField(_("Jahre Mitgliedschaft"))
    bezeichnung = models.CharField(_("Bezeichnung"), max_length=100, blank=True)
    aktiv = models.BooleanField(_("Aktiv"), default=True)

    class Meta:
        verbose_name = _("Jubiläumsregel")
        verbose_name_plural = _("Jubiläumsregeln")
        unique_together = [("verein", "jahre")]
        ordering = ["jahre"]

    def __str__(self):
        return self.bezeichnung or f"{self.jahre} Jahre"


class Ehrungsart(TenantModel):
    name = models.CharField(_("Name"), max_length=100)
    beschreibung = models.CharField(_("Beschreibung"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("Ehrungsart")
        verbose_name_plural = _("Ehrungsarten")
        unique_together = [("verein", "name")]
        ordering = ["name"]

    def __str__(self):
        return self.name


class Ehrung(TenantModel):
    mitglied = models.ForeignKey("members.Mitglied", on_delete=models.PROTECT, verbose_name=_("Mitglied"))
    art = models.ForeignKey(Ehrungsart, on_delete=models.PROTECT, verbose_name=_("Ehrung"))
    datum = models.DateField(_("Datum"))
    anlass = models.CharField(_("Anlass"), max_length=200, blank=True)
    verliehen_durch = models.CharField(_("Verliehen durch"), max_length=100, blank=True)
    urkunde = models.FileField(_("Urkunde / Dokument"), upload_to=upload_pfad, blank=True)
    notizen = models.TextField(_("Notizen"), blank=True)

    class Meta:
        verbose_name = _("Ehrung")
        verbose_name_plural = _("Ehrungen")
        ordering = ["-datum"]

    def __str__(self):
        return f"{self.mitglied.name}: {self.art} ({self.datum:%d.%m.%Y})"
