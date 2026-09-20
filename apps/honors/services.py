from datetime import date

from apps.members.models import Mitglied

from .models import Ehrung, Jubilaeumsregel


def jubilare(verein, jahr):
    """Mitglieder, die im Jahr `jahr` ein konfiguriertes Jubiläum erreichen."""
    regeln = {r.jahre: r for r in Jubilaeumsregel.objects.filter(verein=verein, aktiv=True)}
    out = []
    for m in Mitglied.objects.filter(verein=verein, status__in=["aktiv", "ruhend"], eintrittsdatum__isnull=False):
        j = jahr - m.eintrittsdatum.year
        if j in regeln:
            geehrt = Ehrung.objects.filter(verein=verein, mitglied=m, datum__year=jahr,
                                           art__name__icontains=str(j)).exists()
            out.append({"mitglied": m, "jahre": j, "regel": regeln[j], "geehrt": geehrt,
                        "datum": m.eintrittsdatum.replace(year=jahr) if not (
                            m.eintrittsdatum.month == 2 and m.eintrittsdatum.day == 29) else date(jahr, 2, 28)})
    return sorted(out, key=lambda x: (x["datum"], x["mitglied"].nachname))
