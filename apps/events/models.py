from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum

from apps.core.models import TenantModel
from apps.core.util import upload_pfad


class Veranstaltung(TenantModel):
    ART = [("fest", "Fest / Feier"), ("versammlung", "Versammlung"), ("sitzung", "Sitzung"),
           ("ausflug", "Ausflug"), ("schulung", "Übung / Schulung"), ("sonstiges", "Sonstiges")]
    STATUS = [("idee", "Idee"), ("geplant", "Geplant"), ("bestaetigt", "Bestätigt"), ("abgesagt", "Abgesagt"),
              ("abgeschlossen", "Abgeschlossen")]
    titel = models.CharField("Titel", max_length=200)
    art = models.CharField("Art", max_length=12, choices=ART, default="sonstiges")
    status = models.CharField("Status", max_length=14, choices=STATUS, default="geplant")
    beginn = models.DateTimeField("Beginn")
    ende = models.DateTimeField("Ende", null=True, blank=True)
    ort = models.CharField("Ort", max_length=200, blank=True)
    beschreibung = models.TextField("Beschreibung", blank=True)
    verantwortlich = models.ForeignKey("members.Mitglied", on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name="+", verbose_name="Verantwortlich")
    erwartete_teilnehmer = models.PositiveIntegerField("Erwartete Teilnehmer", null=True, blank=True)
    oeffentlich = models.BooleanField("Öffentliche Veranstaltung", default=False)
    anmeldung_erforderlich = models.BooleanField("Anmeldung erforderlich", default=False)
    anmeldeschluss = models.DateField("Anmeldeschluss", null=True, blank=True)
    notizen = models.TextField("Interne Notizen", blank=True)
    openslides_meeting_id = models.PositiveIntegerField("OpenSlides-Meeting-ID", null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "Veranstaltung"
        verbose_name_plural = "Veranstaltungen"
        ordering = ["-beginn"]

    def __str__(self):
        return f"{self.titel} ({self.beginn:%d.%m.%Y})" if self.beginn else self.titel

    def clean(self):
        if self.beginn and self.ende and self.ende < self.beginn:
            raise ValidationError("Das Ende liegt vor dem Beginn.")

    def summen(self):
        def s(art, feld):
            return self.kosten.filter(art=art).aggregate(x=Sum(feld))["x"] or Decimal("0")
        return {"plan_ein": s("einnahme", "plan_betrag"), "plan_aus": s("ausgabe", "plan_betrag"),
                "ist_ein": s("einnahme", "ist_betrag"), "ist_aus": s("ausgabe", "ist_betrag")}


class Aufgabe(TenantModel):
    STATUS = [("offen", "Offen"), ("arbeit", "In Arbeit"), ("erledigt", "Erledigt")]
    veranstaltung = models.ForeignKey(Veranstaltung, on_delete=models.CASCADE, related_name="aufgaben",
                                      verbose_name="Veranstaltung")
    titel = models.CharField("Aufgabe", max_length=200)
    zustaendig = models.ForeignKey("members.Mitglied", on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+", verbose_name="Zuständig")
    faellig = models.DateField("Fällig bis", null=True, blank=True)
    status = models.CharField("Status", max_length=10, choices=STATUS, default="offen")
    beschreibung = models.TextField("Beschreibung", blank=True)

    class Meta:
        verbose_name = "Aufgabe"
        verbose_name_plural = "Aufgaben"
        ordering = ["faellig", "id"]

    def __str__(self):
        return self.titel


class Schicht(TenantModel):
    veranstaltung = models.ForeignKey(Veranstaltung, on_delete=models.CASCADE, related_name="schichten",
                                      verbose_name="Veranstaltung")
    bezeichnung = models.CharField("Bezeichnung", max_length=150)
    beginn = models.DateTimeField("Beginn")
    ende = models.DateTimeField("Ende")
    benoetigt = models.PositiveIntegerField("Benötigte Helfer", default=1)

    class Meta:
        verbose_name = "Schicht"
        verbose_name_plural = "Schichten"
        ordering = ["beginn"]

    def __str__(self):
        return f"{self.veranstaltung.titel}: {self.bezeichnung} ({self.beginn:%d.%m. %H:%M})"

    @property
    def besetzung(self):
        return f"{self.einsaetze.count()}/{self.benoetigt}"

    @property
    def helfer(self):
        return ", ".join(e.mitglied.name for e in self.einsaetze.select_related("mitglied")) or "–"


class Schichteinsatz(TenantModel):
    schicht = models.ForeignKey(Schicht, on_delete=models.CASCADE, related_name="einsaetze", verbose_name="Schicht")
    mitglied = models.ForeignKey("members.Mitglied", on_delete=models.CASCADE, related_name="+", verbose_name="Helfer")
    bemerkung = models.CharField("Bemerkung", max_length=200, blank=True)

    class Meta:
        verbose_name = "Schichteinsatz"
        verbose_name_plural = "Schichteinsätze"
        unique_together = [("schicht", "mitglied")]

    def __str__(self):
        return f"{self.mitglied.name} – {self.schicht}"

    def clean(self):
        if self.schicht_id and not self.pk and self.schicht.einsaetze.count() >= self.schicht.benoetigt:
            raise ValidationError("Diese Schicht ist bereits vollständig besetzt.")


class Anmeldung(TenantModel):
    STATUS = [("zugesagt", "Zugesagt"), ("offen", "Offen"), ("abgesagt", "Abgesagt")]
    veranstaltung = models.ForeignKey(Veranstaltung, on_delete=models.CASCADE, related_name="anmeldungen",
                                      verbose_name="Veranstaltung")
    mitglied = models.ForeignKey("members.Mitglied", on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="+", verbose_name="Mitglied")
    name = models.CharField("Name (Gast)", max_length=150, blank=True)
    personen = models.PositiveIntegerField("Anzahl Personen", default=1)
    status = models.CharField("Status", max_length=10, choices=STATUS, default="zugesagt")
    bemerkung = models.CharField("Bemerkung", max_length=200, blank=True)

    class Meta:
        verbose_name = "Anmeldung"
        verbose_name_plural = "Anmeldungen"
        ordering = ["id"]

    def __str__(self):
        return self.wer

    @property
    def wer(self):
        return self.mitglied.name if self.mitglied_id else (self.name or "?")

    def clean(self):
        if not (self.mitglied_id or self.name):
            raise ValidationError("Bitte ein Mitglied oder einen Namen angeben.")


class Kostenposition(TenantModel):
    ART = [("einnahme", "Einnahme"), ("ausgabe", "Ausgabe")]
    veranstaltung = models.ForeignKey(Veranstaltung, on_delete=models.CASCADE, related_name="kosten",
                                      verbose_name="Veranstaltung")
    art = models.CharField("Art", max_length=8, choices=ART, default="ausgabe")
    bezeichnung = models.CharField("Bezeichnung", max_length=200)
    plan_betrag = models.DecimalField("Geplant (€)", max_digits=10, decimal_places=2, default=0)
    ist_betrag = models.DecimalField("Tatsächlich (€)", max_digits=10, decimal_places=2, null=True, blank=True)
    beleg = models.FileField("Beleg", upload_to=upload_pfad, blank=True)

    class Meta:
        verbose_name = "Kostenposition"
        verbose_name_plural = "Kostenpositionen"
        ordering = ["art", "id"]

    def __str__(self):
        return self.bezeichnung


class Tagesordnungspunkt(TenantModel):
    veranstaltung = models.ForeignKey(Veranstaltung, on_delete=models.CASCADE, related_name="tagesordnung",
                                      verbose_name="Veranstaltung")
    position = models.PositiveIntegerField("Position", default=1)
    titel = models.CharField("Titel", max_length=250)
    beschreibung = models.TextField("Beschreibung / Beschlussvorlage", blank=True)
    openslides_topic_id = models.PositiveIntegerField("OpenSlides-Themen-ID", null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "Tagesordnungspunkt"
        verbose_name_plural = "Tagesordnung"
        ordering = ["position", "id"]

    def __str__(self):
        return f"TOP {self.position}: {self.titel}"


class Wahlergebnis(TenantModel):
    """Aus OpenSlides zurückübertragenes Wahlergebnis (Rückfluss ins Protokoll) - je Amt und Wahlgang ein
    Datensatz, mit der reinen Stimmenverteilung; wer gewählt ist, trägt der Protokollführer anhand der
    Vereinssatzung (Mehrheitserfordernis, Stichwahl bei Gleichstand usw.) selbst ein, das entscheidet die
    Software bewusst nicht."""
    veranstaltung = models.ForeignKey(Veranstaltung, on_delete=models.CASCADE, related_name="wahlergebnisse",
                                      verbose_name="Veranstaltung")
    amt = models.CharField("Amt / Wahl", max_length=250)
    wahlgang = models.CharField("Wahlgang", max_length=250, blank=True)
    ergebnis = models.TextField("Stimmenverteilung")

    class Meta:
        verbose_name = "Wahlergebnis"
        verbose_name_plural = "Wahlergebnisse"
        ordering = ["amt", "wahlgang", "id"]

    def __str__(self):
        return f"{self.amt} ({self.wahlgang})" if self.wahlgang else self.amt
