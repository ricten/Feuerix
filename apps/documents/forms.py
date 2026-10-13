import json

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.core.anbindungen import Anbindungen
from apps.core.forms import TenantModelForm

from . import richtext
from .models import Ablagedokument, Schriftstueck, Serienbrief, Vorlage
from .platzhalter import OPENSLIDES_PLATZHALTER, PLATZHALTER
from django.utils.translation import gettext


class _TextMixin:
    """Textfeld als formatierter Text (TinyMCE, siehe richtext.py): Platzhalterliste fuer den Editor, alte Klartexte werden
    beim Bearbeiten in HTML gewandelt, beim Speichern wird das HTML bereinigt."""
    use_required_attribute = False      # das echte Feld ist im Editor versteckt - Pflicht prueft der Server
    mit_editor = False

    def textfeld(self):
        if "text" not in self.fields:
            return
        gruppen = PLATZHALTER
        verein = getattr(self, "verein", None)
        if verein is None or not Anbindungen(verein).openslides:    # OpenSlides-Platzhalter nur mit Anbindung anbieten
            gruppen = [(t, [e for e in es if e[0] not in OPENSLIDES_PLATZHALTER])
                       for t, es in PLATZHALTER if not t.startswith("OpenSlides")]
        self.fields["text"].widget = forms.Textarea(attrs={
            "rows": 22, "class": "tinymce-editor", "data-platzhalter": json.dumps(gruppen, ensure_ascii=False)})
        self.mit_editor = True
        if not self.is_bound and self.instance is not None and self.instance.pk and self.instance.text \
                and not richtext.ist_html(self.instance.text):
            self.initial["text"] = richtext.aus_text(self.instance.text)

    def clean_text(self):
        t = self.cleaned_data.get("text") or ""
        h = richtext.als_html(t) if t.strip() else ""
        return "" if richtext.ist_leer(h) else h


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
            self.add_error("text", gettext("Bitte einen Text eingeben oder eine Vorlage wählen."))
        return d


class SchriftstueckForm(VorlageFuellen, TenantModelForm):
    class Meta:
        model = Schriftstueck
        exclude = ("verein",)

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.textfeld()
        if "empfaenger_anschrift" in self.fields:
            self.fields["empfaenger_anschrift"].widget = forms.Textarea(attrs={
                "rows": 4, "class": "form-control", "placeholder": "Max Mustermann\nMusterstraße 1\n12345 Musterstadt"})
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

    ABSCHNITTE = [
        (None, ("name", "art", "betreff", "text", "ist_standard", "aktiv", "hinweis")),
        (_("Layout: Briefkopf und Seite"), ("layout_kopf", "layout_logo_position", "layout_absenderzeile",
                                            "layout_datum_position", "layout_fuss")),
        (_("Layout: Schrift und Ränder"), ("layout_schriftart", "layout_schriftgroesse", "layout_rand_links",
                                           "layout_rand_rechts", "layout_rand_oben", "layout_rand_unten")),
    ]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.textfeld()

    def abschnitte(self):
        """Felder in Karten gegliedert (siehe formular.html); nicht aufgefuehrte Felder landen im ersten Abschnitt."""
        verteilt = {n for _t, namen in self.ABSCHNITTE for n in namen}
        rest = [self[n] for n in self.fields if n not in verteilt]
        ergebnis = []
        for i, (titel, namen) in enumerate(self.ABSCHNITTE):
            felder = [self[n] for n in namen if n in self.fields] + (rest if i == 0 else [])
            if felder:
                ergebnis.append({"titel": titel, "felder": felder})
        return ergebnis


class AblageForm(TenantModelForm):
    class Meta:
        model = Ablagedokument
        exclude = ("verein",)

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        if self.instance.pk:  # Dateien werden nie überschrieben - neue Version = neu hochladen
            self.fields["datei"].disabled = True
            self.fields["datei"].required = False
