from django import forms

from apps.core.forms import TenantModelForm

from .models import OpenSlidesVerbindung
from django.utils.translation import gettext_lazy


class VerbindungForm(TenantModelForm):
    passwort = forms.CharField(label=gettext_lazy("Passwort des technischen Benutzers"), required=False,
                               widget=forms.PasswordInput(render_value=False),
                               help_text=gettext_lazy("Leer lassen = gespeichertes Passwort behalten. Wird verschlüsselt gespeichert."))

    admin_passwort = forms.CharField(
        label=gettext_lazy("Administrator-Passwort (nur Anzeige)"), required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text=gettext_lazy("Leer lassen = gespeichertes Passwort behalten. Wird verschlüsselt gespeichert und kann von "
                               "Superadmins nach erneuter Passworteingabe angezeigt werden. Wird nicht für die Anbindung verwendet."))

    class Meta:
        model = OpenSlidesVerbindung
        exclude = ("verein",)

    # Nur fuer Superadmins sichtbar/aenderbar (siehe views.einstellungen)
    NUR_SUPERADMIN = ("admin_benutzer", "admin_passwort", "passwoerter_abgleichen")

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._alt = self.instance.passwort
        self._alt_admin = self.instance.admin_passwort
        self.stilisieren()

    def save(self, commit=True):
        self.instance.passwort = self.cleaned_data.get("passwort") or self._alt
        self.instance.admin_passwort = self.cleaned_data.get("admin_passwort") or self._alt_admin
        return super().save(commit)
