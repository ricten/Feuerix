from django.db import migrations


def versionen_trennen(apps, schema_editor):
    """Ablage-Dokumente mit gleichem Titel im gleichen Ordner, aber zu verschiedenen Veranstaltungen (z. B. das Protokoll
    einer spaeteren Sitzung, das als "Version 2" der frueheren gezaehlt wurde), sind getrennte Dokumente: je
    Veranstaltung wird die Versionsnummer neu von 1 an vergeben (Reihenfolge: Anlage). Dokumente ohne Veranstaltung
    bleiben unveraendert."""
    Dokument = apps.get_model("documents", "Ablagedokument")
    gruppen = {}
    for d in Dokument.objects.exclude(veranstaltung__isnull=True).order_by("id"):
        gruppen.setdefault((d.verein_id, d.ordner_id, d.titel, d.veranstaltung_id), []).append(d)
    for (verein_id, ordner_id, titel, _ver), dokumente in gruppen.items():
        # nur eingreifen, wenn dieser Titel im Ordner ueber mehrere Veranstaltungen verteilt ist
        if Dokument.objects.filter(verein_id=verein_id, ordner_id=ordner_id, titel=titel).exclude(
                veranstaltung_id=_ver).exists():
            for nummer, d in enumerate(dokumente, start=1):
                if d.version != nummer:
                    Dokument.objects.filter(pk=d.pk).update(version=nummer)


class Migration(migrations.Migration):
    dependencies = [("documents", "0008_auto_uebergabe_dokumenttyp")]
    operations = [migrations.RunPython(versionen_trennen, migrations.RunPython.noop)]
