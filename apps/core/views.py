import json
import os
from collections import Counter, defaultdict
from datetime import date, timedelta

from django.apps import apps as django_apps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Sum
from django.http import FileResponse, Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import audit
from .crud import REGISTRY, wert
from .forms import VereinForm
from .models import DashboardEinstellung, Verein, Zugang
from .util import geld

DASHBOARD_KACHELN = ("kennzahlen", "veranstaltungen", "aufgaben", "verleihe")


def _vorbereiten(request):
    if request.verein is None:
        return redirect("verein_waehlen")
    return None


@login_required
def nach_login(request):
    """Leitet Mitarbeiter (mit Zugang) zum Dashboard, Mitglieder mit Selbstdienst-Konto zu 'Meine Daten'."""
    if request.user.is_superuser or Zugang.objects.filter(user=request.user, aktiv=True).exists():
        return redirect("dashboard")
    if hasattr(request.user, "mitglied_zugang"):
        return redirect("mein_konto")
    return redirect("dashboard")


@login_required
def verein_waehlen(request):
    if request.method == "POST":
        pk = request.POST.get("verein")
        if any(str(v.pk) == pk for v in request.vereine):
            request.session["verein_id"] = int(pk)
        return redirect("dashboard")
    return render(request, "core/verein_waehlen.html")


