import os
from datetime import date

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Max, Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import TenantModel
from apps.core.util import upload_pfad
from apps.members.models import Mitglied

KATEGORIEN = [("rechnung", _("Rechnung")), ("zuwendung", _("Zuwendungsbestätigung")), ("protokoll", _("Protokoll")), ("einladung", _("Einladung")), ("serienbrief", _("Serienbrief")),
              ("satzung", _("Satzung & Verträge")), ("datenschutz", _("Datenschutzerklärung")), ("formular", _("Formulare")),
              ("beleg", _("Belege")), ("kassenbericht", _("Kassenbericht")), ("sonstiges", _("Sonstiges"))]
ORDNER_NAMEN = {"rechnung": "Rechnungen", "zuwendung": "Zuwendungsbestätigungen", "protokoll": "Protokolle",
                "einladung": "Einladungen", "serienbrief": "Serienbriefe",
                "satzung": "Satzung & Verträge", "datenschutz": "Datenschutzerklärung", "formular": "Formulare",
                "beleg": "Belege", "kassenbericht": "Kassenberichte", "sonstiges": "Sonstiges"}


class Ordner(TenantModel):
    name = models.CharField(_("Name"), max_length=100)
    uebergeordnet = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True,
                                      related_name="unterordner", verbose_name=_("Übergeordneter Ordner"))

    class Meta:
        verbose_name = _("Ablage-Ordner")
        verbose_name_plural = _("Ablage-Ordner")
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
                raise ValidationError(_("Ein Ordner kann nicht in sich selbst liegen."))
            o, n = o.uebergeordnet, n + 1


