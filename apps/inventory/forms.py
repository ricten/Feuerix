from django import forms

from apps.core.forms import TenantModelForm, stilisieren_felder
from apps.events.models import Veranstaltung
from apps.members.models import Mitglied

from .models import Gegenstand, Verleih


class VerleihForm(TenantModelForm):
    """Status wird ausschließlich über die Aktionen (Ausgeben, Rückgabe, Storno) geändert."""

    class Meta:
        model = Verleih
        exclude = ("verein", "status")


class SammelverleihForm(forms.Form):
    """Mehrere Gegenstände in einem Vorgang an denselben Entleiher verleihen (statt Verleih für Verleih einzeln)."""
    gegenstaende = forms.ModelMultipleChoiceField(queryset=Gegenstand.objects.none(), label="Gegenstände",
                                                  widget=forms.CheckboxSelectMultiple)
    entleiher = forms.ModelChoiceField(queryset=Mitglied.objects.none(), required=False, label="Entleiher (Mitglied)")
    entleiher_name = forms.CharField(required=False, max_length=150, label="Entleiher (extern)")
    entleiher_kontakt = forms.CharField(required=False, max_length=200, label="Kontakt (extern)")
    veranstaltung = forms.ModelChoiceField(queryset=Veranstaltung.objects.none(), required=False,
                                           label="Für Veranstaltung")
    von = forms.DateField(label="Von", widget=forms.DateInput(attrs={"type": "date"}))
    bis = forms.DateField(label="Bis (geplante Rückgabe)", widget=forms.DateInput(attrs={"type": "date"}))
    zweck = forms.CharField(required=False, max_length=200, label="Zweck")
    notizen = forms.CharField(required=False, widget=forms.Textarea, label="Notizen")

    def __init__(self, *args, verein=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["gegenstaende"].queryset = Gegenstand.objects.filter(
            verein=verein, verleihbar=True).exclude(zustand__in=("defekt", "ausgesondert")).order_by("bezeichnung")
        self.fields["entleiher"].queryset = Mitglied.objects.filter(verein=verein, status="aktiv").order_by(
            "nachname", "vorname")
        self.fields["veranstaltung"].queryset = Veranstaltung.objects.filter(verein=verein).order_by("-beginn")
        stilisieren_felder(self.fields)

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("entleiher") and not cleaned.get("entleiher_name"):
            raise forms.ValidationError("Bitte ein Mitglied oder einen externen Entleiher angeben.")
        if cleaned.get("von") and cleaned.get("bis") and cleaned["bis"] < cleaned["von"]:
            raise forms.ValidationError("Das Rückgabedatum liegt vor dem Beginn.")
        if not cleaned.get("gegenstaende"):
            raise forms.ValidationError("Bitte mindestens einen Gegenstand auswählen.")
        return cleaned
