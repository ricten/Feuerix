from datetime import date

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import reverse

from .services import jubilare


@login_required
def jubilaeen(request):
    if request.verein is None:
        return redirect("verein_waehlen")
    if not request.rechte.darf("ehrungen", "view"):
        raise PermissionDenied
    try:
        jahr = int(request.GET.get("jahr", date.today().year))
    except ValueError:
        jahr = date.today().year
    eintraege = jubilare(request.verein, jahr)
    for e in eintraege:
        e["ehrung_url"] = (reverse("ehrung_add") + f"?mitglied={e['mitglied'].pk}&datum={e['datum']:%Y-%m-%d}"
                           f"&anlass={e['jahre']}+Jahre+Mitgliedschaft")
    return render(request, "honors/jubilaeen.html", {
        "eintraege": eintraege, "jahr": jahr, "titel": f"Jubiläen {jahr}",
        "kann_anlegen": request.rechte.darf("ehrungen", "add")})
