"""NUR FÜR TEST-/DEMOZWECKE: erzeugt Demo-Veranstaltungen und Demo-Verleihe für alle gängigen Szenarien
(vergangen/kommend, Versammlung mit Tagesordnung und Ergebnissen, Fest mit Schichtplan und Helfer-Selbsteintrag,
Anmeldungen, Kosten, Aufgaben; Verleih reserviert/ausgegeben/überfällig/zurückgegeben/storniert, mit Kaution,
Leihgebühr, Sammelvorgang und Vereinsreservierung für eine Veranstaltung).

Alles Erzeugte ist mit "[Demo]" in den Notizen markiert und lässt sich mit --zuruecksetzen wieder entfernen.
Ergänzt `beispieldaten` (Mitglieder, Beiträge, Inventar), ersetzt es aber nicht - fehlende verleihbare
Gegenstände und Mitglieder werden bei Bedarf selbst angelegt.

Aufruf:  python manage.py demodaten --verein <kuerzel> [--zuruecksetzen]
"""
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.core.models import Verein
from apps.events.models import (Anmeldung, Anwesenheit, Aufgabe, Kostenposition, Schicht, Schichteinsatz,
                                Tagesordnungspunkt, Veranstaltung, Wahlergebnis)
from apps.inventory.models import Gegenstand, Kategorie, Lagerort, Verleih
from apps.members.models import Mitglied, Mitgliedsart

MARKE = "[Demo]"

# (Bezeichnung, Kategorie, Lagerort, Preis, Kaution, Leihgebühr, benötigte Stückzahl)
VERLEIHBAR = [
    ("Stromerzeuger", "Werkzeug", "Lager", 2100, 100, 15, 1),
    ("Faltpavillon 3x3m", "Veranstaltungstechnik", "Lager", 280, 30, 10, 3),
    ("Biertischgarnitur", "Veranstaltungstechnik", "Lager", 95, 20, 5, 6),
    ("Grillwagen", "Veranstaltungstechnik", "Lager", 650, 50, 15, 1),
    ("Kaffeemaschine", "Veranstaltungstechnik", "Jugendraum", 480, 20, 5, 1),
    ("Beamer", "Veranstaltungstechnik", "Jugendraum", 450, 50, 10, 1),
    ("Laptop", "Veranstaltungstechnik", "Jugendraum", 850, 100, 0, 1),
]
NAMEN = [("herr", "Thomas", "Brandt"), ("frau", "Sabine", "Löschner"), ("herr", "Markus", "Wasser"),
         ("frau", "Anja", "Rauch"), ("herr", "Florian", "Schlauch"), ("frau", "Petra", "Hellmann"),
         ("herr", "Dieter", "Kamin"), ("frau", "Julia", "Funke")]


def _dt(tag, stunde, minute=0):
    return timezone.make_aware(datetime.combine(tag, time(stunde, minute)))


