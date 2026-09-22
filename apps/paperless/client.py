"""Minimaler Client für die Paperless-ngx-REST-API (Dokumenten-Upload + Status-Abfrage).

Aufbau nach der offiziellen API-Dokumentation (docs.paperless-ngx.com/api). NICHT gegen eine laufende
Instanz getestet - bitte zuerst mit dem Verbindungstest prüfen.
"""
import requests

RESSOURCEN = {"korrespondent": "correspondents", "dokumenttyp": "document_types", "tag": "tags"}


class PaperlessFehler(Exception):
    pass


class PaperlessClient:
    def __init__(self, verbindung, timeout=30):
        self.v = verbindung
        self.basis = verbindung.url.rstrip("/")
        self.timeout = timeout
        self.s = requests.Session()
        self.s.verify = verbindung.tls_pruefen
        self.s.headers["Authorization"] = f"Token {verbindung.api_token}"

    def _anfrage(self, methode, pfad, **kw):
        try:
            r = self.s.request(methode, f"{self.basis}{pfad}", timeout=self.timeout, **kw)
        except requests.RequestException as e:
            raise PaperlessFehler(f"Server nicht erreichbar: {e}")
        return r

    def verbindung_testen(self):
        r = self._anfrage("get", "/api/documents/?page_size=1")
        if r.status_code == 401:
            raise PaperlessFehler("Anmeldung fehlgeschlagen (API-Token prüfen).")
        if r.status_code != 200:
            raise PaperlessFehler(f"Unerwartete Antwort (HTTP {r.status_code}): {r.text[:200]}")
        return "Verbindung erfolgreich."

    def _id_ermitteln(self, art, name):
        """Sucht ein Objekt (Korrespondent/Dokumenttyp/Tag) per Namen, legt es bei Bedarf an -> ID."""
        ressource = RESSOURCEN[art]
        r = self._anfrage("get", f"/api/{ressource}/", params={"name__iexact": name})
        if r.status_code != 200:
            raise PaperlessFehler(f"{art.capitalize()} „{name}“ konnte nicht gesucht werden (HTTP {r.status_code}).")
        treffer = (r.json() or {}).get("results") or []
        if treffer:
            return treffer[0]["id"]
        r = self._anfrage("post", f"/api/{ressource}/", json={"name": name})
        if r.status_code not in (200, 201):
            raise PaperlessFehler(f"{art.capitalize()} „{name}“ konnte nicht angelegt werden "
                                  f"(HTTP {r.status_code}): {r.text[:200]}")
        return r.json()["id"]

    def dokument_senden(self, dateiname, inhalt, *, titel=None, erstellt=None, korrespondent=None,
                        dokumenttyp=None, tags=None):
        """Lädt eine Datei hoch -> UUID der Verarbeitungsaufgabe (Consumption-Task)."""
        daten = {}
        if titel:
            daten["title"] = titel
        if erstellt:
            daten["created"] = erstellt.isoformat()
        if korrespondent:
            daten["correspondent"] = self._id_ermitteln("korrespondent", korrespondent)
        if dokumenttyp:
            daten["document_type"] = self._id_ermitteln("dokumenttyp", dokumenttyp)
        tag_ids = [self._id_ermitteln("tag", t) for t in (tags or [])]
        if tag_ids:
            daten["tags"] = tag_ids  # requests sendet Listenwerte als Mehrfachfeld (tags=1&tags=2&…)
        r = self._anfrage("post", "/api/documents/post_document/", data=daten,
                          files={"document": (dateiname, inhalt)})
        if r.status_code != 200:
            raise PaperlessFehler(f"Upload fehlgeschlagen (HTTP {r.status_code}): {r.text[:300]}")
        try:
            return str(r.json()).strip('"')
        except ValueError:
            return r.text.strip().strip('"')

    def aufgabe_status(self, task_id):
        """-> dict mit mindestens 'status' (PENDING/STARTED/SUCCESS/FAILURE) und 'ergebnis', oder None."""
        r = self._anfrage("get", "/api/tasks/", params={"task_id": task_id})
        if r.status_code != 200:
            return None
        treffer = r.json() or []
        if not treffer:
            return None
        t = treffer[0]
        return {"status": t.get("status"), "ergebnis": t.get("result") or "",
                "dokument_id": t.get("related_document")}
