"""XRechnung-Ausgabe (UBL-Invoice-XML) für Rechnungen dieser Vereinsverwaltung.

Bewusst kein zertifizierter/vollständig validierter EN16931-Generator: Die gängigen Pflichtfelder (Verkäufer,
Käufer, Positionen, Summen, IBAN) werden gefüllt, aber eine differenzierte Umsatzsteuer-Aufschlüsselung fehlt,
da diese Software selbst keine Umsatzsteuersätze je Position führt (Vereinsrechnungen sind überwiegend im
ideellen Bereich umsatzsteuerfrei, § 4 UStG) - alle Positionen werden daher pauschal als steuerbefreit (Code "E")
ausgewiesen. Vor dem Versand an eine Stelle mit E-Rechnungspflicht bitte mit einem offiziellen Prüfwerkzeug
(z. B. dem KoSIT-Validator) gegenprüfen und bei tatsächlich umsatzsteuerpflichtigen Vorgängen (wirtschaftlicher
Geschäftsbetrieb) die Steuerangaben von einem Steuerberater prüfen lassen."""
import xml.etree.ElementTree as ET

UBL_NS = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
CAC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
CBC_NS = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"

ET.register_namespace("", UBL_NS)
ET.register_namespace("cac", CAC_NS)
ET.register_namespace("cbc", CBC_NS)


def _el(parent, tag, ns, text=None):
    e = ET.SubElement(parent, f"{{{ns}}}{tag}")
    if text is not None:
        e.text = str(text)
    return e


def _cbc(parent, tag, text=None):
    return _el(parent, tag, CBC_NS, text)


def _cac(parent, tag):
    return _el(parent, tag, CAC_NS)


def _betrag(parent, tag, wert):
    e = _cbc(parent, tag, f"{wert:.2f}")
    e.set("currencyID", "EUR")
    return e


def _anschrift_zerlegen(text):
    """Grobe Trennung einer freien Anschrift in Straße und 'PLZ Ort' (letzte Zeile) - kein Adressvalidator."""
    zeilen = [z.strip() for z in (text or "").splitlines() if z.strip()]
    if len(zeilen) >= 2:
        strasse, letzte = zeilen[0], zeilen[-1]
        teile = letzte.split(" ", 1)
        if len(teile) == 2 and teile[0].isdigit():
            return strasse, teile[0], teile[1]
        return strasse, "", letzte
    return (zeilen[0] if zeilen else ""), "", ""


def _partei(parent, tag_name, name, strasse="", plz="", ort="", steuernummer=None):
    partei_wrapper = _cac(parent, tag_name)
    partei = _cac(partei_wrapper, "Party")
    if strasse or ort or plz:
        adresse = _cac(partei, "PostalAddress")
        if strasse:
            _cbc(adresse, "StreetName", strasse)
        if ort:
            _cbc(adresse, "CityName", ort)
        if plz:
            _cbc(adresse, "PostalZone", plz)
        _cbc(_cac(adresse, "Country"), "IdentificationCode", "DE")
    if steuernummer:
        steuer = _cac(partei, "PartyTaxScheme")
        _cbc(steuer, "CompanyID", steuernummer)
        _cbc(_cac(steuer, "TaxScheme"), "ID", "FC")
    rechtstraeger = _cac(partei, "PartyLegalEntity")
    _cbc(rechtstraeger, "RegistrationName", name or "-")
    return partei_wrapper


def xrechnung_xml(rechnung):
    """-> XML-Bytes (UBL-Invoice, XRechnung-Struktur) für eine Rechnung dieser Software."""
    v = rechnung.verein
    root = ET.Element(f"{{{UBL_NS}}}Invoice")
    _cbc(root, "CustomizationID", "urn:cen.eu:en16931:2017")
    _cbc(root, "ID", rechnung.nummer or f"ENTWURF-{rechnung.pk}")
    _cbc(root, "IssueDate", rechnung.datum.isoformat())
    if rechnung.faellig_am:
        _cbc(root, "DueDate", rechnung.faellig_am.isoformat())
    _cbc(root, "InvoiceTypeCode", "381" if rechnung.betrag < 0 else "380")
    _cbc(root, "DocumentCurrencyCode", "EUR")
    if rechnung.bemerkung:
        _cbc(root, "Note", rechnung.bemerkung)

    _partei(root, "AccountingSupplierParty", v.name, v.anschrift, v.plz, v.ort, v.steuernummer)
    strasse, plz, ort = _anschrift_zerlegen(rechnung.empfaenger_anschrift)
    _partei(root, "AccountingCustomerParty", rechnung.empfaenger_name, strasse, plz, ort)

    if v.iban:
        zahlung = _cac(root, "PaymentMeans")
        _cbc(zahlung, "PaymentMeansCode", "58")  # SEPA-Überweisung
        konto = _cac(zahlung, "PayeeFinancialAccount")
        _cbc(konto, "ID", v.iban.replace(" ", ""))
        if v.bankname:
            _cbc(konto, "Name", v.bankname)

    taxtotal = _cac(root, "TaxTotal")
    _betrag(taxtotal, "TaxAmount", 0)
    teilsumme = _cac(taxtotal, "TaxSubtotal")
    _betrag(teilsumme, "TaxableAmount", rechnung.betrag)
    _betrag(teilsumme, "TaxAmount", 0)
    kategorie = _cac(teilsumme, "TaxCategory")
    _cbc(kategorie, "ID", "E")
    _cbc(kategorie, "Percent", "0")
    _cbc(kategorie, "TaxExemptionReason", "Steuerbefreiung nach § 4 UStG (ideeller Bereich) - bitte prüfen")
    _cbc(_cac(kategorie, "TaxScheme"), "ID", "VAT")

    summen = _cac(root, "LegalMonetaryTotal")
    _betrag(summen, "LineExtensionAmount", rechnung.betrag)
    _betrag(summen, "TaxExclusiveAmount", rechnung.betrag)
    _betrag(summen, "TaxInclusiveAmount", rechnung.betrag)
    _betrag(summen, "PayableAmount", rechnung.betrag)

    for i, p in enumerate(rechnung.positionen.all(), start=1):
        zeile = _cac(root, "InvoiceLine")
        _cbc(zeile, "ID", i)
        menge = _cbc(zeile, "InvoicedQuantity", p.menge)
        menge.set("unitCode", "C62")
        _betrag(zeile, "LineExtensionAmount", p.betrag)
        posten = _cac(zeile, "Item")
        _cbc(posten, "Name", p.text[:300])
        posten_steuer = _cac(posten, "ClassifiedTaxCategory")
        _cbc(posten_steuer, "ID", "E")
        _cbc(posten_steuer, "Percent", "0")
        _cbc(_cac(posten_steuer, "TaxScheme"), "ID", "VAT")
        preis = _cac(zeile, "Price")
        _betrag(preis, "PriceAmount", p.einzelpreis)

    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="UTF-8")
