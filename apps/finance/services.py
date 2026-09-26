"""Fachlogik Finanzen: Beitragsberechnung, Rechnungslauf, Storno, Gutschrift, Mahnung, Bankzuordnung."""
import re
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import timezone

from apps.members.models import Mitglied

from .models import Bankumsatz, Beitragsjahr, Beitragsregel, Mahnung, Rechnung, Rechnungsposition, Zahlung


def rechnung_fertig(rechnung):
    """Automatische Paperless-Übergabe (falls aktiviert) - stört das Ausstellen nie."""
    try:
        from apps.paperless import auto
        auto.fertiges_dokument("rechnung", rechnung.pk, rechnung.verein)
    except Exception:
        pass


# ------------------------------------------------------------------ Beitrag
def berechne_beitrag(mitglied, bj, regeln=None):
    """-> (betrag, grund). Reihenfolge: individueller Beitrag > erste passende Regel > Standard der Mitgliedsart."""
    if mitglied.individueller_beitrag is not None:
        return mitglied.individueller_beitrag, "individueller Beitrag"
    alter = mitglied.alter(bj.alters_stichtag)
    if regeln is None:
        regeln = Beitragsregel.objects.filter(verein=bj.verein, aktiv=True)
    for r in sorted(regeln, key=lambda x: -x.prioritaet):
        if r.gueltig_ab_jahr and bj.jahr < r.gueltig_ab_jahr:
            continue
        if r.gueltig_bis_jahr and bj.jahr > r.gueltig_bis_jahr:
            continue
        if r.mitgliedsart_id and r.mitgliedsart_id != mitglied.mitgliedsart_id:
            continue
        if r.nur_familie and not mitglied.familie_id:
            continue
        if r.alter_von is not None or r.alter_bis is not None:
            if alter is None:
                continue
            if r.alter_von is not None and alter < r.alter_von:
                continue
            if r.alter_bis is not None and alter > r.alter_bis:
                continue
        if r.nur_familie and not mitglied.ist_familienzahler:
            return Decimal("0"), f"im Familienbeitrag enthalten ({r.name})"
        return r.betrag, r.name
    if mitglied.mitgliedsart_id:
        return mitglied.mitgliedsart.jahresbeitrag, f"Standard {mitglied.mitgliedsart.name}"
    return None, "keine Mitgliedsart / Regel"


@transaction.atomic
def beitragsjahr_abrechnen(bj):
    """Erzeugt für alle beitragspflichtigen Mitglieder eine Beitragsrechnung (Betrag wird eingefroren)."""
    v, jahr = bj.verein, bj.jahr
    anfang, ende = date(jahr, 1, 1), date(jahr, 12, 31)
    regeln = list(Beitragsregel.objects.filter(verein=v, aktiv=True))
    erstellt, uebersprungen = 0, []
    mitglieder = Mitglied.objects.filter(verein=v, status__in=["aktiv", "ruhend"]).select_related("mitgliedsart")
    for m in mitglieder:
        if m.eintrittsdatum and m.eintrittsdatum > ende:
            continue
        if m.austrittsdatum and m.austrittsdatum < anfang:
            continue
        if Rechnung.objects.filter(verein=v, mitglied=m, typ="beitrag", jahr=jahr).exclude(status="storniert").exists():
            continue
        betrag, grund = berechne_beitrag(m, bj, regeln)
        if betrag is None:
            uebersprungen.append((m, grund))
            continue
        if betrag == 0:
            continue
        art = m.mitgliedsart.name if m.mitgliedsart_id else "Mitgliedsbeitrag"
        r = Rechnung.objects.create(
            verein=v, typ="beitrag", status="offen", mitglied=m, datum=date.today(), faellig_am=bj.faelligkeit,
            jahr=jahr, zeitraum_von=anfang, zeitraum_bis=ende,
            kopftext=v.rechnung_kopftext or f"Mitgliedsnummer: {m.mitgliedsnummer}\nBeitragsart: {art}")
        Rechnungsposition.objects.create(verein=v, rechnung=r, text=f"Vereinsbeitrag {jahr} ({art}), "
                                         f"{anfang:%d.%m.%Y} – {ende:%d.%m.%Y}", menge=1, einzelpreis=betrag)
        rechnung_fertig(r)
        erstellt += 1
    bj.abgerechnet_am = timezone.now()
    bj.save(update_fields=["abgerechnet_am", "geaendert"])
    return erstellt, uebersprungen


