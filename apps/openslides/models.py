from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.fields import VerschluesseltesTextField
from apps.core.models import TenantModel
from apps.core.util import pruefe_oeffentliche_adresse


class OpenSlidesVerbindung(TenantModel):
    """Verbindung eines Vereins zu einer OpenSlides-4-Instanz (je Verein genau eine)."""
    url = models.URLField(_("OpenSlides-Adresse"), help_text=_("z. B. https://versammlung.example.org (ohne / am Ende)"))
    benutzername = models.CharField(_("Technischer Benutzer"), max_length=150,
                                    help_text=_("OpenSlides-Konto mit der Organisationsrolle „Organisationsverwalter“ "
                                              "(siehe Installationsanleitung)"))
    passwort = VerschluesseltesTextField(_("Passwort des technischen Benutzers"), blank=True)
    committee_id = models.PositiveIntegerField(_("Ausschuss-ID (Committee)"), default=1,
                                               help_text=_("In OpenSlides in der Adresszeile: …/committees/<ID>"))
    meeting_admin_ids = models.CharField(_("Administratoren neuer Versammlungen (OpenSlides-Konto-IDs)"), max_length=100,
                                         default="1", help_text=_("Kommagetrennt, z. B. 1 oder 1,5"))
    sprache = models.CharField(_("Sprache neuer Versammlungen"), max_length=5, default="de")
    tls_pruefen = models.BooleanField(_("TLS-Zertifikat prüfen"), default=True,
                                      help_text=_("Nur zum Testen mit selbstsigniertem Zertifikat abschalten"))
    sync_funktion = models.ForeignKey("members.Funktion", on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name="+", verbose_name=_("Nur Mitglieder mit dieser Funktion abgleichen"),
                                      help_text=_("Leer = alle aktiven Mitglieder"))
    aktiv = models.BooleanField(_("Anbindung aktiv"), default=False)
    letzter_test = models.CharField(_("Letzter Verbindungstest"), max_length=300, blank=True, editable=False)
    letzter_abgleich_am = models.DateTimeField(_("Letzter Abgleich"), null=True, blank=True, editable=False)
    letzter_abgleich_info = models.TextField(_("Ergebnis des letzten Abgleichs"), blank=True, editable=False)

    AUDIT_MASK = ("passwort",)

    class Meta:
        verbose_name = _("OpenSlides-Verbindung")
        verbose_name_plural = _("OpenSlides-Verbindungen")
        constraints = [models.UniqueConstraint(fields=["verein"], name="eine_openslides_verbindung_je_verein")]

    def __str__(self):
        return f"OpenSlides {self.url}"

    def clean(self):
        if self.url:
            pruefe_oeffentliche_adresse(self.url)

    @property
    def admin_ids(self):
        return [int(x) for x in self.meeting_admin_ids.replace(" ", "").split(",") if x.isdigit()]


class SuperadminKonto(TenantModel):
    """Verknüpfung Benutzerzugang <-> OpenSlides-Konto für Superadministratoren OHNE eigene Mitgliedsakte (vom
    Abgleich mitverwaltet). Superadmins MIT Mitgliedsakte bekommen ihr Konto stattdessen über die entsprechenden
    Felder am Mitglied (siehe apps.members.models.Mitglied), wie jedes andere Mitglied auch."""
    zugang = models.OneToOneField("core.Zugang", on_delete=models.CASCADE, related_name="openslides_konto",
                                  verbose_name=_("Benutzerzugang"))
    openslides_user_id = models.PositiveIntegerField(_("OpenSlides-Konto-ID"))
    openslides_username = models.CharField(_("OpenSlides-Benutzername"), max_length=150)
    openslides_initialpasswort = VerschluesseltesTextField(_("OpenSlides-Startpasswort"), blank=True, editable=False)

    AUDIT_MASK = ("openslides_initialpasswort",)

    class Meta:
        verbose_name = _("OpenSlides-Konto (Superadmin ohne Mitgliedsakte)")
        verbose_name_plural = _("OpenSlides-Konten (Superadmins ohne Mitgliedsakte)")

    def __str__(self):
        # self.zugang_id statt self.zugang: beim Loeschen per Kaskade (Benutzerzugang geloescht) kann das
        # verknuepfte Objekt bei der Audit-Protokollierung (post_delete) schon weg sein - ein Dereferenzieren
        # wuerde dann mit DoesNotExist abbrechen.
        return f"{self.openslides_username} (Zugang #{self.zugang_id})"
