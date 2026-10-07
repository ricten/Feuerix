from django import forms

from apps.core import matrix as mx
from apps.core.forms import TenantModelForm

from .models import Mitglied


class MitgliedForm(TenantModelForm):
    """Tags (Zugriffsrechte) als Haken statt als Mehrfach-Auswahlliste; bei den sechs DSO-Funktionen (die laut
    Datenschutzordnung nur je eine Person haben sollen) steht direkt am Haken, wer das Tag schon trägt."""

    class Meta:
        model = Mitglied
        exclude = ("verein",)
        widgets = {"tags": forms.CheckboxSelectMultiple}

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
