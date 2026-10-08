from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import TenantModel, naechste_nummer
from apps.core.util import upload_pfad

SPHAEREN = [("ideell", _("Ideeller Bereich")), ("vermoegen", _("Vermögensverwaltung")), ("zweck", _("Zweckbetrieb")),
            ("wirtschaft", _("Wirtschaftlicher Geschäftsbetrieb"))]
SPHAEREN_LABEL = dict(SPHAEREN)


class Konto(TenantModel):
    TYP = [("bank", _("Bankkonto")), ("bar", _("Barkasse"))]
    name = models.CharField(_("Bezeichnung"), max_length=100)
    typ = models.CharField(_("Art"), max_length=4, choices=TYP, default="bank")
    eroeffnungsbestand = models.DecimalField(_("Eröffnungsbestand (€)"), max_digits=12, decimal_places=2, default=0,
                                             help_text=_("Bestand zum Eröffnungsdatum – Ausgangspunkt aller Berechnungen"))
    eroeffnungsdatum = models.DateField(_("Eröffnungsdatum"), default=date.today,
                                        help_text=_("Buchungen sind erst ab diesem Datum möglich"))
    aktiv = models.BooleanField(_("Aktiv"), default=True)
    fints_zugang = models.ForeignKey("finance.FinTSZugang", on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name="konten", verbose_name=_("FinTS-Zugang"),
                                     help_text=_("Nur setzen, wenn dieses Konto automatisch per FinTS abgerufen werden "
                                               "soll (Verwaltung › FinTS-Zugänge) - sonst weiterhin manueller "
                                               "Kontoauszug-Import."))

    class Meta:
        verbose_name = _("Konto")
        verbose_name_plural = _("Konten")
        unique_together = [("verein", "name")]
        ordering = ["typ", "name"]

    def __str__(self):
        return self.name


class Buchungskategorie(TenantModel):
    TYP = [("einnahme", _("Einnahme")), ("ausgabe", _("Ausgabe"))]
    name = models.CharField(_("Name"), max_length=100)
    typ = models.CharField(_("Art"), max_length=8, choices=TYP)
    sphaere = models.CharField(_("Steuerliche Sphäre"), max_length=10, choices=SPHAEREN, default="ideell",
                               help_text=_("Zuordnung bitte mit dem Steuerberater/Finanzamt abstimmen"))
    sortierung = models.PositiveIntegerField(_("Sortierung"), default=100)
    aktiv = models.BooleanField(_("Aktiv"), default=True)

    class Meta:
        verbose_name = _("Buchungskategorie")
        verbose_name_plural = _("Buchungskategorien")
        unique_together = [("verein", "name", "typ")]
        ordering = ["typ", "sphaere", "sortierung", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_typ_display()})"


