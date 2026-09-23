from decimal import Decimal

from apps.core.forms import TenantModelForm

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
