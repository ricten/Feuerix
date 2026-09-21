from django.conf import settings
from django.db import models, transaction

from .util import logo_pfad


class Verein(models.Model):
    BESCHEID = [
        ("freistellung", "Freistellungsbescheid"),
        ("anlage", "Anlage zum Körperschaftsteuerbescheid"),
        ("feststellung", "Feststellungsbescheid nach § 60a AO"),
    ]
    name = models.CharField("Name", max_length=200)
    kuerzel = models.SlugField("Kürzel", unique=True)
    anschrift = models.CharField("Straße / Nr.", max_length=200, blank=True)
    plz = models.CharField("PLZ", max_length=10, blank=True)
    ort = models.CharField("Ort", max_length=100, blank=True)
    email = models.EmailField("E-Mail", blank=True)
    vereinsregister = models.CharField("Registergericht / Nr.", max_length=100, blank=True)
    bankname = models.CharField("Bank", max_length=100, blank=True)
    iban = models.CharField("IBAN", max_length=34, blank=True)
    bic = models.CharField("BIC", max_length=11, blank=True)
    glaeubiger_id = models.CharField("Gläubiger-ID (SEPA)", max_length=35, blank=True)
    finanzamt = models.CharField("Finanzamt", max_length=100, blank=True)
    steuernummer = models.CharField("Steuernummer", max_length=30, blank=True)
    bescheid_art = models.CharField("Art des Gemeinnützigkeitsbescheids", max_length=20, choices=BESCHEID,
                                    default="freistellung")
    bescheid_datum = models.DateField("Datum des Bescheids", null=True, blank=True)
    bescheid_zeitraum = models.CharField("Bescheid gilt für Zeitraum / VZ", max_length=100, blank=True)
    beguenstigte_zwecke = models.TextField("Begünstigte Zwecke (laut Satzung)", blank=True)
    zahlungsziel_tage = models.PositiveIntegerField("Zahlungsziel (Tage)", default=14)
    rechnung_kopftext = models.TextField("Rechnungstext oben", blank=True)
    rechnung_fusstext = models.TextField("Rechnungstext unten", blank=True,
                                         default="Bitte überweisen Sie den Betrag unter Angabe des Verwendungszwecks.")
    uebungsleiter_freibetrag = models.DecimalField("Übungsleiterfreibetrag / Jahr (€)", max_digits=8, decimal_places=2,
                                                   default=3300)
    ehrenamts_freibetrag = models.DecimalField("Ehrenamtsfreibetrag / Jahr (€)", max_digits=8, decimal_places=2,
                                               default=960)
    logo = models.ImageField("Vereinslogo (PNG oder JPG)", upload_to=logo_pfad, blank=True,
                             help_text="Wird auf Briefen, Rechnungen und Word-Dokumenten oben rechts gedruckt.")
    akzentfarbe = models.CharField("Akzentfarbe für Briefe/PDFs", max_length=7, default="#1F4E79",
                                   help_text="Hex-Code, z. B. #1F4E79 – für Überschrift und Linie im Briefkopf.")
    unterschrift_1 = models.CharField("Unterschrift 1 (Briefe)", max_length=150, blank=True,
                                      help_text="z. B. Max Mustermann, 1. Vorsitzender")
    unterschrift_2 = models.CharField("Unterschrift 2 (Briefe)", max_length=150, blank=True)
    aktiv = models.BooleanField("Aktiv", default=True)

    AUDIT = True

    class Meta:
        verbose_name = "Verein"
        verbose_name_plural = "Vereine"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def adresszeile(self):
        return ", ".join(x for x in (self.anschrift, f"{self.plz} {self.ort}".strip()) if x)


class Rolle(models.Model):
    verein = models.ForeignKey(Verein, on_delete=models.CASCADE, related_name="rollen")
    name = models.CharField("Name", max_length=100)
    ist_superadmin = models.BooleanField("Superadministrator (alle Rechte)", default=False)
    rechte = models.JSONField("Rechte", default=list, blank=True)

    AUDIT = True

    class Meta:
        verbose_name = "Rolle"
        verbose_name_plural = "Rollen"
        unique_together = [("verein", "name")]
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def anzahl_rechte(self):
        return "alle" if self.ist_superadmin else len(self.rechte or [])


class Zugang(models.Model):
    verein = models.ForeignKey(Verein, on_delete=models.CASCADE, related_name="zugaenge")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="zugaenge")
    rolle = models.ForeignKey(Rolle, on_delete=models.PROTECT, verbose_name="Rolle")
    extra_rechte = models.JSONField("Zusätzliche Einzelrechte", default=list, blank=True)
    aktiv = models.BooleanField("Aktiv", default=True)

    AUDIT = True

    class Meta:
        verbose_name = "Benutzerzugang"
        verbose_name_plural = "Benutzerzugänge"
        unique_together = [("verein", "user")]

    def __str__(self):
        return f"{self.user} ({self.verein})"


class TenantModel(models.Model):
    """Basis aller mandantenbezogenen Modelle: jede Zeile gehoert zu genau einem Verein."""
    verein = models.ForeignKey(Verein, on_delete=models.PROTECT, related_name="+")
    erstellt = models.DateTimeField(auto_now_add=True)
    geaendert = models.DateTimeField(auto_now=True)

    AUDIT = True
    AUDIT_MASK = ()

    class Meta:
        abstract = True


class Nummernkreis(models.Model):
    verein = models.ForeignKey(Verein, on_delete=models.CASCADE, related_name="+")
    schluessel = models.CharField(max_length=20)
    jahr = models.PositiveIntegerField(default=0)
    letzter = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [("verein", "schluessel", "jahr")]


def naechste_nummer(verein, schluessel, jahr=0):
    """Fortlaufende, lueckenlose Nummer pro Verein/Schluessel/Jahr (transaktionssicher)."""
    with transaction.atomic():
        nk, _ = Nummernkreis.objects.select_for_update().get_or_create(
            verein_id=verein.pk if hasattr(verein, "pk") else verein, schluessel=schluessel, jahr=jahr)
        nk.letzter += 1
        nk.save(update_fields=["letzter"])
        return nk.letzter


class AuditLog(models.Model):
    AKTION = [("angelegt", "Angelegt"), ("geaendert", "Geändert"), ("geloescht", "Gelöscht"),
             ("exportiert", "Exportiert"), ("importiert", "Importiert")]
    verein = models.ForeignKey(Verein, on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    zeit = models.DateTimeField("Zeitpunkt", auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name="+")
    user_name = models.CharField("Benutzer", max_length=150, blank=True)
    ip = models.GenericIPAddressField("IP-Adresse", null=True, blank=True)
    modell = models.CharField("Objektart", max_length=100)
    objekt_id = models.CharField("Objekt-ID", max_length=40)
    objekt_repr = models.CharField("Objekt", max_length=200)
    aktion = models.CharField("Aktion", max_length=12, choices=AKTION)
    aenderungen = models.JSONField("Änderungen", default=dict)
    grund = models.CharField("Grund", max_length=200, blank=True)

    class Meta:
        verbose_name = "Protokolleintrag"
        verbose_name_plural = "Änderungsprotokoll"
        ordering = ["-zeit", "-id"]
        indexes = [models.Index(fields=["verein", "modell", "objekt_id"])]

    def __str__(self):
        return f"{self.zeit:%d.%m.%Y %H:%M} {self.user_name} {self.aktion} {self.objekt_repr}"
