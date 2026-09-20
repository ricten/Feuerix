from django import forms

from apps.core.forms import TenantModelForm

from .models import Buchung, Buchungskategorie, Kassenbericht


class BuchungForm(TenantModelForm):
    class Meta:
        model = Buchung
        exclude = ("verein",)

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["kategorie"].queryset = self.fields["kategorie"].queryset.filter(aktiv=True)
        self.fields["konto"].queryset = self.fields["konto"].queryset.filter(aktiv=True)
        if self.instance.pk and self.instance.quelle != "manuell":
            # automatisch übernommene Buchungen: Betrag/Datum/Art gehören zur Quelle und bleiben unverändert
            for f in ("datum", "typ", "betrag"):
                self.fields[f].disabled = True


class KassenberichtForm(TenantModelForm):
    class Meta:
        model = Kassenbericht
        exclude = ("verein",)

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["pruefbemerkung"].widget = forms.Textarea(attrs={"rows": 5, "class": "form-control"})
