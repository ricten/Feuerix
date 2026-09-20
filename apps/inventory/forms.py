from apps.core.forms import TenantModelForm

from .models import Verleih


class VerleihForm(TenantModelForm):
    """Status wird ausschließlich über die Aktionen (Ausgeben, Rückgabe, Storno) geändert."""

    class Meta:
        model = Verleih
        exclude = ("verein", "status")
