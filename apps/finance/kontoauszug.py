"""Kontoauszug-Import in mehreren Formaten: CSV (Bank-Exportformate), MT940 (SWIFT) und CAMT.053 (ISO-20022-XML).

Alle drei Formate landen im gleichen Ablauf: Duplikate werden per Prüfsumme erkannt und übersprungen, danach
kann wie bisher automatisch (`services.zuordnen`) offenen Rechnungen zugeordnet werden. Bewusst kein vollständiger
Validator - insbesondere bei MT940 ist das Feld ":86:" von Bank zu Bank unterschiedlich aufgebaut; erkannt werden
die seit der SEPA-Umstellung gängigen deutschen Feldkennungen (SVWZ+, ABWA+/ABWE+, IBAN+). Gelingt das nicht, wird
der komplette Text als Verwendungszweck übernommen, statt die Zeile zu verwerfen."""
import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from .models import Bankumsatz

# ---------------------------------------------------------------- Gemeinsam
def _pruefsumme(d, b, iban, zweck):
    return hashlib.sha1(f"{d}|{b}|{iban}|{zweck}".encode()).hexdigest()


def _anlegen(verein, d, b, name, iban, zweck, **extra):
    """-> True wenn neu angelegt, False wenn Duplikat (bereits importierter Umsatz). **extra erlaubt zusaetzliche
    Felder (z. B. fints_zugang beim FinTS-Abruf)."""
    summe = _pruefsumme(d, b, iban, zweck)
    if Bankumsatz.objects.filter(verein=verein, pruefsumme=summe).exists():
        return False
    Bankumsatz.objects.create(verein=verein, buchungsdatum=d, betrag=b, gegenkonto_name=(name or "")[:200],
                              gegenkonto_iban=iban or "", verwendungszweck=zweck or "", pruefsumme=summe, **extra)
    return True


# ---------------------------------------------------------------- CSV
def _csv_zahl(s):
    s = str(s).strip().replace("€", "").replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    return Decimal(s)


def _csv_datum(s):
    s = str(s).strip()
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Datum nicht lesbar: {s}")


CSV_SPALTEN = {
    "datum": ("buchungstag", "buchungsdatum", "datum", "valuta", "booking date"),
    "betrag": ("betrag", "umsatz", "amount"),
    "name": ("name zahlungsbeteiligter", "beguenstigter/zahlungspflichtiger", "auftraggeber/empfänger", "name",
             "auftraggeber", "zahlungspflichtiger", "beguenstigter", "begünstigter/zahlungspflichtiger"),
    "iban": ("iban zahlungsbeteiligter", "iban", "kontonummer/iban", "iban auftraggeber"),
    "zweck": ("verwendungszweck", "buchungstext", "zweck", "purpose"),
}


def csv_import(verein, dateiinhalt):
    """Importiert einen Kontoauszug im CSV-Format (Semikolon). Gibt (neu, doppelt) zurück."""
    import csv
    import io
    try:
        text = dateiinhalt.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = dateiinhalt.decode("cp1252")
    zeilen = list(csv.reader(io.StringIO(text), delimiter=";"))
    kopf_idx = next((i for i, z in enumerate(zeilen) if any(c.strip().lower() in CSV_SPALTEN["betrag"] for c in z)
                     and any(c.strip().lower() in CSV_SPALTEN["datum"] for c in z)), None)
    if kopf_idx is None:
        raise ValueError("Kopfzeile mit Spalten 'Buchungstag' und 'Betrag' nicht gefunden.")
    kopf = [c.strip().lower() for c in zeilen[kopf_idx]]

    def idx(key):
        return next((kopf.index(n) for n in CSV_SPALTEN[key] if n in kopf), None)
    i_d, i_b, i_n, i_i, i_z = idx("datum"), idx("betrag"), idx("name"), idx("iban"), idx("zweck")
    neu = doppelt = 0
    for z in zeilen[kopf_idx + 1:]:
        if len(z) <= max(i for i in (i_d, i_b) if i is not None) or not z[i_d].strip():
            continue
        try:
            d, b = _csv_datum(z[i_d]), _csv_zahl(z[i_b])
        except (ValueError, InvalidOperation):
            continue
        name = z[i_n].strip() if i_n is not None and i_n < len(z) else ""
        iban = z[i_i].strip().replace(" ", "") if i_i is not None and i_i < len(z) else ""
        zweck = z[i_z].strip() if i_z is not None and i_z < len(z) else ""
        if _anlegen(verein, d, b, name, iban, zweck):
            neu += 1
        else:
            doppelt += 1
    return neu, doppelt


# ---------------------------------------------------------------- MT940 (SWIFT)
RE_61 = re.compile(r"^:61:(\d{6})\d{0,4}(R?[DC])([\d,]+)")
RE_SEPA_TAG = re.compile(r"(EREF|KREF|MREF|CRED|SVWZ|ABWA|ABWE|IBAN|BIC)\+")


def _mt940_datum(s):
    jahr = 2000 + int(s[0:2])
    return date(jahr, int(s[2:4]), int(s[4:6]))


def _mt940_vorzeichen(marker):
    return 1 if marker in ("C", "RD") else -1


def _mt940_86_parsen(text):
    """Löst die seit SEPA üblichen deutschen Feldkennungen (SVWZ+, ABWA+/ABWE+, IBAN+) aus dem freien
    Verwendungszweck-Text; gelingt das nicht, wird der ganze Text als Verwendungszweck übernommen."""
    treffer = list(RE_SEPA_TAG.finditer(text))
    if not treffer:
        return "", "", text.strip()
    felder = {}
    for i, m in enumerate(treffer):
        ende = treffer[i + 1].start() if i + 1 < len(treffer) else len(text)
        felder[m.group(1)] = text[m.end():ende].strip()
    name = felder.get("ABWA") or felder.get("ABWE") or ""
    return name, felder.get("IBAN", ""), felder.get("SVWZ", "")


