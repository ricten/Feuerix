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

    # ---- Benutzer und Gruppen (Vorstands-Abgleich; benoetigt einen Token mit Administratorrechten)
    def _liste(self, pfad, params):
        r = self._anfrage("get", pfad, params=params)
        if r.status_code in (401, 403):
            raise PaperlessFehler("Keine Berechtigung für die Benutzerverwaltung (Token eines Paperless-"
                                  "Administrators erforderlich).")
        if r.status_code != 200:
            raise PaperlessFehler(f"{pfad}: unerwartete Antwort (HTTP {r.status_code}): {r.text[:200]}")
        daten = r.json() or {}
        return daten.get("results", []) if isinstance(daten, dict) else daten

    def _schreiben(self, methode, pfad, daten):
        r = self._anfrage(methode, pfad, json=daten)
        if r.status_code in (401, 403):
            raise PaperlessFehler("Keine Berechtigung für die Benutzerverwaltung (Token eines Paperless-"
                                  "Administrators erforderlich).")
        if r.status_code not in (200, 201):
            raise PaperlessFehler(f"{pfad}: HTTP {r.status_code}: {r.text[:300]}")
        return r.json()

    def gruppe_sicherstellen(self, name, rechte):
        """-> ID der Gruppe; wird mit den Rechten `rechte` (Paperless-Rechtenamen) angelegt, falls sie fehlt."""
        treffer = self._liste("/api/groups/", {"name__iexact": name})
        if treffer:
            return treffer[0]["id"]
        return self._schreiben("post", "/api/groups/", {"name": name, "permissions": list(rechte)})["id"]

    def benutzer_suchen(self, benutzername):
        """-> dict des Benutzers oder None."""
        treffer = self._liste("/api/users/", {"username__iexact": benutzername})
        return treffer[0] if treffer else None

    def benutzer_anlegen(self, daten):
        return self._schreiben("post", "/api/users/", daten)["id"]

    def benutzer_aendern(self, benutzer_id, daten):
        return self._schreiben("patch", f"/api/users/{int(benutzer_id)}/", daten)

    def gruppen_ohne(self, gruppen_ids, gruppenname):
        """Gruppenliste ohne die Gruppe `gruppenname` (falls vorhanden)."""
        treffer = self._liste("/api/groups/", {"name__iexact": gruppenname})
        entfernen = {g["id"] for g in treffer}
        return [g for g in gruppen_ids if g not in entfernen]

    def benutzer_lesen(self, benutzer_id):
        r = self._anfrage("get", f"/api/users/{int(benutzer_id)}/")
        return r.json() if r.status_code == 200 else None

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

    def dokument_finden(self, md5):
        """Sucht in Paperless ein Dokument mit dieser Datei-Prüfsumme (MD5 der Originaldatei) -> ID oder None."""
        r = self._anfrage("get", "/api/documents/", params={"checksum__iexact": md5, "page_size": 1})
        if r.status_code != 200:
            raise PaperlessFehler(f"Duplikatprüfung fehlgeschlagen (HTTP {r.status_code}): {r.text[:200]}")
        treffer = (r.json() or {}).get("results") or []
        return treffer[0]["id"] if treffer else None

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
        if isinstance(treffer, dict):   # neuere Paperless-Versionen: paginierte Antwort
            treffer = treffer.get("results") or []
        if not treffer:
            return None
        t = treffer[0]
        return {"status": str(t.get("status") or "").upper(), "ergebnis": t.get("result") or "",
                "dokument_id": t.get("related_document")}
