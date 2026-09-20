from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Case, DecimalField, F, Sum, When

from apps.core.fields import VerschluesseltesTextField
from apps.core.models import TenantModel, naechste_nummer


def wirksame_summe(rechnungen_qs):
    """Summe der Zahlungen (Rücklastschriften negativ) zu einer Rechnungs-Queryset."""
    s = Zahlung.objects.filter(rechnung__in=rechnungen_qs).aggregate(s=Sum(Case(
        When(ruecklastschrift=True, then=-F("betrag")), default=F("betrag"),
        output_field=DecimalField(max_digits=10, decimal_places=2))))["s"]
    return s or Decimal("0")


class Beitragsjahr(TenantModel):
    jahr = models.PositiveIntegerField("Jahr")
    faelligkeit = models.DateField("Fälligkeit")
    alters_stichtag = models.DateField("Stichtag für Altersregeln")
    abgerechnet_am = models.DateTimeField("Abgerechnet am", null=True, blank=True, editable=False)
    bemerkung = models.CharField("Bemerkung", max_length=200, blank=True)

    class Meta:
        verbose_name = "Beitragsjahr"
        verbose_name_plural = "Beitragsjahre"
        unique_together = [("verein", "jahr")]
        ordering = ["-jahr"]

    def __str__(self):
        return f"Beitragsjahr {self.jahr}"


class Beitragsregel(TenantModel):
    """Regeln ohne Programmierung: erste passende Regel (höchste Priorität) gewinnt."""
    name = models.CharField("Name", max_length=100)
    mitgliedsart = models.ForeignKey("members.Mitgliedsart", on_delete=models.CASCADE, null=True, blank=True,
                                     verbose_name="Nur für Mitgliedsart")
    nur_familie = models.BooleanField("Nur Familienmitgliedschaften", default=False,
                                      help_text="Betrag wird nur beim 'Familienzahler' berechnet")
    alter_von = models.PositiveIntegerField("Alter von", null=True, blank=True)
    alter_bis = models.PositiveIntegerField("Alter bis (einschl.)", null=True, blank=True)
    betrag = models.DecimalField("Jahresbeitrag (€)", max_digits=8, decimal_places=2)
    prioritaet = models.IntegerField("Priorität (höher = zuerst)", default=10)
    gueltig_ab_jahr = models.PositiveIntegerField("Gültig ab Jahr", null=True, blank=True)
    gueltig_bis_jahr = models.PositiveIntegerField("Gültig bis Jahr", null=True, blank=True)
    aktiv = models.BooleanField("Aktiv", default=True)

    class Meta:
        verbose_name = "Beitragsregel"
        verbose_name_plural = "Beitragsregeln"
        ordering = ["-prioritaet", "name"]

    def __str__(self):
        return self.name


