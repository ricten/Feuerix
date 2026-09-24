"""EXPERIMENTELL: FinTS-Abruf mit TAN-Unterstuetzung fuer die Weboberflaeche.

Ablauf ueber zwei HTTP-Anfragen, da eine laufende FinTS-Sitzung nicht ueber Requests hinweg im Speicher gehalten
werden kann: 1) PIN eingeben, Abruf starten - verlangt die Bank eine TAN, wird der Dialog per pause_dialog()/
deconstruct() eingefroren und (zusammen mit der PIN) in der Session gespeichert; 2) TAN eingeben - der Dialog wird
per resume_dialog()/send_tan() fortgesetzt. Die PIN liegt dabei kurzzeitig in der (serverseitigen) Session, nicht
in der Datenbank - das ist bei diesem Ablauf technisch nicht vermeidbar (python-fints braucht die PIN, um die
Bank-Nachrichten erneut zu signieren) und wird nach Abschluss (Erfolg oder endgueltiger Fehler) sofort geloescht.

Gegen keine echte Bank getestet - vor dem produktiven Einsatz mit der eigenen Bank pruefen."""
from base64 import b64decode, b64encode

from django.conf import settings

from . import kontoauszug
from .models import Bankumsatz

SESSION_KEY = "fints_tan"


class FinTSAblaufFehler(Exception):
    pass


def neuer_client(zugang, pin, from_data=None):
    from fints.client import FinTS3PinTanClient

    if not settings.FINTS_PRODUCT_ID:
        raise FinTSAblaufFehler("FINTS_PRODUCT_ID ist nicht gesetzt (siehe Einstellungen des Servers).")
    return FinTS3PinTanClient(zugang.blz, zugang.kennung, pin, zugang.bank_url,
                              product_id=settings.FINTS_PRODUCT_ID, from_data=from_data)


def _importieren(verein, konto, transaktionen):
    neu = 0
    for t in transaktionen:
        d = t.data
        betrag = d["amount"].amount
        zweck = d.get("purpose") or ""
        iban = d.get("applicant_iban") or ""
        if kontoauszug._anlegen(verein, d["date"], betrag, d.get("applicant_name") or "", iban, zweck):
            neu += 1
    return neu


def _konto_zu_dict(konto):
    return dict(konto._asdict())


def _konto_von_dict(d):
    from fints.models import SEPAAccount
    return SEPAAccount(**d)


def naechster_schritt(client, verein, von, bis, konten_rest):
    """Muss innerhalb von `with client:` bzw. `with client.resume_dialog(...):` aufgerufen werden.

    konten_rest=None bedeutet: Die Kontenliste wurde noch nicht abgerufen (ganz am Anfang des Ablaufs, oder direkt
    nachdem eine TAN auf Ebene der Dialog-Initialisierung aufgeloest wurde).

    Rueckgabe: ("tan", NeedTANResponse, konten_rest) wenn eine TAN noetig ist (konten_rest ist dann der Rest der
    noch abzurufenden Konten, das aktuelle Konto steht an Position 0), sonst ("fertig", anzahl_neuer_umsaetze, None).
    """
    from fints.client import NeedTANResponse

    if konten_rest is None:
        if client.init_tan_response:
            return "tan", client.init_tan_response, None
        konten_rest = client.get_sepa_accounts()
    neu = 0
    while konten_rest:
        konto = konten_rest[0]
        antwort = client.get_transactions(konto, von, bis)
        if isinstance(antwort, NeedTANResponse):
            return "tan", antwort, konten_rest
        neu += _importieren(verein, konto, antwort)
        konten_rest = konten_rest[1:]
    return "fertig", neu, None


def naechster_schritt_nach_tan(client, verein, von, bis, konten_rest, ergebnis):
    """Wie naechster_schritt(), aber die Antwort fuer konten_rest[0] (bzw. fuer die Dialog-Initialisierung, wenn
    konten_rest None ist) liegt bereits vor (Ergebnis von client.send_tan())."""
    from fints.client import NeedTANResponse

    if isinstance(ergebnis, NeedTANResponse):
        return "tan", ergebnis, konten_rest
    if konten_rest is None:
        # Die aufgeloeste TAN betraf die Dialog-Initialisierung, nicht einen konkreten Abruf.
        return naechster_schritt(client, verein, von, bis, None)
    neu = _importieren(verein, konten_rest[0], ergebnis)
    status, wert, rest = naechster_schritt(client, verein, von, bis, konten_rest[1:])
    if status == "fertig":
        wert += neu
    return status, wert, rest


def zustand_speichern(request, zugang, pin, von, bis, client, tan_response, konten_rest, dialog_data):
    request.session[SESSION_KEY] = {
        "zugang_pk": zugang.pk,
        "pin": pin,
        "von": von.isoformat(),
        "bis": bis.isoformat(),
        "client_data": b64encode(client.deconstruct()).decode(),
        "dialog_data": b64encode(dialog_data).decode(),
        "response_data": b64encode(tan_response.get_data()).decode(),
        "phase": "init" if konten_rest is None else "konten",
        "konten_rest": [_konto_zu_dict(k) for k in konten_rest] if konten_rest else [],
        "challenge": tan_response.challenge or "",
        "challenge_html": str(tan_response.challenge_html or ""),
        "challenge_matrix_png": b64encode(tan_response.challenge_matrix[1]).decode()
        if tan_response.challenge_matrix and tan_response.challenge_matrix[0] == "image/png" else None,
        "decoupled": bool(tan_response.decoupled),
    }


def zustand_laden(request):
    return request.session.get(SESSION_KEY)


def zustand_loeschen(request):
    request.session.pop(SESSION_KEY, None)


def client_und_dialog_aus_zustand(zustand, zugang):
    from fints.client import NeedRetryResponse

    client = neuer_client(zugang, zustand["pin"], from_data=b64decode(zustand["client_data"]))
    dialog_data = b64decode(zustand["dialog_data"])
    tan_response = NeedRetryResponse.from_data(b64decode(zustand["response_data"]))
    konten_rest = [_konto_von_dict(d) for d in zustand["konten_rest"]] if zustand["phase"] == "konten" else None
    return client, dialog_data, tan_response, konten_rest
