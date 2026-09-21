"""NUR FÜR TEST-/DEMOZWECKE: erzeugt fiktive Mitglieder inkl. Beitragsrechnungen und Zahlungen
(u. a. mit Zahlungsrückständen/Mahnungen) sowie ein Beispiel-Inventar für einen bestehenden Verein.

Aufruf:  python manage.py beispieldaten --verein <kuerzel> [--anzahl 40] [--ohne-inventar]
"""
import random
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from apps.core.models import Verein
from apps.finance import services as finance_services
from apps.finance.models import Beitragsjahr, Rechnung, Zahlung
from apps.inventory.models import Gegenstand, Kategorie, Standort
from apps.members.models import Abteilung, Mitglied, Mitgliedsart

VORNAMEN_M = ["Michael", "Thomas", "Andreas", "Stefan", "Christian", "Markus", "Daniel", "Alexander", "Florian",
              "Sebastian", "Martin", "Jürgen", "Klaus", "Peter", "Wolfgang", "Frank", "Uwe", "Jörg", "Matthias",
              "Tobias", "Dominik", "Simon", "Fabian", "Patrick", "Marcel", "Rainer", "Günter", "Werner", "Rolf",
              "Bernd"]
VORNAMEN_F = ["Sabine", "Petra", "Andrea", "Claudia", "Nicole", "Sandra", "Julia", "Stefanie", "Anja", "Katrin",
              "Birgit", "Monika", "Karin", "Susanne", "Melanie", "Kerstin", "Simone", "Christina", "Anna", "Lisa",
              "Laura", "Sarah", "Jasmin", "Vanessa", "Nadine", "Heike", "Renate", "Ute", "Ingrid", "Christine"]
NACHNAMEN = ["Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker", "Hoffmann", "Schulz",
             "Koch", "Richter", "Bauer", "Klein", "Wolf", "Neumann", "Schwarz", "Zimmermann", "Braun", "Krüger",
             "Hofmann", "Lange", "Schmitt", "Werner", "Krause", "Meier", "Lehmann", "Schmid", "Schulze", "Maier",
             "Herrmann", "König", "Walter", "Fuchs", "Peters", "Lang", "Scholz", "Möller", "Weiß", "Jung"]
STRASSEN = ["Feuerwehrstraße", "Hauptstraße", "Kirchweg", "Bachstraße", "Ringstraße", "Am Sportplatz", "Feldweg",
            "Alte Gasse", "Industriestraße", "Waldweg", "Bergstraße", "Gartenstraße", "Schulstraße", "Mühlenweg",
            "Lindenallee", "Am Bahnhof", "Wiesenweg", "Rosenstraße", "Talstraße", "Birkenweg"]
ORTE = [("Musterstadt", "12345"), ("Musterstadt", "12345"), ("Musterstadt", "12345"),
        ("Musterstadt-Nord", "12346"), ("Musterdorf", "12399")]
ABTEILUNGEN = ["Löschzug 1", "Löschzug 2", "Jugendfeuerwehr", "Kommando", "Alters- und Ehrenabteilung", "Musikzug"]

