from datetime import date

from django.conf import settings
from django.db import models
from django.db.models import Max

from apps.core.fields import VerschluesseltesTextField
from apps.core.models import TenantModel, naechste_nummer
from apps.core.util import upload_pfad


class Mitgliedsart(TenantModel):
    """Mitgliedsart = Beitragsart (Aktiv, Passiv, Jugend, Familie, Ehrenmitglied ...)."""
    name = models.CharField("Name", max_length=100)
    jahresbeitrag = models.DecimalField("Standard-Jahresbeitrag (€)", max_digits=8, decimal_places=2, default=0)
    beschreibung = models.CharField("Beschreibung", max_length=200, blank=True)

    class Meta:
        verbose_name = "Mitgliedsart"
        verbose_name_plural = "Mitgliedsarten / Beiträge"
        unique_together = [("verein", "name")]
        ordering = ["name"]

    def __str__(self):
        return self.name


class Familie(TenantModel):
    name = models.CharField("Familienname / Bezeichnung", max_length=150)

    class Meta:
        verbose_name = "Familie"
        verbose_name_plural = "Familien"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Abteilung(TenantModel):
    name = models.CharField("Name", max_length=100)

    class Meta:
        verbose_name = "Abteilung"
        verbose_name_plural = "Abteilungen"
        unique_together = [("verein", "name")]
        ordering = ["name"]

    def __str__(self):
        return self.name


class Funktion(TenantModel):
    name = models.CharField("Name", max_length=100)

    class Meta:
        verbose_name = "Funktion"
        verbose_name_plural = "Funktionen"
        unique_together = [("verein", "name")]
        ordering = ["name"]

    def __str__(self):
        return self.name


class Mitglied(TenantModel):
    STATUS = [("aktiv", "Aktiv"), ("ruhend", "Ruhend"), ("ausgetreten", "Ausgetreten"), ("verstorben", "Verstorben")]
    ANREDE = [("herr", "Herr"), ("frau", "Frau"), ("divers", "Divers"), ("firma", "Firma / Organisation")]
    ZAHLART = [("ueberweisung", "Überweisung"), ("lastschrift", "SEPA-Lastschrift"), ("bar", "Bar")]

    mitgliedsnummer = models.PositiveIntegerField("Mitgliedsnummer", null=True, blank=True,
                                                  help_text="Leer lassen = automatisch vergeben")
    anrede = models.CharField("Anrede", max_length=10, choices=ANREDE, blank=True)
    vorname = models.CharField("Vorname", max_length=100)
    nachname = models.CharField("Nachname", max_length=100)
    geburtsdatum = models.DateField("Geburtsdatum", null=True, blank=True)
    eintrittsdatum = models.DateField("Eintrittsdatum", null=True, blank=True)
    austrittsdatum = models.DateField("Austrittsdatum", null=True, blank=True)
    status = models.CharField("Status", max_length=12, choices=STATUS, default="aktiv")
    mitgliedsart = models.ForeignKey(Mitgliedsart, on_delete=models.PROTECT, null=True, blank=True,
                                     verbose_name="Mitgliedsart")
    familie = models.ForeignKey(Familie, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Familie")
    ist_familienzahler = models.BooleanField("Zahlt den Familienbeitrag", default=False)
    individueller_beitrag = models.DecimalField("Individueller Jahresbeitrag (€)", max_digits=8, decimal_places=2,
                                                null=True, blank=True,
                                                help_text="Überschreibt alle Beitragsregeln (0 = beitragsfrei)")
    strasse = models.CharField("Straße / Nr.", max_length=200, blank=True)
    plz = models.CharField("PLZ", max_length=10, blank=True)
    ort = models.CharField("Ort", max_length=100, blank=True)
    email = models.EmailField("E-Mail", blank=True)
    telefon = models.CharField("Telefon", max_length=40, blank=True)
    mobil = models.CharField("Mobil", max_length=40, blank=True)
    zahlungsart = models.CharField("Zahlungsart", max_length=12, choices=ZAHLART, default="ueberweisung")
    kontoinhaber = models.CharField("Kontoinhaber", max_length=150, blank=True)
    iban = VerschluesseltesTextField("IBAN", blank=True)
    bic = models.CharField("BIC", max_length=11, blank=True)
    mandatsreferenz = models.CharField("SEPA-Mandatsreferenz", max_length=35, blank=True)
    mandatsdatum = models.DateField("Datum des SEPA-Mandats", null=True, blank=True)
    abteilungen = models.ManyToManyField(Abteilung, blank=True, verbose_name="Abteilungen")
    foto = models.ImageField("Foto", upload_to=upload_pfad, blank=True)
    notizen = models.TextField("Notizen", blank=True)
    openslides_user_id = models.PositiveIntegerField("OpenSlides-Konto-ID", null=True, blank=True, editable=False)
    openslides_username = models.CharField("OpenSlides-Benutzername", max_length=150, blank=True, editable=False)
    openslides_initialpasswort = VerschluesseltesTextField("OpenSlides-Startpasswort", blank=True, editable=False)
    benutzer = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    editable=False, related_name="mitglied_zugang",
                                    verbose_name="Zugang (Selbstdatenpflege)")
    selbstdienst_initialpasswort = VerschluesseltesTextField("Selbstdienst-Startpasswort", blank=True, editable=False)

    AUDIT_MASK = ("iban", "openslides_initialpasswort", "selbstdienst_initialpasswort")

    class Meta:
        verbose_name = "Mitglied"
        verbose_name_plural = "Mitglieder"
        unique_together = [("verein", "mitgliedsnummer")]
        ordering = ["nachname", "vorname"]

    def __str__(self):
        return f"{self.mitgliedsnummer or '–'} – {self.nachname}, {self.vorname}"

    def save(self, *args, **kwargs):
        if self.mitgliedsnummer is None:
            n = naechste_nummer(self.verein_id, "MITGLIED")
            while Mitglied.objects.filter(verein_id=self.verein_id, mitgliedsnummer=n).exists():
                n = naechste_nummer(self.verein_id, "MITGLIED")
            self.mitgliedsnummer = n
        super().save(*args, **kwargs)

    @property
    def name(self):
        return f"{self.vorname} {self.nachname}".strip()

    def anschrift_zeilen(self):
        return [self.name, self.strasse, f"{self.plz} {self.ort}".strip()]

    def alter(self, stichtag=None):
        if not self.geburtsdatum:
            return None
        s = stichtag or date.today()
        return s.year - self.geburtsdatum.year - ((s.month, s.day) < (self.geburtsdatum.month, self.geburtsdatum.day))

    def mitgliedsjahre(self, stichtag=None):
        if not self.eintrittsdatum:
            return None
        return (stichtag or date.today()).year - self.eintrittsdatum.year


