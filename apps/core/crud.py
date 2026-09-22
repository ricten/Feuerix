"""Generische, mandantensichere CRUD-Views (Liste, Detail, Anlegen, Bearbeiten, Loeschen, Export)."""
import csv
import io
import os
import re
from datetime import date, datetime
from decimal import Decimal
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import FieldDoesNotExist, PermissionDenied
from django.db.models import ProtectedError, Q, RestrictedError
from django.db.models.fields.files import FieldFile
from django.forms import modelform_factory
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from . import audit
from .forms import TenantModelForm
from .util import geld

REGISTRY = {}  # Modell -> Rechte-Modul (fuer den geschuetzten Dateizugriff)


# ---------------------------------------------------------------- Darstellung
def wert(obj, name):
    try:
        feld = obj._meta.get_field(name)
    except FieldDoesNotExist:
        feld = None
    v = getattr(obj, name)
    if feld is not None and feld.many_to_many:
        return ", ".join(map(str, v.all())) or "–"
    if callable(v):
        v = v()
    if isinstance(v, FieldFile):
        return os.path.basename(v.name) if v else "–"
    if v is None or v == "":
        return "–"
    if feld is not None and getattr(feld, "choices", None):
        return getattr(obj, f"get_{name}_display")()
    if isinstance(v, bool):
        return "✓" if v else "✗"
    if isinstance(v, Decimal):
        return geld(v)
    if isinstance(v, datetime):
        return (timezone.localtime(v) if timezone.is_aware(v) else v).strftime("%d.%m.%Y %H:%M")
    if isinstance(v, date):
        return v.strftime("%d.%m.%Y")
    return str(v)


def _sortierbar(model, feldname):
    """Nur echte Modellfelder lassen sich per order_by() sortieren - "__str__" und berechnete Eigenschaften
    (z. B. eine Methode/Property in list_display) nicht."""
    if feldname == "__str__":
        return False
    try:
        model._meta.get_field(feldname)
        return True
    except FieldDoesNotExist:
        return False


def spalten_def(model, liste):
    out = []
    for s in liste:
        if isinstance(s, tuple):
            out.append(s)
            continue
        try:
            out.append((s, str(model._meta.get_field(s).verbose_name)))
        except FieldDoesNotExist:
            out.append((s, s.replace("_", " ").capitalize()))
    return out


def knopf(label, url, post=False, stil="outline-secondary", bestaetigung=None, felder=None):
    return {"label": label, "url": url, "post": post, "stil": stil, "bestaetigung": bestaetigung,
            "felder": felder or {}}


def abschnitt(request, titel, qs, spalten, add_name=None, add_params=None, max_zeilen=50):
    """Tabelle mit Unterobjekten fuer Detailseiten."""
    model = qs.model
    name = model._meta.model_name
    cols = spalten_def(model, spalten)
    modul = REGISTRY.get(model)
    zeilen = []
    for o in qs[:max_zeilen]:
        zeilen.append({"url": reverse(f"{name}_detail", args=[o.pk]), "zellen": [wert(o, c) for c, _ in cols]})
    add_url = None
    if add_name and modul and request.rechte.darf(modul, "add"):
        add_url = reverse(add_name) + "?" + urlencode({**(add_params or {}), "next": request.get_full_path()})
    return {"titel": titel, "spalten": [l for _, l in cols], "zeilen": zeilen, "add_url": add_url}


def _sicher(s):
    s = str(s)
    if s and s[0] in "=+-@" and not re.match(r"^-?\d[\d.,]*( €)?$", s):
        return "'" + s
    return s


# ---------------------------------------------------------------- Basis
class Cfg:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class MandantMixin(LoginRequiredMixin):
    cfg = None
    aktion = "view"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            if request.verein is None:
                return redirect("verein_waehlen")
            if not request.rechte.darf(self.cfg.modul, self.aktion):
                raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return self.cfg.model.objects.filter(verein=self.request.verein)

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        ctx.update(cfg=self.cfg, liste_url=reverse(f"{self.cfg.name}_list"))
        return ctx


