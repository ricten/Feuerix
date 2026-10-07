from django import forms

from apps.core.forms import TenantModelForm

from .models import Mitglied


class MitgliedForm(TenantModelForm):
    """Nur fuer die Mehrfachauswahl der Tags (Zugriffsrechte) als Haken statt als Mehrfach-Auswahlliste."""

    class Meta:
        model = Mitglied
        exclude = ("verein",)
        widgets = {"tags": forms.CheckboxSelectMultiple}
