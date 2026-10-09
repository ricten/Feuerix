# Projektkontext für Claude Code

Vereinsverwaltung (Django, PostgreSQL, Redis/Celery, Docker Compose). Sprache der Oberfläche, Doku und
Commit-Nachrichten: **Deutsch**. (Dieselben Hinweise stehen auch in `AGENTS.md`, als Alias für Agenten,
die nach dieser Konvention suchen - bitte beide Dateien zusammen pflegen oder nur hier ändern und dort
verlinken.)

## Stand
* Produktiv im Einsatz, Migrationen sind im Repository und werden inkrementell gepflegt (`python manage.py
  makemigrations <app>` nach Modelländerungen, Migration prüfen und einchecken). Bei einer unique/Default-
  kombinierten Feldänderung auf einer Tabelle mit Bestandsdaten **nicht** blind einem einzigen `AddField`
  vertrauen - ein einzeln berechneter Default wird bei PostgreSQL für ALLE Bestandszeilen gleich gesetzt
  (siehe z. B. `apps/events/migrations/0003`-`0005`: erst nullable anlegen, dann je Zeile einzeln befüllen,
  erst danach `unique=True` setzen).
* OpenSlides-Anbindung (`apps/openslides`) folgt der Dokumentation von OpenSlides 4, ist nicht gegen eine Instanz getestet.
* FinTS (`fints_abruf`) ist gegen eine echte Bank getestet (reiner Kontoumsätze-Abruf, kein TAN-Erfordernis dort gewesen) – Implementierungen unterscheiden sich je Bank, bei einer neuen Bank vorab kurz prüfen.
* Login-Brute-Force-Schutz über `django-axes` (5 Fehlversuche sperren Benutzername+IP für 1h); während
  `manage.py test` automatisch deaktiviert (`AXES_ENABLED = "test" not in sys.argv`), sonst sperren sich
  Tests mit absichtlich falschen Zugangsdaten gegenseitig aus.

## Aufbau
* `apps/core`: Verein, Rollen/Rechte, Audit-Log, generische CRUD-Views (`crud.py`), PDF (`pdf.py`), Navigation (`context.py`).
* Fachmodule: `members`, `honors`, `finance`, `accounting` (Kassenbuch/-bericht), `inventory`, `donations`, `allowances`,
  `events`, `documents` (Vorlagen, Serienbriefe, Ablage), `openslides`, `paperless` (Paperless-ngx-Anbindung).
* Jedes Modell erbt von `TenantModel` (Feld `verein`). **Jede Abfrage muss nach `verein` filtern** – nie Daten über Vereine hinweg zeigen.
* Neue Listen/Formulare über `crud(...)` in der `urls.py` der jeweiligen App; Rechte über Module (`apps/core/rechte.py`).
* Änderungen an Modellen werden automatisch im Änderungsprotokoll erfasst (`AUDIT`, `AUDIT_MASK` für sensible Felder) -
  das hängt an `pre_save`/`post_save`-Signalen (`apps/core/audit.py`); ein reines `.update()`/`.bulk_create()` auf
  einem auditierten Modell geht daran vorbei und bleibt unprotokolliert (lieber `.save(update_fields=[...])`).
* Nutzerkonfigurierte externe Adressen (Paperless-/OpenSlides-Verbindung, FinTS-Bankadresse) über
  `apps/core/util.py: pruefe_oeffentliche_adresse()` gegen SSRF auf interne Dienste/private IP-Bereiche prüfen
  (in `clean()` der jeweiligen Modelle eingebunden) - bei neuen Feldern mit frei einstellbarer Server-Adresse
  ebenso einbinden.

## Befehle
* Start: `cp .env.example .env` (Schlüssel setzen), `docker compose build && docker compose up -d`
* Tests: `python manage.py test --parallel` (PostgreSQL nötig, `FIELD_ENCRYPTION_KEY`/`SECRET_KEY` gesetzt) –
  `--parallel` verteilt auf alle CPU-Kerne (~520 Tests: einige Minuten → wenige Sekunden); bei `manage.py
  test` ist automatisch ein schneller, unsicherer Passwort-Hasher aktiv (`config/settings.py`, nur bei
  `"test" in sys.argv`, nie produktiv) - beides zusammen bringt den Großteil des Geschwindigkeitsgewinns.
  **Achtung `--parallel`:** ein echter Fehler in einem Test kann als nicht hilfreiches
  `TypeError: cannot pickle 'traceback' object` durchschlagen (Multiprocessing-Limitierung) - bei so einem
  Fehler **ohne** `--parallel` erneut laufen lassen, um den echten Traceback zu sehen.
