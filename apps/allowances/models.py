from datetime import date

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TenantModel
from apps.core.util import upload_pfad


class Aufwandsentschaedigung(TenantModel):
    ART = [
        ("ehrenamtspauschale", _("Ehrenamtspauschale (§ 3 Nr. 26a EStG)")),
        ("uebungsleiterpauschale", _("Übungsleiterpauschale (§ 3 Nr. 26 EStG)")),
        ("aufwandsersatz", _("Aufwandsersatz gegen Beleg (Auslagen, Fahrtkosten)")),
        ("sonstige", _("Sonstige Vergütung")),
    ]
    STATUS = [("beantragt", _("Beantragt")), ("genehmigt", _("Genehmigt")), ("ausgezahlt", _("Ausgezahlt")),
              ("abgelehnt", _("Abgelehnt")), ("verzichtet", _("Verzicht (in Spende umgewandelt)"))]
    empfaenger = models.ForeignKey("members.Mitglied", on_delete=models.PROTECT, verbose_name=_("Empfänger"))
    art = models.CharField(_("Art"), max_length=25, choices=ART)
    status = models.CharField(_("Status"), max_length=12, choices=STATUS, default="beantragt")
    datum = models.DateField(_("Datum"), default=date.today)
    betrag = models.DecimalField(_("Betrag (€)"), max_digits=10, decimal_places=2)
    taetigkeit = models.CharField(_("Tätigkeit / Anlass"), max_length=250)
    zeitraum_von = models.DateField(_("Zeitraum von"), null=True, blank=True)
    zeitraum_bis = models.DateField(_("Zeitraum bis"), null=True, blank=True)
    genehmigt_von = models.CharField(_("Genehmigt durch"), max_length=100, blank=True)
    ausgezahlt_am = models.DateField(_("Ausgezahlt am"), null=True, blank=True)
    freibetrag_erklaerung = models.BooleanField(
        _("Empfänger hat erklärt, dass der Freibetrag nicht anderweitig ausgeschöpft ist"), default=False)
    beleg = models.FileField(_("Beleg / Abrechnung"), upload_to=upload_pfad, blank=True)
    bemerkung = models.CharField(_("Bemerkung"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("Aufwandsentschädigung")
        verbose_name_plural = _("Aufwandsentschädigungen")
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
