import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum

from apps.core.models import TenantModel
from apps.core.util import upload_pfad
from django.utils.translation import gettext_lazy as _


class Veranstaltung(TenantModel):
    ART = [("fest", _("Fest / Feier")), ("versammlung", _("Versammlung")), ("sitzung", _("Sitzung")),
           ("ausflug", _("Ausflug")), ("schulung", _("Übung / Schulung")), ("sonstiges", _("Sonstiges"))]
    STATUS = [("idee", _("Idee")), ("geplant", _("Geplant")), ("bestaetigt", _("Bestätigt")), ("abgesagt", _("Abgesagt")),
              ("abgeschlossen", _("Abgeschlossen"))]
    titel = models.CharField(_("Titel"), max_length=200)
    art = models.CharField(_("Art"), max_length=12, choices=ART, default="sonstiges")
    status = models.CharField(_("Status"), max_length=14, choices=STATUS, default="geplant")
    beginn = models.DateTimeField(_("Beginn"))
    ende = models.DateTimeField(_("Ende"), null=True, blank=True)
    ort = models.CharField(_("Ort"), max_length=200, blank=True)
    beschreibung = models.TextField(_("Beschreibung"), blank=True)
    verantwortlich = models.ForeignKey("members.Mitglied", on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name="+", verbose_name=_("Verantwortlich"))
    erwartete_teilnehmer = models.PositiveIntegerField(_("Erwartete Teilnehmer"), null=True, blank=True)
    oeffentlich = models.BooleanField(_("Öffentliche Veranstaltung"), default=False)
    anmeldung_erforderlich = models.BooleanField(_("Anmeldung erforderlich"), default=False)
    anmeldeschluss = models.DateField(_("Anmeldeschluss"), null=True, blank=True)
    notizen = models.TextField(_("Interne Notizen"), blank=True)
    openslides_meeting_id = models.PositiveIntegerField(_("OpenSlides-Meeting-ID"), null=True, blank=True, editable=False)
    rueckmeldung_code = models.UUIDField(_("Code für öffentliche Rückmeldung"), default=uuid.uuid4, editable=False,
                                         unique=True)

    class Meta:
        verbose_name = _("Veranstaltung")
        verbose_name_plural = _("Veranstaltungen")
        ordering = ["-beginn"]

    def __str__(self):
        return f"{self.titel} ({self.beginn:%d.%m.%Y})" if self.beginn else self.titel

    def clean(self):
        if self.beginn and self.ende and self.ende < self.beginn:
            raise ValidationError(_("Das Ende liegt vor dem Beginn."))

    def summen(self):
        def s(art, feld):
            return self.kosten.filter(art=art).aggregate(x=Sum(feld))["x"] or Decimal("0")
        return {"plan_ein": s("einnahme", "plan_betrag"), "plan_aus": s("ausgabe", "plan_betrag"),
                "ist_ein": s("einnahme", "ist_betrag"), "ist_aus": s("ausgabe", "ist_betrag")}