class Buchung(TenantModel):
    TYP = Buchungskategorie.TYP
    QUELLE = [("manuell", _("Manuell erfasst")), ("zahlung", _("Aus Zahlung")), ("spende", _("Aus Spende")),
              ("aufwand", _("Aus Aufwandsentschädigung")), ("kosten", _("Aus Veranstaltungsbudget"))]
    datum = models.DateField(_("Buchungsdatum"), default=date.today)
    typ = models.CharField(_("Art"), max_length=8, choices=TYP)
    betrag = models.DecimalField(_("Betrag (€)"), max_digits=12, decimal_places=2,
                                 validators=[MinValueValidator(Decimal("0.01"))], help_text=_("immer positiv erfassen"))
    konto = models.ForeignKey(Konto, on_delete=models.PROTECT, verbose_name=_("Konto"))
    kategorie = models.ForeignKey(Buchungskategorie, on_delete=models.PROTECT, verbose_name=_("Kategorie"))
    text = models.CharField(_("Buchungstext"), max_length=250)
    belegnummer = models.CharField(_("Belegnummer"), max_length=30, blank=True,
                                   help_text=_("Leer lassen = automatisch (B-JJJJ-000001)"))
    beleg = models.FileField(_("Beleg (Scan/Foto)"), upload_to=upload_pfad, blank=True)
    veranstaltung = models.ForeignKey("events.Veranstaltung", on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name="buchungen", verbose_name=_("Veranstaltung"))
    quelle = models.CharField(_("Herkunft"), max_length=8, choices=QUELLE, default="manuell", editable=False)
    quelle_id = models.PositiveIntegerField(null=True, blank=True, editable=False)
    ablage = models.ForeignKey("documents.Ablagedokument", on_delete=models.SET_NULL, null=True, blank=True,
                               editable=False, related_name="+", verbose_name=_("Ablage"))

    class Meta:
        verbose_name = _("Buchung")
        verbose_name_plural = _("Kassenbuch")
        ordering = ["-datum", "-id"]
        constraints = [models.UniqueConstraint(fields=["verein", "quelle", "quelle_id"],
                                               condition=Q(quelle_id__isnull=False), name="buchung_quelle_eindeutig")]

    def __str__(self):
        return f"{self.belegnummer or '–'} {self.text}"

    @property
    def vorzeichenbetrag(self):
        return self.betrag if self.typ == "einnahme" else -self.betrag

    @property
    def gesperrt(self):
        """Buchungen in einem abgeschlossenen Kassenbericht sind unveränderbar."""
        return Kassenbericht.objects.filter(verein_id=self.verein_id, status="abgeschlossen", von__lte=self.datum,
                                            bis__gte=self.datum).exists()

    def clean(self):
        if self.kategorie_id and self.typ and self.kategorie.typ != self.typ:
            raise ValidationError(_("Die Kategorie passt nicht zur Art (Einnahme/Ausgabe)."))
        if self.konto_id and self.datum and self.datum < self.konto.eroeffnungsdatum:
            raise ValidationError(_("Das Buchungsdatum liegt vor der Kontoeröffnung (%(datum)s).") %
                                  {"datum": f"{self.konto.eroeffnungsdatum:%d.%m.%Y}"})
        if self.datum and self.verein_id and self.gesperrt:
            raise ValidationError(_("Der Zeitraum gehört zu einem abgeschlossenen Kassenbericht – Buchung nicht möglich."))

    def save(self, *args, **kwargs):
        if not self.belegnummer:
            self.belegnummer = f"B-{self.datum.year}-{naechste_nummer(self.verein_id, 'BELEG', self.datum.year):06d}"
        super().save(*args, **kwargs)


class Kassenbericht(TenantModel):
    STATUS = [("entwurf", _("Entwurf")), ("abgeschlossen", _("Abgeschlossen"))]
    titel = models.CharField(_("Titel"), max_length=150, help_text=_("z. B. Kassenbericht 2026"))
    von = models.DateField(_("Zeitraum von"))
    bis = models.DateField(_("Zeitraum bis"))
    status = models.CharField(_("Status"), max_length=13, choices=STATUS, default="entwurf", editable=False)
    kassenwart = models.CharField(_("Kassenwart/in"), max_length=100, blank=True)
    pruefer_1 = models.CharField(_("Kassenprüfer/in 1"), max_length=100, blank=True)
    pruefer_2 = models.CharField(_("Kassenprüfer/in 2"), max_length=100, blank=True)
    kassenbestand_gezaehlt = models.DecimalField(_("Gezählter Bargeldbestand am Stichtag (€)"), max_digits=12,
                                                 decimal_places=2, null=True, blank=True)
    bankbestand_laut_auszug = models.DecimalField(_("Kontostand laut Kontoauszug am Stichtag (€)"), max_digits=12,
                                                  decimal_places=2, null=True, blank=True,
                                                  help_text=_("Summe aller Bankkonten laut Auszug"))
    pruefbemerkung = models.TextField(_("Bemerkungen / Prüfungsergebnis"), blank=True,
                                      help_text=_("Wird im Bericht abgedruckt (z. B. Ergebnis der Kassenprüfung, Empfehlung zur Entlastung)"))
    abgeschlossen_am = models.DateField(_("Abgeschlossen am"), null=True, blank=True, editable=False)
    ablage = models.ForeignKey("documents.Ablagedokument", on_delete=models.SET_NULL, null=True, blank=True,
                               editable=False, related_name="+", verbose_name=_("Ablage"))

    class Meta:
        verbose_name = _("Kassenbericht")
        verbose_name_plural = _("Kassenberichte")
        ordering = ["-bis", "-id"]

    def __str__(self):
        return self.titel

    def clean(self):
        if self.von and self.bis and self.bis < self.von:
            raise ValidationError(_("Das Ende liegt vor dem Beginn."))
