from django.db import migrations


def nummerieren(apps, schema_editor):
    """Bestehende Tagesordnungen lueckenlos durchnummerieren (Doppelte und Luecken, z. B. nach Loeschen oder durch den
    frueheren Vorschlag "Anzahl + 1"). Die bisherige Reihenfolge (Position, dann ID) bleibt erhalten."""
    TOP = apps.get_model("events", "Tagesordnungspunkt")
    for veranstaltung_id in TOP.objects.values_list("veranstaltung_id", flat=True).distinct():
        punkte = TOP.objects.filter(veranstaltung_id=veranstaltung_id).order_by("position", "id")
        for nummer, top in enumerate(punkte, start=1):
            if top.position != nummer:
                TOP.objects.filter(pk=top.pk).update(position=nummer)


class Migration(migrations.Migration):
    dependencies = [("events", "0011_anwesenheit")]
    operations = [migrations.RunPython(nummerieren, migrations.RunPython.noop)]
