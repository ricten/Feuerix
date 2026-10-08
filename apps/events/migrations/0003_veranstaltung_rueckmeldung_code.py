import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0002_wahlergebnis'),
    ]

    operations = [
        migrations.AddField(
            model_name='veranstaltung',
            name='rueckmeldung_code',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True,
                                   verbose_name='Code für öffentliche Rückmeldung'),
        ),
    ]