class Command(BaseCommand):
    help = "NUR FÜR TESTZWECKE: Demo-Veranstaltungen und Demo-Verleihe für alle Szenarien anlegen."

    def add_arguments(self, parser):
        parser.add_argument("--verein", required=True, help="Kürzel des Vereins")
        parser.add_argument("--zuruecksetzen", action="store_true",
                            help="Vorhandene Demodaten ([Demo]) zuerst entfernen und neu anlegen")

    def handle(self, *args, **opts):
        try:
            verein = Verein.objects.get(kuerzel=opts["verein"])
        except Verein.DoesNotExist:
            raise CommandError(f"Verein mit Kürzel '{opts['verein']}' nicht gefunden.")
        vorhanden = Veranstaltung.objects.filter(verein=verein, notizen__contains=MARKE).exists()
        if vorhanden and not opts["zuruecksetzen"]:
            raise CommandError("Es gibt schon Demodaten. Mit --zuruecksetzen entfernen und neu anlegen.")
        if opts["zuruecksetzen"]:
            self._entfernen(verein)
        self.verein = verein
        self.heute = date.today()
        self.mitglieder = self._mitglieder()
        self.g = self._gegenstaende()
        n_v = self._veranstaltungen()
        n_l = self._verleihe()
        self.stdout.write(self.style.SUCCESS(f"{n_v} Veranstaltungen und {n_l} Verleih-Positionen als Demodaten angelegt."))

    # ---------------------------------------------------------------- Aufräumen / Grunddaten
    def _entfernen(self, verein):
        Verleih.objects.filter(verein=verein, notizen__contains=MARKE).delete()
        Veranstaltung.objects.filter(verein=verein, notizen__contains=MARKE).delete()
        Gegenstand.objects.filter(verein=verein, notizen__contains=MARKE).delete()
        Mitglied.objects.filter(verein=verein, notizen__contains=MARKE).delete()

    def _mitglieder(self):
        liste = list(Mitglied.objects.filter(verein=self.verein, status="aktiv").order_by("id")[:8])
        if len(liste) >= 8:
            return liste
        art = Mitgliedsart.objects.filter(verein=self.verein).first()
        if art is None:
            raise CommandError("Der Verein hat noch keine Mitgliedsarten (Ersteinrichtung nicht gelaufen?).")
        for anrede, vor, nach in NAMEN[len(liste):]:
            liste.append(Mitglied.objects.create(verein=self.verein, anrede=anrede, vorname=vor, nachname=nach,
                                                 status="aktiv", mitgliedsart=art, notizen=MARKE,
                                                 email=f"{vor.lower()}.{nach.lower()}@example.org"))
        return liste

    def _gegenstaende(self):
        """Je Bezeichnung die benötigte Anzahl verleihbarer, einwandfreier Gegenstände (vorhandene werden genutzt)."""
        ergebnis = {}
        for bez, kat, lager, preis, kaution, gebuehr, stueck in VERLEIHBAR:
            vorhanden = list(Gegenstand.objects.filter(verein=self.verein, bezeichnung=bez, verleihbar=True,
                                                       zustand__in=("neu", "gut", "gebrauchsspuren")))
            while len(vorhanden) < stueck:
                vorhanden.append(Gegenstand.objects.create(
                    verein=self.verein, bezeichnung=bez, verleihbar=True, zustand="gut",
                    kategorie=Kategorie.objects.get_or_create(verein=self.verein, name=kat)[0],
                    lagerort=Lagerort.objects.get_or_create(verein=self.verein, name=lager)[0],
                    anschaffungspreis=Decimal(preis), aktueller_wert=Decimal(preis) * Decimal("0.6"),
                    kaution=Decimal(kaution), leihgebuehr=Decimal(gebuehr), notizen=MARKE))
            ergebnis[bez] = vorhanden
        return ergebnis

    # ---------------------------------------------------------------- Veranstaltungen
    def _v(self, **kw):
        return Veranstaltung.objects.create(verein=self.verein, notizen=MARKE, **kw)

    def _veranstaltungen(self):
        h, m = self.heute, self.mitglieder
        tag = lambda n: h + timedelta(days=n)  # noqa: E731

        # 1. Vergangenes, abgeschlossenes Fest mit Schichtplan, Anmeldungen, Ist-Kosten, erledigten Aufgaben
        fest = self._v(titel="Sommerfest (Demo)", art="fest", status="abgeschlossen", beginn=_dt(tag(-45), 14),
                       ende=_dt(tag(-45), 23), ort="Gerätehaus", verantwortlich=m[0], erwartete_teilnehmer=250,
                       oeffentlich=True, beschreibung="Jährliches Sommerfest mit Grillstand, Kaffee und Kuchen.")
        self._schichten(fest, tag(-45), voll=True)
        for i, p in enumerate(m[:5]):
            Anmeldung.objects.create(verein=self.verein, veranstaltung=fest, mitglied=p, personen=1 + i % 3)
        for pos, (art, bez, plan, ist) in enumerate([
                ("einnahme", "Getränkeverkauf", 1800, 2145), ("einnahme", "Speisenverkauf", 1500, 1380),
                ("ausgabe", "Getränke Einkauf", 900, 1020), ("ausgabe", "Fleisch & Brot", 700, 655),
                ("ausgabe", "Miete Toilettenwagen", 250, 250)]):
            Kostenposition.objects.create(verein=self.verein, veranstaltung=fest, art=art, bezeichnung=bez,
                                          plan_betrag=Decimal(plan), ist_betrag=Decimal(ist))
        for t, z in [("Getränke bestellen", 0), ("Helferplan erstellen", 1), ("Aufbau koordinieren", 2)]:
            Aufgabe.objects.create(verein=self.verein, veranstaltung=fest, titel=t, zustaendig=m[z],
                                   faellig=tag(-50 + z), status="erledigt", ergebnis="Erledigt.")

        # 2. Kommende Jahreshauptversammlung (Anmeldung erforderlich, Tagesordnung, gemischte Rückmeldungen)
        jhv = self._v(titel="Jahreshauptversammlung (Demo)", art="versammlung", status="bestaetigt",
                      beginn=_dt(tag(12), 19), ende=_dt(tag(12), 22), ort="Schulungsraum", verantwortlich=m[1],
                      erwartete_teilnehmer=60, anmeldung_erforderlich=True, anmeldeschluss=tag(8),
                      beschreibung="Ordentliche Mitgliederversammlung mit Neuwahlen.")
        for i, titel in enumerate(["Begrüßung und Feststellung der Beschlussfähigkeit", "Bericht des Vorstands",
                                   "Kassenbericht und Entlastung", "Neuwahlen", "Anträge", "Verschiedenes"], start=1):
            Tagesordnungspunkt.objects.create(verein=self.verein, veranstaltung=jhv, position=i, titel=titel)
        for i, (p, st, n) in enumerate([(m[0], "zugesagt", 1), (m[1], "zugesagt", 2), (m[2], "offen", 1),
                                        (m[3], "abgesagt", 1), (m[4], "zugesagt", 1)]):
            Anmeldung.objects.create(verein=self.verein, veranstaltung=jhv, mitglied=p, status=st, personen=n,
                                     bemerkung="Muss früher gehen" if i == 4 else "")
        Anmeldung.objects.create(verein=self.verein, veranstaltung=jhv, name="Gast der Stadtverwaltung", personen=2)
        Aufgabe.objects.create(verein=self.verein, veranstaltung=jhv, titel="Einladung verschicken", zustaendig=m[1],
                               faellig=tag(-3), status="offen")   # überfällig
        Aufgabe.objects.create(verein=self.verein, veranstaltung=jhv, titel="Kassenprüfung abstimmen", zustaendig=m[2],
                               faellig=tag(5), status="arbeit")

        # 3. Vergangene Sitzung mit Protokoll-Material (Tagesordnung, Anwesenheit, Wahlergebnisse)
        sitz = self._v(titel="Vorstandssitzung (Demo)", art="sitzung", status="abgeschlossen",
                       beginn=_dt(tag(-20), 19), ende=_dt(tag(-20), 21), ort="Vereinsheim", verantwortlich=m[1])
        for i, titel in enumerate(["Begrüßung", "Haushaltsplan", "Anschaffung Pavillons", "Verschiedenes"], start=1):
            Tagesordnungspunkt.objects.create(verein=self.verein, veranstaltung=sitz, position=i, titel=titel,
                                              beschreibung="Beschlussvorlage liegt vor." if i == 3 else "")
        for p in m[:5]:
            Anwesenheit.objects.create(verein=self.verein, veranstaltung=sitz, mitglied=p)
        Anwesenheit.objects.create(verein=self.verein, veranstaltung=sitz, name="Gast (Kassenprüfer)")
        Wahlergebnis.objects.create(
            verein=self.verein, veranstaltung=sitz, art="abstimmung", amt="Anschaffung von zwei Pavillons",
            wahlgang="Abstimmung 1", ergebnis="Ja: 4, Nein: 1, Enthaltung: 0",
            details=[["Ja", "4"], ["Nein", "1"], ["Enthaltung", "0"]])
        Wahlergebnis.objects.create(
            verein=self.verein, veranstaltung=sitz, art="wahl", amt="Schriftführer*in", wahlgang="Wahlgang 1",
            ergebnis=f"{m[2].name}: 5, {m[3].name}: 1",
            details=[[m[2].name, "5"], [m[3].name, "1"]])

        # 4. Kommender Tag der offenen Tür: Helfer-Selbsteintrag, teils besetzt, Vereinsreservierung, geplante Kosten
        tdot = self._v(titel="Tag der offenen Tür (Demo)", art="fest", status="geplant", beginn=_dt(tag(21), 10),
                       ende=_dt(tag(21), 17), ort="Gerätehaus", verantwortlich=m[0], erwartete_teilnehmer=400,
                       oeffentlich=True, helfer_eintragung=True,
                       beschreibung="Fahrzeugschau, Vorführungen, Hüpfburg, Kaffee und Kuchen.")
        self._schichten(tdot, tag(21), voll=False)
        for art, bez, plan in [("einnahme", "Spenden", 400), ("einnahme", "Kuchenverkauf", 600),
                               ("ausgabe", "Material Werbung", 150), ("ausgabe", "Getränke", 350)]:
            Kostenposition.objects.create(verein=self.verein, veranstaltung=tdot, art=art, bezeichnung=bez,
                                          plan_betrag=Decimal(plan))
        Aufgabe.objects.create(verein=self.verein, veranstaltung=tdot, titel="Plakate drucken", zustaendig=m[5],
                               faellig=tag(10), status="offen")
        Aufgabe.objects.create(verein=self.verein, veranstaltung=tdot, titel="Fahrzeugschau planen", zustaendig=m[4],
                               faellig=tag(2), status="arbeit")
        self.tdot = tdot

        # 5. Übung mit Anmeldung, Ausflug als Idee, abgesagte Veranstaltung
        self._v(titel="Gemeinschaftsübung Jugendfeuerwehr (Demo)", art="schulung", status="bestaetigt",
                beginn=_dt(tag(6), 17), ende=_dt(tag(6), 19, 30), ort="Übungsgelände", verantwortlich=m[4],
                anmeldung_erforderlich=True, anmeldeschluss=tag(4))
        self._v(titel="Vereinsausflug Freizeitpark (Demo)", art="ausflug", status="idee", beginn=_dt(tag(90), 8),
                ende=_dt(tag(90), 20), ort="Freizeitpark", erwartete_teilnehmer=45)
        self._v(titel="Weihnachtsfeier (Demo)", art="fest", status="abgesagt", beginn=_dt(tag(60), 18),
                ort="Vereinsheim", beschreibung="Wegen Renovierung des Vereinsheims abgesagt.")
        return 7

    def _schichten(self, v, tag, voll):
        """Schichtplan: bei voll=True komplett besetzt (vergangenes Fest), sonst teils offen / nicht freigegeben."""
        plan = [("Aufbau", 8, 12, 4, True), ("Grillstand", 11, 16, 3, True), ("Getränkeausgabe", 12, 18, 3, True),
                ("Kuchentheke", 12, 17, 2, True), ("Abbau", 18, 21, 4, False)]
        namen_gast = ["Karin Gast", "Hans Nachbar", "Lena Jugend"]
        i = 0
        for bez, von, bis, bedarf, frei in plan:
            s = Schicht.objects.create(verein=self.verein, veranstaltung=v, bezeichnung=bez, beginn=_dt(tag, von),
                                       ende=_dt(tag, bis), benoetigt=bedarf, selbsteintrag=frei)
            belegt = bedarf if voll else {"Aufbau": 4, "Grillstand": 1, "Getränkeausgabe": 0}.get(bez, 0)
            for k in range(belegt):
                if k % 4 == 3 and not voll:
                    Schichteinsatz.objects.create(verein=self.verein, schicht=s, name=namen_gast[i % 3],
                                                  kontakt="0170 1234567", selbst_eingetragen=True)
                else:
                    Schichteinsatz.objects.create(verein=self.verein, schicht=s, mitglied=self.mitglieder[(i + k) % 8],
                                                  selbst_eingetragen=(k % 2 == 1), mitglied_angegeben=(k % 2 == 1))
                i += 1

    # ---------------------------------------------------------------- Verleih
    def _verleihe(self):
        h, g, m = self.heute, self.g, self.mitglieder
        n = 0

        def verleih(gegenstand, status, von, bis, **kw):
            nonlocal n
            n += 1
            rueck = kw.pop("rueck", None)
            notiz = kw.pop("notizen", "")
            v = Verleih(verein=self.verein, gegenstand=gegenstand, status=status, von=von, bis=bis,
                        notizen=f"{MARKE} {notiz}".strip(), **kw)
            if status in ("ausgegeben", "zurueckgegeben"):
                v.ausgegeben_am = _dt(von, 9)
                v.ausgegeben_von = "Demo-Verwaltung"
                v.zustand_bei_ausgabe = gegenstand.zustand
            if status == "zurueckgegeben":
                v.zurueckgegeben_am = _dt(bis, 17)
                v.zustand_bei_rueckgabe = rueck or gegenstand.zustand
            v.save()
            return v

        # a) Mitglied leiht privat: laufend, pünktlich (mit Rückgabe-Aufgabe)
        v = verleih(g["Stromerzeuger"][0], "ausgegeben", h - timedelta(days=2), h + timedelta(days=3), entleiher=m[2],
                    zweck="Gartenfest privat")
        v.aufgabe = Aufgabe.objects.create(verein=self.verein, titel="Rückgabe Stromerzeuger", zustaendig=m[2],
                                           faellig=v.bis, status="offen")
        v.save(update_fields=["aufgabe"])

        # b) Extern, überfällig (Ampel rot), Kaution hinterlegt
        verleih(g["Beamer"][0], "ausgegeben", h - timedelta(days=12), h - timedelta(days=5),
                entleiher_name="Schützenverein Musterdorf", entleiher_kontakt="info@schuetzen.example.org",
                zweck="Jahresfeier")

        # c) Sammelvorgang extern: mehrere Gegenstände, reserviert für nächste Woche
        vorgang = uuid.uuid4()
        for p in g["Biertischgarnitur"][:4] + g["Faltpavillon 3x3m"][:2]:
            verleih(p, "reserviert", h + timedelta(days=7), h + timedelta(days=9), vorgang=vorgang,
                    entleiher_name="Gesangverein Eintracht", entleiher_kontakt="0151 2345678",
                    zweck="Sommerkonzert")

        # d) Abgeschlossen, Kaution zurückgezahlt
        verleih(g["Kaffeemaschine"][0], "zurueckgegeben", h - timedelta(days=30), h - timedelta(days=28),
                entleiher=m[3], kaution_zurueckgezahlt=True, zweck="Elternabend")

        # e) Abgeschlossen, mit Mangel -> Kaution einbehalten, Gegenstand Gebrauchsspuren
        verleih(g["Laptop"][0], "zurueckgegeben", h - timedelta(days=40), h - timedelta(days=35),
                entleiher_name="Familie Beispiel", entleiher_kontakt="familie@example.org", kaution_einbehalten=True,
                rueck="gebrauchsspuren", zweck="Foto-Präsentation", notizen="Display zerkratzt")

        # f) Storniert
        verleih(g["Grillwagen"][0], "storniert", h + timedelta(days=14), h + timedelta(days=15),
                entleiher_name="Feuerwehr Nachbarort", zweck="Wegen Terminverschiebung storniert")

        # g) Vereinsreservierung für den Tag der offenen Tür (kein Entleiher, keine Gebühr), später ergänzt
        for p in g["Faltpavillon 3x3m"][:3] + g["Biertischgarnitur"][:6] + g["Grillwagen"][:1] + g["Kaffeemaschine"][:1]:
            if p.pk in {x.gegenstand_id for x in Verleih.objects.filter(
                    verein=self.verein, status__in=("reserviert", "ausgegeben"), von__lte=h + timedelta(days=22),
                    bis__gte=h + timedelta(days=20))}:
                continue
            verleih(p, "reserviert", h + timedelta(days=20), h + timedelta(days=22), veranstaltung=self.tdot,
                    zweck="Ausstattung Tag der offenen Tür")

        # h) Beim Sommerfest verwendet und zurückgegeben (Veranstaltung abgeschlossen)
        sommerfest = Veranstaltung.objects.get(verein=self.verein, notizen=MARKE, titel="Sommerfest (Demo)")
        for p in g["Grillwagen"][:1] + g["Faltpavillon 3x3m"][:2]:
            verleih(p, "zurueckgegeben", h - timedelta(days=46), h - timedelta(days=44), veranstaltung=sommerfest,
                    kaution_zurueckgezahlt=True, zweck="Ausstattung Sommerfest")
        return n
