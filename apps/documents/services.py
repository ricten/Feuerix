from datetime import date

from django.core.files.base import ContentFile

from .models import KATEGORIEN, ORDNER_NAMEN, Ablagedokument, Ordner, Vorlage
from .vorlagen_defaults import STANDARDVORLAGEN


def standardordner_anlegen(verein):
    for name in ORDNER_NAMEN.values():
        Ordner.objects.get_or_create(verein=verein, name=name, uebergeordnet=None)


def standardvorlagen_anlegen(verein):
    """Legt fehlende Standardvorlagen an (bestehende, ggf. geänderte bleiben unangetastet)."""
    neu = 0
    for d in STANDARDVORLAGEN:
        _, created = Vorlage.objects.get_or_create(verein=verein, name=d["name"], defaults={
            "art": d["art"], "betreff": d["betreff"], "text": d["text"], "hinweis": d.get("hinweis", ""),
            "ist_standard": d.get("standard", False)})
        neu += int(created)
    return neu


def ordner_fuer(verein, kategorie, jahr):
    wurzel, _ = Ordner.objects.get_or_create(verein=verein, name=ORDNER_NAMEN.get(kategorie, "Sonstiges"),
                                             uebergeordnet=None)
    sub, _ = Ordner.objects.get_or_create(verein=verein, name=str(jahr), uebergeordnet=wurzel)
    return sub


def ablegen(verein, titel, kategorie, dateiname, inhalt, datum=None, veranstaltung=None, beschreibung=""):
    """Legt eine Datei versioniert in der Ablage ab (Ordner: Kategorie/Jahr)."""
    datum = datum or date.today()
    d = Ablagedokument(verein=verein, titel=titel, kategorie=kategorie, ordner=ordner_fuer(verein, kategorie, datum.year),
                       datum=datum, veranstaltung=veranstaltung, beschreibung=beschreibung)
    d.datei.save(dateiname, ContentFile(inhalt), save=False)
    d.save()
    return d
