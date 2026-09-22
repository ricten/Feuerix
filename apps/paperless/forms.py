from django import forms

from apps.core.forms import TenantModelForm

from .models import PaperlessVerbindung


class VerbindungForm(TenantModelForm):
    api_token = forms.CharField(label="API-Token", required=False, widget=forms.PasswordInput(render_value=False),
                                help_text="Leer lassen = gespeicherten Token behalten. Wird verschlüsselt gespeichert.")

    class Meta:
        model = PaperlessVerbindung
        exclude = ("verein",)

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._alt = self.instance.api_token
        self.stilisieren()

    def save(self, commit=True):
        self.instance.api_token = self.cleaned_data.get("api_token") or self._alt
        return super().save(commit)
