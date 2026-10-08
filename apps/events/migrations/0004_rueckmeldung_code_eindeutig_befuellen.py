import uuid

from django.db import migrations


def eindeutige_codes_vergeben(apps, schema_editor):
    """AddField mit Callable-Default (0003) setzt bei bestehenden Zeilen denselben, einmalig berechneten
    Wert - hier wird jede Zeile einzeln mit einem eigenen UUID versehen, bevor die Unique-Constraint
    (0005) angelegt wird."""
    Veranstaltung = apps.get_model('events', 'Veranstaltung')
    for v in Veranstaltung.objects.all():
        Veranstaltung.objects.filter(pk=v.pk).update(rueckmeldung_code=uuid.uuid4())


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0003_veranstaltung_rueckmeldung_code'),
    ]

    operations = [
        migrations.RunPython(eindeutige_codes_vergeben, migrations.RunPython.noop),
    ]
