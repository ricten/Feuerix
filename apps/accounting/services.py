from datetime import date
from decimal import Decimal

from django.db.models import Case, DecimalField, F, Sum, When

from .models import SPHAEREN, SPHAEREN_LABEL, Buchung, Buchungskategorie, Konto

NULL = Decimal("0")

STANDARD_KATEGORIEN = [  # (Name, Art, Sphäre, Sortierung)
    ("Mitgliedsbeiträge", "einnahme", "ideell", 10), ("Spenden", "einnahme", "ideell", 20),
    ("Zuschüsse / Fördermittel", "einnahme", "ideell", 30), ("Veranstaltungseinnahmen", "einnahme", "wirtschaft", 40),
    ("Zinsen und Kapitalerträge", "einnahme", "vermoegen", 50), ("Sonstige Einnahmen", "einnahme", "ideell", 90),
    ("Aufwandsentschädigungen", "ausgabe", "ideell", 10), ("Veranstaltungskosten", "ausgabe", "wirtschaft", 20),
    ("Verwaltung, Porto, Büro", "ausgabe", "ideell", 30), ("Versicherungen", "ausgabe", "ideell", 40),
    ("Beiträge an Verbände", "ausgabe", "ideell", 50), ("Anschaffungen / Ausstattung", "ausgabe", "ideell", 60),
    ("Raum- und Nebenkosten", "ausgabe", "ideell", 70), ("Bankgebühren", "ausgabe", "ideell", 80),
    ("Rücklastschriften / Beitragskorrekturen", "ausgabe", "ideell", 85),
    ("Erstattungen / Rückzahlungen", "ausgabe", "ideell", 87), ("Sonstige Ausgaben", "ausgabe", "ideell", 90),
]


def standardkonten_anlegen(verein):
    Konto.objects.get_or_create(verein=verein, name="Bankkonto", defaults={"typ": "bank"})
    Konto.objects.get_or_create(verein=verein, name="Barkasse", defaults={"typ": "bar"})


def standardkategorien_anlegen(verein):
    for name, typ, sph, sort in STANDARD_KATEGORIEN:
        Buchungskategorie.objects.get_or_create(verein=verein, name=name, typ=typ,
                                                defaults={"sphaere": sph, "sortierung": sort})


# ---------------------------------------------------------------- Berechnung
def _vorzeichen():
    return Sum(Case(When(typ="einnahme", then=F("betrag")), default=-F("betrag"),
                    output_field=DecimalField(max_digits=14, decimal_places=2)))


def _vorjahr(d):
    try:
        return d.replace(year=d.year - 1)
    except ValueError:
        return d.replace(year=d.year - 1, day=28)


def _kategorien(verein, von, bis, typ):
    """{kategorie_id: Summe} im Zeitraum."""
    qs = Buchung.objects.filter(verein=verein, typ=typ, datum__gte=von, datum__lte=bis).values("kategorie_id") \
        .annotate(s=Sum("betrag"))
    return {r["kategorie_id"]: r["s"] for r in qs}


