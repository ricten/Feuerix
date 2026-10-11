import uuid

from django.db import migrations

AKTIV = ("reserviert", "ausgegeben")


def zusammenfuehren(apps, schema_editor):
    """Laufende Verleihe (reserviert/ausgegeben) derselben Veranstaltung und desselben Entleihers, die auf mehrere
    Vorgaenge (oder Einzelverleihe) verteilt sind - z. B. weil spaeter noch Gegenstaende hinzukamen -, werden zu EINEM
    Vorgang zusammengefuehrt. Abgeschlossene Vorgaenge bleiben unveraendert."""
    Verleih = apps.get_model("inventory", "Verleih")
    gruppen = {}
    for v in Verleih.objects.filter(veranstaltung__isnull=False, status__in=AKTIV).order_by("id"):
        gruppen.setdefault((v.verein_id, v.veranstaltung_id, v.entleiher_id, v.entleiher_name), []).append(v)
    for verleihe in gruppen.values():
        vorgaenge = {v.vorgang for v in verleihe}
        if len(verleihe) < 2 or len(vorgaenge) == 1 and None not in vorgaenge:
            continue
        ziel = next((v.vorgang for v in verleihe if v.vorgang), None) or uuid.uuid4()
        Verleih.objects.filter(pk__in=[v.pk for v in verleihe]).update(vorgang=ziel)


class Migration(migrations.Migration):
    dependencies = [("inventory", "0008_verleih_aufgabe")]
    operations = [migrations.RunPython(zusammenfuehren, migrations.RunPython.noop)]
