"""E-Rechnungen (XRechnung als reines XML, ZUGFeRD/Faktur-X als PDF mit eingebettetem XML) einlesen: die für
das Kassenbuch wichtigsten Angaben (Nummer, Datum, Betrag, Aussteller) extrahieren, damit eine empfangene
Rechnung nicht abgetippt werden muss, sondern als vorausgefüllte Buchung mit Beleg abgelegt werden kann.

Bewusst kein vollständiger EN16931-Validator: es wird nach bekannten Feldnamen gesucht (unabhängig vom exakten
XML-Pfad), damit sowohl XRechnung/UBL als auch ZUGFeRD/CII in ihren gängigen Ausprägungen funktionieren. Wer die
Datei einliest, prüft die übernommenen Werte ohnehin noch einmal, bevor die Buchung gespeichert wird."""
import io
import xml.etree.ElementTree as ET
from datetime import datetime
from decimal import Decimal, InvalidOperation


def _local(tag):
    return tag.split("}")[-1] if "}" in tag else tag


def _direct_child(el, name):
    if el is None:
        return None
    for c in el:
        if _local(c.tag) == name:
            return c
    return None


def _find_first(el, name):
    if el is None:
        return None
    for c in el.iter():
        if _local(c.tag) == name:
            return c
    return None


def _find_any(el, *namen):
    for name in namen:
        treffer = _find_first(el, name)
        if treffer is not None and (treffer.text or "").strip():
            return treffer
    return None


def _datum_parsen(s):
    if not s:
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _zahl_parsen(s):
    if not s:
        return None
    try:
        return Decimal(s.strip().replace(",", "."))
    except InvalidOperation:
        return None


def xml_aus_datei(dateiname, inhalt):
    """-> XML-Bytes oder None. Bei einer PDF wird die eingebettete E-Rechnung (ZUGFeRD/Faktur-X) gesucht,
    bei einer .xml-Datei wird der Inhalt direkt zurückgegeben."""
    name = (dateiname or "").lower()
    if name.endswith(".xml"):
        return inhalt
    if name.endswith(".pdf"):
        from pypdf import PdfReader
        try:
            reader = PdfReader(io.BytesIO(inhalt))
        except Exception:
            return None
        for anhang_name in reader.attachments:
            if anhang_name.lower().endswith(".xml"):
                dateien = reader.attachments[anhang_name]
                return dateien[0] if isinstance(dateien, list) else dateien
    return None


def parse_rechnung(xml_bytes):
    """-> dict mit format/nummer/datum/betrag/verkaeufer/waehrung, oder None wenn das XML nicht lesbar ist."""
    if not xml_bytes:
        return None
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None
    wurzel = _local(root.tag)
    if wurzel == "Invoice":
        nummer_el = _direct_child(root, "ID")
        datum_el = _direct_child(root, "IssueDate")
        waehrung_el = _direct_child(root, "DocumentCurrencyCode")
        summe_el = _find_any(root, "PayableAmount", "TaxInclusiveAmount")
        supplier = _find_first(root, "AccountingSupplierParty")
        verkaeufer_el = _find_any(supplier, "RegistrationName", "Name") if supplier is not None else None
        formatname = "XRechnung (UBL)"
    elif wurzel == "CrossIndustryInvoice":
        doc = _find_first(root, "ExchangedDocument")
        nummer_el = _direct_child(doc, "ID") if doc is not None else _find_first(root, "ID")
        datum_el = _find_first(root, "DateTimeString")
        waehrung_el = _find_first(root, "InvoiceCurrencyCode")
        summe_el = _find_any(root, "DuePayableAmount", "GrandTotalAmount", "TaxInclusiveAmount")
        supplier = _find_first(root, "SellerTradeParty")
        verkaeufer_el = _find_first(supplier, "Name") if supplier is not None else None
        formatname = "ZUGFeRD/XRechnung (CII)"
    else:
        return None  # kein bekanntes E-Rechnungsformat (weder UBL-Invoice noch CII-CrossIndustryInvoice)
    return {
        "format": formatname,
        "nummer": (nummer_el.text or "").strip() if nummer_el is not None else "",
        "datum": _datum_parsen(datum_el.text if datum_el is not None else None),
        "betrag": _zahl_parsen(summe_el.text if summe_el is not None else None),
        "verkaeufer": (verkaeufer_el.text or "").strip() if verkaeufer_el is not None else "",
        "waehrung": (waehrung_el.text or "EUR").strip() if waehrung_el is not None else "EUR",
    }
