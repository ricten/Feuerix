from django.conf import settings
from django.db import models, transaction

from .fields import VerschluesseltesTextField
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
    umsatzsteuerpflichtig = models.BooleanField(
        "Umsatzsteuerpflichtig", default=False,
        help_text="Für nicht gemeinnützige Vereine bzw. den wirtschaftlichen Geschäftsbetrieb: neue "
                  "Rechnungspositionen schlagen dann standardmäßig Umsatzsteuer vor, Rechnungen/E-Rechnungen weisen "
                  "sie entsprechend aus. Ersetzt keine steuerliche Beratung.")
    ust_idnr = models.CharField("USt-IdNr.", max_length=20, blank=True)
    rechnung_steuerhinweis = models.CharField(
        "Steuerhinweis auf Rechnungen ohne Umsatzsteuer", max_length=300, blank=True,
        help_text="Freitext für Rechnungen/E-Rechnungen, wenn (ein Teil) der Rechnung mit 0 % Umsatzsteuer "
                  "ausgewiesen wird, z. B. „Gemäß § 19 UStG wird keine Umsatzsteuer berechnet“ oder eine passende "
                  "Befreiungsvorschrift. Leer lassen für den Standardtext „Steuerbefreiung nach § 4 UStG "
                  "(ideeller Bereich)“. Bitte durch Steuerberater prüfen lassen.")
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
    akzentfarbe = models.CharField("Akzentfarbe (Briefe, PDFs und Weboberfläche)", max_length=7, default="#1F4E79",
                                   help_text="Hex-Code, z. B. #1F4E79 – für Überschrift/Linie im Briefkopf sowie "
                                             "Navigationsleiste und Schaltflächen in der Weboberfläche.")
    akzentfarbe_fuss = models.CharField("Zweite Akzentfarbe (Linie über der Fußzeile)", max_length=7, blank=True,
                                        help_text="Optional, Hex-Code z. B. #005199. Leer = gleiche Farbe wie oben.")
    unterschrift_1 = models.CharField("Unterschrift 1 (Briefe)", max_length=150, blank=True,
                                      help_text="z. B. Max Mustermann, 1. Vorsitzender")
    unterschrift_2 = models.CharField("Unterschrift 2 (Briefe)", max_length=150, blank=True)
    impressum_text = models.TextField(
        "Impressum", blank=True,
        help_text="Vollständiger Text nach § 5 TMG / § 18 MStV (verantwortliche Person, Anschrift, Kontakt, "
                  "Vertretungsberechtigte, ggf. USt-IdNr.). Wird ungeprüft auf der öffentlich erreichbaren "
                  "Impressum-Seite angezeigt – bitte gegen die eigene Satzung/das Vereinsregister prüfen.")
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


class Systemeinstellung(models.Model):
    """Instanzweite (nicht vereinsgebundene) Einstellungen - genau ein Datensatz (pk=1). Bearbeitbar nur über die
    Django-Admin-Oberfläche (/admin/), da sie nicht zu einem einzelnen Verein gehören und ihre Änderung Rechte
    braucht, die über die normale Rollen-/Rechteverwaltung eines Vereins hinausgehen (Serverbetrieb)."""
    fints_produkt_id = VerschluesseltesTextField(
        "FinTS-Produkt-ID", blank=True,
        help_text="Alternative zur Umgebungsvariable FINTS_PRODUCT_ID - wird bevorzugt verwendet, wenn gesetzt. "
                  "Kostenlos zu registrieren bei der Deutschen Kreditwirtschaft: "
                  "https://www.hbci-zka.de/register/prod_register.htm")

    class Meta:
        verbose_name = "Systemeinstellung"
        verbose_name_plural = "Systemeinstellungen"

    def __str__(self):
        return "Systemeinstellungen"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  # Singleton - Löschen wird stillschweigend ignoriert statt eine Ausnahme zu werfen.

    @classmethod
    def laden(cls):
        return cls.objects.first() or cls()

    @classmethod
    def fints_produkt_id_aktuell(cls):
        return cls.laden().fints_produkt_id or settings.FINTS_PRODUCT_ID
