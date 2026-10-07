from django.db import models
from django.db.models import Q

from apps.core.fields import VerschluesseltesTextField
from apps.core.models import TenantModel


class PaperlessVerbindung(TenantModel):
    """Verbindung eines Vereins zu einer Paperless-ngx-Instanz (je Verein genau eine)."""
    url = models.URLField("Paperless-Adresse", help_text="z. B. https://paperless.example.org (ohne / am Ende)")
    api_token = VerschluesseltesTextField("API-Token", blank=True,
                                          help_text="Unter Paperless: Mein Profil › API-Token erzeugen")
    korrespondent = models.CharField("Standard-Korrespondent", max_length=150, blank=True,
                                     help_text="Wird in Paperless angelegt, falls noch nicht vorhanden. Leer = keiner.")
    dokumenttyp = models.CharField("Standard-Dokumenttyp", max_length=150, blank=True,
                                   help_text="Wird in Paperless angelegt, falls noch nicht vorhanden. Leer = keiner.")
    tags = models.CharField("Standard-Tags", max_length=300, blank=True,
                            help_text="Kommagetrennt, z. B. Vereinsverwaltung,Ablage. Werden in Paperless angelegt, "
                                      "falls noch nicht vorhanden.")
    kategorie_tags = models.BooleanField(
        "Art und Jahr automatisch als Tag setzen", default=True,
        help_text="Gilt für Dokumente ohne eigene Tags (neue Dokumente bekommen Art und Jahr ohnehin als "
                  "bearbeitbare Tags vorbelegt).")
    auto_uebergabe = models.BooleanField(
        "Fertiggestellte Dokumente automatisch übergeben", default=True,
        help_text="Rechnungen (beim Ausstellen), Zuwendungsbestätigungen, abgeschlossene Kassenberichte, "
                  "abgelegte Schriftstücke (Status „Final“), Serienbriefe und Belege werden ohne weiteren Klick an "
                  "Paperless übergeben.")
    vorstand_gruppe = models.CharField(
        "Paperless-Gruppe für den Vorstand", max_length=150, default="Vorstand", blank=True,
        help_text="Vorstandsmitglieder (Häkchen am Mitglied) werden per „Vorstand abgleichen“ als Paperless-Benutzer "
                  "angelegt und dieser Gruppe zugeordnet. Die Gruppe wird bei Bedarf mit Leserechten für Dokumente "
                  "angelegt; weitere Rechte lassen sich in Paperless vergeben.")
    letzter_abgleich_am = models.DateTimeField("Letzter Vorstands-Abgleich", null=True, blank=True, editable=False)
    letzter_abgleich_info = models.TextField("Ergebnis des letzten Abgleichs", blank=True, editable=False)
    tls_pruefen = models.BooleanField("TLS-Zertifikat prüfen", default=True,
                                      help_text="Nur zum Testen mit selbstsigniertem Zertifikat abschalten")
    aktiv = models.BooleanField("Anbindung aktiv", default=False)
    letzter_test = models.CharField("Letzter Verbindungstest", max_length=300, blank=True, editable=False)

    AUDIT_MASK = ("api_token",)

    class Meta:
        verbose_name = "Paperless-Verbindung"
        verbose_name_plural = "Paperless-Verbindungen"
        constraints = [models.UniqueConstraint(fields=["verein"], name="eine_paperless_verbindung_je_verein")]

    def __str__(self):
        return f"Paperless {self.url}"

    @property
    def tag_liste(self):
        return [t.strip() for t in self.tags.split(",") if t.strip()]


class PaperlessBenutzer(TenantModel):
    """Verknüpfung Vorstandsmitglied bzw. Superadministrator-Benutzerzugang <-> Paperless-Benutzerkonto (vom
    Abgleich verwaltet). Genau eines von mitglied/zugang ist gesetzt - zugang nur für Superadmins ohne eigene
    Mitgliedsakte (z. B. ein rein technischer Betreuer-Zugang), die sonst keinen Konto-Abgleich hätten."""
    mitglied = models.OneToOneField("members.Mitglied", on_delete=models.CASCADE, related_name="paperless_benutzer",
                                    verbose_name="Mitglied", null=True, blank=True)
    zugang = models.OneToOneField("core.Zugang", on_delete=models.CASCADE, related_name="paperless_benutzer",
                                  verbose_name="Benutzerzugang (Superadmin ohne Mitgliedsakte)", null=True, blank=True)
    paperless_id = models.PositiveIntegerField("Paperless-Benutzer-ID")
    benutzername = models.CharField("Paperless-Benutzername", max_length=150)
    angelegt = models.BooleanField(
        "Vom Abgleich angelegt", default=True,
        help_text="Nur selbst angelegte Konten werden bei Ausscheiden aus dem Vorstand deaktiviert; bereits "
                  "vorhandene Konten werden lediglich der Gruppe zugeordnet bzw. daraus entfernt.")
    initialpasswort = VerschluesseltesTextField("Startpasswort", blank=True, editable=False)

    AUDIT_MASK = ("initialpasswort",)

    class Meta:
        verbose_name = "Paperless-Benutzer"
        verbose_name_plural = "Paperless-Benutzer"
        constraints = [
            models.CheckConstraint(condition=Q(mitglied__isnull=False) | Q(zugang__isnull=False),
                                   name="paperless_benutzer_mitglied_oder_zugang"),
            models.CheckConstraint(condition=Q(mitglied__isnull=True) | Q(zugang__isnull=True),
                                   name="paperless_benutzer_nicht_beides"),
        ]

    def __str__(self):
        return f"{self.benutzername} ({self.mitglied or self.zugang})"
