from datetime import date

from django.conf import settings
from django.db import models
from django.db.models import Max
from django.utils.translation import gettext_lazy as _

from apps.core.fields import VerschluesseltesTextField
from apps.core.models import TenantModel, naechste_nummer
from apps.core.util import upload_pfad


class Mitgliedsart(TenantModel):
    """Mitgliedsart = Beitragsart (Aktiv, Passiv, Jugend, Familie, Ehrenmitglied ...)."""
    name = models.CharField(_("Name"), max_length=100)
    jahresbeitrag = models.DecimalField(_("Standard-Jahresbeitrag (€)"), max_digits=8, decimal_places=2, default=0)
    beschreibung = models.CharField(_("Beschreibung"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("Mitgliedsart")
        verbose_name_plural = _("Mitgliedsarten / Beiträge")
        unique_together = [("verein", "name")]
        ordering = ["name"]

    def __str__(self):
        return self.name


class Familie(TenantModel):
    name = models.CharField(_("Familienname / Bezeichnung"), max_length=150)

    class Meta:
        verbose_name = _("Familie")
        verbose_name_plural = _("Familien")
        ordering = ["name"]

    def __str__(self):
        return self.name


class Abteilung(TenantModel):
    name = models.CharField(_("Name"), max_length=100)

    class Meta:
        verbose_name = _("Abteilung")
        verbose_name_plural = _("Abteilungen")
        unique_together = [("verein", "name")]
        ordering = ["name"]

    def __str__(self):
        return self.name


class MitgliedTag(TenantModel):
    """Berechtigungs-Tag: statt Rollen einzeln zu verteilen, bekommen Mitglieder Tags. Ein Tag legt fest, in welcher
    Paperless-Gruppe und in welcher OpenSlides-Versammlungsgruppe (Rolle) seine Träger geführt werden."""
    name = models.CharField(_("Name"), max_length=100, help_text=_("z. B. Vorstand, Kassenwart, Schriftführer"))
    beschreibung = models.CharField(_("Beschreibung"), max_length=200, blank=True)
    paperless_gruppe = models.CharField(
        _("Paperless-Gruppe"), max_length=150, blank=True,
        help_text=_("Leer = kein Paperless-Zugang über dieses Tag. Sonst wird für Träger des Tags ein Paperless-Konto "
                  "angelegt und dieser Gruppe zugeordnet (Gruppe wird bei Bedarf angelegt)."))
    paperless_nur_lesen = models.BooleanField(
        _("In Paperless nur lesen"), default=False,
        help_text=_("Gilt für neu angelegte Gruppen: nur Dokumente ansehen statt ansehen, hochladen und bearbeiten."))
    rolle = models.ForeignKey(
        "core.Rolle", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        verbose_name=_("Rolle in dieser Software"),
        help_text=_("Träger des Tags erhalten (sofern sie einen Benutzerzugang haben) automatisch diese Rolle; "
                  "fällt das Tag weg, wird der Zugang deaktiviert (Rechte entziehen nach Funktionsende)."))
    openslides_gruppe = models.CharField(
        _("OpenSlides-Gruppe in Versammlungen"), max_length=100, blank=True,
        help_text=_("Name der Gruppe in der OpenSlides-Versammlung (z. B. Admin, Staff, Delegates). Träger des Tags "
                  "erhalten beim Anlegen bzw. Übertragen einer Veranstaltung diese Rechte. Leer = keine."))

    class Meta:
        verbose_name = _("Tag (Zugriffsrechte)")
        verbose_name_plural = _("Tags (Zugriffsrechte)")
        unique_together = [("verein", "name")]
        ordering = ["name"]

    def __str__(self):
        return self.name


class Funktion(TenantModel):
    name = models.CharField(_("Name"), max_length=100)

    class Meta:
        verbose_name = _("Funktion")
        verbose_name_plural = _("Funktionen")
        unique_together = [("verein", "name")]
        ordering = ["name"]

    def __str__(self):
        return self.name


class Mitglied(TenantModel):
    STATUS = [("aktiv", _("Aktiv")), ("ruhend", _("Ruhend")), ("ausgetreten", _("Ausgetreten")),
              ("verstorben", _("Verstorben"))]
    ANREDE = [("herr", _("Herr")), ("frau", _("Frau")), ("divers", _("Divers")),
             ("firma", _("Firma / Organisation"))]
    ZAHLART = [("ueberweisung", _("Überweisung")), ("lastschrift", _("SEPA-Lastschrift")), ("bar", _("Bar"))]

    mitgliedsnummer = models.PositiveIntegerField(_("Mitgliedsnummer"), null=True, blank=True,
                                                  help_text=_("Leer lassen = automatisch vergeben"))
    anrede = models.CharField(_("Anrede"), max_length=10, choices=ANREDE, blank=True)
    vorname = models.CharField(_("Vorname"), max_length=100)
    nachname = models.CharField(_("Nachname"), max_length=100)
    geburtsdatum = models.DateField(_("Geburtsdatum"), null=True, blank=True)
    eintrittsdatum = models.DateField(_("Eintrittsdatum"), null=True, blank=True)
    austrittsdatum = models.DateField(_("Austrittsdatum"), null=True, blank=True)
    status = models.CharField(_("Status"), max_length=12, choices=STATUS, default="aktiv")
    mitgliedsart = models.ForeignKey(Mitgliedsart, on_delete=models.PROTECT, null=True, blank=True,
                                     verbose_name=_("Mitgliedsart"))
    familie = models.ForeignKey(Familie, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Familie"))
    ist_familienzahler = models.BooleanField(_("Zahlt den Familienbeitrag"), default=False)
    individueller_beitrag = models.DecimalField(_("Individueller Jahresbeitrag (€)"), max_digits=8, decimal_places=2,
                                                null=True, blank=True,
                                                help_text=_("Überschreibt alle Beitragsregeln (0 = beitragsfrei)"))
    strasse = models.CharField(_("Straße / Nr."), max_length=200, blank=True)
    plz = models.CharField(_("PLZ"), max_length=10, blank=True)
    ort = models.CharField(_("Ort"), max_length=100, blank=True)
    email = models.EmailField(_("E-Mail"), blank=True)
    telefon = models.CharField(_("Telefon"), max_length=40, blank=True)
    mobil = models.CharField(_("Mobil"), max_length=40, blank=True)
    zahlungsart = models.CharField(_("Zahlungsart"), max_length=12, choices=ZAHLART, default="ueberweisung")
    kontoinhaber = models.CharField(_("Kontoinhaber"), max_length=150, blank=True)
    iban = VerschluesseltesTextField(_("IBAN"), blank=True)
    bic = models.CharField(_("BIC"), max_length=11, blank=True)
    mandatsreferenz = models.CharField(_("SEPA-Mandatsreferenz"), max_length=35, blank=True)
    mandatsdatum = models.DateField(_("Datum des SEPA-Mandats"), null=True, blank=True)
    abteilungen = models.ManyToManyField(Abteilung, blank=True, verbose_name=_("Abteilungen"))
    tags = models.ManyToManyField(
        MitgliedTag, blank=True, related_name="mitglieder", verbose_name=_("Tags (Zugriffsrechte)"),
        help_text=_("Bestimmen die Zugriffsrechte in Paperless und OpenSlides (Verwaltung › Tags)."))
    vorstandsmitglied = models.BooleanField(
        _("Vorstandsmitglied"), default=False, editable=False,
        help_text=_("Wird automatisch anhand der Tags geführt (DSO-Funktionen bzw. Beisitzer) - keine manuelle "
                  "Auswahl mehr, sondern über Verwaltung › Funktionen: Tags vergeben. Setzt automatisch die "
                  "Funktion „Vorstandsmitglied“. Nur Vorstandsmitglieder können mit Paperless abgeglichen werden "
                  "(Verwaltung › Paperless-Anbindung)."))
    alters_ehrenabteilung = models.BooleanField(_("Alters- und Ehrenabteilung"), default=False)
    einsatzabteilung_aktiv = models.BooleanField(_("Aktives Mitglied der Einsatzabteilung"), default=False)
    foto = models.ImageField(_("Foto"), upload_to=upload_pfad, blank=True)
    notizen = models.TextField(_("Notizen"), blank=True)
    openslides_user_id = models.PositiveIntegerField(_("OpenSlides-Konto-ID"), null=True, blank=True, editable=False)
    openslides_username = models.CharField(_("OpenSlides-Benutzername"), max_length=150, blank=True, editable=False)
    openslides_initialpasswort = VerschluesseltesTextField(_("OpenSlides-Startpasswort"), blank=True, editable=False)
    benutzer = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    editable=False, related_name="mitglied_zugang",
                                    verbose_name=_("Zugang (Selbstdatenpflege)"))
    selbstdienst_initialpasswort = VerschluesseltesTextField(_("Selbstdienst-Startpasswort"), blank=True, editable=False)

    AUDIT_MASK = ("iban", "openslides_initialpasswort", "selbstdienst_initialpasswort")

    class Meta:
        verbose_name = _("Mitglied")
        verbose_name_plural = _("Mitglieder")
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
        self._vorstandsmitglied_abgleichen()
        rolle_aus_tags(self)

    def _vorstandsmitglied_abgleichen(self):
        """Vorstandsmitglied wird aus den Tags abgeleitet (eine der sechs DSO-Funktionen oder Beisitzer) - keine
        manuelle Auswahl mehr, siehe Verwaltung › Funktionen: Tags. Für jedes dieser Tags wird eine eigene
        historisierte Funktion (Von/Bis) mit dem Namen DES JEWEILIGEN TAGS geführt (z. B. „Kassenwart“ oder
        „Beisitzer“, nicht ein allgemeiner Platzhalter „Vorstandsmitglied“) - Tag gesetzt -> offene Funktion
        anlegen, Tag entfernt -> laufende Funktion beenden (der Verlauf bleibt erhalten)."""
        from datetime import date as _date

        from django.db.models import Q

        from apps.core.matrix import VORSTAND_TAGNAMEN
        gehalten = set(self.tags.filter(name__in=VORSTAND_TAGNAMEN).values_list("name", flat=True))
        neu = bool(gehalten)
        if neu != self.vorstandsmitglied:
            Mitglied.objects.filter(pk=self.pk).update(vorstandsmitglied=neu)
            self.vorstandsmitglied = neu
        for name in VORSTAND_TAGNAMEN:
            offen = MitgliedFunktion.objects.filter(mitglied=self, funktion__name=name).filter(
                Q(bis__isnull=True) | Q(bis__gte=_date.today()))
            if name in gehalten:
                # nur eine unbefristet laufende Funktion zaehlt - eine heute beendete wird neu angelegt
                if not offen.filter(bis__isnull=True).exists():
                    f, _ = Funktion.objects.get_or_create(verein_id=self.verein_id, name=name)
                    MitgliedFunktion.objects.create(verein_id=self.verein_id, mitglied=self, funktion=f,
                                                    von=_date.today())
            else:
                offen.update(bis=_date.today())

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
    mitglied = models.ForeignKey(Mitglied, on_delete=models.CASCADE, verbose_name=_("Mitglied"), related_name="funktionen")
    funktion = models.ForeignKey(Funktion, on_delete=models.PROTECT, verbose_name=_("Funktion"))
    von = models.DateField(_("Von"), null=True, blank=True)
    bis = models.DateField(_("Bis"), null=True, blank=True)

    class Meta:
        verbose_name = _("Funktion eines Mitglieds")
        verbose_name_plural = _("Funktionen der Mitglieder")
        ordering = ["-von"]

    def __str__(self):
        return f"{self.mitglied.name}: {self.funktion}"

    @property
    def anzeige(self):
        """Funktion samt Zeitraum - zwei Amtszeiten derselben Funktion sind sonst in einer Liste nicht
        auseinanderzuhalten (z. B. zwei Mal "Vorstandsmitglied" ohne erkennbaren Unterschied)."""
        von = f"{self.von:%d.%m.%Y}" if self.von else "?"
        bis = f"{self.bis:%d.%m.%Y}" if self.bis else "heute"
        return f"{self.funktion} ({von} – {bis})"


class Dokument(TenantModel):
    KATEGORIE = [("beitritt", _("Beitrittserklärung")), ("sepa", _("SEPA-Mandat")), ("ehrung", _("Ehrung")),
                 ("kuendigung", _("Kündigung")), ("sonstiges", _("Sonstiges"))]
    mitglied = models.ForeignKey(Mitglied, on_delete=models.CASCADE, verbose_name=_("Mitglied"), related_name="dokumente")
    kategorie = models.CharField(_("Kategorie"), max_length=12, choices=KATEGORIE, default="sonstiges")
    titel = models.CharField(_("Titel"), max_length=200)
    datei = models.FileField(_("Datei"), upload_to=upload_pfad)
    version = models.PositiveIntegerField(_("Version"), default=1, editable=False)

    class Meta:
        verbose_name = _("Dokument")
        verbose_name_plural = _("Dokumente")
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


def rolle_aus_tags(mitglied):
    """Verteilt die Rolle in dieser Software anhand der Tags (Funktion) und entzieht sie bei Funktionsende:
    * Mitglied mit Benutzerzugang und einem Tag mit Rolle -> Zugang bekommt diese Rolle (und wird aktiv).
    * kein solches Tag mehr bzw. Mitglied nicht mehr aktiv -> ein Zugang, dessen Rolle über Tags verwaltet wird,
      wird deaktiviert (nie gelöscht, Superadministratoren bleiben unberührt)."""
    if not mitglied.benutzer_id:
        return
    from apps.core.models import Zugang
    z = Zugang.objects.select_related("rolle").filter(verein_id=mitglied.verein_id, user_id=mitglied.benutzer_id).first()
    if z is None or z.rolle.ist_superadmin:
        return
    verwaltete = set(MitgliedTag.objects.filter(verein_id=mitglied.verein_id, rolle__isnull=False)
                     .values_list("rolle_id", flat=True))
    tags = list(mitglied.tags.filter(rolle__isnull=False).order_by("id"))
    if mitglied.status != "aktiv" or not tags:
        if z.rolle_id in verwaltete and z.aktiv:
            z.aktiv = False
            z.save(update_fields=["aktiv"])
        return
    if z.rolle_id != tags[0].rolle_id or not z.aktiv:
        z.rolle_id, z.aktiv = tags[0].rolle_id, True
        z.save(update_fields=["rolle", "aktiv"])


def _tags_geaendert(sender, instance, action, reverse, pk_set, **kw):
    if action not in ("post_add", "post_remove", "post_clear"):
        return
    if reverse:   # von der Tag-Seite: alle betroffenen Mitglieder
        for m in Mitglied.objects.filter(pk__in=pk_set or []):
            m._vorstandsmitglied_abgleichen()
            rolle_aus_tags(m)
    else:
        instance._vorstandsmitglied_abgleichen()
        rolle_aus_tags(instance)


from django.db.models.signals import m2m_changed  # noqa: E402

m2m_changed.connect(_tags_geaendert, sender=Mitglied.tags.through, dispatch_uid="mitglied_tags_rolle")
