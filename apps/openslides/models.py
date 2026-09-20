from django.db import models

from apps.core.fields import VerschluesseltesTextField
from apps.core.models import TenantModel


class OpenSlidesVerbindung(TenantModel):
    """Verbindung eines Vereins zu einer OpenSlides-4-Instanz (je Verein genau eine)."""
    url = models.URLField("OpenSlides-Adresse", help_text="z. B. https://versammlung.example.org (ohne / am Ende)")
    benutzername = models.CharField("Technischer Benutzer", max_length=150,
                                    help_text="OpenSlides-Konto mit der Organisationsrolle „Organisationsverwalter“ "
                                              "(siehe Installationsanleitung)")
    passwort = VerschluesseltesTextField("Passwort des technischen Benutzers", blank=True)
    committee_id = models.PositiveIntegerField("Ausschuss-ID (Committee)", default=1,
                                               help_text="In OpenSlides in der Adresszeile: …/committees/<ID>")
    meeting_admin_ids = models.CharField("Administratoren neuer Versammlungen (OpenSlides-Konto-IDs)", max_length=100,
                                         default="1", help_text="Kommagetrennt, z. B. 1 oder 1,5")
    sprache = models.CharField("Sprache neuer Versammlungen", max_length=5, default="de")
    tls_pruefen = models.BooleanField("TLS-Zertifikat prüfen", default=True,
                                      help_text="Nur zum Testen mit selbstsigniertem Zertifikat abschalten")
    sync_funktion = models.ForeignKey("members.Funktion", on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name="+", verbose_name="Nur Mitglieder mit dieser Funktion abgleichen",
                                      help_text="Leer = alle aktiven Mitglieder")
    aktiv = models.BooleanField("Anbindung aktiv", default=False)
    letzter_test = models.CharField("Letzter Verbindungstest", max_length=300, blank=True, editable=False)
    letzter_abgleich_am = models.DateTimeField("Letzter Abgleich", null=True, blank=True, editable=False)
    letzter_abgleich_info = models.TextField("Ergebnis des letzten Abgleichs", blank=True, editable=False)

    AUDIT_MASK = ("passwort",)

    class Meta:
        verbose_name = "OpenSlides-Verbindung"
        verbose_name_plural = "OpenSlides-Verbindungen"
        constraints = [models.UniqueConstraint(fields=["verein"], name="eine_openslides_verbindung_je_verein")]

    def __str__(self):
        return f"OpenSlides {self.url}"

    @property
    def admin_ids(self):
        return [int(x) for x in self.meeting_admin_ids.replace(" ", "").split(",") if x.isdigit()]
