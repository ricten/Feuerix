from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import Rolle, Verein, Zugang
from .rechte import AKTIONEN, MODULE


class TenantModelForm(forms.ModelForm):
    """Basisformular: Bootstrap-Klassen, Datumsfelder, Auswahllisten nur aus dem aktiven Verein."""
    aenderungsgrund = forms.CharField(label="Grund der Änderung (für das Protokoll)", required=False, max_length=200)

    def __init__(self, *args, verein=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.verein = verein
        if verein is not None and hasattr(self.instance, "verein_id") and self.instance.verein_id is None:
            self.instance.verein_id = verein.pk
        if not self.instance.pk:
            self.fields.pop("aenderungsgrund", None)
        for f in self.fields.values():
            qs = getattr(f, "queryset", None)
            if qs is not None and verein is not None and hasattr(qs.model, "verein"):
                f.queryset = qs.filter(verein=verein)
        self.stilisieren()

    def stilisieren(self):
        for f in self.fields.values():
            w = f.widget
            if isinstance(f, forms.DateTimeField) and w.attrs.get("type") != "datetime-local":
                f.widget = w = forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")
                f.input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M"]
            elif isinstance(f, forms.DateField) and w.attrs.get("type") != "date":
                f.widget = w = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
                f.input_formats = ["%Y-%m-%d", "%d.%m.%Y"]
            if isinstance(w, (forms.CheckboxInput, forms.CheckboxSelectMultiple, forms.RadioSelect)):
                css = "form-check-input"
            elif isinstance(w, forms.Select):
                css = "form-select"
            else:
                css = "form-control"
            if css not in w.attrs.get("class", ""):
                w.attrs["class"] = (w.attrs.get("class", "") + " " + css).strip()

    def _get_validation_exclusions(self):
        # damit unique_together (verein, ...) trotz ausgeblendetem Vereinsfeld geprueft wird
        ex = set(super()._get_validation_exclusions())
        if getattr(self.instance, "verein_id", None):
            ex.discard("verein")
        return ex


class VereinForm(TenantModelForm):
    class Meta:
        model = Verein
        exclude = ("kuerzel", "aktiv")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["akzentfarbe"].widget = forms.TextInput(attrs={"type": "color",
                                                                   "class": "form-control form-control-color"})


class RechteFelderMixin:
    def rechte_felder(self, vorhanden):
        for m, label in MODULE.items():
            self.fields[f"r_{m}"] = forms.MultipleChoiceField(
                label=label, required=False, choices=list(AKTIONEN.items()),
                widget=forms.CheckboxSelectMultiple,
                initial=[a for a in AKTIONEN if f"{m}.{a}" in vorhanden])
        self.stilisieren()

    def gesammelte_rechte(self):
        return [f"{m}.{a}" for m in MODULE for a in self.cleaned_data.get(f"r_{m}", [])]


class RolleForm(RechteFelderMixin, TenantModelForm):
    class Meta:
        model = Rolle
        fields = ("name", "ist_superadmin")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rechte_felder(set(self.instance.rechte or []))

    def save(self, commit=True):
        self.instance.rechte = self.gesammelte_rechte()
        return super().save(commit)


class ZugangForm(RechteFelderMixin, TenantModelForm):
    username = forms.CharField(label="Benutzername", max_length=150)
    vorname = forms.CharField(label="Vorname", required=False, max_length=150)
    nachname = forms.CharField(label="Nachname", required=False, max_length=150)
    email = forms.EmailField(label="E-Mail", required=False)
    passwort = forms.CharField(label="Passwort (bei neuen Benutzern Pflicht)", required=False,
                               widget=forms.PasswordInput(render_value=False))

    class Meta:
        model = Zugang
        fields = ("rolle", "aktiv")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rechte_felder(set(self.instance.extra_rechte or []))
        if self.instance.pk:
            u = self.instance.user
            self.fields["username"].initial = u.username
            self.fields["username"].disabled = True
            self.fields["vorname"].initial = u.first_name
            self.fields["nachname"].initial = u.last_name
            self.fields["email"].initial = u.email
        self.order_fields(["username", "vorname", "nachname", "email", "passwort", "rolle", "aktiv"])

    def clean(self):
        d = super().clean()
        if self.instance.pk:
            return d
        User = get_user_model()
        u = User.objects.filter(username=d.get("username")).first()
        if u is None and not d.get("passwort"):
            self.add_error("passwort", "Für neue Benutzer ist ein Passwort erforderlich.")
        if u is not None and Zugang.objects.filter(verein=self.verein, user=u).exists():
            self.add_error("username", "Dieser Benutzer hat bereits Zugang zu diesem Verein.")
        if u is None and d.get("passwort"):
            try:
                validate_password(d["passwort"])
            except ValidationError as e:
                self.add_error("passwort", e)
        return d

    def save(self, commit=True):
        d = self.cleaned_data
        User = get_user_model()
        if self.instance.pk:
            user = self.instance.user
            eigenstaendig = Zugang.objects.filter(user=user).count() == 1
            neu = False
        else:
            user, neu = User.objects.get_or_create(username=d["username"])
            eigenstaendig = neu
        # Stammdaten/Passwort nur aendern, wenn der Benutzer ausschliesslich zu diesem Verein gehoert
        if eigenstaendig:
            user.first_name, user.last_name, user.email = d.get("vorname", ""), d.get("nachname", ""), d.get("email", "")
            if d.get("passwort"):
                user.set_password(d["passwort"])
            elif neu:
                user.set_unusable_password()
            user.save()
        self.instance.user = user
        self.instance.extra_rechte = self.gesammelte_rechte()
        return super().save(commit)
