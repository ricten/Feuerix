from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.fields import VerschluesseltesTextField
from apps.core.models import TenantModel
from apps.core.util import pruefe_oeffentliche_adresse


class PaperlessVerbindung(TenantModel):
    """Verbindung eines Vereins zu einer Paperless-ngx-Instanz (je Verein genau eine)."""
    url = models.URLField(_("Paperless-Adresse"), help_text=_("z. B. https://paperless.example.org (ohne / am Ende)"))
    api_token = VerschluesseltesTextField(_("API-Token"), blank=True,
                                          help_text=_("Unter Paperless: Mein Profil › API-Token erzeugen"))
    korrespondent = models.CharField(_("Standard-Korrespondent"), max_length=150, blank=True,
                                     help_text=_("Wird in Paperless angelegt, falls noch nicht vorhanden. Leer = keiner."))
    dokumenttyp = models.CharField(_("Standard-Dokumenttyp"), max_length=150, blank=True,
                                   help_text=_("Wird in Paperless angelegt, falls noch nicht vorhanden. Leer = keiner."))
    tags = models.CharField(_("Standard-Tags"), max_length=300, blank=True,
                            help_text=_("Kommagetrennt, z. B. Vereinsverwaltung,Ablage. Werden in Paperless angelegt, "
                                      "falls noch nicht vorhanden."))
    kategorie_tags = models.BooleanField(
        _("Art und Jahr automatisch als Tag setzen"), default=True,
        help_text=_("Gilt für Dokumente ohne eigene Tags (neue Dokumente bekommen Art und Jahr ohnehin als "
                  "bearbeitbare Tags vorbelegt)."))
    auto_uebergabe = models.BooleanField(
        _("Fertiggestellte Dokumente automatisch übergeben"), default=True,
        help_text=_("Rechnungen (beim Ausstellen), Zuwendungsbestätigungen, abgeschlossene Kassenberichte, "
                  "abgelegte Schriftstücke (Status „Final“), Serienbriefe und Belege werden ohne weiteren Klick an "
                  "Paperless übergeben."))
    vorstand_gruppe = models.CharField(
        _("Paperless-Gruppe für den Vorstand"), max_length=150, default="Vorstand", blank=True,
        help_text=_("Vorstandsmitglieder (Häkchen am Mitglied) werden per „Vorstand abgleichen“ als Paperless-Benutzer "
                  "angelegt und dieser Gruppe zugeordnet. Die Gruppe wird bei Bedarf mit Leserechten für Dokumente "
                  "angelegt; weitere Rechte lassen sich in Paperless vergeben."))
    letzter_abgleich_am = models.DateTimeField(_("Letzter Vorstands-Abgleich"), null=True, blank=True, editable=False)
    letzter_abgleich_info = models.TextField(_("Ergebnis des letzten Abgleichs"), blank=True, editable=False)
    tls_pruefen = models.BooleanField(_("TLS-Zertifikat prüfen"), default=True,
                                      help_text=_("Nur zum Testen mit selbstsigniertem Zertifikat abschalten"))
    aktiv = models.BooleanField(_("Anbindung aktiv"), default=False)
    letzter_test = models.CharField(_("Letzter Verbindungstest"), max_length=300, blank=True, editable=False)

    AUDIT_MASK = ("api_token",)

    class Meta:
        verbose_name = _("Paperless-Verbindung")
        verbose_name_plural = _("Paperless-Verbindungen")
        constraints = [models.UniqueConstraint(fields=["verein"], name="eine_paperless_verbindung_je_verein")]

    def __str__(self):
        return f"Paperless {self.url}"

    def clean(self):
        if self.url:
            pruefe_oeffentliche_adresse(self.url)

    @property
    def tag_liste(self):
        return [t.strip() for t in self.tags.split(",") if t.strip()]


class PaperlessBenutzer(TenantModel):
    """Verknüpfung Vorstandsmitglied bzw. Superadministrator-Benutzerzugang <-> Paperless-Benutzerkonto (vom
    Abgleich verwaltet). Genau eines von mitglied/zugang ist gesetzt - zugang nur für Superadmins ohne eigene
    Mitgliedsakte (z. B. ein rein technischer Betreuer-Zugang), die sonst keinen Konto-Abgleich hätten."""
    mitglied = models.OneToOneField("members.Mitglied", on_delete=models.CASCADE, related_name="paperless_benutzer",
                                    verbose_name=_("Mitglied"), null=True, blank=True)
    zugang = models.OneToOneField("core.Zugang", on_delete=models.CASCADE, related_name="paperless_benutzer",
                                  verbose_name=_("Benutzerzugang (Superadmin ohne Mitgliedsakte)"), null=True, blank=True)
    paperless_id = models.PositiveIntegerField(_("Paperless-Benutzer-ID"))
    benutzername = models.CharField(_("Paperless-Benutzername"), max_length=150)
    angelegt = models.BooleanField(
        _("Vom Abgleich angelegt"), default=True,
        help_text=_("Nur selbst angelegte Konten werden bei Ausscheiden aus dem Vorstand deaktiviert; bereits "
                  "vorhandene Konten werden lediglich der Gruppe zugeordnet bzw. daraus entfernt."))
    initialpasswort = VerschluesseltesTextField(_("Startpasswort"), blank=True, editable=False)

    AUDIT_MASK = ("initialpasswort",)

    class Meta:
        verbose_name = _("Paperless-Benutzer")
        verbose_name_plural = _("Paperless-Benutzer")
        constraints = [
            models.CheckConstraint(condition=Q(mitglied__isnull=False) | Q(zugang__isnull=False),
                                   name="paperless_benutzer_mitglied_oder_zugang"),
            models.CheckConstraint(condition=Q(mitglied__isnull=True) | Q(zugang__isnull=True),
                                   name="paperless_benutzer_nicht_beides"),
        ]

    def __str__(self):
        # bewusst ueber die rohen FK-IDs (attname) statt ueber self.mitglied/self.zugang: beim Loeschen per
        # Kaskade (z. B. Benutzerzugang geloescht) kann das verknuepfte Objekt zum Zeitpunkt der Audit-Protokollierung
        # (post_delete) schon weg sein - ein Dereferenzieren wuerde dann mit DoesNotExist abbrechen.
        ziel = f"Mitglied #{self.mitglied_id}" if self.mitglied_id else f"Zugang #{self.zugang_id}"
        return f"{self.benutzername} ({ziel})"
