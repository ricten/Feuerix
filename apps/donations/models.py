from datetime import date

from django.db import models

from apps.core.models import TenantModel, naechste_nummer


class Zuwendungsbestaetigung(TenantModel):
    TYP = [("einzel", "Einzelbestätigung"), ("sammel", "Sammelbestätigung")]
    ART = [("geld", "Geldzuwendung"), ("sach", "Sachzuwendung")]
    STATUS = [("entwurf", "Entwurf"), ("ausgestellt", "Ausgestellt"), ("storniert", "Storniert")]
    nummer = models.CharField("Nummer", max_length=30, blank=True, editable=False)
    typ = models.CharField("Typ", max_length=8, choices=TYP, default="einzel")
    art = models.CharField("Art", max_length=6, choices=ART, default="geld")
    status = models.CharField("Status", max_length=12, choices=STATUS, default="entwurf", editable=False)
    spender_name = models.CharField("Zuwendender", max_length=200)
    spender_anschrift = models.CharField("Anschrift des Zuwendenden", max_length=300)
    betrag = models.DecimalField("Betrag (€)", max_digits=10, decimal_places=2)
    datum_von = models.DateField("Zuwendung von")
    datum_bis = models.DateField("Zuwendung bis")
    ist_mitgliedsbeitrag = models.BooleanField("Es handelt sich um einen Mitgliedsbeitrag", default=False)
    verzicht_aufwendungen = models.BooleanField("Verzicht auf Erstattung von Aufwendungen", default=False)
    sach_beschreibung = models.TextField("Bezeichnung der Sachzuwendung", blank=True)
    sach_herkunft = models.CharField("Herkunft der Sachzuwendung", max_length=200, blank=True)
    sach_wertermittlung = models.CharField("Wertermittlung", max_length=200, blank=True)
    ausgestellt_am = models.DateField("Ausgestellt am", null=True, blank=True, editable=False)
    vereinsdaten = models.JSONField("Vereinsdaten zum Ausstellungszeitpunkt", default=dict, blank=True, editable=False)

    class Meta:
        verbose_name = "Spendenquittung"
        verbose_name_plural = "Spendenquittungen (Zuwendungsbestätigungen)"
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
    ART = [("geld", "Geldspende"), ("sach", "Sachspende"), ("mitgliedsbeitrag", "Mitgliedsbeitrag"),
           ("aufwandsverzicht", "Aufwandsspende (Verzicht auf Erstattung)")]
    HERKUNFT = [("", "keine Angabe"), ("privat", "Privatvermögen"), ("betrieb", "Betriebsvermögen")]
    spender = models.ForeignKey("members.Mitglied", on_delete=models.PROTECT, null=True, blank=True,
                                verbose_name="Spender (Mitglied)")
    spender_name = models.CharField("Spender (Name, falls kein Mitglied)", max_length=200, blank=True)
    spender_anschrift = models.CharField("Anschrift (falls kein Mitglied)", max_length=300, blank=True)
    datum = models.DateField("Datum der Zuwendung", default=date.today)
    betrag = models.DecimalField("Betrag / Wert (€)", max_digits=10, decimal_places=2)
    art = models.CharField("Art", max_length=20, choices=ART, default="geld")
    zweck = models.CharField("Verwendungszweck", max_length=200, blank=True)
    sach_beschreibung = models.TextField("Bezeichnung der Sachspende", blank=True)
    sach_herkunft = models.CharField("Herkunft", max_length=10, choices=HERKUNFT, blank=True)
    sach_wertermittlung = models.CharField("Wertermittlung", max_length=200, blank=True,
                                           help_text="z. B. Kaufbeleg, Schätzung, Gutachten")
    bankumsatz = models.ForeignKey("finance.Bankumsatz", on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+", verbose_name="Bankumsatz")
    bestaetigung = models.ForeignKey(Zuwendungsbestaetigung, on_delete=models.SET_NULL, null=True, blank=True,
                                     editable=False, related_name="spenden", verbose_name="Spendenquittung")
    bemerkung = models.CharField("Bemerkung", max_length=200, blank=True)

    class Meta:
        verbose_name = "Spende"
        verbose_name_plural = "Spenden"
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
