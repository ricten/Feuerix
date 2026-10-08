import uuid
from datetime import date

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TenantModel, naechste_nummer
from apps.core.util import upload_pfad


class Kategorie(TenantModel):
    name = models.CharField(_("Name"), max_length=100)

    class Meta:
        verbose_name = _("Inventar-Kategorie")
        verbose_name_plural = _("Inventar-Kategorien")
        unique_together = [("verein", "name")]
        ordering = ["name"]

    def __str__(self):
        return self.name


class Lagerort(TenantModel):
    name = models.CharField(_("Name"), max_length=100)
    beschreibung = models.CharField(_("Beschreibung"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("Lagerort")
        verbose_name_plural = _("Inventar-Lagerorte")
        unique_together = [("verein", "name")]
        ordering = ["name"]

    def __str__(self):
        return self.name


class Gegenstand(TenantModel):
    ZUSTAND = [("neu", _("Neu")), ("gut", _("Gut")), ("gebrauchsspuren", _("Gebrauchsspuren")), ("defekt", _("Defekt")),
               ("ausgesondert", _("Ausgesondert"))]
    inventarnummer = models.CharField(_("Inventarnummer"), max_length=20, blank=True,
                                      help_text=_("Leer lassen = automatisch (INV-000001)"))
    bezeichnung = models.CharField(_("Bezeichnung"), max_length=200)
    kategorie = models.ForeignKey(Kategorie, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Kategorie"))
    hersteller = models.CharField(_("Hersteller"), max_length=100, blank=True)
    modell = models.CharField(_("Modell"), max_length=100, blank=True)
    seriennummer = models.CharField(_("Seriennummer"), max_length=100, blank=True)
    anschaffungsdatum = models.DateField(_("Anschaffungsdatum"), null=True, blank=True)
    anschaffungspreis = models.DecimalField(_("Anschaffungspreis (€)"), max_digits=10, decimal_places=2, null=True,
                                            blank=True)
    aktueller_wert = models.DecimalField(_("Aktueller Wert (€)"), max_digits=10, decimal_places=2, null=True, blank=True)
    lagerort = models.ForeignKey(Lagerort, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Lagerort"))
    verantwortlicher = models.ForeignKey("members.Mitglied", on_delete=models.SET_NULL, null=True, blank=True,
                                         related_name="+", verbose_name=_("Verantwortlicher"))
    zustand = models.CharField(_("Zustand"), max_length=15, choices=ZUSTAND, default="gut")
    garantie_bis = models.DateField(_("Garantie bis"), null=True, blank=True)
    verleihbar = models.BooleanField(_("Verleihbar"), default=False)
    leihgebuehr = models.DecimalField(_("Leihgebühr (€)"), max_digits=8, decimal_places=2, default=0)
    kaution = models.DecimalField(_("Kaution (€)"), max_digits=8, decimal_places=2, default=0)
    foto = models.ImageField(_("Foto"), upload_to=upload_pfad, blank=True)
    dokument = models.FileField(_("Dokument (Rechnung, Handbuch …)"), upload_to=upload_pfad, blank=True)
    notizen = models.TextField(_("Notizen"), blank=True)

    class Meta:
        verbose_name = _("Gegenstand")
        verbose_name_plural = _("Inventar")
        unique_together = [("verein", "inventarnummer")]
        ordering = ["inventarnummer"]

    def __str__(self):
        return f"{self.inventarnummer} {self.bezeichnung}"

    def save(self, *args, **kwargs):
        if not self.inventarnummer:
            n = naechste_nummer(self.verein_id, "INV")
            while Gegenstand.objects.filter(verein_id=self.verein_id, inventarnummer=f"INV-{n:06d}").exists():
                n = naechste_nummer(self.verein_id, "INV")
            self.inventarnummer = f"INV-{n:06d}"
        super().save(*args, **kwargs)

    @property
    def aktuell_verliehen(self):
        return self.verleihe.filter(status="ausgegeben").first()


def aktuelles_jahr():
    return date.today().year


AKTIV = ("reserviert", "ausgegeben")


class Verleih(TenantModel):
    STATUS = [("reserviert", _("Reserviert")), ("ausgegeben", _("Ausgegeben")), ("zurueckgegeben", _("Zurückgegeben")),
              ("storniert", _("Storniert"))]
    gegenstand = models.ForeignKey(Gegenstand, on_delete=models.PROTECT, related_name="verleihe",
                                   verbose_name=_("Gegenstand"))
    vorgang = models.UUIDField(_("Vorgang"), null=True, blank=True, editable=False,
                              help_text=_("Gruppiert mehrere gleichzeitig an denselben Entleiher verliehene Gegenstände."))
    entleiher = models.ForeignKey("members.Mitglied", on_delete=models.PROTECT, null=True, blank=True,
                                  related_name="+", verbose_name=_("Entleiher (Mitglied)"))
    entleiher_name = models.CharField(_("Entleiher (extern)"), max_length=150, blank=True)
    entleiher_kontakt = models.CharField(_("Kontakt (extern)"), max_length=200, blank=True)
    veranstaltung = models.ForeignKey("events.Veranstaltung", on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name="verleihe", verbose_name=_("Für Veranstaltung"))
    status = models.CharField(_("Status"), max_length=15, choices=STATUS, default="reserviert")
    von = models.DateField(_("Von"))
    bis = models.DateField(_("Bis (geplante Rückgabe)"))
    zweck = models.CharField(_("Zweck"), max_length=200, blank=True)
    leihgebuehr = models.DecimalField(_("Leihgebühr (€)"), max_digits=8, decimal_places=2, null=True, blank=True)
    kaution = models.DecimalField(_("Kaution (€)"), max_digits=8, decimal_places=2, null=True, blank=True)
    kaution_zurueckgezahlt = models.BooleanField(_("Kaution zurückgezahlt"), default=False)
    kaution_einbehalten = models.BooleanField(_("Kaution einbehalten (auf Rechnung)"), default=False, editable=False)
    ausgegeben_am = models.DateTimeField(_("Ausgegeben am"), null=True, blank=True, editable=False)
    ausgegeben_von = models.CharField(_("Ausgegeben durch"), max_length=150, blank=True, editable=False)
    zustand_bei_ausgabe = models.CharField(_("Zustand bei Ausgabe"), max_length=15, choices=Gegenstand.ZUSTAND,
                                           blank=True, editable=False)
    zurueckgegeben_am = models.DateTimeField(_("Zurückgegeben am"), null=True, blank=True, editable=False)
    zustand_bei_rueckgabe = models.CharField(_("Zustand bei Rückgabe"), max_length=15, choices=Gegenstand.ZUSTAND,
                                             blank=True, editable=False)
    rechnung = models.ForeignKey("finance.Rechnung", on_delete=models.SET_NULL, null=True, blank=True,
                                 editable=False, related_name="verleih_positionen",
                                 verbose_name=_("Rechnung (Leihgebühr)"))
    notizen = models.TextField(_("Notizen"), blank=True)

    class Meta:
        verbose_name = _("Verleih")
        verbose_name_plural = _("Verleih")
        ordering = ["-von", "-id"]

    def __str__(self):
        wer = self.wer
        g = self.gegenstand.inventarnummer if self.gegenstand_id else "?"
        return f"{g} → {wer} ({self.von:%d.%m.%Y})" if self.von else f"{g} → {wer}"

    @property
    def wer(self):
        if self.entleiher_id:
            return self.entleiher.name
        if self.entleiher_name:
            return self.entleiher_name
        if self.veranstaltung_id:
            return f"Verein selbst ({self.veranstaltung.titel})"
        return "?"

    @property
    def ueberfaellig(self):
        return self.status == "ausgegeben" and self.bis < date.today()

    def clean(self):
        if not (self.entleiher_id or self.entleiher_name or self.veranstaltung_id):
            raise ValidationError(_("Bitte ein Mitglied, einen externen Entleiher oder eine Veranstaltung angeben."))
        if self.von and self.bis and self.bis < self.von:
            raise ValidationError(_("Das Rückgabedatum liegt vor dem Beginn."))
        if self.gegenstand_id and self.status in AKTIV:
            g = self.gegenstand
            if not g.verleihbar:
                raise ValidationError(_("Dieser Gegenstand ist nicht als verleihbar markiert."))
            if g.zustand in ("defekt", "ausgesondert"):
                raise ValidationError(_("Gegenstand ist %(zustand)s und nicht verleihbar.") %
                                      {"zustand": g.get_zustand_display().lower()})
            if self.von and self.bis:
                konflikt = Verleih.objects.filter(gegenstand_id=g.pk, status__in=AKTIV, von__lte=self.bis,
                                                  bis__gte=self.von).exclude(pk=self.pk).first()
                if konflikt:
                    raise ValidationError(_("Im gewählten Zeitraum bereits verplant: %(konflikt)s.") %
                                          {"konflikt": konflikt})
            if Verleih.objects.filter(gegenstand_id=g.pk, status="ausgegeben", bis__lt=date.today()).exclude(
                    pk=self.pk).exists():
                raise ValidationError(_("Der Gegenstand ist überfällig und noch nicht zurückgegeben."))

    def save(self, *args, **kwargs):
        if self._state.adding and self.gegenstand_id:
            # Reserviert der Verein selbst fuer eine Veranstaltung (kein Entleiher angegeben), ergibt eine
            # Leihgebuehr/Kaution an sich selbst keinen Sinn - unabhaengig davon, was am Gegenstand hinterlegt ist.
            ist_vereinsreservierung = self.veranstaltung_id and not self.entleiher_id and not self.entleiher_name
            if not ist_vereinsreservierung:
                if self.kaution is None:
                    self.kaution = self.gegenstand.kaution
                if self.leihgebuehr is None:
                    self.leihgebuehr = self.gegenstand.leihgebuehr
        super().save(*args, **kwargs)


class Inventur(TenantModel):
    STATUS = [("laufend", _("Laufend")), ("abgeschlossen", _("Abgeschlossen"))]
    name = models.CharField(_("Bezeichnung"), max_length=100)
    jahr = models.PositiveIntegerField(_("Jahr"), default=aktuelles_jahr)
    status = models.CharField(_("Status"), max_length=15, choices=STATUS, default="laufend", editable=False)
    abgeschlossen_am = models.DateField(_("Abgeschlossen am"), null=True, blank=True, editable=False)
    bemerkung = models.TextField(_("Bemerkung"), blank=True)

    class Meta:
        verbose_name = _("Inventur")
        verbose_name_plural = _("Inventuren")
        ordering = ["-jahr", "-id"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        neu = self._state.adding
        super().save(*args, **kwargs)
        if neu:  # Momentaufnahme des Bestands
            Inventurposition.objects.bulk_create([
                Inventurposition(verein_id=self.verein_id, inventur=self, gegenstand=g,
                                 inventarnummer=g.inventarnummer, bezeichnung=g.bezeichnung,
                                 lagerort_text=str(g.lagerort) if g.lagerort_id else "")
                for g in Gegenstand.objects.filter(verein_id=self.verein_id).exclude(zustand="ausgesondert")])

    def zaehlung(self):
        z = {k: 0 for k, _ in Inventurposition.ERGEBNIS}
        for e in self.positionen.values_list("ergebnis", flat=True):
            z[e] += 1
        return z


class Inventurposition(TenantModel):
    ERGEBNIS = [("offen", _("Offen")), ("gefunden", _("Gefunden")), ("nicht_gefunden", _("Nicht gefunden")),
                ("beschaedigt", _("Beschädigt"))]
    inventur = models.ForeignKey(Inventur, on_delete=models.CASCADE, related_name="positionen", verbose_name=_("Inventur"))
    gegenstand = models.ForeignKey(Gegenstand, on_delete=models.PROTECT, related_name="+", verbose_name=_("Gegenstand"))
    inventarnummer = models.CharField(_("Inventarnummer"), max_length=20)
    bezeichnung = models.CharField(_("Bezeichnung"), max_length=200)
    lagerort_text = models.CharField(_("Lagerort (Soll)"), max_length=100, blank=True)
    lagerort_ist = models.ForeignKey(Lagerort, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                                     verbose_name=_("Lagerort (Ist)"),
                                     help_text=_("Bei der Zählung tatsächlich vorgefundener Lagerort, falls abweichend."))
    ergebnis = models.CharField(_("Ergebnis"), max_length=15, choices=ERGEBNIS, default="offen")
    notiz = models.CharField(_("Notiz"), max_length=200, blank=True)

    AUDIT = False

    class Meta:
        verbose_name = _("Inventurposition")
        verbose_name_plural = _("Inventurpositionen")
        ordering = ["inventarnummer"]

    def __str__(self):
        return f"{self.inventarnummer} {self.bezeichnung}"