# ------------------------------------------------------------------ Storno / Gutschrift
@transaction.atomic
def storniere(rechnung):
    if rechnung.status in ("entwurf", "storniert", "verbucht") or rechnung.typ in ("storno", "gutschrift"):
        raise ValueError("Diese Rechnung kann nicht storniert werden.")
    s = Rechnung.objects.create(verein=rechnung.verein, typ="storno", status="verbucht", mitglied=rechnung.mitglied,
                                empfaenger_name=rechnung.empfaenger_name,
                                empfaenger_anschrift=rechnung.empfaenger_anschrift, datum=date.today(),
                                jahr=rechnung.jahr, storno_von=rechnung,
                                kopftext=f"Storno zur Rechnung {rechnung.nummer}")
    for p in rechnung.positionen.all():
        Rechnungsposition.objects.create(verein=rechnung.verein, rechnung=s, text=f"Storno: {p.text}", menge=p.menge,
                                         einzelpreis=-p.einzelpreis, steuersatz=p.steuersatz)
    rechnung.status = "storniert"
    rechnung.save(update_fields=["status", "geaendert"])
    s.refresh_from_db()
    rechnung_fertig(s)
    return s


@transaction.atomic
def gutschrift(rechnung, betrag, text):
    betrag = Decimal(betrag)
    if betrag <= 0 or betrag > rechnung.betrag:
        raise ValueError("Der Gutschriftsbetrag muss zwischen 0 und dem Rechnungsbetrag liegen.")
    g = Rechnung.objects.create(verein=rechnung.verein, typ="gutschrift", status="verbucht",
                                mitglied=rechnung.mitglied, empfaenger_name=rechnung.empfaenger_name,
                                empfaenger_anschrift=rechnung.empfaenger_anschrift, datum=date.today(),
                                jahr=rechnung.jahr, storno_von=rechnung,
                                kopftext=f"Gutschrift zur Rechnung {rechnung.nummer}")
    Rechnungsposition.objects.create(verein=rechnung.verein, rechnung=g, text=text or "Gutschrift", menge=1,
                                     einzelpreis=-betrag)
    g.refresh_from_db()
    rechnung_fertig(g)
    return g


@transaction.atomic
def rechnung_erstellen(verein, positionen, mitglied=None, empfaenger_name="", empfaenger_anschrift="", bemerkung=""):
    """Erzeugt sofort eine offene Rechnung (kein Entwurf) für sonstige Leistungen außerhalb des Beitragswesens
    (z. B. Leihgebühren) - positionen: Liste von (text, menge, einzelpreis) oder (text, menge, einzelpreis,
    steuersatz), falls Umsatzsteuer ausgewiesen werden soll (Standard ohne Angabe: 0 %)."""
    r = Rechnung.objects.create(verein=verein, typ="individuell", status="offen", mitglied=mitglied,
                                empfaenger_name=empfaenger_name, empfaenger_anschrift=empfaenger_anschrift,
                                datum=date.today(), bemerkung=bemerkung)
    for text, menge, einzelpreis, *rest in positionen:
        Rechnungsposition.objects.create(verein=verein, rechnung=r, text=text, menge=menge, einzelpreis=einzelpreis,
                                         steuersatz=rest[0] if rest else Decimal("0"))
    r.refresh_from_db()
    rechnung_fertig(r)
    return r


@transaction.atomic
def rechnung_positionen_hinzufuegen(rechnung, positionen):
    """Ergänzt eine bereits bestehende Rechnung um weitere Positionen (z. B. wenn ein mehrteiliger Vorgang in
    mehreren Schritten abgeschlossen wird und trotzdem alles auf einer Rechnung landen soll) - positionen wie
    bei rechnung_erstellen()."""
    for text, menge, einzelpreis, *rest in positionen:
        Rechnungsposition.objects.create(verein=rechnung.verein, rechnung=rechnung, text=text, menge=menge,
                                         einzelpreis=einzelpreis, steuersatz=rest[0] if rest else Decimal("0"))
    rechnung.refresh_from_db()
    return rechnung


def mahnung_erstellen(rechnung, gebuehr=Decimal("0"), frist_tage=14):
    letzte = rechnung.mahnungen.order_by("-stufe").first()
    stufe = min((letzte.stufe if letzte else 0) + 1, 3)
    return Mahnung.objects.create(verein=rechnung.verein, rechnung=rechnung, stufe=stufe, datum=date.today(),
                                  frist=date.today() + timedelta(days=frist_tage), gebuehr=gebuehr)