class Rechnung(TenantModel):
    TYP = [("beitrag", "Beitragsrechnung"), ("individuell", "Individuelle Rechnung"),
           ("sammel", "Sammelrechnung"), ("gutschrift", "Gutschrift"), ("storno", "Storno")]
    STATUS = [("entwurf", "Entwurf"), ("offen", "Offen"), ("teilbezahlt", "Teilweise bezahlt"),
              ("bezahlt", "Bezahlt"), ("storniert", "Storniert"), ("verbucht", "Verbucht")]

    nummer = models.CharField("Rechnungsnummer", max_length=30, null=True, blank=True, default=None, editable=False)
    typ = models.CharField("Art", max_length=12, choices=TYP, default="individuell")
    status = models.CharField("Status", max_length=12, choices=STATUS, default="entwurf")
    mitglied = models.ForeignKey("members.Mitglied", on_delete=models.PROTECT, null=True, blank=True,
                                 verbose_name="Mitglied")
    empfaenger_name = models.CharField("Empfänger", max_length=200, blank=True)
    empfaenger_anschrift = models.TextField("Anschrift des Empfängers", blank=True)
    datum = models.DateField("Rechnungsdatum", default=date.today)
    faellig_am = models.DateField("Fällig am", null=True, blank=True)
    jahr = models.PositiveIntegerField("Beitragsjahr", null=True, blank=True)
    zeitraum_von = models.DateField("Leistungszeitraum von", null=True, blank=True)
    zeitraum_bis = models.DateField("Leistungszeitraum bis", null=True, blank=True)
    betrag = models.DecimalField("Betrag (€)", max_digits=10, decimal_places=2, default=0, editable=False)
    kopftext = models.TextField("Text oben", blank=True)
    fusstext = models.TextField("Text unten", blank=True)
    storno_von = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, editable=False,
                                   related_name="gegenbuchungen", verbose_name="Bezieht sich auf")
    versendet_am = models.DateTimeField("Per E-Mail versendet", null=True, blank=True, editable=False)
    bemerkung = models.CharField("Bemerkung", max_length=200, blank=True)

    class Meta:
        verbose_name = "Rechnung"
        verbose_name_plural = "Rechnungen"
        unique_together = [("verein", "nummer")]
        ordering = ["-datum", "-id"]

    def __str__(self):
        return self.nummer or f"Entwurf #{self.pk or 'neu'}"

    def save(self, *args, **kwargs):
        if self.mitglied_id and not self.empfaenger_name:
            m = self.mitglied
            self.empfaenger_name = m.name
            self.empfaenger_anschrift = "\n".join(z for z in (m.strasse, f"{m.plz} {m.ort}".strip()) if z)
        if not self.kopftext:
            self.kopftext = self.verein.rechnung_kopftext
        if not self.fusstext:
            self.fusstext = self.verein.rechnung_fusstext
        if not self.faellig_am and self.datum:
            self.faellig_am = self.datum + timedelta(days=self.verein.zahlungsziel_tage)
        if self.status != "entwurf" and not self.nummer:
            self.nummer_vergeben()
        super().save(*args, **kwargs)

    def nummer_vergeben(self):
        self.nummer = f"RE-{self.datum.year}-{naechste_nummer(self.verein_id, 'RE', self.datum.year):06d}"

    @property
    def bezahlt_summe(self):
        if not self.pk:
            return Decimal("0")
        return wirksame_summe(Rechnung.objects.filter(pk=self.pk))

    @property
    def offen_betrag(self):
        return self.betrag - self.bezahlt_summe

    @property
    def ueberfaellig(self):
        return self.status in ("offen", "teilbezahlt") and self.faellig_am and self.faellig_am < date.today()

    def neu_berechnen(self):
        s = self.positionen.aggregate(s=Sum(F("menge") * F("einzelpreis"),
                                            output_field=DecimalField(max_digits=12, decimal_places=2)))["s"]
        self.betrag = s or Decimal("0")
        Rechnung.objects.filter(pk=self.pk).update(betrag=self.betrag)

    def aktualisiere_status(self):
        if self.status in ("entwurf", "storniert", "verbucht"):
            return
        bez = self.bezahlt_summe
        neu = "bezahlt" if (bez >= self.betrag and self.betrag > 0) else ("teilbezahlt" if bez > 0 else "offen")
        if neu != self.status:
            self.status = neu
            self.save(update_fields=["status", "geaendert"])


