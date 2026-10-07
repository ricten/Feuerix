from django import forms

from apps.core import matrix as mx
from apps.core.forms import RechteFelderMixin, TenantModelForm
from apps.core.models import Rolle

from .models import Mitglied, MitgliedTag


class MitgliedForm(TenantModelForm):
    """Tags (Zugriffsrechte) als Haken statt als Mehrfach-Auswahlliste; bei den sechs DSO-Funktionen (die laut
    Datenschutzordnung nur je eine Person haben sollen) steht direkt am Haken, wer das Tag schon trägt."""

    class Meta:
        model = Mitglied
        exclude = ("verein",)
        widgets = {"tags": forms.CheckboxSelectMultiple, "abteilungen": forms.CheckboxSelectMultiple}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        if "tags" in self.fields:
            self.fields["tags"].label_from_instance = self._tag_label

    def _tag_label(self, tag):
        if tag.name in mx.OHNE_BESETZUNGSPFLICHT or not tag.rolle_id:
            return tag.name
        traeger = Mitglied.objects.filter(verein_id=tag.verein_id, status="aktiv", tags=tag)
        if self.instance.pk:
            traeger = traeger.exclude(pk=self.instance.pk)
        namen = [m.name for m in traeger]
        return f"{tag.name} (bereits vergeben an: {', '.join(namen)})" if namen else tag.name


class MitgliedTagForm(RechteFelderMixin, TenantModelForm):
    """Ein Tag kann beim Anlegen (und später) wahlweise eigene Software-Rechte bekommen (dafür wird im
    Hintergrund eine Rolle mit gleichem Namen angelegt bzw. aktualisiert) oder rein organisatorisch bleiben
    (z. B. Beisitzer: ohne weitere Rechte)."""
    rechte_vorhanden = forms.BooleanField(
        label="Hat eigene Rechte in dieser Software", required=False,
        help_text="Ohne Haken ist das Tag eine reine Kennzeichnung ohne Software-Rechte (z. B. Beisitzer). Die "
                  "Rechte unten (je Modul) wirken nur, wenn dieser Haken gesetzt ist.")

    class Meta:
        model = MitgliedTag
        exclude = ("verein", "rolle")

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        hat_rechte = bool(self.instance.rolle_id)
        self.fields["rechte_vorhanden"].initial = hat_rechte
        self.rechte_felder(set(self.instance.rolle.rechte or []) if hat_rechte else set())

    def clean(self):
        cleaned = super().clean()
        name = cleaned.get("name")
        if name and cleaned.get("rechte_vorhanden"):
            konflikt = Rolle.objects.filter(verein=self.verein, name=name).exclude(pk=self.instance.rolle_id or 0)
            if konflikt.exists():
                self.add_error("name", f"Es gibt bereits eine Rolle „{name}“ - bitte einen anderen Namen wählen "
                                       "oder das vorhandene Tag dafür bearbeiten.")
        return cleaned

    def save(self, commit=True):
        tag = super().save(commit=False)
        if self.cleaned_data.get("rechte_vorhanden"):
            rechte = self.gesammelte_rechte()
            if tag.rolle_id:
                rolle = tag.rolle
                rolle.rechte, rolle.matrix = rechte, {}
                rolle.save(update_fields=["rechte", "matrix"])
            else:
                tag.rolle = Rolle.objects.create(verein=self.verein, name=tag.name, rechte=rechte, matrix={})
        else:
            tag.rolle = None
        if commit:
            tag.save()
        return tag