class Aufgabe(TenantModel):
    STATUS = [("offen", _("Offen")), ("arbeit", _("In Arbeit")), ("erledigt", _("Erledigt"))]
    veranstaltung = models.ForeignKey(Veranstaltung, on_delete=models.CASCADE, related_name="aufgaben",
                                      null=True, blank=True, verbose_name=_("Veranstaltung"),
                                      help_text=_("Optional - leer lassen für eine eigenständige Aufgabe ohne "
                                                "Bezug zu einer Veranstaltung/Sitzung."))
    titel = models.CharField(_("Aufgabe"), max_length=200)
    zustaendig = models.ForeignKey("members.Mitglied", on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+", verbose_name=_("Zuständig"))
    faellig = models.DateField(_("Fällig bis"), null=True, blank=True)
    status = models.CharField(_("Status"), max_length=10, choices=STATUS, default="offen")
    beschreibung = models.TextField(_("Beschreibung"), blank=True)
    ergebnis = models.TextField(_("Ergebnis"), blank=True,
                                help_text=_("Kurzes Fazit beim Abschließen - was wurde erreicht/entschieden."))
    benachrichtigt_am = models.DateTimeField(_("Überfälligkeits-Benachrichtigung verschickt am"), null=True,
                                             blank=True, editable=False)

    class Meta:
        verbose_name = _("Aufgabe")
        verbose_name_plural = _("Aufgaben")
        ordering = ["faellig", "id"]

    def __str__(self):
        return self.titel

    @property
    def ueberfaellig(self):
        from datetime import date
        return bool(self.faellig and self.faellig < date.today() and self.status != "erledigt")

    @property
    def faelligkeits_stufe(self):
        """'rot'/'gelb'/'gruen' je nach Resttagen bis zur Fälligkeit, oder None ohne Fälligkeit/bei bereits
        erledigten Aufgaben (keine Dringlichkeit mehr). rot: unter 2 Tage (inkl. überfällig), gelb: 2 bis
        unter 10 Tage, grün: ab 10 Tagen."""
        from datetime import date
        if not self.faellig or self.status == "erledigt":
            return None
        resttage = (self.faellig - date.today()).days
        if resttage < 2:
            return "rot"
        if resttage < 10:
            return "gelb"
        return "gruen"

    def clean(self):
        if self.status == "erledigt" and not self.ergebnis:
            raise ValidationError(_("Bitte beim Abschließen ein Ergebnis eintragen."))


class AufgabeNotiz(TenantModel):
    """Zwischennotiz zu einer Aufgabe (wie ein Ticket-Verlauf) - append-only, nicht nachtraeglich aenderbar,
    damit der Verlauf nachvollziehbar bleibt. Zeitpunkt kommt aus dem geerbten TenantModel-Feld 'erstellt'."""
    aufgabe = models.ForeignKey(Aufgabe, on_delete=models.CASCADE, related_name="notizen", verbose_name=_("Aufgabe"))
    text = models.TextField(_("Notiz"))
    erstellt_von = models.CharField(_("Von"), max_length=150, blank=True, editable=False)

    class Meta:
        verbose_name = _("Zwischennotiz")
        verbose_name_plural = _("Zwischennotizen")
        ordering = ["erstellt", "id"]

    def __str__(self):
        return f"{self.aufgabe.titel}: {self.text[:40]}"


class Schicht(TenantModel):
    veranstaltung = models.ForeignKey(Veranstaltung, on_delete=models.CASCADE, related_name="schichten",
                                      verbose_name=_("Veranstaltung"))
    bezeichnung = models.CharField(_("Bezeichnung"), max_length=150)
    beginn = models.DateTimeField(_("Beginn"))
    ende = models.DateTimeField(_("Ende"))
    benoetigt = models.PositiveIntegerField(_("Benötigte Helfer"), default=1)

    class Meta:
        verbose_name = _("Schicht")
        verbose_name_plural = _("Schichten")
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
    schicht = models.ForeignKey(Schicht, on_delete=models.CASCADE, related_name="einsaetze", verbose_name=_("Schicht"))
    mitglied = models.ForeignKey("members.Mitglied", on_delete=models.CASCADE, related_name="+", verbose_name=_("Helfer"))
    bemerkung = models.CharField(_("Bemerkung"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("Schichteinsatz")
        verbose_name_plural = _("Schichteinsätze")
        unique_together = [("schicht", "mitglied")]

    def __str__(self):
        return f"{self.mitglied.name} – {self.schicht}"

    def clean(self):
        if self.schicht_id and not self.pk and self.schicht.einsaetze.count() >= self.schicht.benoetigt:
            raise ValidationError(_("Diese Schicht ist bereits vollständig besetzt."))


class Anmeldung(TenantModel):
    STATUS = [("zugesagt", _("Zugesagt")), ("offen", _("Offen")), ("abgesagt", _("Abgesagt"))]
    veranstaltung = models.ForeignKey(Veranstaltung, on_delete=models.CASCADE, related_name="anmeldungen",
                                      verbose_name=_("Veranstaltung"))
    mitglied = models.ForeignKey("members.Mitglied", on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="+", verbose_name=_("Mitglied"))
    name = models.CharField(_("Name (Gast)"), max_length=150, blank=True)
    personen = models.PositiveIntegerField(_("Anzahl Personen"), default=1)
    status = models.CharField(_("Status"), max_length=10, choices=STATUS, default="zugesagt")
    bemerkung = models.CharField(_("Bemerkung"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("Anmeldung")
        verbose_name_plural = _("Anmeldungen")
        ordering = ["id"]

    def __str__(self):
        return self.wer

    @property
    def wer(self):
        return self.mitglied.name if self.mitglied_id else (self.name or "?")

    def clean(self):
        if not (self.mitglied_id or self.name):
            raise ValidationError(_("Bitte ein Mitglied oder einen Namen angeben."))


class Kostenposition(TenantModel):
    ART = [("einnahme", _("Einnahme")), ("ausgabe", _("Ausgabe"))]
    veranstaltung = models.ForeignKey(Veranstaltung, on_delete=models.CASCADE, related_name="kosten",
                                      verbose_name=_("Veranstaltung"))
    art = models.CharField(_("Art"), max_length=8, choices=ART, default="ausgabe")
    bezeichnung = models.CharField(_("Bezeichnung"), max_length=200)
    plan_betrag = models.DecimalField(_("Geplant (€)"), max_digits=10, decimal_places=2, default=0)
    ist_betrag = models.DecimalField(_("Tatsächlich (€)"), max_digits=10, decimal_places=2, null=True, blank=True)
    beleg = models.FileField(_("Beleg"), upload_to=upload_pfad, blank=True)

    class Meta:
        verbose_name = _("Kostenposition")
        verbose_name_plural = _("Kostenpositionen")
        ordering = ["art", "id"]

    def __str__(self):
        return self.bezeichnung


class Tagesordnungspunkt(TenantModel):
    veranstaltung = models.ForeignKey(Veranstaltung, on_delete=models.CASCADE, related_name="tagesordnung",
                                      verbose_name=_("Veranstaltung"))
    position = models.PositiveIntegerField(_("Position"), default=1)
    titel = models.CharField(_("Titel"), max_length=250)
    beschreibung = models.TextField(_("Beschreibung / Beschlussvorlage"), blank=True)
    openslides_topic_id = models.PositiveIntegerField(_("OpenSlides-Themen-ID"), null=True, blank=True, editable=False)

    class Meta:
        verbose_name = _("Tagesordnungspunkt")
        verbose_name_plural = _("Tagesordnung")
        ordering = ["position", "id"]

    def __str__(self):
        return f"TOP {self.position}: {self.titel}"


class Wahlergebnis(TenantModel):
    """Aus OpenSlides zurückübertragenes Wahlergebnis (Rückfluss ins Protokoll) - je Amt und Wahlgang ein
    Datensatz, mit der reinen Stimmenverteilung; wer gewählt ist, trägt der Protokollführer anhand der
    Vereinssatzung (Mehrheitserfordernis, Stichwahl bei Gleichstand usw.) selbst ein, das entscheidet die
    Software bewusst nicht."""
    veranstaltung = models.ForeignKey(Veranstaltung, on_delete=models.CASCADE, related_name="wahlergebnisse",
                                      verbose_name=_("Veranstaltung"))
    amt = models.CharField(_("Amt / Wahl"), max_length=250)
    wahlgang = models.CharField(_("Wahlgang"), max_length=250, blank=True)
    ergebnis = models.TextField(_("Stimmenverteilung"))

    class Meta:
        verbose_name = _("Wahlergebnis")
        verbose_name_plural = _("Wahlergebnisse")
        ordering = ["amt", "wahlgang", "id"]

    def __str__(self):
        return f"{self.amt} ({self.wahlgang})" if self.wahlgang else self.amt
