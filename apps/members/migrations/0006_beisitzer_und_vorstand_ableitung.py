"""Das Häkchen "Vorstandsmitglied" ist keine manuelle Eingabe mehr, sondern wird aus den Tags abgeleitet (eine
der sechs DSO-Funktionen oder das neue Tag "Beisitzer": Vorstandsmitglied ohne weitere Rechte in dieser Software).

Für bestehende Daten: Mitglieder, die bereits als Vorstandsmitglied markiert waren, aber keine der DSO-Funktionen
tragen, bekommen automatisch das Tag "Beisitzer", damit ihr Status erhalten bleibt. Anschließend wird das Feld
überall neu aus den Tags berechnet und die historisierte Funktion "Vorstandsmitglied" nachgezogen.

Bewusst in sich geschlossen (keine Importe aus apps.core.matrix/apps.members.models), siehe Migration
core.0011_altes_rollensystem_abloesen für dieselbe Begründung."""
from datetime import date

from django.db import migrations

DSO_TAGNAMEN = {"1. Vorsitzender", "2. Vorsitzender", "Kassenwart", "Stellv. Kassenwart", "Schriftführer",
                "Stellv. Schriftführer"}
BEISITZER = "Beisitzer"
VORSTAND_FUNKTION = "Vorstandsmitglied"


def vorwaerts(apps, schema_editor):
    Verein = apps.get_model("core", "Verein")
    MitgliedTag = apps.get_model("members", "MitgliedTag")
    Mitglied = apps.get_model("members", "Mitglied")
    Funktion = apps.get_model("members", "Funktion")
    MitgliedFunktion = apps.get_model("members", "MitgliedFunktion")
    heute = date.today()

    for verein in Verein.objects.all():
        beisitzer, _ = MitgliedTag.objects.get_or_create(verein=verein, name=BEISITZER, defaults={
            "paperless_gruppe": "Vorstand", "openslides_gruppe": "Staff",
            "beschreibung": "Vorstandsmitglied ohne weitere Rechte in dieser Software"})
        for m in Mitglied.objects.filter(verein=verein):
            hat_dso_tag = m.tags.filter(name__in=DSO_TAGNAMEN).exists()
            richtig = hat_dso_tag or m.tags.filter(pk=beisitzer.pk).exists()
            if m.vorstandsmitglied and not richtig:
                m.tags.add(beisitzer)
                richtig = True
            if m.vorstandsmitglied != richtig:
                m.vorstandsmitglied = richtig
                m.save(update_fields=["vorstandsmitglied"])
            if richtig:
                f, _ = Funktion.objects.get_or_create(verein=verein, name=VORSTAND_FUNKTION)
                if not MitgliedFunktion.objects.filter(mitglied=m, funktion=f, bis__isnull=True).exists():
                    MitgliedFunktion.objects.create(verein=verein, mitglied=m, funktion=f, von=heute)


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0005_alter_mitglied_vorstandsmitglied"),
        ("core", "0011_altes_rollensystem_abloesen"),
    ]
    operations = [migrations.RunPython(vorwaerts, migrations.RunPython.noop)]
