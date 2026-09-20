from datetime import date

from django.db import models

from apps.core.models import TenantModel
from apps.core.util import upload_pfad


class Aufwandsentschaedigung(TenantModel):
    ART = [
        ("ehrenamtspauschale", "Ehrenamtspauschale (§ 3 Nr. 26a EStG)"),
        ("uebungsleiterpauschale", "Übungsleiterpauschale (§ 3 Nr. 26 EStG)"),
        ("aufwandsersatz", "Aufwandsersatz gegen Beleg (Auslagen, Fahrtkosten)"),
        ("sonstige", "Sonstige Vergütung"),
    ]
    STATUS = [("beantragt", "Beantragt"), ("genehmigt", "Genehmigt"), ("ausgezahlt", "Ausgezahlt"),
              ("abgelehnt", "Abgelehnt"), ("verzichtet", "Verzicht (in Spende umgewandelt)")]
    empfaenger = models.ForeignKey("members.Mitglied", on_delete=models.PROTECT, verbose_name="Empfänger")
    art = models.CharField("Art", max_length=25, choices=ART)
    status = models.CharField("Status", max_length=12, choices=STATUS, default="beantragt")
    datum = models.DateField("Datum", default=date.today)
    betrag = models.DecimalField("Betrag (€)", max_digits=10, decimal_places=2)
    taetigkeit = models.CharField("Tätigkeit / Anlass", max_length=250)
    zeitraum_von = models.DateField("Zeitraum von", null=True, blank=True)
    zeitraum_bis = models.DateField("Zeitraum bis", null=True, blank=True)
    genehmigt_von = models.CharField("Genehmigt durch", max_length=100, blank=True)
    ausgezahlt_am = models.DateField("Ausgezahlt am", null=True, blank=True)
    freibetrag_erklaerung = models.BooleanField(
        "Empfänger hat erklärt, dass der Freibetrag nicht anderweitig ausgeschöpft ist", default=False)
    beleg = models.FileField("Beleg / Abrechnung", upload_to=upload_pfad, blank=True)
    bemerkung = models.CharField("Bemerkung", max_length=200, blank=True)

    class Meta:
        verbose_name = "Aufwandsentschädigung"
        verbose_name_plural = "Aufwandsentschädigungen"
        ordering = ["-datum", "-id"]

    def __str__(self):
        return f"{self.empfaenger.name}: {self.get_art_display()} {self.betrag} € ({self.datum:%d.%m.%Y})"

    @property
    def ist_pauschale(self):
        return self.art in ("ehrenamtspauschale", "uebungsleiterpauschale")


def freibetrag_stand(verein, empfaenger, jahr):
    """Summe (genehmigt + ausgezahlt) je Pauschalenart und Empfänger im Jahr, mit Grenzen des Vereins."""
    qs = Aufwandsentschaedigung.objects.filter(verein=verein, empfaenger=empfaenger, datum__year=jahr,
                                               status__in=["genehmigt", "ausgezahlt"])
    def summe(art):
        return sum((a.betrag for a in qs if a.art == art), 0)
    return {
        "ehrenamtspauschale": (summe("ehrenamtspauschale"), verein.ehrenamts_freibetrag),
        "uebungsleiterpauschale": (summe("uebungsleiterpauschale"), verein.uebungsleiter_freibetrag),
    }
