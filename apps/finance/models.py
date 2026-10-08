from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Case, DecimalField, F, Sum, When
from django.utils.translation import gettext_lazy as _

from apps.core.fields import VerschluesseltesTextField
from apps.core.models import TenantModel, naechste_nummer
from apps.core.util import pruefe_oeffentliche_adresse, upload_pfad

# Bewusst kein gettext_lazy: wird als tatsächlicher Feldwert in die ZUGFeRD/Factur-X-XML (BT-120) geschrieben,
# die facturx-Bibliothek prüft dort strikt auf echten str (ein Lazy-Proxy wird abgelehnt).
STANDARD_STEUERHINWEIS = "Steuerbefreiung nach § 4 UStG (ideeller Bereich) - bitte prüfen"


def wirksame_summe(rechnungen_qs):
    """Summe der Zahlungen (Rücklastschriften negativ) zu einer Rechnungs-Queryset."""
    s = Zahlung.objects.filter(rechnung__in=rechnungen_qs).aggregate(s=Sum(Case(
        When(ruecklastschrift=True, then=-F("betrag")), default=F("betrag"),
        output_field=DecimalField(max_digits=10, decimal_places=2))))["s"]
    return s or Decimal("0")


class Beitragsjahr(TenantModel):
    jahr = models.PositiveIntegerField(_("Jahr"))
    faelligkeit = models.DateField(_("Fälligkeit"))
    alters_stichtag = models.DateField(_("Stichtag für Altersregeln"))
    abgerechnet_am = models.DateTimeField(_("Abgerechnet am"), null=True, blank=True, editable=False)
    bemerkung = models.CharField(_("Bemerkung"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("Beitragsjahr")
        verbose_name_plural = _("Beitragsjahre")
        unique_together = [("verein", "jahr")]
        ordering = ["-jahr"]

    def __str__(self):
        return f"Beitragsjahr {self.jahr}"


class Beitragsregel(TenantModel):
    """Regeln ohne Programmierung: erste passende Regel (höchste Priorität) gewinnt."""
    name = models.CharField(_("Name"), max_length=100)
    mitgliedsart = models.ForeignKey("members.Mitgliedsart", on_delete=models.CASCADE, null=True, blank=True,
                                     verbose_name=_("Nur für Mitgliedsart"))
    nur_familie = models.BooleanField(_("Nur Familienmitgliedschaften"), default=False,
                                      help_text=_("Betrag wird nur beim 'Familienzahler' berechnet"))
    alter_von = models.PositiveIntegerField(_("Alter von"), null=True, blank=True)
    alter_bis = models.PositiveIntegerField(_("Alter bis (einschl.)"), null=True, blank=True)
    betrag = models.DecimalField(_("Jahresbeitrag (€)"), max_digits=8, decimal_places=2)
    prioritaet = models.IntegerField(_("Priorität (höher = zuerst)"), default=10)
    gueltig_ab_jahr = models.PositiveIntegerField(_("Gültig ab Jahr"), null=True, blank=True)
    gueltig_bis_jahr = models.PositiveIntegerField(_("Gültig bis Jahr"), null=True, blank=True)
    aktiv = models.BooleanField(_("Aktiv"), default=True)

    class Meta:
        verbose_name = _("Beitragsregel")
        verbose_name_plural = _("Beitragsregeln")
        ordering = ["-prioritaet", "name"]

    def __str__(self):
        return self.name


class Rechnung(TenantModel):
    TYP = [("beitrag", _("Beitragsrechnung")), ("individuell", _("Individuelle Rechnung")),
           ("sammel", _("Sammelrechnung")), ("gutschrift", _("Gutschrift")), ("storno", _("Storno"))]
    STATUS = [("entwurf", _("Entwurf")), ("offen", _("Offen")), ("teilbezahlt", _("Teilweise bezahlt")),
              ("bezahlt", _("Bezahlt")), ("storniert", _("Storniert")), ("verbucht", _("Verbucht"))]

    nummer = models.CharField(_("Rechnungsnummer"), max_length=30, null=True, blank=True, default=None, editable=False)
    typ = models.CharField(_("Art"), max_length=12, choices=TYP, default="individuell")
    status = models.CharField(_("Status"), max_length=12, choices=STATUS, default="entwurf")
    mitglied = models.ForeignKey("members.Mitglied", on_delete=models.PROTECT, null=True, blank=True,
                                 verbose_name=_("Mitglied"))
    empfaenger_name = models.CharField(_("Empfänger"), max_length=200, blank=True)
    empfaenger_anschrift = models.TextField(_("Anschrift des Empfängers"), blank=True)
    datum = models.DateField(_("Rechnungsdatum"), default=date.today)
    faellig_am = models.DateField(_("Fällig am"), null=True, blank=True)
    jahr = models.PositiveIntegerField(_("Beitragsjahr"), null=True, blank=True)
    zeitraum_von = models.DateField(_("Leistungszeitraum von"), null=True, blank=True)
    zeitraum_bis = models.DateField(_("Leistungszeitraum bis"), null=True, blank=True)
    betrag = models.DecimalField(_("Betrag brutto (€)"), max_digits=10, decimal_places=2, default=0, editable=False)
    nettobetrag = models.DecimalField(_("Nettobetrag (€)"), max_digits=10, decimal_places=2, default=0, editable=False)
    steuerbetrag = models.DecimalField(_("Umsatzsteuer (€)"), max_digits=10, decimal_places=2, default=0, editable=False)
    kopftext = models.TextField(_("Text oben"), blank=True)
    fusstext = models.TextField(_("Text unten"), blank=True)
    storno_von = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, editable=False,
                                   related_name="gegenbuchungen", verbose_name=_("Bezieht sich auf"))
    versendet_am = models.DateTimeField(_("Per E-Mail versendet"), null=True, blank=True, editable=False)
    bemerkung = models.CharField(_("Bemerkung"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("Rechnung")
        verbose_name_plural = _("Rechnungen")
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

    @property
    def rueckzahlung_noetig(self):
        """Storno/Gutschrift auf eine bereits bezahlte Rechnung: der (negative) Betrag muss an den ursprünglichen
        Zahler zurückerstattet werden."""
        return self.typ in ("storno", "gutschrift") and self.betrag < 0

    @property
    def rueckzahlung_bereits_gebucht(self):
        if not self.pk:
            return Decimal("0")
        return self.zahlungen.filter(art="rueckzahlung").aggregate(s=Sum("betrag"))["s"] or Decimal("0")

    @property
    def rueckzahlung_offen(self):
        return -self.betrag - self.rueckzahlung_bereits_gebucht

    def neu_berechnen(self):
        zeilen = list(self.positionen.all())
        self.nettobetrag = sum((p.nettobetrag for p in zeilen), Decimal("0.00"))
        self.steuerbetrag = sum((p.steuerbetrag for p in zeilen), Decimal("0.00"))
        self.betrag = self.nettobetrag + self.steuerbetrag
        # .save() statt .update(), damit die Betragsänderung - anders als bei einem reinen SQL-UPDATE - auch
        # im Änderungsprotokoll erscheint (das haengt an pre_save/post_save-Signalen, die .update() nicht
        # auslöst).
        self.save(update_fields=["nettobetrag", "steuerbetrag", "betrag"])

    @property
    def steuer_gruppen(self):
        """Positionen gruppiert nach Umsatzsteuersatz -> {satz: {"netto": ..., "steuer": ...}} - für die
        Steueraufschlüsselung auf Rechnung/PDF und E-Rechnung (BG-23), auch bei gemischten Steuersätzen."""
        gruppen = {}
        for p in self.positionen.all():
            g = gruppen.setdefault(p.steuersatz, {"netto": Decimal("0.00"), "steuer": Decimal("0.00")})
            g["netto"] += p.nettobetrag
            g["steuer"] += p.steuerbetrag
        return gruppen

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
                                 verbose_name=_("Rechnung"))
    text = models.CharField(_("Bezeichnung"), max_length=300)
    # Storno/Gutschrift erzeugen ihre Ausgleichsposition mit negativem einzelpreis direkt per .create() (siehe
    # services.storniere()/gutschrift()) - das umgeht Validatoren bewusst (die greifen nur bei full_clean()/
    # ModelForm). Hier wird daher nur der normale Erfassungsweg über das Formular abgesichert.
    menge = models.DecimalField(_("Menge"), max_digits=8, decimal_places=2, default=1,
                                validators=[MinValueValidator(Decimal("0.01"))])
    einzelpreis = models.DecimalField(_("Einzelpreis netto (€)"), max_digits=10, decimal_places=2,
                                      validators=[MinValueValidator(Decimal("0.01"))])
    steuersatz = models.DecimalField(_("Umsatzsteuersatz (%)"), max_digits=5, decimal_places=2, default=0,
                                     help_text=_("0 für umsatzsteuerfreie Positionen (z. B. ideeller Bereich)."))

    class Meta:
        verbose_name = _("Rechnungsposition")
        verbose_name_plural = _("Rechnungspositionen")
        ordering = ["id"]

    def __str__(self):
        return self.text

    @property
    def nettobetrag(self):
        return self.menge * self.einzelpreis

    @property
    def steuerbetrag(self):
        return (self.nettobetrag * self.steuersatz / 100).quantize(Decimal("0.01"))

    @property
    def bruttobetrag(self):
        return self.nettobetrag + self.steuerbetrag

    @property
    def betrag(self):
        """Historischer Name für nettobetrag (vor Einführung der Umsatzsteuer war das der einzige Betrag)."""
        return self.nettobetrag

    def clean(self):
        if self.rechnung_id and self.rechnung.status != "entwurf":
            raise ValidationError(_("Positionen können nur bei Rechnungen im Status 'Entwurf' geändert werden."))

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.rechnung.neu_berechnen()

    def delete(self, *args, **kwargs):
        r = self.rechnung
        if r.status != "entwurf":
            raise ValidationError(_("Nur bei Entwürfen möglich."))
        super().delete(*args, **kwargs)
        r.neu_berechnen()


class Bankumsatz(TenantModel):
    STATUS = [("neu", _("Neu")), ("zugeordnet", _("Zugeordnet")), ("manuell", _("Manuelle Zuordnung erforderlich")),
              ("ignoriert", _("Ignoriert"))]
    buchungsdatum = models.DateField(_("Buchungsdatum"))
    betrag = models.DecimalField(_("Betrag (€)"), max_digits=10, decimal_places=2)
    gegenkonto_name = models.CharField(_("Name"), max_length=200, blank=True)
    gegenkonto_iban = VerschluesseltesTextField(_("IBAN"), blank=True)
    verwendungszweck = models.TextField(_("Verwendungszweck"), blank=True)
    status = models.CharField(_("Status"), max_length=12, choices=STATUS, default="neu")
    pruefsumme = models.CharField(max_length=40, blank=True, editable=False)
    fints_zugang = models.ForeignKey("FinTSZugang", on_delete=models.SET_NULL, null=True, blank=True,
                                     editable=False, related_name="bankumsaetze", verbose_name=_("FinTS-Zugang"))

    AUDIT_MASK = ("gegenkonto_iban",)

    class Meta:
        verbose_name = _("Bankumsatz")
        verbose_name_plural = _("Bankumsätze")
        ordering = ["-buchungsdatum", "-id"]
        indexes = [models.Index(fields=["verein", "pruefsumme"])]

    def __str__(self):
        return f"{self.buchungsdatum:%d.%m.%Y} {self.gegenkonto_name} {self.betrag} €"


class Zahlung(TenantModel):
    ART = [("ueberweisung", _("Überweisung")), ("lastschrift", _("SEPA-Lastschrift")), ("bar", _("Bar")),
           ("rueckzahlung", _("Rückzahlung")), ("sonstige", _("Sonstige"))]
    rechnung = models.ForeignKey(Rechnung, on_delete=models.PROTECT, related_name="zahlungen", verbose_name=_("Rechnung"))
    datum = models.DateField(_("Zahlungsdatum"), default=date.today)
    betrag = models.DecimalField(_("Betrag (€)"), max_digits=10, decimal_places=2, help_text=_("immer positiv erfassen"),
                                 validators=[MinValueValidator(Decimal("0.01"))])
    art = models.CharField(_("Zahlungsart"), max_length=12, choices=ART, default="ueberweisung")
    ruecklastschrift = models.BooleanField(_("Rücklastschrift (Betrag wird abgezogen)"), default=False)
    referenz = models.CharField(_("Referenz"), max_length=200, blank=True)
    bemerkung = models.CharField(_("Bemerkung"), max_length=200, blank=True)
    bankumsatz = models.OneToOneField(Bankumsatz, on_delete=models.SET_NULL, null=True, blank=True, editable=False,
                                      related_name="zahlung")

    class Meta:
        verbose_name = _("Zahlung")
        verbose_name_plural = _("Zahlungen")
        ordering = ["-datum", "-id"]

    def __str__(self):
        return f"{'−' if self.ruecklastschrift else ''}{self.betrag} € auf {self.rechnung}"

    @property
    def gesperrt(self):
        """Bereits ins Kassenbuch uebernommene Zahlungen in einem abgeschlossenen Kassenbericht sind
        unveraenderlich - sonst wuerde der bereits abgeschlossene Bericht nicht mehr zum (dann veraenderten)
        Live-Zustand passen."""
        from apps.accounting.models import Buchung
        b = Buchung.objects.filter(verein_id=self.verein_id, quelle="zahlung", quelle_id=self.pk).first()
        return bool(b and b.gesperrt)

    def clean(self):
        if self.gesperrt:
            raise ValidationError(_("Diese Zahlung wurde bereits in einen abgeschlossenen Kassenbericht "
                                    "übernommen und kann nicht mehr geändert werden."))
        if not self.rechnung_id:
            return
        r = self.rechnung
        # Rückzahlungen auf eine Storno-/Gutschrift-Rechnung sind der einzige Fall, in dem eine "verbuchte"
        # Rechnung noch eine Zahlung erhalten darf - sie gleicht den einbehaltenen/erstatteten Betrag aus.
        ist_rueckzahlung = self.art == "rueckzahlung" and r.typ in ("storno", "gutschrift")
        if r.status == "entwurf" or (r.status in ("storniert", "verbucht") and not ist_rueckzahlung):
            raise ValidationError(_("Auf diese Rechnung kann keine Zahlung gebucht werden (Status: %(status)s).") %
                                  {"status": r.get_status_display()})

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.rechnung.aktualisiere_status()

    def delete(self, *args, **kwargs):
        r = self.rechnung
        super().delete(*args, **kwargs)
        r.aktualisiere_status()


class SepaEinzug(TenantModel):
    nummer = models.CharField(_("Nummer"), max_length=30, editable=False)
    faelligkeitsdatum = models.DateField(_("Fälligkeitsdatum (Einzugstermin)"))
    anzahl = models.PositiveIntegerField(_("Anzahl Lastschriften"), default=0, editable=False)
    summe = models.DecimalField(_("Summe (€)"), max_digits=10, decimal_places=2, default=0, editable=False)
    datei = models.FileField(_("SEPA-XML-Datei"), upload_to=upload_pfad, editable=False)

    class Meta:
        verbose_name = _("SEPA-Einzug")
        verbose_name_plural = _("SEPA-Einzüge")
        unique_together = [("verein", "nummer")]
        ordering = ["-erstellt"]

    def __str__(self):
        return f"{self.nummer} ({self.faelligkeitsdatum:%d.%m.%Y})"


class SepaEinzugPosition(TenantModel):
    SEQUENZTYP = [("FRST", _("Erstlastschrift (FRST)")), ("RCUR", _("Folgelastschrift (RCUR)"))]
    einzug = models.ForeignKey(SepaEinzug, on_delete=models.CASCADE, related_name="positionen", verbose_name=_("Einzug"))
    rechnung = models.ForeignKey(Rechnung, on_delete=models.PROTECT, related_name="sepa_positionen",
                                 verbose_name=_("Rechnung"))
    mitglied = models.ForeignKey("members.Mitglied", on_delete=models.PROTECT, related_name="+",
                                 verbose_name=_("Mitglied"))
    betrag = models.DecimalField(_("Betrag (€)"), max_digits=10, decimal_places=2)
    mandatsreferenz = models.CharField(_("SEPA-Mandatsreferenz"), max_length=35)
    mandatsdatum = models.DateField(_("Datum des SEPA-Mandats"))
    sequenztyp = models.CharField(_("Sequenztyp"), max_length=4, choices=SEQUENZTYP)

    class Meta:
        verbose_name = _("SEPA-Einzugsposition")
        verbose_name_plural = _("SEPA-Einzugspositionen")
        ordering = ["id"]

    def __str__(self):
        return f"{self.mitglied.name}: {self.betrag} € ({self.rechnung})"


class FinTSZugang(TenantModel):
    """Verbindungsdaten fuer den FinTS-Abruf - die Bank-PIN wird bewusst NICHT gespeichert, sondern bei jedem
    Abruf erneut eingegeben; die Online-Banking-Kennung (Login-Name, keine PIN) liegt verschluesselt in der
    Datenbank (siehe VerschluesseltesTextField). Ein Verein kann mehrere Zugaenge anlegen (z. B. je Bank); jedes
    Kassenbuch-Konto kann optional einem davon zugeordnet werden (accounting.Konto.fints_zugang)."""
    bezeichnung = models.CharField(_("Bezeichnung"), max_length=100, default="",
                                   help_text=_("Zur Unterscheidung, wenn mehrere Zugänge angelegt sind, z. B. Name der Bank"))
    blz = models.CharField(_("Bankleitzahl"), max_length=8)
    kennung = VerschluesseltesTextField(_("Online-Banking-Kennung"),
                                        help_text=_("Die Kennung fürs Online-Banking, nicht die PIN"))
    bank_url = models.URLField(_("FinTS-Adresse der Bank"),
                               help_text=_("Von der Bank vorgegebene FinTS-Serveradresse, z. B. https://banking.beispielbank.de/fints30"))
    tage = models.PositiveIntegerField(_("Tage rückwirkend abrufen"), default=60)
    abzurufende_ibans = models.TextField(
        _("Abzurufende Konten (IBAN)"), blank=True,
        help_text=_("Kommagetrennt. Leer = alle Konten dieses Zugangs werden abgerufen (Standard). Ein "
                  "Online-Banking-Zugang deckt oft mehrere Konten ab - hier lässt sich der Abruf auf einzelne "
                  "davon beschränken. Über „Kontodaten abrufen“ bequem per Haken auswählbar."))
    letzter_abruf = models.DateTimeField(_("Letzter erfolgreicher Abruf"), null=True, blank=True, editable=False)
    letzte_meldung = models.CharField(_("Letzte Meldung"), max_length=300, blank=True, editable=False)

    AUDIT_MASK = ("kennung",)

    class Meta:
        verbose_name = _("FinTS-Zugang")
        verbose_name_plural = _("FinTS-Zugänge")
        ordering = ["bezeichnung"]

    def __str__(self):
        return self.bezeichnung

    def clean(self):
        if self.bank_url:
            pruefe_oeffentliche_adresse(self.bank_url)

    @property
    def iban_liste(self):
        return [i.strip().replace(" ", "").upper() for i in self.abzurufende_ibans.split(",") if i.strip()]


class Mahnung(TenantModel):
    STUFE = [(1, _("Zahlungserinnerung")), (2, _("1. Mahnung")), (3, _("2. Mahnung / letzte Mahnung"))]
    rechnung = models.ForeignKey(Rechnung, on_delete=models.PROTECT, related_name="mahnungen", verbose_name=_("Rechnung"))
    stufe = models.PositiveSmallIntegerField(_("Stufe"), choices=STUFE, default=1)
    datum = models.DateField(_("Datum"), default=date.today)
    frist = models.DateField(_("Neue Zahlungsfrist"))
    gebuehr = models.DecimalField(_("Mahngebühr (€)"), max_digits=8, decimal_places=2, default=0)

    class Meta:
        verbose_name = _("Mahnung")
        verbose_name_plural = _("Mahnungen")
        ordering = ["-datum", "-stufe"]

    def __str__(self):
        return f"{self.get_stufe_display()} zu {self.rechnung}"
