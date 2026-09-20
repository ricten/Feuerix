from apps.core.forms import TenantModelForm

from .models import Rechnung


class RechnungForm(TenantModelForm):
    """Manuelle Rechnungen: immer als Entwurf; Beitragsrechnungen entstehen über den Rechnungslauf."""

    class Meta:
        model = Rechnung
        exclude = ("verein", "status")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["typ"].choices = [c for c in Rechnung.TYP if c[0] in ("individuell", "sammel")]
        self.fields["empfaenger_name"].help_text = "Leer lassen = aus dem Mitglied übernehmen"
