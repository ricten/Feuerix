import json
import os
from collections import Counter, defaultdict
from datetime import date, timedelta

from django.apps import apps as django_apps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordChangeView
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Sum
from django.http import FileResponse, Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _lazy
from django.views.decorators.http import require_POST

from . import audit, passwortabgleich
from .crud import REGISTRY, wert
from .forms import VereinForm
from .models import DashboardEinstellung, Verein, Zugang
from .util import anzeige_dateiname, geld

DASHBOARD_KACHELN = ("kennzahlen", "veranstaltungen", "aufgaben", "verleihe")


def _vorbereiten(request):
    if request.verein is None:
        return redirect("verein_waehlen")
    return None


class PasswortAendernView(PasswordChangeView):
    """Eigenes Passwort aendern; bei eingeschaltetem Passwort-Abgleich wird es auch in Paperless/OpenSlides gesetzt."""

    def form_valid(self, form):
        antwort = super().form_valid(form)
        passwortabgleich.melden(self.request, passwortabgleich.abgleichen(self.request.user, form.cleaned_data["new_password1"]))
        return antwort


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
    # mindestens gelben Aufgaben schlägt die Kachelfarbe auf Gelb um (rot zählt dabei auch als "mindestens
    # gelb" mit), ab zwei roten auf Rot.
    stufen = Counter(a.faelligkeits_stufe for a in alle_meine_aufgaben if a.faelligkeits_stufe)
    if stufen.get("rot", 0) >= 2:
        meine_aufgaben_farbe = "rot"
    elif stufen.get("rot", 0) + stufen.get("gelb", 0) >= 2:
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
    return FileResponse(fdatei.open("rb"), as_attachment=(feld != "foto"), filename=anzeige_dateiname(fdatei.name))


@login_required
def verein_logo(request):
    verein = request.verein
    if verein is None:
        m = getattr(request.user, "mitglied_zugang", None)
        verein = m.verein if m is not None else None
    if verein is None or not verein.logo:
        raise Http404
    return FileResponse(verein.logo.open("rb"))


# Aufteilung der Vereinseinstellungen nach Themen (vertikale Navigation): (id, Titel, Symbol, Hinweis, [(Zwischenueberschrift
# oder None, Felder)]). Felder, die hier nicht vorkommen, landen unter "Weitere", damit nach Modelländerungen nichts verschwindet.
EINSTELLUNGS_GRUPPEN = [
    ("stamm", _lazy("Verein"), "bi-building", "",
     [(None, ("name", "anschrift", "plz", "ort", "email", "vereinsregister"), None)]),
    ("finanzen", _lazy("Finanzen"), "bi-cash-coin",
     _lazy("Steuerlich Relevantes bitte mit dem Steuerberater abstimmen."),
     [(_lazy("Bank"), ("bankname", "iban", "bic", "glaeubiger_id"), "finanzen-bank"),
      (_lazy("Steuern & Gemeinnützigkeit"),
       ("finanzamt", "steuernummer", "umsatzsteuerpflichtig", "ust_idnr", "rechnung_steuerhinweis", "bescheid_art",
        "bescheid_datum", "bescheid_zeitraum", "beguenstigte_zwecke", "uebungsleiter_freibetrag",
        "ehrenamts_freibetrag"), "finanzen-steuern"),
      (_lazy("Rechnungen"), ("zahlungsziel_tage", "rechnung_kopftext", "rechnung_fusstext"), "finanzen-rechnungen")]),
    ("design", _lazy("Erscheinungsbild"), "bi-palette", "",
     [(_lazy("Logo & Farben"), ("logo", "akzentfarbe", "akzentfarbe_fuss", "akzentfarbe_web", "akzentfarbe_web_2",
                                "akzentfarbe_web_3"), "design-logo"),
      (_lazy("Briefe"), ("unterschrift_1", "unterschrift_2"), "design-briefe"),
      (_lazy("Etiketten"), ("etikett_breite_mm", "etikett_hoehe_mm", "etikett_spalten", "etikett_zeilen"),
       "design-etiketten")]),
    ("startseite", _lazy("Startseite & Impressum"), "bi-megaphone", "",
     [(None, ("startseite_banner", "startseite_banner_art", "startseite_banner_bis", "impressum_text"), None)]),
]


