from django import forms

from apps.core.forms import TenantModelForm

from .models import OpenSlidesVerbindung


class VerbindungForm(TenantModelForm):
    passwort = forms.CharField(label="Passwort des technischen Benutzers", required=False,
                               widget=forms.PasswordInput(render_value=False),
                               help_text="Leer lassen = gespeichertes Passwort behalten. Wird verschlüsselt gespeichert.")

    class Meta:
        model = OpenSlidesVerbindung
        exclude = ("verein",)

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._alt = self.instance.passwort
        self.stilisieren()

    def save(self, commit=True):
        self.instance.passwort = self.cleaned_data.get("passwort") or self._alt
        return super().save(commit)