* Ohne Docker/Postgres lokal testen: `config/settings_sqlite.py` (In-Memory-SQLite, setzt
  `SECRET_KEY`/`FIELD_ENCRYPTION_KEY` selbst) - `DJANGO_SETTINGS_MODULE=config.settings_sqlite python
  manage.py test` bzw. `... makemigrations --check --dry-run`. Nur für schnelle lokale Läufe gedacht, CI/
  Produktion nutzen weiterhin PostgreSQL.
* Migrationen: `python manage.py makemigrations <app>` (gezielt pro App, nicht pauschal alle Apps).
* Übersetzungen: `python manage.py makemessages -l en`, dann übersetzen, dann `compilemessages`.
  **Bekannte Eigenart:** `makemessages` erzeugt bei vielen `#:`-Referenzen auf eine Zeichenkette gelegentlich
  eine Kommentar-Fortsetzungszeile ohne das führende `#:` (bricht `polib`/manche Parser mit einem
  Syntaxfehler an der gemeldeten Zeile) - einfach die fehlende Zeile im `locale/.../django.po` von Hand mit
  `#: ` ergänzen, ist kein Datenverlust.

## Regeln
* Keine Zugangsdaten committen (`.env`, `openslides/secrets/` sind ignoriert).
* Sensible Daten (IBAN) nur über `VerschluesseltesTextField`; nicht in Logs/Exports ohne Berechtigung.
* Steuerlich/rechtlich Relevantes (Spendenquittung, Freibeträge, Sphären) nur als Vorschlag kennzeichnen; Texte gegen amtliche Muster prüfen lassen.
* Neue Funktionen mit Tests in der jeweiligen `tests.py` absichern.
* `gettext_lazy`-Werte (Übersetzungen) sind in Django-Templates/Formular-Choices unproblematisch, aber
  Bibliotheken außerhalb von Django (z. B. `openpyxl`, `factur-x`) akzeptieren den Lazy-Proxy oft nicht und
  brechen mit einer kryptischen Typ-Fehlermeldung ab - an solchen Stellen `str(...)` davorsetzen statt das
  Feld selbst un-lazy zu machen (das würde die eigentliche Übersetzung an anderer Stelle wieder kaputt machen).
* Bei einer eher losen Versionsobergrenze in `requirements.txt` (z. B. `paket>=X`) nach einem Fehlschlag
  lieber den Code an die neue Bibliotheksversion anpassen als eine Obergrenze einzuziehen, außer eine Anpassung
  ist unverhältnismäßig aufwändig - siehe `apps/finance/erechnung.py` (an `factur-x` 7.x angepasst statt `<7.0`).

## Versionierung
Die Datei `VERSION` folgt Semantic Versioning (`MAJOR.MINOR.PATCH`), bei jeder nennenswerten Änderung erhöhen:
* **PATCH** (`1.0.0` → `1.0.1`): Bugfixes, kleine Korrekturen ohne neues Verhalten.
* **MINOR** (`1.0.0` → `1.1.0`): Neue Funktionen/Module, abwärtskompatible Erweiterungen.
* **MAJOR** (`1.0.0` → `2.0.0`): Große strukturelle Änderungen (z. B. Datenmodell-Umbau, Architekturwechsel).
Bei jeder Version zusätzlich die Versionsnummer im Titel von `docs/HANDBUCH.md` **und** `docs/HANDBUCH.en.md`
(jeweils Zeile 1) synchron halten.
Außerdem bei jeder Versionserhöhung einen kurzen Stichpunkt ganz oben in `CHANGELOG.md` ergänzen (ein bis zwei
Zeilen, kein Roman) - dafür sind keine Testläufe nötig.