class Rechnungsposition(TenantModel):
    rechnung = models.ForeignKey(Rechnung, on_delete=models.CASCADE, related_name="positionen",
                                 verbose_name="Rechnung")
    text = models.CharField("Bezeichnung", max_length=300)
    menge = models.DecimalField("Menge", max_digits=8, decimal_places=2, default=1)
    einzelpreis = models.DecimalField("Einzelpreis (€)", max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = "Rechnungsposition"
        verbose_name_plural = "Rechnungspositionen"
        ordering = ["id"]

    def __str__(self):
        return self.text

    @property
    def betrag(self):
        return self.menge * self.einzelpreis

    def clean(self):
        if self.rechnung_id and self.rechnung.status != "entwurf":
            raise ValidationError("Positionen können nur bei Rechnungen im Status 'Entwurf' geändert werden.")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.rechnung.neu_berechnen()

    def delete(self, *args, **kwargs):
        r = self.rechnung
        if r.status != "entwurf":
            raise ValidationError("Nur bei Entwürfen möglich.")
        super().delete(*args, **kwargs)
        r.neu_berechnen()


class Bankumsatz(TenantModel):
    STATUS = [("neu", "Neu"), ("zugeordnet", "Zugeordnet"), ("manuell", "Manuelle Zuordnung erforderlich"),
              ("ignoriert", "Ignoriert")]
    buchungsdatum = models.DateField("Buchungsdatum")
    betrag = models.DecimalField("Betrag (€)", max_digits=10, decimal_places=2)
    gegenkonto_name = models.CharField("Name", max_length=200, blank=True)
    gegenkonto_iban = VerschluesseltesTextField("IBAN", blank=True)
    verwendungszweck = models.TextField("Verwendungszweck", blank=True)
    status = models.CharField("Status", max_length=12, choices=STATUS, default="neu")
    pruefsumme = models.CharField(max_length=40, blank=True, editable=False)

    AUDIT_MASK = ("gegenkonto_iban",)

    class Meta:
        verbose_name = "Bankumsatz"
        verbose_name_plural = "Bankumsätze"
        ordering = ["-buchungsdatum", "-id"]
        indexes = [models.Index(fields=["verein", "pruefsumme"])]

    def __str__(self):
        return f"{self.buchungsdatum:%d.%m.%Y} {self.gegenkonto_name} {self.betrag} €"


class Zahlung(TenantModel):
    ART = [("ueberweisung", "Überweisung"), ("lastschrift", "SEPA-Lastschrift"), ("bar", "Bar"),
           ("sonstige", "Sonstige")]
    rechnung = models.ForeignKey(Rechnung, on_delete=models.PROTECT, related_name="zahlungen", verbose_name="Rechnung")
    datum = models.DateField("Zahlungsdatum", default=date.today)
    betrag = models.DecimalField("Betrag (€)", max_digits=10, decimal_places=2)
    art = models.CharField("Zahlungsart", max_length=12, choices=ART, default="ueberweisung")
    ruecklastschrift = models.BooleanField("Rücklastschrift (Betrag wird abgezogen)", default=False)
    referenz = models.CharField("Referenz", max_length=200, blank=True)
    bemerkung = models.CharField("Bemerkung", max_length=200, blank=True)
    bankumsatz = models.OneToOneField(Bankumsatz, on_delete=models.SET_NULL, null=True, blank=True, editable=False,
                                      related_name="zahlung")

    class Meta:
        verbose_name = "Zahlung"
        verbose_name_plural = "Zahlungen"
        ordering = ["-datum", "-id"]

    def __str__(self):
        return f"{'−' if self.ruecklastschrift else ''}{self.betrag} € auf {self.rechnung}"

    def clean(self):
        if self.rechnung_id and self.rechnung.status in ("entwurf", "storniert", "verbucht"):
            raise ValidationError("Auf diese Rechnung kann keine Zahlung gebucht werden (Status: "
                                  f"{self.rechnung.get_status_display()}).")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.rechnung.aktualisiere_status()

    def delete(self, *args, **kwargs):
        r = self.rechnung
        super().delete(*args, **kwargs)
        r.aktualisiere_status()


class Mahnung(TenantModel):
    STUFE = [(1, "Zahlungserinnerung"), (2, "1. Mahnung"), (3, "2. Mahnung / letzte Mahnung")]
    rechnung = models.ForeignKey(Rechnung, on_delete=models.PROTECT, related_name="mahnungen", verbose_name="Rechnung")
    stufe = models.PositiveSmallIntegerField("Stufe", choices=STUFE, default=1)
    datum = models.DateField("Datum", default=date.today)
    frist = models.DateField("Neue Zahlungsfrist")
    gebuehr = models.DecimalField("Mahngebühr (€)", max_digits=8, decimal_places=2, default=0)

    class Meta:
        verbose_name = "Mahnung"
        verbose_name_plural = "Mahnungen"
        ordering = ["-datum", "-stufe"]

    def __str__(self):
        return f"{self.get_stufe_display()} zu {self.rechnung}"
