"""Die historisierte Funktion eines Vorstandsmitglieds trägt ab jetzt den Namen des jeweiligen Tags (z. B.
"Kassenwart" oder "Beisitzer") statt eines allgemeinen Platzhalters "Vorstandsmitglied" - zwei unterschiedliche
Ämter waren darüber bisher nicht zu unterscheiden.

Für bestehende Daten: eine noch laufende (offene) Funktion "Vorstandsmitglied" wird beendet und durch die
passenden, nach Tag benannten Funktionen ersetzt. Bereits beendete "Vorstandsmitglied"-Einträge bleiben als
historischer Datensatz unverändert - sie waren zum jeweiligen Zeitpunkt korrekt und lassen sich im Nachhinein
nicht mehr eindeutig einem einzelnen Tag zuordnen.

Bewusst in sich geschlossen (keine Importe aus apps.core.matrix/apps.members.models), siehe die Migrationen
core.0011_altes_rollensystem_abloesen und members.0006 für dieselbe Begründung."""
from datetime import date

from django.db import migrations

DSO_TAGNAMEN = {"1. Vorsitzender", "2. Vorsitzender", "Kassenwart", "Stellv. Kassenwart", "Schriftführer",
                "Stellv. Schriftführer"}
VORSTAND_TAGNAMEN = DSO_TAGNAMEN | {"Beisitzer"}
ALTER_PLATZHALTER = "Vorstandsmitglied"


def vorwaerts(apps, schema_editor):
    Verein = apps.get_model("core", "Verein")
    MitgliedTag = apps.get_model("members", "MitgliedTag")
    Mitglied = apps.get_model("members", "Mitglied")
    Funktion = apps.get_model("members", "Funktion")
    MitgliedFunktion = apps.get_model("members", "MitgliedFunktion")
    heute = date.today()

    for verein in Verein.objects.all():
        offene = MitgliedFunktion.objects.filter(
            mitglied__verein=verein, funktion__name=ALTER_PLATZHALTER, bis__isnull=True)
        mitglieder = {mf.mitglied_id for mf in offene}
        offene.update(bis=heute)
        for mitglied_id in mitglieder:
            m = Mitglied.objects.get(pk=mitglied_id)
            gehalten = set(MitgliedTag.objects.filter(mitglieder=m, name__in=VORSTAND_TAGNAMEN)
                           .values_list("name", flat=True))
            for name in gehalten:
                f, _ = Funktion.objects.get_or_create(verein=verein, name=name)
                if not MitgliedFunktion.objects.filter(mitglied=m, funktion=f, bis__isnull=True).exists():
                    MitgliedFunktion.objects.create(verein=verein, mitglied=m, funktion=f, von=heute)


class Migration(migrations.Migration):
    dependencies = [("members", "0006_beisitzer_und_vorstand_ableitung")]
    operations = [migrations.RunPython(vorwaerts, migrations.RunPython.noop)]
