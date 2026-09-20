# Projekt auf GitHub ablegen

## Vorbemerkung
Das Projekt ist so vorbereitet, dass es direkt in ein Git-Repository passt:
* `.gitignore` schließt `.env`, `openslides/secrets/` und Build-Artefakte aus – **Zugangsdaten gelangen nicht ins Repository**.
* `.github/workflows/ci.yml` startet bei jedem Push automatisch die Tests (Django-Check, Migrationen, Testsuite gegen PostgreSQL).
* `scripts/github_einrichten.sh` erledigt `git init`, ersten Commit und Push in einem Schritt.

## Einmalig auf GitHub (im Browser)
1. Konto anlegen bzw. anmelden, **New repository**.
2. Name z. B. `vereinsverwaltung`, Sichtbarkeit **Private** (enthält Vereinskonzepte, sollte nicht öffentlich sein).
3. **Keine** README/.gitignore/Lizenz vorab hinzufügen lassen (das Repository muss leer sein).
4. Adresse kopieren, z. B. `git@github.com:IHR-NAME/vereinsverwaltung.git` (SSH) oder `https://github.com/IHR-NAME/vereinsverwaltung.git`.

## Auf Ihrem Rechner
Voraussetzung: `git` installiert und bei GitHub angemeldet – am einfachsten mit der GitHub-CLI (`gh auth login`) oder mit einem
SSH-Schlüssel (GitHub › Settings › SSH keys).

```bash
git config --global user.name  "Ihr Name"
git config --global user.email "ihre@mail.de"

unzip vereinsverwaltung.zip && cd vereinsverwaltung
./scripts/github_einrichten.sh git@github.com:IHR-NAME/vereinsverwaltung.git
```

Das Skript entspricht diesen Befehlen:

```bash
git init -b main
git add -A
git commit -m "Erstversion"
git remote add origin git@github.com:IHR-NAME/vereinsverwaltung.git
git push -u origin main
```

Mit GitHub-CLI geht es noch kürzer: `gh repo create vereinsverwaltung --private --source=. --push`

## Danach
* **Actions-Reiter** öffnen: der erste CI-Lauf zeigt, ob alles startet. Da das Projekt bisher nie ausgeführt wurde, sind
  Fehlermeldungen beim ersten Lauf zu erwarten – die Log-Ausgabe des roten Schritts hier einfügen, dann werden sie gezielt behoben.
* **Migrationen einchecken:** Nach dem ersten Start (`makemigrations`, siehe INSTALL.md) liegen Dateien in `apps/*/migrations/`.
  Diese **gehören ins Repository** (`git add apps/*/migrations && git commit`).
* **Nie einchecken:** `.env`, `openslides/secrets/`, Datenbank-Dumps, Backups. Bei versehentlichem Commit Passwörter/Schlüssel
  sofort ändern (das bloße Löschen der Datei genügt nicht, die Historie bleibt).
* Empfohlen: Branch `main` schützen (Settings › Branches), Änderungen über Pull Requests, Releases mit Tags (`v0.1.0`),
  Dependabot für Sicherheitsupdates aktivieren (Settings › Code security).
* Lizenz: ohne `LICENSE`-Datei gilt das Projekt als „alle Rechte vorbehalten“. Für die Weitergabe an andere Vereine
  bewusst eine Lizenz wählen (z. B. AGPL-3.0 oder MIT).

## Kann Claude direkt committen?
In dieser Umgebung nicht: Der Arbeitsbereich hat keinen Internetzugang und keine Zugangsdaten zu GitHub. Ein direkter Commit
wäre nur möglich, wenn ein GitHub-Connector mit Schreibrechten in Claude verbunden ist (in der Connector-Auswahl derzeit
nicht verfügbar). Der beschriebene Weg über Ihren Rechner braucht dafür nur wenige Minuten.
