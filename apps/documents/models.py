import os
from datetime import date

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Max, Q

from apps.core.models import TenantModel
from apps.core.util import upload_pfad
from apps.members.models import Mitglied

KATEGORIEN = [("protokoll", "Protokoll"), ("einladung", "Einladung"), ("serienbrief", "Serienbrief"),
              ("satzung", "Satzung & Verträge"), ("datenschutz", "Datenschutzerklärung"), ("formular", "Formulare"),
              ("beleg", "Belege"), ("kassenbericht", "Kassenbericht"), ("sonstiges", "Sonstiges")]
ORDNER_NAMEN = {"protokoll": "Protokolle", "einladung": "Einladungen", "serienbrief": "Serienbriefe",
                "satzung": "Satzung & Verträge", "datenschutz": "Datenschutzerklärung", "formular": "Formulare",
                "beleg": "Belege", "kassenbericht": "Kassenberichte", "sonstiges": "Sonstiges"}


class Ordner(TenantModel):
    name = models.CharField("Name", max_length=100)
    uebergeordnet = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True,
                                      related_name="unterordner", verbose_name="Übergeordneter Ordner")

    class Meta:
        verbose_name = "Ablage-Ordner"
        verbose_name_plural = "Ablage-Ordner"
        ordering = ["name"]

    def __str__(self):
        return self.pfad

    @property
    def pfad(self):
        teile, o, n = [], self, 0
        while o is not None and n < 20:
            teile.append(o.name)
            o, n = o.uebergeordnet, n + 1
        return " / ".join(reversed(teile))

    def clean(self):
        o, n = self.uebergeordnet, 0
        while o is not None and n < 20:
            if self.pk and o.pk == self.pk:
                raise ValidationError("Ein Ordner kann nicht in sich selbst liegen.")
            o, n = o.uebergeordnet, n + 1