def _einstellungs_gruppen(form):
    """Teilt die Felder des Formulars nach Themen auf; das erste Thema mit Fehlern (sonst das erste) ist aktiv."""
    verteilt, gruppen = set(), []
    for gid, titel, icon, hinweis, bloecke in EINSTELLUNGS_GRUPPEN:
        liste = []
        for blocktitel, namen, block_id in bloecke:
            felder = [form[n] for n in namen if n in form.fields]
            verteilt.update(n for n in namen if n in form.fields)
            if felder:
                liste.append({"titel": blocktitel, "felder": felder, "id": block_id})
        gruppen.append({"id": gid, "titel": titel, "icon": icon, "hinweis": hinweis, "bloecke": liste})
    rest = [form[n] for n in form.fields if n not in verteilt]
    if rest:
        gruppen.append({"id": "weitere", "titel": _lazy("Weitere"), "icon": "bi-three-dots", "hinweis": "",
                        "bloecke": [{"titel": None, "felder": rest, "id": None}]})
    gruppen = [g for g in gruppen if g["bloecke"]]
    for g in gruppen:
        g["felder"] = [f for blk in g["bloecke"] for f in blk["felder"]]
        g["fehler"] = sum(len(f.errors) for f in g["felder"])
        g["aktiv"] = False
    erste = next((g for g in gruppen if g["fehler"]), gruppen[0] if gruppen else None)
    if erste:
        erste["aktiv"] = True
    return gruppen


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
        messages.success(request, _("Vereinsdaten gespeichert."))
        return redirect("verein_einstellungen")
    gruppen = _einstellungs_gruppen(form)
    return render(request, "core/formular.html", {"form": form, "titel": _("Verein / Einstellungen"),
                                                  "abbrechen_url": "/", "gruppen": gruppen,
                                                  "gruppen_hat_fehler": any(g["fehler"] for g in gruppen)})


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
    return render(request, "core/impressum.html", {"verein": verein, "titel": _("Impressum – %(name)s") % {"name": verein.name}})


def oeffentliche_dokumente(request, kuerzel):
    """Öffentliche Dokumente eines Vereins (z. B. Datenschutzerklärung, Aufnahmeformular) - ohne Anmeldung."""
    from apps.documents.models import Ablagedokument
    verein = get_object_or_404(Verein, kuerzel=kuerzel, aktiv=True)
    dokumente = Ablagedokument.objects.filter(verein=verein, oeffentlich=True).order_by("kategorie", "titel")
    return render(request, "core/oeffentliche_dokumente.html",
                 {"verein": verein, "dokumente": dokumente, "titel": _("Downloads – %(name)s") % {"name": verein.name}})


def oeffentliches_dokument_download(request, kuerzel, pk):
    """Datei-Download zu oeffentliche_dokumente() - liefert NUR Dokumente mit oeffentlich=True aus."""
    from apps.documents.models import Ablagedokument
    verein = get_object_or_404(Verein, kuerzel=kuerzel, aktiv=True)
    d = get_object_or_404(Ablagedokument, pk=pk, verein=verein, oeffentlich=True)
    if not d.datei:
        raise Http404
    return FileResponse(d.datei.open("rb"), as_attachment=True, filename=anzeige_dateiname(d.datei.name))


@login_required
def einstellungen_uebersicht(request):
    """Alle Verwaltungs- und Stammdatenseiten nach Themen geordnet (siehe einstellungen.py)."""
    from .einstellungen import sichtbare_bereiche
    if request.verein is None:
        return redirect("verein_waehlen")
    bereiche = sichtbare_bereiche(request)
    if not bereiche:
        raise PermissionDenied
    return render(request, "core/einstellungen.html", {"titel": _("Einstellungen"), "bereiche": bereiche})


@login_required
def anbindungen_uebersicht(request):
    """Neutraler Einstieg zum Einrichten externer Dienste (OpenSlides, Paperless-ngx). Im Menue stehen deren eigene
    Einstellungsseiten erst, wenn die jeweilige Instanz angebunden ist - hier kommt man vorher dorthin."""
    from .anbindungen import anbindungen
    rechte, a = request.rechte, anbindungen(request)
    dienste = []
    if rechte.darf("openslides", "view"):
        dienste.append({"name": "OpenSlides", "aktiv": a.openslides, "url": reverse("openslides_einstellungen"),
                        "text": _("Online-Mitgliederversammlungen: Konten, Versammlung und Tagesordnung anlegen, "
                                  "Anwesenheit, Wahlen und Abstimmungen ins Protokoll übernehmen.")})
    if rechte.darf("paperless", "view"):
        dienste.append({"name": "Paperless-ngx", "aktiv": a.paperless, "url": reverse("paperless_einstellungen"),
                        "text": _("Dokumentenarchiv: Dokumente aus der Ablage an Paperless-ngx übergeben.")})
    if not dienste:
        raise PermissionDenied
    return render(request, "core/anbindungen.html", {"titel": _("Externe Anbindungen"), "dienste": dienste})