class ListeView(MandantMixin, ListView):
    template_name = "core/liste.html"

    @property
    def paginate_by(self):
        return self.cfg.paginate

    def get_queryset(self):
        cfg, req = self.cfg, self.request
        qs = super().get_queryset()
        if cfg.select_related:
            qs = qs.select_related(*cfg.select_related)
        q = req.GET.get("q", "").strip()
        if q and cfg.suche:
            cond = Q()
            for f in cfg.suche:
                cond |= Q(**{f"{f}__icontains": q})
            qs = qs.filter(cond)
        for f in cfg.filter:
            v = req.GET.get(f)
            if v:
                try:
                    qs = qs.filter(**{f: v})
                    list(qs[:0])
                except (ValueError, TypeError, Exception):
                    return qs.none()
        sortierung = req.GET.get("sort", "")
        erlaubt = {c for c, _ in spalten_def(cfg.model, cfg.list_display) if _sortierbar(cfg.model, c)}
        if sortierung.lstrip("-") in erlaubt:
            return qs.order_by(sortierung)
        return qs.order_by(*cfg.ordering) if cfg.ordering else qs

    def get(self, request, *args, **kwargs):
        fmt = request.GET.get("export")
        if fmt in ("csv", "xlsx"):
            return self.exportieren(fmt)
        return super().get(request, *args, **kwargs)

    def exportieren(self, fmt):
        cols = spalten_def(self.cfg.model, self.cfg.list_display)
        kopf = [l for _, l in cols]
        zeilen = [[_sicher(wert(o, c)) for c, _ in cols] for o in self.get_queryset()]
        dateiname = f"{self.cfg.name}-{date.today():%Y%m%d}"
        if fmt == "csv":
            out = io.StringIO()
            w = csv.writer(out, delimiter=";")
            w.writerow(kopf)
            w.writerows(zeilen)
            r = HttpResponse("\ufeff" + out.getvalue(), content_type="text/csv; charset=utf-8")
            r["Content-Disposition"] = f'attachment; filename="{dateiname}.csv"'
            return r
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(kopf)
        for z in zeilen:
            ws.append(z)
        buf = io.BytesIO()
        wb.save(buf)
        r = HttpResponse(buf.getvalue(),
                         content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        r["Content-Disposition"] = f'attachment; filename="{dateiname}.xlsx"'
        return r

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        cfg, req = self.cfg, self.request
        cols = spalten_def(cfg.model, cfg.list_display)
        zeilen = [{
            "url": reverse(f"{cfg.name}_detail", args=[o.pk]) if cfg.detail else None,
            "zellen": [wert(o, c) for c, _ in cols],
        } for o in ctx["object_list"]]
        filterfelder = []
        for f in cfg.filter:
            try:
                feld = cfg.model._meta.get_field(f)
            except FieldDoesNotExist:
                feld = None
            if feld is not None and getattr(feld, "choices", None):
                filterfelder.append({"name": f, "label": str(feld.verbose_name), "wert": req.GET.get(f, ""),
                                     "optionen": list(feld.choices), "select": True})
            elif req.GET.get(f):
                filterfelder.append({"name": f, "wert": req.GET.get(f), "select": False})
        params = req.GET.copy()
        params.pop("page", None)
        params.pop("export", None)
        aktuell = req.GET.get("sort", "")
        aktuelles_feld = aktuell.lstrip("-")
        aktuelle_richtung = "ab" if aktuell.startswith("-") else "auf"
        sort_basis = params.copy()
        sort_basis.pop("sort", None)
        sort_basis_qs = sort_basis.urlencode()
        spalten = []
        for feld, label in cols:
            if _sortierbar(cfg.model, feld):
                ist_aktuell = feld == aktuelles_feld
                naechstes = f"-{feld}" if (ist_aktuell and aktuelle_richtung == "auf") else feld
                spalten.append({"label": label, "aktiv": ist_aktuell,
                                "richtung": aktuelle_richtung if ist_aktuell else None,
                                "sort_url": f"?{sort_basis_qs}&sort={naechstes}" if sort_basis_qs
                                else f"?sort={naechstes}"})
            else:
                spalten.append({"label": label, "aktiv": False, "richtung": None, "sort_url": None})
        ctx.update(
            spalten=spalten, zeilen=zeilen, q=req.GET.get("q", ""), filterfelder=filterfelder,
            can_add=cfg.add and req.rechte.darf(cfg.modul, "add"),
            add_url=reverse(f"{cfg.name}_add") if cfg.add else None,
            qs_ohne_seite=params.urlencode(), export_qs=params.urlencode(),
            aktionen=cfg.listen_aktionen(req) if cfg.listen_aktionen else [],
        )
        return ctx


class DetailAnsicht(MandantMixin, DetailView):
    def get_template_names(self):
        return ["core/detail.html"]

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        cfg, req, o = self.cfg, self.request, self.object
        felder = []
        for f in list(o._meta.concrete_fields) + list(o._meta.many_to_many):
            if f.name in ("id", "verein", "erstellt", "geaendert") or f.name in cfg.detail_ausblenden:
                continue
            eintrag = {"label": str(f.verbose_name), "wert": wert(o, f.name), "url": None}
            if f.get_internal_type() in ("FileField", "ImageField") and getattr(o, f.name):
                eintrag["url"] = reverse("datei", args=[o._meta.app_label, o._meta.model_name, o.pk, f.name])
            felder.append(eintrag)
        extra = cfg.kontext(req, o) if cfg.kontext else {}
        ctx.update(
            felder=felder, cfg=cfg, titel=str(o),
            can_change=cfg.edit and req.rechte.darf(cfg.modul, "change") and (not cfg.bearbeitbar or cfg.bearbeitbar(o)),
            can_delete=cfg.delete and req.rechte.darf(cfg.modul, "delete") and (not cfg.loeschbar or cfg.loeschbar(o)),
            aktionen=[], abschnitte=[], hinweise=[],
        )
        ctx.update(extra)
        return ctx


class FormularMixin(MandantMixin):
    template_name = "core/formular.html"
    neu = True

    def get_form_class(self):
        return self.cfg.form

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["verein"] = self.request.verein
        return kw

    def _next(self):
        nxt = self.request.POST.get("next") or self.request.GET.get("next")
        if nxt and url_has_allowed_host_and_scheme(nxt, {self.request.get_host()}, self.request.is_secure()):
            return nxt
        return None

    def get_success_url(self):
        return self._next() or (
            reverse(f"{self.cfg.name}_detail", args=[self.object.pk]) if self.cfg.detail
            else reverse(f"{self.cfg.name}_list"))

    def form_valid(self, form):
        audit.kontext_setzen(grund=form.cleaned_data.get("aenderungsgrund"))
        form.instance.verein = self.request.verein
        response = super().form_valid(form)
        if self.cfg.nach_speichern:
            self.cfg.nach_speichern(self.request, self.object, self.neu)
        messages.success(self.request, f"{self.cfg.label} gespeichert.")
        return response

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        ctx.update(titel=(f"{self.cfg.label} anlegen" if self.neu else f"{self.cfg.label} bearbeiten"),
                   next=self._next() or "", abbrechen_url=self._next() or reverse(f"{self.cfg.name}_list"))
        return ctx


class ErstellenView(FormularMixin, CreateView):
    aktion = "add"

    def get_initial(self):
        ini = super().get_initial().copy()
        ini.update({k: v for k, v in self.request.GET.items() if k != "next"})
        return ini


class AendernView(FormularMixin, UpdateView):
    aktion = "change"
    neu = False

    def get_object(self, queryset=None):
        o = super().get_object(queryset)
        if self.cfg.bearbeitbar and not self.cfg.bearbeitbar(o):
            raise PermissionDenied("Dieser Datensatz ist nicht mehr änderbar.")
        return o


class LoeschenView(MandantMixin, DeleteView):
    aktion = "delete"
    template_name = "core/loeschen.html"

    def get_object(self, queryset=None):
        o = super().get_object(queryset)
        if self.cfg.loeschbar and not self.cfg.loeschbar(o):
            raise PermissionDenied("Dieser Datensatz kann nicht gelöscht werden.")
        return o

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        ctx["titel"] = f"{self.cfg.label} löschen"
        return ctx

    def form_valid(self, form):
        try:
            self.object.delete()
        except (ProtectedError, RestrictedError):
            messages.error(self.request, "Löschen nicht möglich: Der Datensatz wird noch von anderen Daten verwendet.")
            return redirect(reverse(f"{self.cfg.name}_list"))
        messages.success(self.request, f"{self.cfg.label} gelöscht.")
        return redirect(reverse(f"{self.cfg.name}_list"))


def crud(prefix, model, modul, *, form=None, list_display=None, suche=(), filter=(), ordering=None,
         select_related=(), add=True, edit=True, delete=True, detail=True, kontext=None, nach_speichern=None,
         bearbeitbar=None, loeschbar=None, label=None, detail_ausblenden=(), paginate=50, listen_aktionen=None):
    """Erzeugt die URL-Patterns fuer ein Modell. URL-Namen: <modell>_list/_add/_detail/_edit/_delete."""
    name = model._meta.model_name
    REGISTRY[model] = modul
    if form is None and (add or edit):
        form = modelform_factory(model, form=TenantModelForm, exclude=("verein",))
    cfg = Cfg(model=model, name=name, modul=modul, form=form, list_display=list_display or ("__str__",),
              suche=suche, filter=filter, ordering=ordering, select_related=select_related, add=add, edit=edit,
              delete=delete, detail=detail, kontext=kontext, nach_speichern=nach_speichern, bearbeitbar=bearbeitbar,
              loeschbar=loeschbar, label=label or str(model._meta.verbose_name),
              label_plural=str(model._meta.verbose_name_plural), detail_ausblenden=detail_ausblenden,
              paginate=paginate, listen_aktionen=listen_aktionen)
    if cfg.list_display == ("__str__",):
        cfg.list_display = (("__str__", cfg.label),)
    urls = [path(f"{prefix}/", ListeView.as_view(cfg=cfg), name=f"{name}_list")]
    if add:
        urls.append(path(f"{prefix}/neu/", ErstellenView.as_view(cfg=cfg), name=f"{name}_add"))
    if detail:
        urls.append(path(f"{prefix}/<int:pk>/", DetailAnsicht.as_view(cfg=cfg), name=f"{name}_detail"))
    if edit:
        urls.append(path(f"{prefix}/<int:pk>/bearbeiten/", AendernView.as_view(cfg=cfg), name=f"{name}_edit"))
    if delete:
        urls.append(path(f"{prefix}/<int:pk>/loeschen/", LoeschenView.as_view(cfg=cfg), name=f"{name}_delete"))
    return urls