# (Bezeichnung, Kategorie, Standort, Hersteller, Modell, Zustand, Alter in Jahren, Anschaffungspreis, verleihbar,
#  Kaution, Leihgebühr) - Einsatzausrüstung ist bewusst nicht verleihbar, Veranstaltungsausstattung schon.
GEGENSTAENDE = [
    ("Feuerwehrhelm Rosenbauer HEROS", "Persönliche Schutzausrüstung", "Gerätehaus", "Rosenbauer", "HEROS-titan",
     "gut", 3, 320, False, 0, 0),
    ("Feuerwehrhelm Rosenbauer HEROS", "Persönliche Schutzausrüstung", "Gerätehaus", "Rosenbauer", "HEROS-titan",
     "gut", 3, 320, False, 0, 0),
    ("Feuerwehr-Schutzanzug HuPF", "Persönliche Schutzausrüstung", "Gerätehaus", "Lion", "Janus", "gut", 2, 890, False, 0, 0),
    ("Pressluftatmer", "Atemschutz", "Fahrzeughalle", "Dräger", "PSS 7000", "gut", 4, 2450, False, 0, 0),
    ("Pressluftatmer", "Atemschutz", "Fahrzeughalle", "Dräger", "PSS 7000", "gebrauchsspuren", 6, 2450, False, 0, 0),
    ("Wärmebildkamera", "Atemschutz", "Fahrzeughalle", "Dräger", "UCF 9000", "gut", 2, 4200, False, 0, 0),
    ("B-Druckschlauch 20m", "Schläuche & Armaturen", "Fahrzeughalle", "", "", "gut", 3, 180, False, 0, 0),
    ("C-Druckschlauch 15m", "Schläuche & Armaturen", "Fahrzeughalle", "", "", "gut", 3, 120, False, 0, 0),
    ("Hydraulisches Rettungsgerät (Spreizer)", "Rettungsgerät", "Fahrzeughalle", "Weber Rescue", "Spreader SP 42",
     "gut", 5, 8900, False, 0, 0),
    ("Tauchpumpe TS 2/5", "Rettungsgerät", "Fahrzeughalle", "", "TS 2/5", "gut", 4, 1650, False, 0, 0),
    ("Kettensäge", "Werkzeug", "Lager", "Stihl", "MS 261", "gut", 2, 780, False, 0, 0),
    ("Stromerzeuger", "Werkzeug", "Lager", "Honda", "EU30i", "gut", 3, 2100, True, 100, 15),
    ("Handfunkgerät (Digitalfunk)", "Kommunikation", "Gerätehaus", "Motorola", "DP4801e", "gut", 2, 650, False, 0, 0),
    ("Handfunkgerät (Digitalfunk)", "Kommunikation", "Gerätehaus", "Motorola", "DP4801e", "gut", 2, 650, False, 0, 0),
    ("Funkmeldeempfänger", "Kommunikation", "Gerätehaus", "Swissphone", "s.QUAD", "gut", 5, 320, False, 0, 0),
    ("Defibrillator (AED)", "Erste Hilfe", "Fahrzeughalle", "Philips", "HeartStart FRx", "gut", 3, 1450, False, 0, 0),
    ("Erste-Hilfe-Koffer DIN 13157", "Erste Hilfe", "Fahrzeughalle", "", "", "gut", 1, 90, False, 0, 0),
    ("Steckleiter (3-teilig)", "Rettungsgerät", "Fahrzeughalle", "", "", "gebrauchsspuren", 8, 540, False, 0, 0),
    ("Verkehrsleitkegel (Set 10 Stück)", "Werkzeug", "Lager", "", "", "gut", 4, 150, False, 0, 0),
    ("Absperrband-Rolle", "Werkzeug", "Lager", "", "", "neu", 0, 15, False, 0, 0),
    ("Faltpavillon 3x3m", "Veranstaltungstechnik", "Lager", "", "", "gut", 2, 280, True, 30, 10),
    ("Faltpavillon 3x3m", "Veranstaltungstechnik", "Lager", "", "", "gut", 2, 280, True, 30, 10),
    ("Biertischgarnitur", "Veranstaltungstechnik", "Lager", "", "", "gebrauchsspuren", 6, 95, True, 20, 5),
    ("Biertischgarnitur", "Veranstaltungstechnik", "Lager", "", "", "gebrauchsspuren", 6, 95, True, 20, 5),
    ("Biertischgarnitur", "Veranstaltungstechnik", "Lager", "", "", "gebrauchsspuren", 6, 95, True, 20, 5),
    ("Grillwagen", "Veranstaltungstechnik", "Lager", "", "", "gut", 3, 650, True, 50, 15),
    ("Kaffeemaschine", "Veranstaltungstechnik", "Jugendraum", "Bonamat", "Matic", "gut", 4, 480, True, 20, 5),
    ("Beamer", "Veranstaltungstechnik", "Jugendraum", "Epson", "EB-X05", "gut", 3, 450, True, 50, 10),
    ("Laptop", "Veranstaltungstechnik", "Jugendraum", "Lenovo", "ThinkPad E14", "gut", 2, 850, True, 100, 0),
    ("Notstromaggregat", "Werkzeug", "Lager", "", "", "defekt", 12, 1200, False, 0, 0),
]