@login_required
def dashboard(request):
    if (r := _vorbereiten(request)):
        return r
    from apps.allowances.models import Aufwandsentschaedigung
    from apps.events.models import Aufgabe, Veranstaltung
    from apps.finance.models import Rechnung, wirksame_summe
    from apps.honors.models import Ehrung
    from apps.honors.services import jubilare
    from apps.inventory.models import Verleih
    from apps.members.models import Mitglied

    v, heute = request.verein, date.today()
    jahr = heute.year
    # Höchstens alle 6 Stunden im Hintergrund prüfen, ob Aufgaben überfällig geworden sind und dafür
    # benachrichtigen - wie der Update-Check (apps.core.context.version) bewusst beim nächsten Seitenaufruf
    # statt über einen eigenen Cron/Celery-Beat, um keine zusätzliche Infrastruktur zu brauchen.
    if v.aufgaben_geprueft_am is None or timezone.now() - v.aufgaben_geprueft_am > timedelta(hours=6):
        from apps.events.tasks import aufgaben_faellig_benachrichtigen_task
        aufgaben_faellig_benachrichtigen_task.delay(v.pk)
        v.aufgaben_geprueft_am = timezone.now()
        v.save(update_fields=["aufgaben_geprueft_am"])
    # Zuständig kann ein Mitglied oder ein Administrator (Benutzer mit Zugang, z. B. ohne eigene
    # Mitgliedschaft) sein - beide Faelle hier beruecksichtigen.
    mitglied = getattr(request.user, "mitglied_zugang", None)
    zustaendigkeit = Q(zustaendig_benutzer=request.user) | Q(zustaendig=mitglied) if mitglied else \
        Q(zustaendig_benutzer=request.user)
    alle_meine_aufgaben = list(Aufgabe.objects.filter(verein=v).filter(zustaendigkeit)
                              .exclude(status="erledigt").select_related("veranstaltung", "zustaendig",
                                                                         "zustaendig_benutzer").order_by("faellig"))
    meine_aufgaben = alle_meine_aufgaben[:8]
    # Die Kachel soll nicht schon wegen einer einzelnen knapp fälligen Aufgabe grell werden - erst ab zwei
    # Aufgaben in derselben Dringlichkeitsstufe schlägt die Kachelfarbe insgesamt dorthin um.
    stufen = Counter(a.faelligkeits_stufe for a in alle_meine_aufgaben if a.faelligkeits_stufe)
    if stufen.get("rot", 0) >= 2:
        meine_aufgaben_farbe = "rot"
    elif stufen.get("gelb", 0) >= 2:
        meine_aufgaben_farbe = "gelb"
    else:
        meine_aufgaben_farbe = "gruen"
    anstehende_verleihe = sorted(
        Verleih.objects.filter(verein=v, status__in=["reserviert", "ausgegeben"])
        .select_related("gegenstand", "entleiher", "veranstaltung"),
        key=lambda x: x.relevantes_datum or date.max)[:8]
    # Persoenliche Kachel-Reihenfolge/-Sichtbarkeit (Drag & Drop bzw. Ein-/Ausblenden auf der Startseite) -
    # unbekannte/entfernte Kacheln werden stillschweigend ignoriert, neue haengen sich hinten an.
    einst = getattr(request.user, "dashboard_einstellung", None)
    gespeicherte_reihenfolge = [k for k in (einst.kacheln_reihenfolge if einst else []) if k in DASHBOARD_KACHELN]
    kacheln_ausgeblendet = set((einst.kacheln_ausgeblendet if einst else [])) & set(DASHBOARD_KACHELN)
    kachel_reihenfolge = gespeicherte_reihenfolge + [k for k in DASHBOARD_KACHELN if k not in gespeicherte_reihenfolge]
    kachel_order = {k: i for i, k in enumerate(kachel_reihenfolge)}
    mitglieder = Mitglied.objects.filter(verein=v)
    aktive = mitglieder.filter(status="aktiv")
    grenze18 = date(heute.year - 18, heute.month, heute.day) if not (heute.month == 2 and heute.day == 29) \
        else date(heute.year - 18, 2, 28)
    beitraege = Rechnung.objects.filter(verein=v, typ="beitrag", jahr=jahr).exclude(status__in=["storniert", "entwurf"])
    soll = beitraege.aggregate(s=Sum("betrag"))["s"] or 0
    ist = wirksame_summe(beitraege)
    ctx = {
        "kennzahlen": [
            ("Mitglieder gesamt", mitglieder.exclude(status__in=["ausgetreten", "verstorben"]).count()),
            ("davon aktiv", aktive.count()),
            ("Jugendliche (unter 18)", aktive.filter(geburtsdatum__gt=grenze18).count()),
        ],
        "finanzen": [
            (f"Beiträge {jahr} (Soll)", geld(soll)),
            ("Bezahlt", geld(ist)),
            ("Offen", geld(soll - ist)),
            ("Offene Rechnungen", Rechnung.objects.filter(verein=v, status__in=["offen", "teilbezahlt"]).count()),
        ],
        "jubilaeen": len(jubilare(v, jahr)),
        "ehrungen": Ehrung.objects.filter(verein=v, datum__year=jahr).count(),
        "ueberfaellig": Verleih.objects.filter(verein=v, status="ausgegeben", bis__lt=heute).count(),
        "kommende": Veranstaltung.objects.filter(verein=v, beginn__date__gte=heute).exclude(status="abgesagt")
        .order_by("beginn")[:5],
        "offene_aufgaben": Aufgabe.objects.filter(verein=v).exclude(status="erledigt").count(),
        "aufwand_offen": Aufwandsentschaedigung.objects.filter(verein=v, status="beantragt").count(),
        "meine_aufgaben": meine_aufgaben,
        "meine_aufgaben_farbe": meine_aufgaben_farbe,
        "anstehende_verleihe": anstehende_verleihe,
        "kachel_order": kachel_order,
        "kacheln_ausgeblendet": kacheln_ausgeblendet,
        "jahr": jahr,
    }
    return render(request, "core/dashboard.html", ctx)


@login_required
@require_POST
def dashboard_kacheln_speichern(request):
    """Speichert die per Drag & Drop bzw. Ein-/Ausblenden geänderte Kachel-Reihenfolge/-Sichtbarkeit auf der
    Startseite - pro Benutzerkonto, unabhängig vom gerade gewählten Verein."""
    try:
        daten = json.loads(request.body)
    except (ValueError, TypeError):
        return HttpResponseBadRequest()
    reihenfolge = [k for k in daten.get("reihenfolge", []) if k in DASHBOARD_KACHELN]
    ausgeblendet = [k for k in daten.get("ausgeblendet", []) if k in DASHBOARD_KACHELN]
    DashboardEinstellung.objects.update_or_create(
        user=request.user, defaults={"kacheln_reihenfolge": reihenfolge, "kacheln_ausgeblendet": ausgeblendet})
    return JsonResponse({"ok": True})


