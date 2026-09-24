from decimal import Decimal

from django import forms

from apps.core.forms import TenantModelForm, stilisieren_felder

from .models import Rechnung, Rechnungsposition


class RechnungForm(TenantModelForm):
    """Manuelle Rechnungen: immer als Entwurf; Beitragsrechnungen entstehen über den Rechnungslauf."""

    class Meta:
        model = Rechnung
        exclude = ("verein", "status")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["typ"].choices = [c for c in Rechnung.TYP if c[0] in ("individuell", "sammel")]
        self.fields["empfaenger_name"].help_text = "Leer lassen = aus dem Mitglied übernehmen"


class RechnungspositionForm(TenantModelForm):
    class Meta:
        model = Rechnungsposition
        exclude = ("verein",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk and self.verein and self.verein.umsatzsteuerpflichtig:
            self.fields["steuersatz"].initial = Decimal("19.00")


class FinTSPinForm(forms.Form):
    pin = forms.CharField(label="Bank-PIN", widget=forms.PasswordInput(render_value=False))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        stilisieren_felder(self.fields)


class FinTSTanForm(forms.Form):
    tan = forms.CharField(label="TAN", required=False)

    def __init__(self, *args, decoupled=False, **kwargs):
        super().__init__(*args, **kwargs)
        if decoupled:
            self.fields["tan"].help_text = "Bitte in der Banking-App bestätigen und danach hier weiter klicken."
        else:
            self.fields["tan"].required = True
        stilisieren_felder(self.fields)