ZUSTAND_WERTFAKTOR = {"neu": 0.95, "gut": 0.65, "gebrauchsspuren": 0.35, "defekt": 0.05, "ausgesondert": 0.0}


def _zufallsdatum(von_jahr, bis_jahr):
    jahr = random.randint(von_jahr, bis_jahr)
    return date(jahr, random.randint(1, 12), random.randint(1, 28))


class Command(BaseCommand):
    help = "NUR FÜR TESTZWECKE: erzeugt fiktive Mitglieder, einen Beitragsjahr-Rechnungslauf und Zahlungen " \
           "(inkl. Zahlungsrückständen und Mahnungen) sowie ein Beispiel-Inventar für einen bestehenden Verein."

    def add_arguments(self, parser):
        parser.add_argument("--verein", required=True, help="Kürzel des Vereins")
        parser.add_argument("--anzahl", type=int, default=40, help="Anzahl neu anzulegender Mitglieder")
        parser.add_argument("--ohne-inventar", action="store_true", help="Kein Beispiel-Inventar anlegen")

    def handle(self, *args, **opts):
        try:
            verein = Verein.objects.get(kuerzel=opts["verein"])
        except Verein.DoesNotExist:
            raise CommandError(f"Verein mit Kürzel '{opts['verein']}' nicht gefunden.")

        arten = list(Mitgliedsart.objects.filter(verein=verein))
        if not arten:
            raise CommandError("Der Verein hat noch keine Mitgliedsarten (Ersteinrichtung nicht gelaufen?).")
        arten_nach_name = {a.name: a for a in arten}
        abteilungen = {name: Abteilung.objects.get_or_create(verein=verein, name=name)[0] for name in ABTEILUNGEN}

        heute = date.today()
        neue = []
        for i in range(opts["anzahl"]):
            ist_frau = random.random() < 0.5
            vorname = random.choice(VORNAMEN_F if ist_frau else VORNAMEN_M)
            nachname = random.choice(NACHNAMEN)
            alter = random.randint(16, 85)
            geburtsjahr = heute.year - alter
            eintrittsjahr = random.randint(1975, heute.year - 1)
            if alter < 18:
                art_name = "Jugend"
            elif alter >= 75 and random.random() < 0.3:
                art_name = "Ehrenmitglied"
            else:
                art_name = random.choice(["Aktiv"] * 6 + ["Passiv", "Fördermitglied"])
            art = arten_nach_name.get(art_name) or arten[0]
            ort, plz = random.choice(ORTE)
            m = Mitglied.objects.create(
                verein=verein, anrede="frau" if ist_frau else "herr", vorname=vorname, nachname=nachname,
                geburtsdatum=_zufallsdatum(geburtsjahr, geburtsjahr), eintrittsdatum=_zufallsdatum(eintrittsjahr, eintrittsjahr),
                status="aktiv", mitgliedsart=art, strasse=f"{random.choice(STRASSEN)} {random.randint(1, 60)}",
                plz=plz, ort=ort,
                email=f"{vorname.lower()}.{nachname.lower()}{i}@example.org" if random.random() < 0.7 else "",
                mobil=f"01{random.randint(50, 79)} {random.randint(1000000, 9999999)}" if random.random() < 0.8 else "")
            m.abteilungen.add(abteilungen["Jugendfeuerwehr"] if art_name == "Jugend"
                              else abteilungen["Alters- und Ehrenabteilung"] if art_name == "Ehrenmitglied"
                              else abteilungen[random.choice(ABTEILUNGEN[:-1])])
            neue.append(m)

        faelligkeit = min(date(heute.year, 3, 31), heute - timedelta(days=14))
        bj, _ = Beitragsjahr.objects.get_or_create(
            verein=verein, jahr=heute.year,
            defaults={"faelligkeit": faelligkeit, "alters_stichtag": date(heute.year, 1, 1), "bemerkung": "Testdaten"})
        erstellt, _ = finance_services.beitragsjahr_abrechnen(bj)

        rechnungen = list(Rechnung.objects.filter(verein=verein, typ="beitrag", jahr=heute.year,
                                                  status__in=["offen", "teilbezahlt"]))
        random.shuffle(rechnungen)
        voll = int(len(rechnungen) * 0.5)
        teil = int(len(rechnungen) * 0.15)
        gemahnt = 0
        for idx, r in enumerate(rechnungen):
            if idx < voll:
                Zahlung.objects.create(verein=verein, rechnung=r, betrag=r.betrag,
                                       datum=r.faellig_am - timedelta(days=random.randint(1, 20)))
            elif idx < voll + teil:
                Zahlung.objects.create(verein=verein, rechnung=r, betrag=(r.betrag / 2).quantize(Decimal("0.01")),
                                       datum=r.faellig_am + timedelta(days=random.randint(1, 15)))
                if random.random() < 0.5:
                    finance_services.mahnung_erstellen(r)
                    gemahnt += 1
            # der Rest bleibt unbezahlt -> ueberfaellig, da Faelligkeit in der Vergangenheit liegt

        offen = len(rechnungen) - voll - teil
        inventar_text = ""
        if not opts["ohne_inventar"]:
            inventar_text = f" {self._gegenstaende(verein, heute)} Gegenstände im Inventar angelegt."
        self.stdout.write(self.style.SUCCESS(
            f"{len(neue)} Mitglieder angelegt. Beitragsjahr {heute.year}: {erstellt} Rechnungen erzeugt "
            f"(Fälligkeit {faelligkeit:%d.%m.%Y}), davon {voll} vollständig bezahlt, {teil} teilbezahlt "
            f"({gemahnt} davon mit Mahnung), {offen} komplett offen/überfällig.{inventar_text}"))

    def _gegenstaende(self, verein, heute):
        kategorien = {name: Kategorie.objects.get_or_create(verein=verein, name=name)[0]
                     for name in {g[1] for g in GEGENSTAENDE}}
        standorte = {name: Standort.objects.get_or_create(verein=verein, name=name)[0]
                    for name in {g[2] for g in GEGENSTAENDE}}
        for (bezeichnung, kategorie, standort, hersteller, modell, zustand, alter, preis, verleihbar, kaution,
             leihgebuehr) in GEGENSTAENDE:
            anschaffungsdatum = (_zufallsdatum(heute.year - alter, heute.year - alter) if alter
                                else heute - timedelta(days=random.randint(1, 60)))
            aktueller_wert = (Decimal(str(preis)) * Decimal(str(ZUSTAND_WERTFAKTOR[zustand]))).quantize(Decimal("0.01"))
            Gegenstand.objects.create(
                verein=verein, bezeichnung=bezeichnung, kategorie=kategorien[kategorie], standort=standorte[standort],
                hersteller=hersteller, modell=modell, zustand=zustand, anschaffungsdatum=anschaffungsdatum,
                anschaffungspreis=Decimal(str(preis)), aktueller_wert=aktueller_wert, verleihbar=verleihbar,
                kaution=Decimal(str(kaution)), leihgebuehr=Decimal(str(leihgebuehr)))
        return len(GEGENSTAENDE)