def berichtsdaten(b):
    """Alle Zahlen eines Kassenberichts (inkl. Vorjahresvergleich, Sphären, Kontenübersicht, Soll/Ist-Bestände)."""
    v, von, bis = b.verein, b.von, b.bis
    vvon, vbis = _vorjahr(von), _vorjahr(bis)
    konten = []
    for k in Konto.objects.filter(verein=v, aktiv=True):
        anfang = k.eroeffnungsbestand + (Buchung.objects.filter(konto=k, datum__gte=k.eroeffnungsdatum, datum__lt=von)
                                         .aggregate(s=_vorzeichen())["s"] or NULL)
        ein = Buchung.objects.filter(konto=k, typ="einnahme", datum__gte=von, datum__lte=bis).aggregate(s=Sum("betrag"))["s"] or NULL
        aus = Buchung.objects.filter(konto=k, typ="ausgabe", datum__gte=von, datum__lte=bis).aggregate(s=Sum("betrag"))["s"] or NULL
        konten.append({"name": k.name, "typ": k.typ, "anfang": anfang, "einnahmen": ein, "ausgaben": aus,
                       "ende": anfang + ein - aus})
    anfang = sum((k["anfang"] for k in konten), NULL)
    ein = sum((k["einnahmen"] for k in konten), NULL)
    aus = sum((k["ausgaben"] for k in konten), NULL)

    def gruppen(typ):
        akt, vor = _kategorien(v, von, bis, typ), _kategorien(v, vvon, vbis, typ)
        kats = Buchungskategorie.objects.filter(verein=v, typ=typ)
        out = []
        for sph, label in SPHAEREN:
            zeilen = [(k.name, akt.get(k.pk, NULL), vor.get(k.pk, NULL)) for k in kats if k.sphaere == sph
                      and (akt.get(k.pk) or vor.get(k.pk))]
            if zeilen:
                out.append({"sphaere": sph, "label": label, "zeilen": zeilen,
                            "summe": sum((z[1] for z in zeilen), NULL), "vorjahr": sum((z[2] for z in zeilen), NULL)})
        return out

    ein_g, aus_g = gruppen("einnahme"), gruppen("ausgabe")
    sphaeren = []
    for sph, label in SPHAEREN:
        e = next((g["summe"] for g in ein_g if g["sphaere"] == sph), NULL)
        a = next((g["summe"] for g in aus_g if g["sphaere"] == sph), NULL)
        if e or a:
            sphaeren.append((label, e, a, e - a))
    bar_soll = sum((k["ende"] for k in konten if k["typ"] == "bar"), NULL)
    bank_soll = sum((k["ende"] for k in konten if k["typ"] == "bank"), NULL)
    ist = {"bar_soll": bar_soll, "bank_soll": bank_soll,
           "bar_ist": b.kassenbestand_gezaehlt, "bank_ist": b.bankbestand_laut_auszug}
    ist["bar_diff"] = None if b.kassenbestand_gezaehlt is None else b.kassenbestand_gezaehlt - bar_soll
    ist["bank_diff"] = None if b.bankbestand_laut_auszug is None else b.bankbestand_laut_auszug - bank_soll
    buchungen = Buchung.objects.filter(verein=v, datum__gte=von, datum__lte=bis).select_related("kategorie", "konto") \
        .order_by("datum", "id")
    vj_ein = Buchung.objects.filter(verein=v, typ="einnahme", datum__gte=vvon, datum__lte=vbis).aggregate(s=Sum("betrag"))["s"] or NULL
    vj_aus = Buchung.objects.filter(verein=v, typ="ausgabe", datum__gte=vvon, datum__lte=vbis).aggregate(s=Sum("betrag"))["s"] or NULL
    return {"konten": konten, "anfang": anfang, "einnahmen": ein, "ausgaben": aus, "ende": anfang + ein - aus,
            "ueberschuss": ein - aus, "einnahmen_gruppen": ein_g, "ausgaben_gruppen": aus_g, "sphaeren": sphaeren,
            "ist": ist, "buchungen": buchungen, "vorjahr": {"einnahmen": vj_ein, "ausgaben": vj_aus, "von": vvon, "bis": vbis},
            "ohne_beleg": buchungen.filter(quelle="manuell", beleg="").count(), "anzahl": buchungen.count()}


# ---------------------------------------------------------------- Übernahme aus anderen Modulen
def _kat(verein, name, typ):
    k = Buchungskategorie.objects.filter(verein=verein, name=name, typ=typ).first()
    if k is None:
        k = Buchungskategorie.objects.create(verein=verein, name=name, typ=typ)
    return k


