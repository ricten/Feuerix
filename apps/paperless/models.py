from django.db import models

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
        "Kategorie als Tag setzen", default=True,
        help_text="Jedes Dokument bekommt in Paperless automatisch die Ablage-Kategorie (z. B. Protokoll, Belege) "
                  "als Tag - zusätzlich zu den Standard-Tags.")
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
