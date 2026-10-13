from django import forms

from apps.core.forms import TenantModelForm

from .models import PaperlessVerbindung
from django.utils.translation import gettext_lazy


class VerbindungForm(TenantModelForm):
    api_token = forms.CharField(label=gettext_lazy("API-Token"), required=False, widget=forms.PasswordInput(render_value=False),
                                help_text=gettext_lazy("Leer lassen = gespeicherten Token behalten. Wird verschlüsselt gespeichert."))

    admin_passwort = forms.CharField(
        label=gettext_lazy("Administrator-Passwort (nur Anzeige)"), required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text=gettext_lazy("Leer lassen = gespeichertes Passwort behalten. Wird verschlüsselt gespeichert und kann von "
                               "Superadmins nach erneuter Passworteingabe angezeigt werden. Wird nicht für die Anbindung verwendet."))

    class Meta:
        model = PaperlessVerbindung
        exclude = ("verein",)

    # Nur fuer Superadmins sichtbar/aenderbar (siehe views.einstellungen)
    NUR_SUPERADMIN = ("admin_benutzer", "admin_passwort", "passwoerter_abgleichen")

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._alt = self.instance.api_token
        self._alt_admin = self.instance.admin_passwort
        self.stilisieren()

    def save(self, commit=True):
        self.instance.api_token = self.cleaned_data.get("api_token") or self._alt
        self.instance.admin_passwort = self.cleaned_data.get("admin_passwort") or self._alt_admin
        return super().save(commit)
