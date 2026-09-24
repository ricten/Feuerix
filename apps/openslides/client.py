"""Minimaler Client für die OpenSlides-4-API (Auth-Service + Action-Service).

Aufbau nach der offiziellen Dokumentation (openslides-auth-service, openslides-backend/docs/actions).
NICHT gegen eine laufende Instanz getestet - bitte zuerst mit dem Verbindungstest prüfen.
"""
import requests


class OpenSlidesFehler(Exception):
    pass


class OSClient:
    def __init__(self, verbindung, timeout=30):
        self.v = verbindung
        self.basis = verbindung.url.rstrip("/")
        self.timeout = timeout
        self.s = requests.Session()
        self.s.verify = verbindung.tls_pruefen
        self.token = None

    def login(self):
        try:
            r = self.s.post(f"{self.basis}/system/auth/login", json={
                "username": self.v.benutzername, "password": self.v.passwort}, timeout=self.timeout)
        except requests.RequestException as e:
            raise OpenSlidesFehler(f"Server nicht erreichbar: {e}")
        if r.status_code != 200:
            raise OpenSlidesFehler(f"Anmeldung fehlgeschlagen (HTTP {r.status_code}): {r.text[:200]}")
        token = r.headers.get("authentication")
        if not token:
            try:
                token = r.json().get("token")
            except ValueError:
                token = None
        if not token:
            raise OpenSlidesFehler("Anmeldung ohne Token beantwortet – OpenSlides-Version/Adresse prüfen.")
        self.token = token
        return True

    def action(self, name, daten, _erneut=True):
        """Führt eine Backend-Action aus und gibt die Ergebnisliste der ersten Action zurück."""
        if not self.token:
            self.login()
        try:
            r = self.s.post(f"{self.basis}/system/action/handle_request",
                            json=[{"action": name, "data": daten}],
                            headers={"Authentication": self.token, "Content-Type": "application/json"},
                            timeout=self.timeout)
        except requests.RequestException as e:
            raise OpenSlidesFehler(f"Server nicht erreichbar: {e}")
        if r.status_code in (401, 403) and _erneut:
            self.token = None
            return self.action(name, daten, _erneut=False)
        try:
            js = r.json()
        except ValueError:
            raise OpenSlidesFehler(f"Unerwartete Antwort (HTTP {r.status_code}): {r.text[:200]}")
        if r.status_code != 200 or not js.get("success", False):
            raise OpenSlidesFehler(str(js.get("message") or js)[:400])
        res = js.get("results") or [[]]
        return res[0] if res else []

    def erstelle(self, name, daten):
        """Action, die genau ein Objekt anlegt -> ID."""
        res = self.action(name, [daten])
        try:
            return int(res[0]["id"])
        except (IndexError, KeyError, TypeError, ValueError):
            raise OpenSlidesFehler(f"Keine ID in der Antwort: {res}")

    def abfragen(self, anfrage, _erneut=True):
        """Einmalige (nicht-streamende) Lese-Abfrage über den Autoupdate-Dienst (single=1) - fuer Daten, die
        keine Action liefert (z. B. Wahlergebnisse). `anfrage` ist eine Liste von Request-Objekten nach dem
        Schema des openslides-autoupdate-service (collection/ids/fields, mit optional verschachtelten
        relation-list/generic-relation-Feldern fuer Verknuepfungen in einer einzigen Anfrage). Die Antwort ist ein
        flaches Mapping "kollektion/id/feld" -> Wert."""
        if not self.token:
            self.login()
        try:
            r = self.s.post(f"{self.basis}/system/autoupdate?single=1", json=anfrage,
                            headers={"Authentication": self.token, "Content-Type": "application/json"},
                            timeout=self.timeout)
        except requests.RequestException as e:
            raise OpenSlidesFehler(f"Server nicht erreichbar: {e}")
        if r.status_code in (401, 403) and _erneut:
            self.token = None
            return self.abfragen(anfrage, _erneut=False)
        try:
            return r.json()
        except ValueError:
            raise OpenSlidesFehler(f"Unerwartete Antwort (HTTP {r.status_code}): {r.text[:200]}")