@login_required
def datei(request, app_label, modell, pk, feld):
    """Geschuetzter Dateizugriff: Login + Mandant + Recht."""
    if request.verein is None:
        raise Http404
    try:
        Model = django_apps.get_model(app_label, modell)
    except LookupError:
        raise Http404
    modul = REGISTRY.get(Model)
    if modul is None:
        raise Http404
    if not request.rechte.darf(modul, "view"):
        raise PermissionDenied
    obj = get_object_or_404(Model, pk=pk, verein=request.verein)
    try:
        f = Model._meta.get_field(feld)
    except Exception:
        raise Http404
    if f.get_internal_type() not in ("FileField", "ImageField"):
        raise Http404
    fdatei = getattr(obj, feld)
    if not fdatei:
        raise Http404
    return FileResponse(fdatei.open("rb"), as_attachment=(feld != "foto"), filename=os.path.basename(fdatei.name))


@login_required
def verein_logo(request):
    verein = request.verein
    if verein is None:
        m = getattr(request.user, "mitglied_zugang", None)
        verein = m.verein if m is not None else None
    if verein is None or not verein.logo:
        raise Http404
    return FileResponse(verein.logo.open("rb"))


@login_required
def verein_einstellungen(request):
    if request.verein is None:
        return redirect("verein_waehlen")
    if not request.rechte.darf("verwaltung", "change"):
        raise PermissionDenied
    form = VereinForm(request.POST or None, request.FILES or None, instance=request.verein)
    if request.method == "POST" and form.is_valid():
        audit.kontext_setzen(grund=form.cleaned_data.get("aenderungsgrund"))
        form.save()
        messages.success(request, "Vereinsdaten gespeichert.")
        return redirect("verein_einstellungen")
    return render(request, "core/formular.html", {"form": form, "titel": "Verein / Einstellungen",
                                                  "abbrechen_url": "/"})


