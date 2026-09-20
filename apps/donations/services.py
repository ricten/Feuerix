from collections import defaultdict
from datetime import date

from django.db import transaction

from .models import Spende, Zuwendungsbestaetigung


def _bestaetigung(verein, spenden, typ):
    s0 = spenden[0]
    art = "sach" if s0.art == "sach" else "geld"
    b = Zuwendungsbestaetigung.objects.create(
        verein=verein, typ=typ, art=art, spender_name=s0.name_des_spenders,
        spender_anschrift=s0.anschrift_des_spenders, betrag=sum(s.betrag for s in spenden),
        datum_von=min(s.datum for s in spenden), datum_bis=max(s.datum for s in spenden),
        ist_mitgliedsbeitrag=all(s.art == "mitgliedsbeitrag" for s in spenden),
        verzicht_aufwendungen=all(s.art == "aufwandsverzicht" for s in spenden),
        sach_beschreibung="\n".join(s.sach_beschreibung for s in spenden if s.sach_beschreibung),
        sach_herkunft=s0.get_sach_herkunft_display() if s0.sach_herkunft else "",
        sach_wertermittlung=s0.sach_wertermittlung)
    for s in spenden:
        s.bestaetigung = b
        s.save(update_fields=["bestaetigung", "geaendert"])
    return b


@transaction.atomic
def einzelbestaetigung(verein, spende):
    return _bestaetigung(verein, [spende], "einzel")


def offene_gruppen(verein, jahr):
    """Unbestätigte Geldzuwendungen des Jahres, gruppiert je Spender."""
    gruppen = defaultdict(list)
    for s in Spende.objects.filter(verein=verein, datum__year=jahr, bestaetigung__isnull=True).exclude(art="sach") \
            .select_related("spender"):
        gruppen[s.spender_schluessel()].append(s)
    return list(gruppen.values())


@transaction.atomic
def sammelbestaetigungen(verein, jahr):
    return [_bestaetigung(verein, g, "sammel") for g in offene_gruppen(verein, jahr)]