def mt940_import(verein, dateiinhalt):
    """Importiert einen Kontoauszug im SWIFT-MT940-Format. Gibt (neu, doppelt) zurück."""
    if isinstance(dateiinhalt, bytes):
        try:
            text = dateiinhalt.decode("utf-8")
        except UnicodeDecodeError:
            text = dateiinhalt.decode("cp1252", errors="replace")
    else:
        text = dateiinhalt
    neu = doppelt = 0
    aktuell = None
    gefunden = False

    def _abschliessen():
        nonlocal neu, doppelt
        if aktuell is None:
            return
        name, iban, zweck = _mt940_86_parsen(aktuell["ergaenzung"])
        if _anlegen(verein, aktuell["datum"], aktuell["betrag"], name, iban, zweck or aktuell["ergaenzung"].strip()):
            neu += 1
        else:
            doppelt += 1

    for zeile in text.replace("\r\n", "\n").split("\n"):
        m = RE_61.match(zeile)
        if m:
            _abschliessen()
            gefunden = True
            betrag = Decimal(m.group(3).replace(",", ".")) * _mt940_vorzeichen(m.group(2))
            aktuell = {"datum": _mt940_datum(m.group(1)), "betrag": betrag, "ergaenzung": ""}
        elif zeile.startswith(":86:") and aktuell is not None:
            aktuell["ergaenzung"] += zeile[4:]
        elif aktuell is not None and zeile.strip() and not zeile.startswith(":"):
            aktuell["ergaenzung"] += " " + zeile.strip()
    _abschliessen()
    if not gefunden:
        raise ValueError("Keine Umsatzzeilen (Feld ':61:') in der MT940-Datei gefunden.")
    return neu, doppelt


# ---------------------------------------------------------------- CAMT.053 (ISO 20022)
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


def _find_all(el, name):
    if el is None:
        return []
    return [c for c in el.iter() if _local(c.tag) == name]


def _camt_datum(s):
    try:
        return date.fromisoformat((s or "").strip()[:10])
    except ValueError:
        return None


def camt053_import(verein, dateiinhalt):
    """Importiert einen Kontoauszug im CAMT.053-Format (ISO-20022-XML). Gibt (neu, doppelt) zurück."""
    try:
        root = ET.fromstring(dateiinhalt)
    except ET.ParseError as e:
        raise ValueError(f"CAMT.053-Datei nicht lesbar: {e}")
    eintraege = _find_all(root, "Ntry")
    if not eintraege:
        raise ValueError("Keine Umsätze (Ntry) in der CAMT.053-Datei gefunden.")
    neu = doppelt = 0
    for ntry in eintraege:
        betrag_el = _direct_child(ntry, "Amt")
        richtung_el = _direct_child(ntry, "CdtDbtInd")
        bookgdt = _direct_child(ntry, "BookgDt")
        datum_el = _direct_child(bookgdt, "Dt")
        if datum_el is None:
            datum_el = _direct_child(bookgdt, "DtTm")
        if betrag_el is None or richtung_el is None or datum_el is None:
            continue
        try:
            b = Decimal((betrag_el.text or "0").strip())
        except InvalidOperation:
            continue
        if (richtung_el.text or "").strip().upper() == "DBIT":
            b = -b
        d = _camt_datum(datum_el.text)
        if d is None:
            continue
        name, iban, zweck = "", "", ""
        tx = _find_first(ntry, "TxDtls")
        if tx is not None:
            gegenpartei_tag = "Dbtr" if b > 0 else "Cdtr"
            partei = _find_first(tx, gegenpartei_tag)
            name_el = _direct_child(partei, "Nm") if partei is not None else None
            name = (name_el.text or "").strip() if name_el is not None else ""
            konto_tag = "DbtrAcct" if b > 0 else "CdtrAcct"
            konto = _find_first(tx, konto_tag)
            iban_el = _find_first(konto, "IBAN") if konto is not None else None
            iban = (iban_el.text or "").strip() if iban_el is not None else ""
            zweck = " ".join((z.text or "").strip() for z in _find_all(tx, "Ustrd") if z.text)
        if _anlegen(verein, d, b, name, iban, zweck):
            neu += 1
        else:
            doppelt += 1
    return neu, doppelt


# ---------------------------------------------------------------- Dispatcher
def importieren(verein, dateiname, dateiinhalt):
    """Erkennt das Format (CSV / MT940 / CAMT.053) anhand von Dateiname und Inhalt -> (neu, doppelt, formatname)."""
    name = (dateiname or "").lower()
    kopf = dateiinhalt[:200].lstrip()
    if name.endswith(".xml") or kopf.startswith(b"<?xml") or kopf.startswith(b"<Document"):
        neu, doppelt = camt053_import(verein, dateiinhalt)
        return neu, doppelt, "CAMT.053"
    if name.endswith((".sta", ".mt940", ".940")) or kopf.startswith(b":20:"):
        neu, doppelt = mt940_import(verein, dateiinhalt)
        return neu, doppelt, "MT940"
    if name.endswith((".csv", ".txt")):
        neu, doppelt = csv_import(verein, dateiinhalt)
        return neu, doppelt, "CSV"
    raise ValueError("Dateiformat nicht erkannt. Unterstützt werden CSV, MT940 (.sta) und CAMT.053 (.xml).")
