"""ZUGFeRD/Factur-X-Ausgabe (PDF mit eingebetteter CII-XML, Profil EN16931) für Rechnungen dieser Vereinsverwaltung.

Nutzt die Bibliothek `factur-x` (github.com/akretion/factur-x), die die eingebettete XML nach den offiziellen
EN16931-Business-Terms aufbaut und automatisch gegen das amtliche XML-Schema (XSD) prüft, bevor sie in die
bestehende PDF-Rechnung eingebettet wird - das ist eine echte strukturelle Validierung, kein handgeschriebenes
XML mehr. Was damit NICHT geprüft wird: die vollständigen EN16931-Geschäftsregeln (Schematron), die offiziell
nur mit dem KoSIT-Prüfwerkzeug (Java) bzw. einem Saxon-Server geprüft werden können - das ist hier bewusst nicht
eingebunden (zusätzliche Infrastruktur, siehe Abwägung im Handbuch). Ebenso wird die Trägerdatei nicht auf echte
PDF/A-3-Konformität geprüft (z. B. mit veraPDF) - die meisten empfangenden Systeme lesen ohnehin nur die
eingebettete XML-Datei aus, für eine amtliche Langzeitarchivierungs-Zusage würde das aber nicht ausreichen.

Bewusst pauschal umsatzsteuerbefreit (Kategorie "E"): diese Software führt keine Umsatzsteuersätze je Position
(Vereinsrechnungen sind überwiegend im ideellen Bereich umsatzsteuerfrei, § 4 UStG). Vor dem Versand an eine
Stelle mit E-Rechnungspflicht bzw. bei tatsächlich umsatzsteuerpflichtigen Vorgängen (wirtschaftlicher
Geschäftsbetrieb) bitte mit einem offiziellen Prüfwerkzeug gegenprüfen bzw. einen Steuerberater hinzuziehen."""
from decimal import Decimal

from facturx import generate_from_binary
from facturx.generate_xml import generate_cii_xml

from .pdf import rechnung_pdf

LEVEL = "en16931"


def _betrag(wert):
    return f"{Decimal(wert):.2f}"


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


def _cii_data_dict(rechnung):
    """-> data_dict nach den EN16931-Business-Terms (BT-...), wie von facturx.generate_cii_xml erwartet."""
    v = rechnung.verein
    positionen = list(rechnung.positionen.all())
    zwischensumme = sum((p.betrag for p in positionen), Decimal("0"))
    strasse, plz, ort = _anschrift_zerlegen(rechnung.empfaenger_anschrift)

    zeilen = [{
        "BT-126": str(i), "BT-153": p.text[:300], "BT-129": _betrag(p.menge), "BT-130": "C62",
        "BT-146": _betrag(p.einzelpreis), "BT-151": "E", "BT-131": _betrag(p.betrag),
    } for i, p in enumerate(positionen, start=1)]

    d = {
        "BT-1": rechnung.nummer or f"ENTWURF-{rechnung.pk}",
        "BT-2": rechnung.datum,
        "BT-3": "381" if rechnung.betrag < 0 else "380",
        "BT-5": "EUR",
        "BT-27": v.name,
        "BT-40": "DE",
        "BT-44": rechnung.empfaenger_name or "-",
        "BT-55": "DE",
        # BT-72 (tatsächliches Lieferdatum) wird immer gesetzt - ohne jedes Feld im Lieferabschnitt
        # (kein Lieferort, kein Lieferdatum) erzeugt die facturx-Bibliothek ein leeres, laut Schema aber
        # nicht "nillable" ApplicableHeaderTradeDelivery-Element und die XSD-Prüfung schlägt fehl.
        "BT-72": rechnung.zeitraum_bis or rechnung.datum,
        "BG-23": [{
            "BT-116": _betrag(zwischensumme), "BT-117": "0.00", "BT-118": "E",
            "BT-120": "Steuerbefreiung nach § 4 UStG (ideeller Bereich) - bitte prüfen",
        }],
        "BG-25": zeilen,
        "BT-106": _betrag(zwischensumme),
        "BT-109": _betrag(zwischensumme),
        "BT-110": "0.00", "BT-110-1": "EUR",
        "BT-112": _betrag(zwischensumme),
        "BT-115": _betrag(zwischensumme),
    }
    if v.anschrift:
        d["BT-35"] = v.anschrift
    if v.ort:
        d["BT-37"] = v.ort
    if v.plz:
        d["BT-38"] = v.plz
    if v.steuernummer:
        d["BT-32"] = v.steuernummer
    if rechnung.faellig_am:
        d["BT-9"] = rechnung.faellig_am
    if strasse:
        d["BT-50"] = strasse
    if ort:
        d["BT-52"] = ort
    if plz:
        d["BT-53"] = plz
    if v.iban:
        d["BT-81"] = "58"  # SEPA-Überweisung
        d["BT-84"] = v.iban.replace(" ", "")
        if v.bankname:
            d["BT-85"] = v.bankname
        if v.bic:
            d["BT-86"] = v.bic
    return d


def zugferd_xml(rechnung):
    """-> CII-XML-Bytes, bereits gegen das offizielle EN16931/Factur-X-Schema (XSD) validiert."""
    return generate_cii_xml(_cii_data_dict(rechnung), level=LEVEL, check_xsd=True, check_schematron=False)


def zugferd_pdf(rechnung):
    """-> PDF-Bytes (ZUGFeRD/Factur-X, Profil EN16931) für eine Rechnung dieser Software: die normale
    PDF-Rechnung mit eingebetteter, XSD-validierter CII-XML (Dateiname im PDF: „factur-x.xml“)."""
    xml_bytes = zugferd_xml(rechnung)
    pdf_bytes = rechnung_pdf(rechnung)
    return generate_from_binary(pdf_bytes, xml_bytes, flavor="factur-x", level=LEVEL, check_xsd=True,
                                check_schematron=False)