class Ablagedokument(TenantModel):
    titel = models.CharField("Titel", max_length=200)
    kategorie = models.CharField("Kategorie", max_length=13, choices=KATEGORIEN, default="sonstiges")
    ordner = models.ForeignKey(Ordner, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Ordner")
    datum = models.DateField("Datum des Dokuments", default=date.today)
    datei = models.FileField("Datei", upload_to=upload_pfad)
    version = models.PositiveIntegerField("Version", default=1, editable=False)
    veranstaltung = models.ForeignKey("events.Veranstaltung", on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name="ablage", verbose_name="Zur Veranstaltung")
    beschreibung = models.CharField("Beschreibung", max_length=300, blank=True)
    oeffentlich = models.BooleanField(
        "Öffentlich auf der Startseite sichtbar", default=False,
        help_text="Ohne Anmeldung für jeden abrufbar (z. B. Datenschutzerklärung, Aufnahmeformular). "
                  "Nur aktivieren, wenn das Dokument wirklich für die Öffentlichkeit bestimmt ist!")
    paperless_gesendet_am = models.DateTimeField("An Paperless gesendet am", null=True, blank=True, editable=False)
    paperless_task_id = models.CharField("Paperless-Task-ID", max_length=50, blank=True, editable=False)
    paperless_fehler = models.CharField("Letzter Paperless-Fehler", max_length=300, blank=True, editable=False)
    paperless_pruefsumme = models.CharField("Prüfsumme der übergebenen Datei", max_length=64, blank=True,
                                            editable=False)
    paperless_info = models.CharField("Paperless-Hinweis", max_length=300, blank=True, editable=False)

    class Meta:
        verbose_name = "Ablage-Dokument"
        verbose_name_plural = "Ablage"
        ordering = ["-datum", "-id"]

    def __str__(self):
        return f"{self.titel} (v{self.version})"

    @property
    def dateiname(self):
        return os.path.basename(self.datei.name) if self.datei else ""

    def save(self, *args, **kwargs):
        # Versionierung: gleicher Titel im gleichen Ordner -> neue Version; alte Dateien bleiben erhalten
        if self._state.adding:
            h = Ablagedokument.objects.filter(verein_id=self.verein_id, ordner_id=self.ordner_id,
                                              titel=self.titel).aggregate(m=Max("version"))["m"]
            self.version = (h or 0) + 1
        super().save(*args, **kwargs)


class Vorlage(TenantModel):
    ART = [("einladung", "Einladung"), ("protokoll", "Protokoll"), ("serienbrief", "Serienbrief / Mitgliederinformation"),
           ("brief", "Brief"), ("sonstiges", "Sonstiges")]
    name = models.CharField("Name der Vorlage", max_length=150)
    art = models.CharField("Art", max_length=12, choices=ART, default="brief")
    betreff = models.CharField("Betreff / Titel", max_length=250, blank=True)
    text = models.TextField("Text", help_text="Absätze durch Leerzeile trennen. Platzhalter wie {vorname} siehe "
                                              "Seite 'Platzhalter-Hilfe'.")
    ist_standard = models.BooleanField("Standardvorlage dieser Art", default=False,
                                       help_text="Wird bei 'Einladung/Protokoll erstellen' in Veranstaltungen verwendet.")
    aktiv = models.BooleanField("Aktiv", default=True)
    hinweis = models.TextField("Interner Hinweis", blank=True)

    class Meta:
        verbose_name = "Vorlage"
        verbose_name_plural = "Vorlagen"
        unique_together = [("verein", "name")]
        ordering = ["art", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.ist_standard:
            Vorlage.objects.filter(verein_id=self.verein_id, art=self.art).exclude(pk=self.pk).update(
                ist_standard=False)


class Schriftstueck(TenantModel):
    STATUS = [("entwurf", "Entwurf"), ("final", "Final")]
    titel = models.CharField("Bezeichnung (intern)", max_length=200)
    art = models.CharField("Art", max_length=12, choices=Vorlage.ART, default="brief")
    vorlage = models.ForeignKey(Vorlage, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Vorlage",
                                help_text="Beim Anlegen werden Betreff und Text aus der Vorlage übernommen.")
    veranstaltung = models.ForeignKey("events.Veranstaltung", on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name="schriftstuecke", verbose_name="Veranstaltung")
    mitglied = models.ForeignKey(Mitglied, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                                 verbose_name="Empfänger (Mitglied, optional)")
    datum = models.DateField("Datum", default=date.today)
    betreff = models.CharField("Betreff / Titel", max_length=250, blank=True)
    text = models.TextField("Text", blank=True)
    status = models.CharField("Status", max_length=8, choices=STATUS, default="entwurf")
    ablage = models.ForeignKey(Ablagedokument, on_delete=models.SET_NULL, null=True, blank=True, editable=False,
                               related_name="+", verbose_name="Zuletzt abgelegt als")

    class Meta:
        verbose_name = "Schriftstück"
        verbose_name_plural = "Schriftstücke"
        ordering = ["-datum", "-id"]

    def __str__(self):
        return self.titel

    def kontext(self):
        from .platzhalter import kontext
        return kontext(self.verein, mitglied=self.mitglied, veranstaltung=self.veranstaltung, datum=self.datum)


class Serienbrief(TenantModel):
    STATUS_FILTER = [("aktiv", "Nur aktive Mitglieder"), ("aktiv_ruhend", "Aktive und ruhende Mitglieder"),
                     ("alle", "Alle Mitglieder (auch ausgetretene)")]
    titel = models.CharField("Bezeichnung (intern)", max_length=200)
    vorlage = models.ForeignKey(Vorlage, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Vorlage",
                                help_text="Beim Anlegen werden Betreff und Text aus der Vorlage übernommen.")
    veranstaltung = models.ForeignKey("events.Veranstaltung", on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name="serienbriefe", verbose_name="Veranstaltung")
    datum = models.DateField("Briefdatum", default=date.today)
    betreff = models.CharField("Betreff", max_length=250, blank=True)
    text = models.TextField("Text", blank=True)
    status_filter = models.CharField("Empfänger: Status", max_length=14, choices=STATUS_FILTER, default="aktiv")
    mitgliedsart = models.ForeignKey("members.Mitgliedsart", on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name="+", verbose_name="Nur Mitgliedsart")
    abteilung = models.ForeignKey("members.Abteilung", on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name="+", verbose_name="Nur Abteilung")
    funktion = models.ForeignKey("members.Funktion", on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="+", verbose_name="Nur Funktion (z. B. Vorstand)")
    nur_mit_email = models.BooleanField("Nur Mitglieder mit E-Mail-Adresse", default=False)
    ablage = models.ForeignKey(Ablagedokument, on_delete=models.SET_NULL, null=True, blank=True, editable=False,
                               related_name="+", verbose_name="Zuletzt abgelegt als")
    versendet_am = models.DateTimeField("Per E-Mail versendet am", null=True, blank=True, editable=False)
    versand_info = models.CharField("Versandergebnis", max_length=300, blank=True, editable=False)

    class Meta:
        verbose_name = "Serienbrief"
        verbose_name_plural = "Serienbriefe"
        ordering = ["-datum", "-id"]

    def __str__(self):
        return self.titel

    def empfaenger(self):
        qs = Mitglied.objects.filter(verein_id=self.verein_id)
        if self.status_filter == "aktiv":
            qs = qs.filter(status="aktiv")
        elif self.status_filter == "aktiv_ruhend":
            qs = qs.filter(status__in=["aktiv", "ruhend"])
        if self.mitgliedsart_id:
            qs = qs.filter(mitgliedsart_id=self.mitgliedsart_id)
        if self.abteilung_id:
            qs = qs.filter(abteilungen=self.abteilung_id)
        if self.funktion_id:
            qs = qs.filter(Q(funktionen__funktion_id=self.funktion_id),
                           Q(funktionen__bis__isnull=True) | Q(funktionen__bis__gte=date.today()))
        if self.nur_mit_email:
            qs = qs.exclude(email="")
        return qs.distinct().order_by("nachname", "vorname")