@login_required
def auswertungen(request):
    if request.verein is None:
        return redirect("verein_waehlen")
    if not request.rechte.darf("auswertungen", "view"):
        raise PermissionDenied
    from apps.allowances.models import Aufwandsentschaedigung
    from apps.donations.models import Spende
    from apps.finance.models import Rechnung, Zahlung, wirksame_summe
    from apps.inventory.models import Gegenstand
    from apps.members.models import Mitglied

    v, heute = request.verein, date.today()
    abschnitte = []

    eintritte, austritte = defaultdict(int), defaultdict(int)
    for m in Mitglied.objects.filter(verein=v):
        if m.eintrittsdatum:
            eintritte[m.eintrittsdatum.year] += 1
        if m.austrittsdatum:
            austritte[m.austrittsdatum.year] += 1
    jahre = sorted(set(eintritte) | set(austritte))
    bestand = 0
    zeilen = []
    for j in jahre:
        bestand += eintritte[j] - austritte[j]
        zeilen.append([j, eintritte[j], austritte[j], bestand])
    abschnitte.append((_("Mitgliederentwicklung (Ein-/Austritte)"),
                       [_("Jahr"), _("Eintritte"), _("Austritte"), _("Bestand (kumuliert)")],
                       zeilen, _("Bestand nur aus erfassten Ein-/Austrittsdaten berechnet.")))

    klassen = [("0–17", 0, 17), ("18–25", 18, 25), ("26–40", 26, 40), ("41–60", 41, 60), ("61+", 61, 200)]
    zaehler = defaultdict(int)
    for m in Mitglied.objects.filter(verein=v, status__in=["aktiv", "ruhend"]):
        a = m.alter()
        if a is None:
            zaehler["unbekannt"] += 1
            continue
        for label, lo, hi in klassen:
            if lo <= a <= hi:
                zaehler[label] += 1
    abschnitte.append((_("Altersstruktur"), [_("Altersgruppe"), _("Anzahl")],
                       [[k, zaehler[k]] for k, _lo, _hi in klassen] + [[_("unbekannt"), zaehler["unbekannt"]]], ""))

    zeilen = []
    for j in sorted(set(Rechnung.objects.filter(verein=v, typ="beitrag").values_list("jahr", flat=True))):
        qs = Rechnung.objects.filter(verein=v, typ="beitrag", jahr=j).exclude(status__in=["storniert", "entwurf"])
        soll = qs.aggregate(s=Sum("betrag"))["s"] or 0
        ist = wirksame_summe(qs)
        zeilen.append([j, geld(soll), geld(ist), geld(soll - ist)])
    abschnitte.append((_("Beitragsaufkommen"), [_("Jahr"), _("Soll"), _("Bezahlt"), _("Offen")], zeilen, ""))

    rl = defaultdict(int)
    for z in Zahlung.objects.filter(verein=v, ruecklastschrift=True):
        rl[z.datum.year] += 1
    abschnitte.append((_("Rücklastschriften"), [_("Jahr"), _("Anzahl")], [[j, rl[j]] for j in sorted(rl)], ""))

    inv = Gegenstand.objects.filter(verein=v).exclude(zustand="ausgesondert")
    abschnitte.append((_("Inventar"), [_("Gegenstände"), _("Aktueller Wert"), _("Anschaffungswert")],
                       [[inv.count(), geld(inv.aggregate(s=Sum("aktueller_wert"))["s"] or 0),
                         geld(inv.aggregate(s=Sum("anschaffungspreis"))["s"] or 0)]], ""))

    sp = defaultdict(lambda: 0)
    for s in Spende.objects.filter(verein=v):
        sp[s.datum.year] += s.betrag
    abschnitte.append((_("Spenden je Jahr"), [_("Jahr"), _("Summe")], [[j, geld(sp[j])] for j in sorted(sp)], ""))

    if request.rechte.darf("aufwand", "view"):
        au = defaultdict(lambda: 0)
        for a in Aufwandsentschaedigung.objects.filter(verein=v, status__in=["genehmigt", "ausgezahlt"]):
            au[a.datum.year] += a.betrag
        abschnitte.append((_("Aufwandsentschädigungen je Jahr"), [_("Jahr"), _("Summe")],
                           [[j, geld(au[j])] for j in sorted(au)], ""))
    return render(request, "core/auswertungen.html", {"abschnitte": abschnitte, "titel": _("Auswertungen")})


# ---------------------------------------------------------------- Öffentliche Seiten (ohne Anmeldung)
def impressum(request, kuerzel):
    """Öffentlich erreichbar (Pflichtangabe nach § 5 TMG) - bewusst ohne @login_required."""
    verein = get_object_or_404(Verein, kuerzel=kuerzel, aktiv=True)
    return render(request, "core/impressum.html", {"verein": verein, "titel": f"Impressum – {verein.name}"})


def oeffentliche_dokumente(request, kuerzel):
    """Öffentliche Dokumente eines Vereins (z. B. Datenschutzerklärung, Aufnahmeformular) - ohne Anmeldung."""
    from apps.documents.models import Ablagedokument
    verein = get_object_or_404(Verein, kuerzel=kuerzel, aktiv=True)
    dokumente = Ablagedokument.objects.filter(verein=verein, oeffentlich=True).order_by("kategorie", "titel")
    return render(request, "core/oeffentliche_dokumente.html",
                 {"verein": verein, "dokumente": dokumente, "titel": f"Downloads – {verein.name}"})


def oeffentliches_dokument_download(request, kuerzel, pk):
    """Datei-Download zu oeffentliche_dokumente() - liefert NUR Dokumente mit oeffentlich=True aus."""
    from apps.documents.models import Ablagedokument
    verein = get_object_or_404(Verein, kuerzel=kuerzel, aktiv=True)
    d = get_object_or_404(Ablagedokument, pk=pk, verein=verein, oeffentlich=True)
    if not d.datei:
        raise Http404
    return FileResponse(d.datei.open("rb"), as_attachment=True, filename=os.path.basename(d.datei.name))
