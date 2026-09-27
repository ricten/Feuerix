from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from . import matrix as mx
from .models import Rolle


def _pruefen(request, aktion):
    if request.verein is None or not request.rechte.darf("verwaltung", aktion):
        raise PermissionDenied


def _rollen(verein):
    rollen = list(Rolle.objects.filter(verein=verein, ist_superadmin=False))
    dso = list(mx.DSO_ROLLEN)
    rollen.sort(key=lambda r: (dso.index(r.name) if r.name in dso else len(dso), r.name))
    return rollen


@login_required
def berechtigungsmatrix(request):
    """Berechtigungsmatrix: Datenbereiche x Rollen, jede Zelle ist wählbar (– / L / B / V)."""
    _pruefen(request, "view")
    kann = request.rechte.darf("verwaltung", "change")
    rollen = _rollen(request.verein)
    aktuell = {r.pk: mx.matrix_der_rolle(r) for r in rollen}
    if request.method == "POST":
        if not kann:
            raise PermissionDenied
        gueltig = {s for s, _ in mx.STUFEN}
        geaendert = []
        for r in rollen:
            neu = {}
            for schluessel in [b.key for b in mx.BEREICHE] + [mx.LOESCHUNG]:
                wert = request.POST.get(f"m_{r.pk}_{schluessel}", aktuell[r.pk][schluessel])
                neu[schluessel] = wert if wert in gueltig else aktuell[r.pk][schluessel]
            if neu != aktuell[r.pk]:   # nur tatsächlich geänderte Rollen werden neu berechnet
                r.matrix = neu
                r.rechte = mx.rechte_aus_matrix(neu)
                r.save()
                geaendert.append(r.name)
        if geaendert:
            messages.success(request, "Berechtigungen gespeichert für: " + ", ".join(geaendert))
        else:
            messages.info(request, "Keine Änderungen.")
        return redirect("berechtigungsmatrix")
    def zeile(schluessel, label):
        return {"key": schluessel, "label": label,
                "zellen": [{"feld": f"m_{r.pk}_{schluessel}", "wert": aktuell[r.pk][schluessel]} for r in rollen]}

    zeilen = [zeile(b.key, b.label) for b in mx.BEREICHE if b.dso]
    zeilen.append(zeile(mx.LOESCHUNG, mx.LOESCHUNG_LABEL))
    weitere = [zeile(b.key, b.label) for b in mx.BEREICHE if not b.dso]
    if weitere:
        zeilen += [{"trenner": True}] + weitere
    dso_fehlt = [n for n in mx.DSO_ROLLEN if not any(r.name == n for r in rollen)]
    return render(request, "core/matrix.html", {
        "titel": "Berechtigungsmatrix", "rollen": rollen, "zeilen": zeilen, "kann": kann,
        "spalten": len(rollen) + 1, "hinweise": mx.dso_pruefung(request.verein),
        "dso_fehlt": dso_fehlt})


@login_required
@require_POST
def berechtigungsmatrix_dso(request):
    _pruefen(request, "change")
    rollen, tags = mx.dso_anlegen(request.verein)
    messages.success(request, f"Datenschutzordnung: {rollen} Rolle(n) und {tags} Tag(s) angelegt "
                              "(vorhandene bleiben unverändert).")
    return redirect("berechtigungsmatrix")
