"""SEPA-Lastschrift-Sammeleinzug (pain.008.001.02) für Mitgliedsbeiträge und andere offene Rechnungen.

Erzeugt nur die Einzugsdatei zum Hochladen ins Online-Banking - die tatsächliche Gutschrift/Rücklastschrift
wird weiterhin über den normalen Kontoauszug-Import verbucht (der Bank-Rückmeldeprozess ist nicht Teil dieser
Software). Aufbau nach der offiziellen ISO-20022-Spezifikation (pain.008.001.02), wie sie von deutschen
Banken für den SEPA-Basislastschrifteinzug (CORE) akzeptiert wird.
"""
import re
import xml.etree.ElementTree as ET
from decimal import Decimal

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.core.models import naechste_nummer

from .models import Rechnung, SepaEinzug, SepaEinzugPosition

PAIN008_NS = "urn:iso:std:iso:20022:tech:xsd:pain.008.001.02"
ERLAUBTE_ZEICHEN = re.compile(r"[^A-Za-z0-9/\-?:().,'+ ]")


def _sepa_kennung(s, maxlen=35):
    """SEPA-Referenzen (EndToEndId, PmtInfId, MsgId) dürfen nur den eingeschränkten lateinischen Zeichensatz
    enthalten - unzulässige Zeichen (z. B. Umlaute) werden entfernt."""
    return ERLAUBTE_ZEICHEN.sub("", s or "").strip()[:maxlen] or "NOTPROVIDED"


def _betrag(d):
    return f"{Decimal(d):.2f}"


def _el(parent, tag, text=None):
    e = ET.SubElement(parent, tag)
    if text is not None:
        e.text = str(text)
    return e


def _finanzinstitut(parent, tag, bic):
    """<tag><FinInstnId><BIC>…</BIC></FinInstnId></tag> bzw. mit Othr/Id=NOTPROVIDED, wenn kein BIC bekannt ist
    (seit 2016 für SEPA-Inlandszahlungen nicht mehr zwingend erforderlich, das Element selbst aber schon)."""
    fininstnid = _el(_el(parent, tag), "FinInstnId")
    if bic:
        _el(fininstnid, "BIC", bic)
    else:
        _el(_el(fininstnid, "Othr"), "Id", "NOTPROVIDED")


def eligible_rechnungen(verein):
    """Offene/teilbezahlte Rechnungen von Mitgliedern mit Zahlungsart Lastschrift und vollständigem SEPA-Mandat."""
    return Rechnung.objects.filter(
        verein=verein, status__in=["offen", "teilbezahlt"], mitglied__zahlungsart="lastschrift",
    ).exclude(mitglied__iban="").exclude(mitglied__mandatsreferenz="").exclude(
        mitglied__mandatsdatum__isnull=True).select_related("mitglied").order_by("mitglied__nachname", "-datum")


