import os
from collections import defaultdict
from datetime import date, timedelta

from django.apps import apps as django_apps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Sum
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import audit
from .crud import REGISTRY, wert
from .forms import VereinForm
from .models import Zugang
from .util import geld


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
        "jahr": jahr,
    }
    return render(request, "core/dashboard.html", ctx)


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
    abschnitte.append(("Mitgliederentwicklung (Ein-/Austritte)", ["Jahr", "Eintritte", "Austritte", "Bestand (kumuliert)"],
                       zeilen, "Bestand nur aus erfassten Ein-/Austrittsdaten berechnet."))

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
    abschnitte.append(("Altersstruktur", ["Altersgruppe", "Anzahl"],
                       [[k, zaehler[k]] for k, _, _ in klassen] + [["unbekannt", zaehler["unbekannt"]]], ""))

    zeilen = []
    for j in sorted(set(Rechnung.objects.filter(verein=v, typ="beitrag").values_list("jahr", flat=True))):
        qs = Rechnung.objects.filter(verein=v, typ="beitrag", jahr=j).exclude(status__in=["storniert", "entwurf"])
        soll = qs.aggregate(s=Sum("betrag"))["s"] or 0
        ist = wirksame_summe(qs)
        zeilen.append([j, geld(soll), geld(ist), geld(soll - ist)])
    abschnitte.append(("Beitragsaufkommen", ["Jahr", "Soll", "Bezahlt", "Offen"], zeilen, ""))

    rl = defaultdict(int)
    for z in Zahlung.objects.filter(verein=v, ruecklastschrift=True):
        rl[z.datum.year] += 1
    abschnitte.append(("Rücklastschriften", ["Jahr", "Anzahl"], [[j, rl[j]] for j in sorted(rl)], ""))

    inv = Gegenstand.objects.filter(verein=v).exclude(zustand="ausgesondert")
    abschnitte.append(("Inventar", ["Gegenstände", "Aktueller Wert", "Anschaffungswert"],
                       [[inv.count(), geld(inv.aggregate(s=Sum("aktueller_wert"))["s"] or 0),
                         geld(inv.aggregate(s=Sum("anschaffungspreis"))["s"] or 0)]], ""))

    sp = defaultdict(lambda: 0)
    for s in Spende.objects.filter(verein=v):
        sp[s.datum.year] += s.betrag
    abschnitte.append(("Spenden je Jahr", ["Jahr", "Summe"], [[j, geld(sp[j])] for j in sorted(sp)], ""))

    if request.rechte.darf("aufwand", "view"):
        au = defaultdict(lambda: 0)
        for a in Aufwandsentschaedigung.objects.filter(verein=v, status__in=["genehmigt", "ausgezahlt"]):
            au[a.datum.year] += a.betrag
        abschnitte.append(("Aufwandsentschädigungen je Jahr", ["Jahr", "Summe"],
                           [[j, geld(au[j])] for j in sorted(au)], ""))
    return render(request, "core/auswertungen.html", {"abschnitte": abschnitte, "titel": "Auswertungen"})