class MitgliedFunktion(TenantModel):
    mitglied = models.ForeignKey(Mitglied, on_delete=models.CASCADE, verbose_name="Mitglied", related_name="funktionen")
    funktion = models.ForeignKey(Funktion, on_delete=models.PROTECT, verbose_name="Funktion")
    von = models.DateField("Von", null=True, blank=True)
    bis = models.DateField("Bis", null=True, blank=True)

    class Meta:
        verbose_name = "Funktion eines Mitglieds"
        verbose_name_plural = "Funktionen der Mitglieder"
        ordering = ["-von"]

    def __str__(self):
        return f"{self.mitglied.name}: {self.funktion}"


class Dokument(TenantModel):
    KATEGORIE = [("beitritt", "Beitrittserklärung"), ("sepa", "SEPA-Mandat"), ("ehrung", "Ehrung"),
                 ("kuendigung", "Kündigung"), ("sonstiges", "Sonstiges")]
    mitglied = models.ForeignKey(Mitglied, on_delete=models.CASCADE, verbose_name="Mitglied", related_name="dokumente")
    kategorie = models.CharField("Kategorie", max_length=12, choices=KATEGORIE, default="sonstiges")
    titel = models.CharField("Titel", max_length=200)
    datei = models.FileField("Datei", upload_to=upload_pfad)
    version = models.PositiveIntegerField("Version", default=1, editable=False)

    class Meta:
        verbose_name = "Dokument"
        verbose_name_plural = "Dokumente"
        ordering = ["-erstellt"]

    def __str__(self):
        return f"{self.titel} (v{self.version})"

    def save(self, *args, **kwargs):
        # Versionierung: gleicher Titel beim gleichen Mitglied -> neue Version, alte bleiben erhalten
        if self._state.adding:
            h = Dokument.objects.filter(verein_id=self.verein_id, mitglied_id=self.mitglied_id,
                                        titel=self.titel).aggregate(m=Max("version"))["m"]
            self.version = (h or 0) + 1
        super().save(*args, **kwargs)
