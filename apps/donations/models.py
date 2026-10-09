from datetime import date
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TenantModel, naechste_nummer


class Zuwendungsbestaetigung(TenantModel):
    TYP = [("einzel", _("Einzelbestätigung")), ("sammel", _("Sammelbestätigung"))]
    ART = [("geld", _("Geldzuwendung")), ("sach", _("Sachzuwendung"))]
    STATUS = [("entwurf", _("Entwurf")), ("ausgestellt", _("Ausgestellt")), ("storniert", _("Storniert"))]
    nummer = models.CharField(_("Nummer"), max_length=30, blank=True, editable=False)
    typ = models.CharField(_("Typ"), max_length=8, choices=TYP, default="einzel")
    art = models.CharField(_("Art"), max_length=6, choices=ART, default="geld")
    status = models.CharField(_("Status"), max_length=12, choices=STATUS, default="entwurf", editable=False)
    spender_name = models.CharField(_("Zuwendender"), max_length=200)
    spender_anschrift = models.CharField(_("Anschrift des Zuwendenden"), max_length=300)
    betrag = models.DecimalField(_("Betrag (€)"), max_digits=10, decimal_places=2,
                                 validators=[MinValueValidator(Decimal("0.01"))])
    datum_von = models.DateField(_("Zuwendung von"))
    datum_bis = models.DateField(_("Zuwendung bis"))
    ist_mitgliedsbeitrag = models.BooleanField(_("Es handelt sich um einen Mitgliedsbeitrag"), default=False)
    verzicht_aufwendungen = models.BooleanField(_("Verzicht auf Erstattung von Aufwendungen"), default=False)
    sach_beschreibung = models.TextField(_("Bezeichnung der Sachzuwendung"), blank=True)
    sach_herkunft = models.CharField(_("Herkunft der Sachzuwendung"), max_length=200, blank=True)
    sach_wertermittlung = models.CharField(_("Wertermittlung"), max_length=200, blank=True)
    ausgestellt_am = models.DateField(_("Ausgestellt am"), null=True, blank=True, editable=False)
    vereinsdaten = models.JSONField(_("Vereinsdaten zum Ausstellungszeitpunkt"), default=dict, blank=True, editable=False)

    class Meta:
        verbose_name = _("Spendenquittung")
        verbose_name_plural = _("Spendenquittungen (Zuwendungsbestätigungen)")
        ordering = ["-datum_bis", "-id"]

    def __str__(self):
        return self.nummer or f"Entwurf #{self.pk or 'neu'}"

    def ausstellen(self):
        v = self.verein
        self.nummer = f"ZB-{date.today().year}-{naechste_nummer(self.verein_id, 'ZB', date.today().year):06d}"
        self.status, self.ausgestellt_am = "ausgestellt", date.today()
        self.vereinsdaten = {
            "name": v.name, "anschrift": v.adresszeile, "finanzamt": v.finanzamt, "steuernummer": v.steuernummer,
            "bescheid_art": v.get_bescheid_art_display(),
            "bescheid_datum": v.bescheid_datum.isoformat() if v.bescheid_datum else "",
            "bescheid_zeitraum": v.bescheid_zeitraum, "zwecke": v.beguenstigte_zwecke}
        self.save()


class Spende(TenantModel):
    ART = [("geld", _("Geldspende")), ("sach", _("Sachspende")), ("mitgliedsbeitrag", _("Mitgliedsbeitrag")),
           ("aufwandsverzicht", _("Aufwandsspende (Verzicht auf Erstattung)"))]
    HERKUNFT = [("", _("keine Angabe")), ("privat", _("Privatvermögen")), ("betrieb", _("Betriebsvermögen"))]
    spender = models.ForeignKey("members.Mitglied", on_delete=models.PROTECT, null=True, blank=True,
                                verbose_name=_("Spender (Mitglied)"))
    spender_name = models.CharField(_("Spender (Name, falls kein Mitglied)"), max_length=200, blank=True)
    spender_anschrift = models.CharField(_("Anschrift (falls kein Mitglied)"), max_length=300, blank=True)
    datum = models.DateField(_("Datum der Zuwendung"), default=date.today)
    betrag = models.DecimalField(_("Betrag / Wert (€)"), max_digits=10, decimal_places=2,
                                 validators=[MinValueValidator(Decimal("0.01"))])
    art = models.CharField(_("Art"), max_length=20, choices=ART, default="geld")
    zweck = models.CharField(_("Verwendungszweck"), max_length=200, blank=True)
    sach_beschreibung = models.TextField(_("Bezeichnung der Sachspende"), blank=True)
    sach_herkunft = models.CharField(_("Herkunft"), max_length=10, choices=HERKUNFT, blank=True)
    sach_wertermittlung = models.CharField(_("Wertermittlung"), max_length=200, blank=True,
                                           help_text=_("z. B. Kaufbeleg, Schätzung, Gutachten"))
    bankumsatz = models.ForeignKey("finance.Bankumsatz", on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+", verbose_name=_("Bankumsatz"))
    bestaetigung = models.ForeignKey(Zuwendungsbestaetigung, on_delete=models.SET_NULL, null=True, blank=True,
                                     editable=False, related_name="spenden", verbose_name=_("Spendenquittung"))
    bemerkung = models.CharField(_("Bemerkung"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("Spende")
        verbose_name_plural = _("Spenden")
        ordering = ["-datum", "-id"]

    def __str__(self):
        return f"{self.name_des_spenders} – {self.betrag} € ({self.datum:%d.%m.%Y})"

    @property
    def name_des_spenders(self):
        return self.spender.name if self.spender_id else (self.spender_name or "?")

    @property
    def anschrift_des_spenders(self):
        if self.spender_id:
            m = self.spender
            return ", ".join(x for x in (m.strasse, f"{m.plz} {m.ort}".strip()) if x)
        return self.spender_anschrift

    def spender_schluessel(self):
        return (f"m{self.spender_id}" if self.spender_id
                else f"x{self.spender_name.strip().lower()}|{self.spender_anschrift.strip().lower()}")
