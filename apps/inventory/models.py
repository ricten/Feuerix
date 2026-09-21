import uuid
from datetime import date

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import TenantModel, naechste_nummer
from apps.core.util import upload_pfad


class Kategorie(TenantModel):
    name = models.CharField("Name", max_length=100)

    class Meta:
        verbose_name = "Inventar-Kategorie"
        verbose_name_plural = "Inventar-Kategorien"
        unique_together = [("verein", "name")]
        ordering = ["name"]

    def __str__(self):
        return self.name


class Standort(TenantModel):
    name = models.CharField("Name", max_length=100)
    beschreibung = models.CharField("Beschreibung", max_length=200, blank=True)

    class Meta:
        verbose_name = "Standort"
        verbose_name_plural = "Inventar-Standorte"
        unique_together = [("verein", "name")]
        ordering = ["name"]

    def __str__(self):
        return self.name


class Gegenstand(TenantModel):
    ZUSTAND = [("neu", "Neu"), ("gut", "Gut"), ("gebrauchsspuren", "Gebrauchsspuren"), ("defekt", "Defekt"),
               ("ausgesondert", "Ausgesondert")]
    inventarnummer = models.CharField("Inventarnummer", max_length=20, blank=True,
                                      help_text="Leer lassen = automatisch (INV-000001)")
    bezeichnung = models.CharField("Bezeichnung", max_length=200)
    kategorie = models.ForeignKey(Kategorie, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Kategorie")
    hersteller = models.CharField("Hersteller", max_length=100, blank=True)
    modell = models.CharField("Modell", max_length=100, blank=True)
    seriennummer = models.CharField("Seriennummer", max_length=100, blank=True)
    anschaffungsdatum = models.DateField("Anschaffungsdatum", null=True, blank=True)
    anschaffungspreis = models.DecimalField("Anschaffungspreis (€)", max_digits=10, decimal_places=2, null=True,
                                            blank=True)
    aktueller_wert = models.DecimalField("Aktueller Wert (€)", max_digits=10, decimal_places=2, null=True, blank=True)
    standort = models.ForeignKey(Standort, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Standort")
    verantwortlicher = models.ForeignKey("members.Mitglied", on_delete=models.SET_NULL, null=True, blank=True,
                                         related_name="+", verbose_name="Verantwortlicher")
    zustand = models.CharField("Zustand", max_length=15, choices=ZUSTAND, default="gut")
    garantie_bis = models.DateField("Garantie bis", null=True, blank=True)
    verleihbar = models.BooleanField("Verleihbar", default=False)
    leihgebuehr = models.DecimalField("Leihgebühr (€)", max_digits=8, decimal_places=2, default=0)
    kaution = models.DecimalField("Kaution (€)", max_digits=8, decimal_places=2, default=0)
    foto = models.ImageField("Foto", upload_to=upload_pfad, blank=True)
    dokument = models.FileField("Dokument (Rechnung, Handbuch …)", upload_to=upload_pfad, blank=True)
    notizen = models.TextField("Notizen", blank=True)

    class Meta:
        verbose_name = "Gegenstand"
        verbose_name_plural = "Inventar"
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
    STATUS = [("reserviert", "Reserviert"), ("ausgegeben", "Ausgegeben"), ("zurueckgegeben", "Zurückgegeben"),
              ("storniert", "Storniert")]
    gegenstand = models.ForeignKey(Gegenstand, on_delete=models.PROTECT, related_name="verleihe",
                                   verbose_name="Gegenstand")
    vorgang = models.UUIDField("Vorgang", null=True, blank=True, editable=False,
                              help_text="Gruppiert mehrere gleichzeitig an denselben Entleiher verliehene Gegenstände.")
    entleiher = models.ForeignKey("members.Mitglied", on_delete=models.PROTECT, null=True, blank=True,
                                  related_name="+", verbose_name="Entleiher (Mitglied)")
    entleiher_name = models.CharField("Entleiher (extern)", max_length=150, blank=True)
    entleiher_kontakt = models.CharField("Kontakt (extern)", max_length=200, blank=True)
    veranstaltung = models.ForeignKey("events.Veranstaltung", on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name="verleihe", verbose_name="Für Veranstaltung")
    status = models.CharField("Status", max_length=15, choices=STATUS, default="reserviert")
    von = models.DateField("Von")
    bis = models.DateField("Bis (geplante Rückgabe)")
    zweck = models.CharField("Zweck", max_length=200, blank=True)
    leihgebuehr = models.DecimalField("Leihgebühr (€)", max_digits=8, decimal_places=2, null=True, blank=True)
    kaution = models.DecimalField("Kaution (€)", max_digits=8, decimal_places=2, null=True, blank=True)
    kaution_zurueckgezahlt = models.BooleanField("Kaution zurückgezahlt", default=False)
    ausgegeben_am = models.DateTimeField("Ausgegeben am", null=True, blank=True, editable=False)
    ausgegeben_von = models.CharField("Ausgegeben durch", max_length=150, blank=True, editable=False)
    zustand_bei_ausgabe = models.CharField("Zustand bei Ausgabe", max_length=15, choices=Gegenstand.ZUSTAND,
                                           blank=True, editable=False)
    zurueckgegeben_am = models.DateTimeField("Zurückgegeben am", null=True, blank=True, editable=False)
    zustand_bei_rueckgabe = models.CharField("Zustand bei Rückgabe", max_length=15, choices=Gegenstand.ZUSTAND,
                                             blank=True, editable=False)
    notizen = models.TextField("Notizen", blank=True)

    class Meta:
        verbose_name = "Verleih"
        verbose_name_plural = "Verleih"
        ordering = ["-von", "-id"]

    def __str__(self):
        wer = self.entleiher.name if self.entleiher_id else (self.entleiher_name or "?")
        g = self.gegenstand.inventarnummer if self.gegenstand_id else "?"
        return f"{g} → {wer} ({self.von:%d.%m.%Y})" if self.von else f"{g} → {wer}"

    @property
    def wer(self):
        return self.entleiher.name if self.entleiher_id else self.entleiher_name

    @property
    def ueberfaellig(self):
        return self.status == "ausgegeben" and self.bis < date.today()

    def clean(self):
        if not (self.entleiher_id or self.entleiher_name):
            raise ValidationError("Bitte ein Mitglied oder einen externen Entleiher angeben.")
        if self.von and self.bis and self.bis < self.von:
            raise ValidationError("Das Rückgabedatum liegt vor dem Beginn.")
        if self.gegenstand_id and self.status in AKTIV:
            g = self.gegenstand
            if not g.verleihbar:
                raise ValidationError("Dieser Gegenstand ist nicht als verleihbar markiert.")
            if g.zustand in ("defekt", "ausgesondert"):
                raise ValidationError(f"Gegenstand ist {g.get_zustand_display().lower()} und nicht verleihbar.")
            if self.von and self.bis:
                konflikt = Verleih.objects.filter(gegenstand_id=g.pk, status__in=AKTIV, von__lte=self.bis,
                                                  bis__gte=self.von).exclude(pk=self.pk).first()
                if konflikt:
                    raise ValidationError(f"Im gewählten Zeitraum bereits verplant: {konflikt}.")
            if Verleih.objects.filter(gegenstand_id=g.pk, status="ausgegeben", bis__lt=date.today()).exclude(
                    pk=self.pk).exists():
                raise ValidationError("Der Gegenstand ist überfällig und noch nicht zurückgegeben.")

    def save(self, *args, **kwargs):
        if self._state.adding and self.gegenstand_id:
            if self.kaution is None:
                self.kaution = self.gegenstand.kaution
            if self.leihgebuehr is None:
                self.leihgebuehr = self.gegenstand.leihgebuehr
        super().save(*args, **kwargs)


class Inventur(TenantModel):
    STATUS = [("laufend", "Laufend"), ("abgeschlossen", "Abgeschlossen")]
    name = models.CharField("Bezeichnung", max_length=100)
    jahr = models.PositiveIntegerField("Jahr", default=aktuelles_jahr)
    status = models.CharField("Status", max_length=15, choices=STATUS, default="laufend", editable=False)
    abgeschlossen_am = models.DateField("Abgeschlossen am", null=True, blank=True, editable=False)
    bemerkung = models.TextField("Bemerkung", blank=True)

    class Meta:
        verbose_name = "Inventur"
        verbose_name_plural = "Inventuren"
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
                                 standort_text=str(g.standort) if g.standort_id else "")
                for g in Gegenstand.objects.filter(verein_id=self.verein_id).exclude(zustand="ausgesondert")])

    def zaehlung(self):
        z = {k: 0 for k, _ in Inventurposition.ERGEBNIS}
        for e in self.positionen.values_list("ergebnis", flat=True):
            z[e] += 1
        return z


class Inventurposition(TenantModel):
    ERGEBNIS = [("offen", "Offen"), ("gefunden", "Gefunden"), ("nicht_gefunden", "Nicht gefunden"),
                ("beschaedigt", "Beschädigt")]
    inventur = models.ForeignKey(Inventur, on_delete=models.CASCADE, related_name="positionen", verbose_name="Inventur")
    gegenstand = models.ForeignKey(Gegenstand, on_delete=models.PROTECT, related_name="+", verbose_name="Gegenstand")
    inventarnummer = models.CharField("Inventarnummer", max_length=20)
    bezeichnung = models.CharField("Bezeichnung", max_length=200)
    standort_text = models.CharField("Standort (Soll)", max_length=100, blank=True)
    ergebnis = models.CharField("Ergebnis", max_length=15, choices=ERGEBNIS, default="offen")
    notiz = models.CharField("Notiz", max_length=200, blank=True)

    AUDIT = False

    class Meta:
        verbose_name = "Inventurposition"
        verbose_name_plural = "Inventurpositionen"
        ordering = ["inventarnummer"]

    def __str__(self):
        return f"{self.inventarnummer} {self.bezeichnung}"
