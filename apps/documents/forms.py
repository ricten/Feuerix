from django import forms

from apps.core.forms import TenantModelForm

from .models import Ablagedokument, Schriftstueck, Serienbrief, Vorlage


class _TextMixin:
    def textfeld(self):
        if "text" in self.fields:
            self.fields["text"].widget = forms.Textarea(attrs={"rows": 22, "class": "form-control font-monospace"})


class VorlageFuellen(_TextMixin):
    """Beim Anlegen: Betreff/Text aus der gewählten Vorlage übernehmen (danach frei bearbeitbar)."""

    def clean(self):
        d = super().clean()
        v = d.get("vorlage")
        if v is not None:
            if not d.get("text"):
                d["text"] = v.text
            if not d.get("betreff"):
                d["betreff"] = v.betreff
        if not d.get("text"):
            self.add_error("text", "Bitte einen Text eingeben oder eine Vorlage wählen.")
        return d


class SchriftstueckForm(VorlageFuellen, TenantModelForm):
    class Meta:
        model = Schriftstueck
        exclude = ("verein",)

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.textfeld()
        self.fields["vorlage"].queryset = self.fields["vorlage"].queryset.filter(aktiv=True)


class SerienbriefForm(VorlageFuellen, TenantModelForm):
    class Meta:
        model = Serienbrief
        exclude = ("verein",)

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.textfeld()
        self.fields["vorlage"].queryset = self.fields["vorlage"].queryset.filter(aktiv=True)


class VorlageForm(_TextMixin, TenantModelForm):
    class Meta:
        model = Vorlage
        exclude = ("verein",)

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.textfeld()


class AblageForm(TenantModelForm):
    class Meta:
        model = Ablagedokument
        exclude = ("verein",)

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        if self.instance.pk:  # Dateien werden nie überschrieben - neue Version = neu hochladen
            self.fields["datei"].disabled = True
            self.fields["datei"].required = False
