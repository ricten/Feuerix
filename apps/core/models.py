from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from .fields import VerschluesseltesTextField
from .util import logo_pfad


class Verein(models.Model):
    BESCHEID = [
        ("freistellung", _("Freistellungsbescheid")),
        ("anlage", _("Anlage zum Körperschaftsteuerbescheid")),
        ("feststellung", _("Feststellungsbescheid nach § 60a AO")),
    ]
    name = models.CharField(_("Name"), max_length=200)
    kuerzel = models.SlugField(_("Kürzel"), unique=True)
    anschrift = models.CharField(_("Straße / Nr."), max_length=200, blank=True)
    plz = models.CharField(_("PLZ"), max_length=10, blank=True)
    ort = models.CharField(_("Ort"), max_length=100, blank=True)
    email = models.EmailField(_("E-Mail"), blank=True)
    vereinsregister = models.CharField(_("Registergericht / Nr."), max_length=100, blank=True)
    bankname = models.CharField(_("Bank"), max_length=100, blank=True)
    iban = models.CharField(_("IBAN"), max_length=34, blank=True)
    bic = models.CharField(_("BIC"), max_length=11, blank=True)
    glaeubiger_id = models.CharField(_("Gläubiger-ID (SEPA)"), max_length=35, blank=True)
    finanzamt = models.CharField(_("Finanzamt"), max_length=100, blank=True)
    steuernummer = models.CharField(_("Steuernummer"), max_length=30, blank=True)
    umsatzsteuerpflichtig = models.BooleanField(
        _("Umsatzsteuerpflichtig"), default=False,
        help_text=_("Für nicht gemeinnützige Vereine bzw. den wirtschaftlichen Geschäftsbetrieb: neue "
                  "Rechnungspositionen schlagen dann standardmäßig Umsatzsteuer vor, Rechnungen/E-Rechnungen weisen "
                  "sie entsprechend aus. Ersetzt keine steuerliche Beratung."))
    ust_idnr = models.CharField(_("USt-IdNr."), max_length=20, blank=True)
    rechnung_steuerhinweis = models.CharField(
        _("Steuerhinweis auf Rechnungen ohne Umsatzsteuer"), max_length=300, blank=True,
        help_text=_("Freitext für Rechnungen/E-Rechnungen, wenn (ein Teil) der Rechnung mit 0 % Umsatzsteuer "
                  "ausgewiesen wird, z. B. „Gemäß § 19 UStG wird keine Umsatzsteuer berechnet“ oder eine passende "
                  "Befreiungsvorschrift. Leer lassen für den Standardtext „Steuerbefreiung nach § 4 UStG "
                  "(ideeller Bereich)“. Bitte durch Steuerberater prüfen lassen."))
    bescheid_art = models.CharField(_("Art des Gemeinnützigkeitsbescheids"), max_length=20, choices=BESCHEID,
                                    default="freistellung")
    bescheid_datum = models.DateField(_("Datum des Bescheids"), null=True, blank=True)
    bescheid_zeitraum = models.CharField(_("Bescheid gilt für Zeitraum / VZ"), max_length=100, blank=True)
    beguenstigte_zwecke = models.TextField(_("Begünstigte Zwecke (laut Satzung)"), blank=True)
    zahlungsziel_tage = models.PositiveIntegerField(_("Zahlungsziel (Tage)"), default=14)
    rechnung_kopftext = models.TextField(_("Rechnungstext oben"), blank=True)
    rechnung_fusstext = models.TextField(_("Rechnungstext unten"), blank=True,
                                         default="Bitte überweisen Sie den Betrag unter Angabe des Verwendungszwecks.")
    uebungsleiter_freibetrag = models.DecimalField(_("Übungsleiterfreibetrag / Jahr (€)"), max_digits=8, decimal_places=2,
                                                   default=3300)
    ehrenamts_freibetrag = models.DecimalField(_("Ehrenamtsfreibetrag / Jahr (€)"), max_digits=8, decimal_places=2,
                                               default=960)
    logo = models.ImageField(_("Vereinslogo (PNG oder JPG)"), upload_to=logo_pfad, blank=True,
                             help_text=_("Wird auf Briefen, Rechnungen und Word-Dokumenten oben rechts gedruckt."))
    akzentfarbe = models.CharField(_("Akzentfarbe (Briefe und PDFs)"), max_length=7, default="#AF2B1E",
                                   help_text=_("Hex-Code, z. B. #AF2B1E (Feuerwehrrot) – für Überschrift/Linie im "
                                             "Briefkopf. Gilt auch für die Weboberfläche, solange unten keine "
                                             "eigene Farbe dafür eingetragen ist. Unter dem Farbfeld stehen "
                                             "gängige Feuerwehr-Farben zur Auswahl, es kann aber jede beliebige "
                                             "Farbe eingetragen werden."))
    akzentfarbe_fuss = models.CharField(_("Zweite Akzentfarbe (Linie über der Fußzeile)"), max_length=7, blank=True,
                                        help_text=_("Optional, Hex-Code z. B. #005199. Leer = gleiche Farbe wie oben "
                                                  "(für Briefe/PDFs)."))
    akzentfarbe_web = models.CharField(_("Hauptfarbe (Weboberfläche)"), max_length=7, blank=True,
                                       help_text=_("Optional eigene Farbe nur für Navigationsleiste und "
                                                 "Schaltflächen in der Anwendung, unabhängig von Briefen/PDFs. "
                                                 "Leer = gleiche Farbe wie oben."))
    akzentfarbe_web_2 = models.CharField(_("Akzentfarbe 1 (Weboberfläche, für Farbverläufe)"), max_length=7,
                                         blank=True,
                                         help_text=_("Optional, für Farbverläufe in Navigation und Schaltflächen "
                                                   "(z. B. Rot nach Schwarz). Leer = automatisch aus der "
                                                   "Hauptfarbe abgeleitet (dunklere Stufe)."))
    akzentfarbe_web_3 = models.CharField(_("Akzentfarbe 2 (Weboberfläche, für Hervorhebungen)"), max_length=7,
                                         blank=True,
                                         help_text=_("Optional, für Icon-Hintergründe auf den Kennzahlen-Karten und "
                                                   "ähnliche Hervorhebungen. Leer = Leuchtgelb (#F7FA00). Die "
                                                   "Textfarbe darauf wird automatisch für Lesbarkeit berechnet."))
    unterschrift_1 = models.CharField(_("Unterschrift 1 (Briefe)"), max_length=150, blank=True,
                                      help_text=_("z. B. Max Mustermann, 1. Vorsitzender"))
    unterschrift_2 = models.CharField(_("Unterschrift 2 (Briefe)"), max_length=150, blank=True)
    impressum_text = models.TextField(
        _("Impressum"), blank=True,
        help_text=_("Vollständiger Text nach § 5 TMG / § 18 MStV (verantwortliche Person, Anschrift, Kontakt, "
                  "Vertretungsberechtigte, ggf. USt-IdNr.). Wird ungeprüft auf der öffentlich erreichbaren "
                  "Impressum-Seite angezeigt – bitte gegen die eigene Satzung/das Vereinsregister prüfen."))
    STARTSEITE_BANNER_ART = [("info", _("Info")), ("warnung", _("Warnung")), ("wichtig", _("Wichtig"))]
    startseite_banner = models.TextField(
        _("Benachrichtigungsbanner (Startseite)"), blank=True,
        help_text=_("Wird oben auf der Startseite allen angemeldeten Benutzern dieses Vereins angezeigt, bis "
                  "entfernt oder das Bis-Datum erreicht ist - z. B. für Hinweise zur nächsten "
                  "Mitgliederversammlung oder geplante Wartungsarbeiten. Leer = kein Banner."))
    startseite_banner_art = models.CharField(_("Art des Banners"), max_length=8, choices=STARTSEITE_BANNER_ART,
                                             default="info")
    startseite_banner_bis = models.DateField(_("Banner sichtbar bis"), null=True, blank=True,
                                             help_text=_("Leer = dauerhaft sichtbar, bis der Text hier entfernt wird."))
    aufgaben_geprueft_am = models.DateTimeField(_("Zuletzt auf überfällige Aufgaben geprüft"), null=True,
                                               blank=True, editable=False)
    etikett_breite_mm = models.PositiveIntegerField(
        _("Etikettenbreite (mm)"), default=58, validators=[MinValueValidator(10)],
        help_text=_("Für Inventar-Etiketten (QR-Code). Standard passt auf gängige A4-Etikettenbögen. Für einen "
                  "Etikettendrucker mit Endlosrolle (z. B. Dymo LabelWriter 450, Standardadresse 89 × 28 mm) "
                  "hier die Rollenbreite eintragen und „Etiketten je Zeile“/„Etikettenzeilen je Seite“ unten "
                  "jeweils auf 1 setzen – die PDF-Seite wird dann exakt auf diese Größe zugeschnitten statt auf A4."))
    etikett_hoehe_mm = models.PositiveIntegerField(_("Etikettenhöhe (mm)"), default=40,
                                                   validators=[MinValueValidator(10)])
    etikett_spalten = models.PositiveIntegerField(_("Etiketten je Zeile (Spalten)"), default=3,
                                                  validators=[MinValueValidator(1)])
    etikett_zeilen = models.PositiveIntegerField(_("Etikettenzeilen je Seite"), default=6,
                                                 validators=[MinValueValidator(1)])
    aktiv = models.BooleanField(_("Aktiv"), default=True)

    AUDIT = True

    class Meta:
        verbose_name = _("Verein")
        verbose_name_plural = _("Vereine")
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def adresszeile(self):
        return ", ".join(x for x in (self.anschrift, f"{self.plz} {self.ort}".strip()) if x)

    @property
    def startseite_banner_aktiv(self):
        from datetime import date
        return bool(self.startseite_banner) and (not self.startseite_banner_bis
                                                  or self.startseite_banner_bis >= date.today())