def uebernehmen(verein, von, bis):
    """Erzeugt Buchungen aus Zahlungen, Geldspenden, ausgezahlten Aufwandsentschädigungen und Veranstaltungs-Istwerten.
    Idempotent (jede Quelle wird nur einmal gebucht); gesperrte Zeiträume werden übersprungen."""
    from apps.allowances.models import Aufwandsentschaedigung
    from apps.donations.models import Spende
    from apps.events.models import Kostenposition
    from apps.finance.models import Zahlung

    standardkonten_anlegen(verein)
    bank = Konto.objects.filter(verein=verein, typ="bank", aktiv=True).first()
    bar = Konto.objects.filter(verein=verein, typ="bar", aktiv=True).first() or bank
    zaehler = {"zahlung": 0, "spende": 0, "aufwand": 0, "kosten": 0, "gesperrt": 0, "vor_eroeffnung": 0}

    def buche(quelle, qid, datum, typ, betrag, konto, kat, text, veranstaltung=None):
        if Buchung.objects.filter(verein=verein, quelle=quelle, quelle_id=qid).exists():
            return
        if konto is None:
            return
        b = Buchung(verein=verein, datum=datum, typ=typ, betrag=betrag, konto=konto, kategorie=kat, text=text[:250],
                    quelle=quelle, quelle_id=qid, veranstaltung=veranstaltung)
        if b.gesperrt:
            zaehler["gesperrt"] += 1
            return
        if datum < konto.eroeffnungsdatum:
            zaehler["vor_eroeffnung"] += 1
            return
        b.save()
        zaehler[quelle] += 1

    for z in Zahlung.objects.filter(verein=verein, datum__gte=von, datum__lte=bis).select_related("rechnung"):
        konto = bar if z.art == "bar" else bank
        wer = z.rechnung.empfaenger_name or ""
        if z.art == "rueckzahlung":
            buche("zahlung", z.pk, z.datum, "ausgabe", abs(z.betrag), konto,
                  _kat(verein, "Erstattungen / Rückzahlungen", "ausgabe"), f"Rückzahlung {z.rechnung.nummer} {wer}")
        elif z.ruecklastschrift:
            buche("zahlung", z.pk, z.datum, "ausgabe", z.betrag, konto, _kat(verein, "Rücklastschriften / Beitragskorrekturen", "ausgabe"),
                  f"Rücklastschrift {z.rechnung.nummer} {wer}")
        else:
            name = "Mitgliedsbeiträge" if z.rechnung.typ == "beitrag" else "Sonstige Einnahmen"
            buche("zahlung", z.pk, z.datum, "einnahme", z.betrag, konto, _kat(verein, name, "einnahme"),
                  f"Zahlung {z.rechnung.nummer} {wer}")
    for s in Spende.objects.filter(verein=verein, datum__gte=von, datum__lte=bis, art="geld"):
        buche("spende", s.pk, s.datum, "einnahme", s.betrag, bank, _kat(verein, "Spenden", "einnahme"),
              f"Spende {s.name_des_spenders}")
    for a in Aufwandsentschaedigung.objects.filter(verein=verein, status="ausgezahlt", ausgezahlt_am__gte=von,
                                                   ausgezahlt_am__lte=bis).select_related("empfaenger"):
        buche("aufwand", a.pk, a.ausgezahlt_am, "ausgabe", a.betrag, bank, _kat(verein, "Aufwandsentschädigungen", "ausgabe"),
              f"{a.get_art_display().split(' (')[0]}: {a.empfaenger.name}")
    for k in Kostenposition.objects.filter(verein=verein, ist_betrag__isnull=False, ist_betrag__gt=0,
                                           veranstaltung__beginn__date__gte=von,
                                           veranstaltung__beginn__date__lte=bis).select_related("veranstaltung"):
        ein = k.art == "einnahme"
        buche("kosten", k.pk, k.veranstaltung.beginn.date(), "einnahme" if ein else "ausgabe", k.ist_betrag, bank,
              _kat(verein, "Veranstaltungseinnahmen" if ein else "Veranstaltungskosten", "einnahme" if ein else "ausgabe"),
              f"{k.veranstaltung.titel}: {k.bezeichnung}", veranstaltung=k.veranstaltung)
    return zaehler
