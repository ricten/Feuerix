"""Benennt "Standort" in "Lagerort" um - reine Umbenennung (RenameModel/RenameField), keine Datenverluste:
bestehende Lagerort-Datensaetze und ihre Zuordnung zu Gegenstaenden/Inventurpositionen bleiben erhalten."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0004_verleih_kaution_einbehalten'),
    ]

    operations = [
        migrations.RenameModel(old_name='Standort', new_name='Lagerort'),
        migrations.AlterModelOptions(
            name='lagerort',
            options={'ordering': ['name'], 'verbose_name': 'Lagerort', 'verbose_name_plural': 'Inventar-Lagerorte'},
        ),
        migrations.RenameField(model_name='gegenstand', old_name='standort', new_name='lagerort'),
        migrations.AlterField(
            model_name='gegenstand',
            name='lagerort',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL,
                                    to='inventory.lagerort', verbose_name='Lagerort'),
        ),
        migrations.RenameField(model_name='inventurposition', old_name='standort_text', new_name='lagerort_text'),
        migrations.AlterField(
            model_name='inventurposition',
            name='lagerort_text',
            field=models.CharField(blank=True, max_length=100, verbose_name='Lagerort (Soll)'),
        ),
    ]