class Rolle(models.Model):
    verein = models.ForeignKey(Verein, on_delete=models.CASCADE, related_name="rollen")
    name = models.CharField(_("Name"), max_length=100)
    ist_superadmin = models.BooleanField(_("Superadministrator (alle Rechte)"), default=False)
    rechte = models.JSONField(_("Rechte"), default=list, blank=True)
    matrix = models.JSONField(_("Berechtigungsmatrix (Stufen je Datenbereich)"), default=dict, blank=True, editable=False)

    AUDIT = True

    class Meta:
        verbose_name = _("Rolle")
        verbose_name_plural = _("Rollen")
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
    rolle = models.ForeignKey(Rolle, on_delete=models.PROTECT, verbose_name=_("Rolle"))
    extra_rechte = models.JSONField(_("Zusätzliche Einzelrechte"), default=list, blank=True)
    aktiv = models.BooleanField(_("Aktiv"), default=True)

    AUDIT = True

    class Meta:
        verbose_name = _("Benutzerzugang")
        verbose_name_plural = _("Benutzerzugänge")
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
    AKTION = [("angelegt", _("Angelegt")), ("geaendert", _("Geändert")), ("geloescht", _("Gelöscht")),
             ("exportiert", _("Exportiert")), ("importiert", _("Importiert"))]
    verein = models.ForeignKey(Verein, on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    zeit = models.DateTimeField(_("Zeitpunkt"), auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name="+")
    user_name = models.CharField(_("Benutzer"), max_length=150, blank=True)
    ip = models.GenericIPAddressField(_("IP-Adresse"), null=True, blank=True)
    modell = models.CharField(_("Objektart"), max_length=100)
    objekt_id = models.CharField(_("Objekt-ID"), max_length=40)
    objekt_repr = models.CharField(_("Objekt"), max_length=200)
    aktion = models.CharField(_("Aktion"), max_length=12, choices=AKTION)
    aenderungen = models.JSONField(_("Änderungen"), default=dict)
    grund = models.CharField(_("Grund"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("Protokolleintrag")
        verbose_name_plural = _("Änderungsprotokoll")
        ordering = ["-zeit", "-id"]
        indexes = [models.Index(fields=["verein", "modell", "objekt_id"])]

    def __str__(self):
        return f"{self.zeit:%d.%m.%Y %H:%M} {self.user_name} {self.aktion} {self.objekt_repr}"


class Systemeinstellung(models.Model):
    """Instanzweite (nicht vereinsgebundene) Einstellungen - genau ein Datensatz (pk=1). Bearbeitbar nur über die
    Django-Admin-Oberfläche (/admin/), da sie nicht zu einem einzelnen Verein gehören und ihre Änderung Rechte
    braucht, die über die normale Rollen-/Rechteverwaltung eines Vereins hinausgehen (Serverbetrieb)."""
    fints_produkt_id = VerschluesseltesTextField(
        _("FinTS-Produkt-ID"), blank=True,
        help_text=_("Alternative zur Umgebungsvariable FINTS_PRODUCT_ID - wird bevorzugt verwendet, wenn gesetzt. "
                  "Kostenlos zu registrieren bei der Deutschen Kreditwirtschaft: "
                  "https://www.hbci-zka.de/register/prod_register.htm"))
    update_verfuegbare_version = models.CharField(_("Verfügbare neue Version"), max_length=20, blank=True,
                                                  editable=False)
    update_geprueft_am = models.DateTimeField(_("Zuletzt auf Updates geprüft"), null=True, blank=True, editable=False)

    class Meta:
        verbose_name = _("Systemeinstellung")
        verbose_name_plural = _("Systemeinstellungen")

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

    def update_anzeigen(self, aktuelle_version):
        """Gibt die bekannte neue Versionsnummer zurück, wenn sie höher als aktuelle_version ist, sonst ''."""
        def teile(s):
            try:
                return tuple(int(x) for x in (s or "").strip().split("."))
            except ValueError:
                return None
        neu, akt = teile(self.update_verfuegbare_version), teile(aktuelle_version)
        return self.update_verfuegbare_version if (neu is not None and akt is not None and neu > akt) else ""