def pain008_xml(verein, positionen, faelligkeitsdatum, nachricht_id):
    """positionen: Liste von SepaEinzugPosition (mit .mitglied/.rechnung vorab geladen) -> XML-Bytes."""
    root = ET.Element("Document")
    root.set("xmlns", PAIN008_NS)
    root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
    init = _el(root, "CstmrDrctDbtInitn")

    gesamt_summe = sum((p.betrag for p in positionen), Decimal("0"))
    hdr = _el(init, "GrpHdr")
    _el(hdr, "MsgId", _sepa_kennung(nachricht_id))
    _el(hdr, "CreDtTm", timezone.now().strftime("%Y-%m-%dT%H:%M:%S"))
    _el(hdr, "NbOfTxs", len(positionen))
    _el(hdr, "CtrlSum", _betrag(gesamt_summe))
    _el(_el(hdr, "InitgPty"), "Nm", verein.name[:70])

    # CORE-Lastschriften mit unterschiedlichem Sequenztyp (Erst-/Folgelastschrift) müssen laut SEPA-Regelwerk
    # in getrennten PmtInf-Blöcken stehen - sie dürfen nicht innerhalb eines Blocks gemischt werden.
    for i, seqtyp in enumerate(("FRST", "RCUR"), start=1):
        gruppe = [p for p in positionen if p.sequenztyp == seqtyp]
        if not gruppe:
            continue
        pmt = _el(init, "PmtInf")
        _el(pmt, "PmtInfId", _sepa_kennung(f"{nachricht_id}-{seqtyp}"))
        _el(pmt, "PmtMtd", "DD")
        _el(pmt, "NbOfTxs", len(gruppe))
        _el(pmt, "CtrlSum", _betrag(sum((p.betrag for p in gruppe), Decimal("0"))))
        typinf = _el(pmt, "PmtTpInf")
        _el(_el(typinf, "SvcLvl"), "Cd", "SEPA")
        _el(_el(typinf, "LclInstrm"), "Cd", "CORE")
        _el(typinf, "SeqTp", seqtyp)
        _el(pmt, "ReqdColltnDt", faelligkeitsdatum.isoformat())
        _el(_el(pmt, "Cdtr"), "Nm", verein.name[:70])
        _el(_el(_el(pmt, "CdtrAcct"), "Id"), "IBAN", verein.iban.replace(" ", ""))
        _finanzinstitut(pmt, "CdtrAgt", verein.bic)
        _el(pmt, "ChrgBr", "SLEV")
        othr = _el(_el(_el(pmt, "CdtrSchmeId"), "Id"), "PrvtId")
        othr = _el(othr, "Othr")
        _el(othr, "Id", verein.glaeubiger_id.replace(" ", ""))
        _el(_el(othr, "SchmeNm"), "Prtry", "SEPA")

        for p in gruppe:
            tx = _el(pmt, "DrctDbtTxInf")
            _el(_el(tx, "PmtId"), "EndToEndId", _sepa_kennung(p.rechnung.nummer or f"RG{p.rechnung_id}"))
            _el(tx, "InstdAmt", _betrag(p.betrag)).set("Ccy", "EUR")
            mndt = _el(_el(tx, "DrctDbtTx"), "MndtRltdInf")
            _el(mndt, "MndtId", _sepa_kennung(p.mandatsreferenz))
            _el(mndt, "DtOfSgntr", p.mandatsdatum.isoformat())
            _finanzinstitut(tx, "DbtrAgt", p.mitglied.bic)
            _el(_el(tx, "Dbtr"), "Nm", (p.mitglied.kontoinhaber or p.mitglied.name)[:70])
            _el(_el(_el(tx, "DbtrAcct"), "Id"), "IBAN", p.mitglied.iban.replace(" ", ""))
            zweck = f"Mitgliedsbeitrag {p.rechnung.jahr}" if p.rechnung.jahr else "Vereinsbeitrag"
            if p.rechnung.nummer:
                zweck += f" – Rechnung {p.rechnung.nummer}"
            _el(_el(tx, "RmtInf"), "Ustrd", zweck[:140])

    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="UTF-8")


@transaction.atomic
def einzug_erstellen(verein, faelligkeitsdatum, rechnung_ids):
    """Erstellt einen SEPA-Einzug für die angegebenen Rechnungen (Betrag = jeweils offener Betrag) und generiert
    die pain.008-Datei. Erstlastschrift (FRST) für Mitglieder, die noch nie in einem Einzug dieses Vereins
    enthalten waren, sonst Folgelastschrift (RCUR)."""
    rechnungen = list(eligible_rechnungen(verein).filter(pk__in=rechnung_ids))
    if not rechnungen:
        raise ValueError("Keine gültigen Rechnungen ausgewählt.")
    if not verein.iban or not verein.glaeubiger_id:
        raise ValueError("Bitte zuerst IBAN und Gläubiger-ID des Vereins unter Verwaltung › Verein hinterlegen.")
    bereits_eingezogen = set(SepaEinzugPosition.objects.filter(verein=verein).values_list("mitglied_id", flat=True))
    jahr = faelligkeitsdatum.year
    nummer = f"EZG-{jahr}-{naechste_nummer(verein, 'EZG', jahr):06d}"
    einzug = SepaEinzug.objects.create(verein=verein, nummer=nummer, faelligkeitsdatum=faelligkeitsdatum)
    positionen = []
    for r in rechnungen:
        m = r.mitglied
        positionen.append(SepaEinzugPosition(
            verein=verein, einzug=einzug, rechnung=r, mitglied=m, betrag=r.offen_betrag,
            mandatsreferenz=m.mandatsreferenz, mandatsdatum=m.mandatsdatum,
            sequenztyp="RCUR" if m.pk in bereits_eingezogen else "FRST"))
        bereits_eingezogen.add(m.pk)
    SepaEinzugPosition.objects.bulk_create(positionen)
    xml_bytes = pain008_xml(verein, positionen, faelligkeitsdatum, nummer)
    einzug.datei.save(f"{nummer}.xml", ContentFile(xml_bytes), save=False)
    einzug.anzahl = len(positionen)
    einzug.summe = sum((p.betrag for p in positionen), Decimal("0"))
    einzug.save(update_fields=["datei", "anzahl", "summe", "geaendert"])
    return einzug