# ------------------------------------------------------------------ Mail
def rechnung_mailen(rechnung):
    from .pdf import rechnung_pdf
    m = rechnung.mitglied
    if not (m and m.email):
        raise ValueError("Kein Mitglied mit E-Mail-Adresse hinterlegt.")
    mail = EmailMessage(
        subject=f"{rechnung.verein.name}: Rechnung {rechnung.nummer}",
        body=f"Guten Tag {m.name},\n\nanbei erhalten Sie Ihre Rechnung {rechnung.nummer}.\n\n"
             f"Mit freundlichen Grüßen\n{rechnung.verein.name}",
        from_email=settings.DEFAULT_FROM_EMAIL, to=[m.email])
    mail.attach(f"{rechnung.nummer}.pdf", rechnung_pdf(rechnung), "application/pdf")
    mail.send()
    rechnung.versendet_am = timezone.now()
    rechnung.save(update_fields=["versendet_am", "geaendert"])


# ------------------------------------------------------------------ Bank
RE_RECHNUNG = re.compile(r"RE-(\d{4})-(\d+)")
RE_MITGLIED = re.compile(r"MITGLIED(?:SNR|SNUMMER|SNR\.)?[\s.:-]*(\d+)", re.I)


def zuordnen(verein, umsaetze=None):
    """Ordnet Bankumsätze offenen Rechnungen zu: Rechnungsnr. > Mitgliedsnr. > IBAN. Gibt (zugeordnet, manuell) zurück."""
    if umsaetze is None:
        umsaetze = Bankumsatz.objects.filter(verein=verein, status__in=["neu", "manuell"])
    iban_map = {}
    for m in Mitglied.objects.filter(verein=verein).exclude(iban=""):
        if m.iban:
            iban_map.setdefault(m.iban.replace(" ", "").upper(), []).append(m)
    ok = manuell = 0
    for u in umsaetze:
        text = (u.verwendungszweck or "").upper()
        rechnung, kandidaten = None, []
        mo = RE_RECHNUNG.search(text)
        if mo:
            nr = f"RE-{mo.group(1)}-{int(mo.group(2)):06d}"
            rechnung = Rechnung.objects.filter(verein=verein, nummer=nr).exclude(
                status__in=["entwurf", "storniert", "verbucht"]).first()
        if rechnung is None:
            m = None
            mm = RE_MITGLIED.search(text)
            if mm:
                m = Mitglied.objects.filter(verein=verein, mitgliedsnummer=int(mm.group(1))).first()
            if m is None:
                treffer = iban_map.get((u.gegenkonto_iban or "").replace(" ", "").upper(), [])
                if len(treffer) == 1:
                    m = treffer[0]
            if m is not None:
                kandidaten = list(Rechnung.objects.filter(verein=verein, mitglied=m, status__in=["offen", "teilbezahlt"]))
                jm = re.search(r"\b(20\d{2})\b", text)
                if jm and len(kandidaten) > 1:
                    kandidaten = [r for r in kandidaten if r.jahr == int(jm.group(1))] or kandidaten
                if len(kandidaten) > 1:
                    passend = [r for r in kandidaten if r.offen_betrag == abs(u.betrag)]
                    kandidaten = passend if len(passend) == 1 else kandidaten
                if len(kandidaten) == 1:
                    rechnung = kandidaten[0]
        if rechnung is None:
            u.status = "manuell"
            u.save(update_fields=["status", "geaendert"])
            manuell += 1
            continue
        ist_rueck = u.betrag < 0
        if ist_rueck and not re.search(r"R.?CKLAST|RETOURE|R.?CKBUCH", text):
            u.status = "manuell"
            u.save(update_fields=["status", "geaendert"])
            manuell += 1
            continue
        with transaction.atomic():
            Zahlung.objects.create(verein=verein, rechnung=rechnung, datum=u.buchungsdatum, betrag=abs(u.betrag),
                                   art="lastschrift" if ist_rueck else "ueberweisung", ruecklastschrift=ist_rueck,
                                   referenz=u.verwendungszweck[:200], bankumsatz=u)
            u.status = "zugeordnet"
            u.save(update_fields=["status", "geaendert"])
        ok += 1
    return ok, manuell
