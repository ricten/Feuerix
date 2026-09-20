# Projektkontext für Claude Code

Mandantenfähige Vereinsverwaltung (Django, PostgreSQL, Redis/Celery, Docker Compose). Sprache der Oberfläche, Doku und
Commit-Nachrichten: **Deutsch**.

## Wichtiger Stand
* Der Code wurde **noch nie ausgeführt** (ohne Django/Postgres geschrieben). Zuerst starten, Tests laufen lassen, Fehler beheben.
* Migrationen sind noch **nicht** im Repository: `python manage.py makemigrations`, dann prüfen und einchecken.
* OpenSlides-Anbindung (`apps/openslides`) folgt der Dokumentation von OpenSlides 4, ist nicht gegen eine Instanz getestet.
* FinTS (`fints_abruf`) ist experimentell und ungetestet.

## Aufbau
* `apps/core`: Verein (Mandant), Rollen/Rechte, Audit-Log, generische CRUD-Views (`crud.py`), PDF (`pdf.py`), Navigation (`context.py`).
* Fachmodule: `members`, `honors`, `finance`, `accounting` (Kassenbuch/-bericht), `inventory`, `donations`, `allowances`,
  `events`, `documents` (Vorlagen, Serienbriefe, Ablage), `openslides`.
* Jedes Modell erbt von `TenantModel` (Feld `verein`). **Jede Abfrage muss nach `verein` filtern** – nie Daten über Vereine hinweg zeigen.
* Neue Listen/Formulare über `crud(...)` in der `urls.py` der jeweiligen App; Rechte über Module (`apps/core/rechte.py`).
* Änderungen an Modellen werden automatisch im Änderungsprotokoll erfasst (`AUDIT`, `AUDIT_MASK` für sensible Felder).

## Befehle
* Start: `cp .env.example .env` (Schlüssel setzen), `docker compose build && docker compose up -d`
* Tests: `python manage.py test` (PostgreSQL nötig, `FIELD_ENCRYPTION_KEY` gesetzt)
* Migrationen: `python manage.py makemigrations`

## Regeln
* Keine Zugangsdaten committen (`.env`, `openslides/secrets/` sind ignoriert).
* Sensible Daten (IBAN) nur über `VerschluesseltesTextField`; nicht in Logs/Exports ohne Berechtigung.
* Steuerlich/rechtlich Relevantes (Spendenquittung, Freibeträge, Sphären) nur als Vorschlag kennzeichnen; Texte gegen amtliche Muster prüfen lassen.
* Neue Funktionen mit Tests in der jeweiligen `tests.py` absichern.