class Ablagedokument(TenantModel):
    titel = models.CharField(_("Titel"), max_length=200)
    kategorie = models.CharField(_("Kategorie"), max_length=13, choices=KATEGORIEN, default="sonstiges")
    ordner = models.ForeignKey(Ordner, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Ordner"))
    datum = models.DateField(_("Datum des Dokuments"), default=date.today)
    datei = models.FileField(_("Datei"), upload_to=upload_pfad)
    version = models.PositiveIntegerField(_("Version"), default=1, editable=False)
    veranstaltung = models.ForeignKey("events.Veranstaltung", on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name="ablage", verbose_name=_("Zur Veranstaltung"))
    beschreibung = models.CharField(_("Beschreibung"), max_length=300, blank=True)
    oeffentlich = models.BooleanField(
        _("Öffentlich auf der Startseite sichtbar"), default=False,
        help_text=_("Ohne Anmeldung für jeden abrufbar (z. B. Datenschutzerklärung, Aufnahmeformular). "
                  "Nur aktivieren, wenn das Dokument wirklich für die Öffentlichkeit bestimmt ist!"))
    dokumenttyp = models.CharField(
        _("Dokumenttyp (Paperless)"), max_length=150, blank=True,
        help_text=_("Leer lassen = die Art des Dokuments (z. B. Protokoll, Rechnung) wird als Dokumenttyp übergeben."))
    tags = models.CharField(
        _("Tags"), max_length=300, blank=True,
        help_text=_("Kommagetrennt. Werden bei der Übergabe an Paperless als Tags gesetzt. Leer lassen = Art des "
                  "Dokuments und Jahr werden automatisch eingetragen."))
    paperless_tags = models.CharField(_("Tags in Paperless (zuletzt übergeben)"), max_length=500, blank=True,
                                      editable=False)
    paperless_status = models.CharField(_("Paperless-Status"), max_length=15, blank=True, editable=False)
    paperless_gesendet_am = models.DateTimeField(_("An Paperless gesendet am"), null=True, blank=True, editable=False)
    paperless_task_id = models.CharField(_("Paperless-Task-ID"), max_length=50, blank=True, editable=False)
    paperless_fehler = models.CharField(_("Letzter Paperless-Fehler"), max_length=300, blank=True, editable=False)
    paperless_pruefsumme = models.CharField(_("Prüfsumme der übergebenen Datei"), max_length=64, blank=True,
                                            editable=False)
    paperless_info = models.CharField(_("Paperless-Hinweis"), max_length=300, blank=True, editable=False)

    class Meta:
        verbose_name = _("Ablage-Dokument")
        verbose_name_plural = _("Ablage")
        ordering = ["-datum", "-id"]

    def __str__(self):
        return f"{self.titel} (v{self.version})"

    @property
    def tag_liste(self):
        return [t.strip() for t in self.tags.split(",") if t.strip()]

    @property
    def standard_tags(self):
        """Art des Dokuments und Jahr - Vorbelegung der Tags."""
        return [str(self.get_kategorie_display()), str(self.datum.year)]

    @property
    def paperless_uebergeben(self):
        """True, wenn die Datei erfolgreich an Paperless übergeben wurde (sonst leer, für die Listenanzeige)."""
        return True if self.paperless_gesendet_am and not self.paperless_fehler else ""

    @property
    def dateiname(self):
        return os.path.basename(self.datei.name) if self.datei else ""

    def save(self, *args, **kwargs):
        # Versionierung: gleicher Titel im gleichen Ordner -> neue Version; alte Dateien bleiben erhalten
        if self._state.adding and not self.tags:
            self.tags = ", ".join(self.standard_tags)
        if self._state.adding:
            h = Ablagedokument.objects.filter(verein_id=self.verein_id, ordner_id=self.ordner_id,
                                              titel=self.titel).aggregate(m=Max("version"))["m"]
            self.version = (h or 0) + 1
        super().save(*args, **kwargs)


class Vorlage(TenantModel):
    ART = [("einladung", _("Einladung")), ("protokoll", _("Protokoll")), ("serienbrief", _("Serienbrief / Mitgliederinformation")),
           ("brief", _("Brief")), ("sonstiges", _("Sonstiges"))]
    name = models.CharField(_("Name der Vorlage"), max_length=150)
    art = models.CharField(_("Art"), max_length=12, choices=ART, default="brief")
    betreff = models.CharField(_("Betreff / Titel"), max_length=250, blank=True)
    text = models.TextField(_("Text"), help_text=_("Absätze durch Leerzeile trennen. Platzhalter wie {vorname} siehe "
                                              "Seite 'Platzhalter-Hilfe'."))
    ist_standard = models.BooleanField(_("Standardvorlage dieser Art"), default=False,
                                       help_text=_("Wird bei 'Einladung/Protokoll erstellen' in Veranstaltungen verwendet."))
    aktiv = models.BooleanField(_("Aktiv"), default=True)
    hinweis = models.TextField(_("Interner Hinweis"), blank=True)

    class Meta:
        verbose_name = _("Vorlage")
        verbose_name_plural = _("Vorlagen")
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
    STATUS = [("entwurf", _("Entwurf")), ("final", _("Final"))]
    titel = models.CharField(_("Bezeichnung (intern)"), max_length=200)
    art = models.CharField(_("Art"), max_length=12, choices=Vorlage.ART, default="brief")
    vorlage = models.ForeignKey(Vorlage, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Vorlage"),
                                help_text=_("Beim Anlegen werden Betreff und Text aus der Vorlage übernommen."))
    veranstaltung = models.ForeignKey("events.Veranstaltung", on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name="schriftstuecke", verbose_name=_("Veranstaltung"))
    mitglied = models.ForeignKey(Mitglied, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                                 verbose_name=_("Empfänger (Mitglied, optional)"))
    datum = models.DateField(_("Datum"), default=date.today)
    betreff = models.CharField(_("Betreff / Titel"), max_length=250, blank=True)
    text = models.TextField(_("Text"), blank=True)
    status = models.CharField(_("Status"), max_length=8, choices=STATUS, default="entwurf")
    ablage = models.ForeignKey(Ablagedokument, on_delete=models.SET_NULL, null=True, blank=True, editable=False,
                               related_name="+", verbose_name=_("Zuletzt abgelegt als"))

    class Meta:
        verbose_name = _("Schriftstück")
        verbose_name_plural = _("Schriftstücke")
        ordering = ["-datum", "-id"]

    def __str__(self):
        return self.titel

    def kontext(self):
        from .platzhalter import kontext
        return kontext(self.verein, mitglied=self.mitglied, veranstaltung=self.veranstaltung, datum=self.datum)


class Serienbrief(TenantModel):
    STATUS_FILTER = [("aktiv", _("Nur aktive Mitglieder")), ("aktiv_ruhend", _("Aktive und ruhende Mitglieder")),
                     ("alle", _("Alle Mitglieder (auch ausgetretene)"))]
    titel = models.CharField(_("Bezeichnung (intern)"), max_length=200)
    vorlage = models.ForeignKey(Vorlage, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Vorlage"),
                                help_text=_("Beim Anlegen werden Betreff und Text aus der Vorlage übernommen."))
    veranstaltung = models.ForeignKey("events.Veranstaltung", on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name="serienbriefe", verbose_name=_("Veranstaltung"))
    datum = models.DateField(_("Briefdatum"), default=date.today)
    betreff = models.CharField(_("Betreff"), max_length=250, blank=True)
    text = models.TextField(_("Text"), blank=True)
    status_filter = models.CharField(_("Empfänger: Status"), max_length=14, choices=STATUS_FILTER, default="aktiv")
    mitgliedsart = models.ForeignKey("members.Mitgliedsart", on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name="+", verbose_name=_("Nur Mitgliedsart"))
    abteilung = models.ForeignKey("members.Abteilung", on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name="+", verbose_name=_("Nur Abteilung"))
    funktion = models.ForeignKey("members.Funktion", on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="+", verbose_name=_("Nur Funktion (z. B. Vorstand)"))
    nur_mit_email = models.BooleanField(_("Nur Mitglieder mit E-Mail-Adresse"), default=False)
    ablage = models.ForeignKey(Ablagedokument, on_delete=models.SET_NULL, null=True, blank=True, editable=False,
                               related_name="+", verbose_name=_("Zuletzt abgelegt als"))
    versendet_am = models.DateTimeField(_("Per E-Mail versendet am"), null=True, blank=True, editable=False)
    versand_info = models.CharField(_("Versandergebnis"), max_length=300, blank=True, editable=False)

    class Meta:
        verbose_name = _("Serienbrief")
        verbose_name_plural = _("Serienbriefe")
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
