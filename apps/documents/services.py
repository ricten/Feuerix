import os
from datetime import date

from django.core.files.base import ContentFile
from django.utils import translation

from apps.core.util import dateiname_bereinigen

from .models import KATEGORIEN, ORDNER_NAMEN, Ablagedokument, Ordner, Vorlage
from .vorlagen_defaults import STANDARDVORLAGEN


def standardordner_anlegen(verein):
    for name in ORDNER_NAMEN.values():
        Ordner.objects.get_or_create(verein=verein, name=name, uebergeordnet=None)


def standardvorlagen_anlegen(verein):
    """Legt fehlende Standardvorlagen an (bestehende, ggf. geänderte bleiben unangetastet)."""
    neu = 0
    from apps.core.anbindungen import Anbindungen
    anbindungen = Anbindungen(verein)
    for d in STANDARDVORLAGEN:
        if d.get("nur_mit") and not anbindungen.aktiv(d["nur_mit"]):
            continue   # z. B. die OpenSlides-Zugangsdaten-Vorlage erst, wenn OpenSlides angebunden ist
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


def ablage_dateiname(titel, kategorie, datum, dateiname):
    """Dateiname fuer die Ablage und die Uebergabe an Paperless: `JJJJ-MM-TT_Art_Titel.ext` (ISO-Datum zuerst, Teile mit
    Unterstrichen; Paperless liest das Datum aus dem Namen, wenn PAPERLESS_FILENAME_DATE_ORDER=YMD gesetzt ist, und ein
    Workflow kann Art/Titel per Dateinamen-Muster zuordnen). Rechnungen behalten ihren Namen (Rechnungsnummer_Typ_Empfaenger).
    Die Art bleibt weg, wenn der Titel bereits damit beginnt (\"Protokoll Jahreshauptversammlung\")."""
    if kategorie == "rechnung" or not dateiname:
        return dateiname
    with translation.override("de"):
        art = str(dict(KATEGORIEN).get(kategorie, ""))
    titel = " ".join(str(titel or "").split())
    teile = [(datum or date.today()).isoformat()]
    erstes = titel.split()[0].lower() if titel else ""
    doppelt = titel.lower().startswith(art.lower()) or (len(erstes) >= 4 and art.lower().startswith(erstes))   # "Beleg 5" / Art "Belege"
    if art and not doppelt:
        teile.append(art)
    if titel:
        teile.append(titel)
    endung = os.path.splitext(dateiname)[1].lower()
    return "_".join(dateiname_bereinigen(t).replace(" ", "_") for t in teile) + endung


def ablegen(verein, titel, kategorie, dateiname, inhalt, datum=None, veranstaltung=None, beschreibung="",
            erste_version=False):
    """Legt eine Datei versioniert in der Ablage ab (Ordner: Kategorie/Jahr). `erste_version=True`: das Dokument wird
    zum ersten Mal abgelegt und beginnt bei Version 1, auch wenn es schon ein anderes mit gleichem Titel gibt."""
    datum = datum or date.today()
    d = Ablagedokument(verein=verein, titel=titel, kategorie=kategorie, ordner=ordner_fuer(verein, kategorie, datum.year),
                       datum=datum, veranstaltung=veranstaltung, beschreibung=beschreibung)
    d._erste_version = erste_version
    d.datei.save(ablage_dateiname(titel, kategorie, datum, dateiname), ContentFile(inhalt), save=False)
    d.save()
    return d
