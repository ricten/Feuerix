from django.db import models

from apps.core.models import TenantModel
from apps.core.util import upload_pfad


class Jubilaeumsregel(TenantModel):
    jahre = models.PositiveIntegerField("Jahre Mitgliedschaft")
    bezeichnung = models.CharField("Bezeichnung", max_length=100, blank=True)
    aktiv = models.BooleanField("Aktiv", default=True)

    class Meta:
        verbose_name = "Jubiläumsregel"
        verbose_name_plural = "Jubiläumsregeln"
        unique_together = [("verein", "jahre")]
        ordering = ["jahre"]

    def __str__(self):
        return self.bezeichnung or f"{self.jahre} Jahre"


class Ehrungsart(TenantModel):
    name = models.CharField("Name", max_length=100)
    beschreibung = models.CharField("Beschreibung", max_length=200, blank=True)

    class Meta:
        verbose_name = "Ehrungsart"
        verbose_name_plural = "Ehrungsarten"
        unique_together = [("verein", "name")]
        ordering = ["name"]

    def __str__(self):
        return self.name


class Ehrung(TenantModel):
    mitglied = models.ForeignKey("members.Mitglied", on_delete=models.PROTECT, verbose_name="Mitglied")
    art = models.ForeignKey(Ehrungsart, on_delete=models.PROTECT, verbose_name="Ehrung")
    datum = models.DateField("Datum")
    anlass = models.CharField("Anlass", max_length=200, blank=True)
    verliehen_durch = models.CharField("Verliehen durch", max_length=100, blank=True)
    urkunde = models.FileField("Urkunde / Dokument", upload_to=upload_pfad, blank=True)
    notizen = models.TextField("Notizen", blank=True)

    class Meta:
        verbose_name = "Ehrung"
        verbose_name_plural = "Ehrungen"
        ordering = ["-datum"]

    def __str__(self):
        return f"{self.mitglied.name}: {self.art} ({self.datum:%d.%m.%Y})"
