from django.db import migrations

AKTIONEN = ("view", "add", "change", "delete")
# (bisheriges Modul, neues Modul, Aktionen): bestehende Rollen behalten ihr bisheriges Verhalten
ABLEITUNG = (
    ("mitglieder", "geburtsdatum", ("view", "change")),
    ("mitglieder", "bankdaten", ("view", "change")),
    ("veranstaltungen", "teilnehmer", AKTIONEN),
    ("schriftverkehr", "rundschreiben", AKTIONEN),
)


def _erweitern(rechte):
    r = set(rechte or [])
    for alt, neu, aktionen in ABLEITUNG:
        r.update(f"{neu}.{a}" for a in aktionen if f"{alt}.{a}" in r)
    return sorted(r)


def vorwaerts(apps, schema_editor):
    Rolle = apps.get_model("core", "Rolle")
    Zugang = apps.get_model("core", "Zugang")
    for rolle in Rolle.objects.filter(ist_superadmin=False):
        neu = _erweitern(rolle.rechte)
        if rolle.name == "Lesebenutzer":   # Standardrolle: Bankdaten nie sichtbar (Datenschutz)
            neu = [x for x in neu if not x.startswith("bankdaten.")]
        if neu != sorted(rolle.rechte or []):
            rolle.rechte = neu
            rolle.save(update_fields=["rechte"])
    for z in Zugang.objects.exclude(extra_rechte=[]):
        neu = _erweitern(z.extra_rechte)
        if neu != sorted(z.extra_rechte or []):
            z.extra_rechte = neu
            z.save(update_fields=["extra_rechte"])


class Migration(migrations.Migration):
    dependencies = [("core", "0009_matrix_und_tags")]
    operations = [migrations.RunPython(vorwaerts, migrations.RunPython.noop)]
