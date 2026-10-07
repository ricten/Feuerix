# Projekt auf GitHub ablegen

*English version: [GITHUB.en.md](GITHUB.en.md).*

## Vorbemerkung
Das Projekt ist so vorbereitet, dass es direkt in ein Git-Repository passt:
* `.gitignore` schließt `.env`, `openslides/secrets/` und Build-Artefakte aus – **Zugangsdaten gelangen nicht ins Repository**.
* `.github/workflows/ci.yml` startet bei jedem Push automatisch die Tests (Django-Check, Migrationen, Testsuite gegen PostgreSQL).
* `scripts/github_einrichten.sh` erledigt `git init`, ersten Commit und Push in einem Schritt.

## Einmalig auf GitHub (im Browser)
1. Konto anlegen bzw. anmelden, **New repository**.
2. Name z. B. `feuerix`, Sichtbarkeit **Private** (enthält Vereinskonzepte, sollte nicht öffentlich sein).
3. **Keine** README/.gitignore/Lizenz vorab hinzufügen lassen (das Repository muss leer sein).
4. Adresse kopieren, z. B. `git@github.com:IHR-NAME/feuerix.git` (SSH) oder `https://github.com/IHR-NAME/feuerix.git`.

## Auf Ihrem Rechner
Voraussetzung: `git` installiert und bei GitHub angemeldet – am einfachsten mit der GitHub-CLI (`gh auth login`) oder mit einem
SSH-Schlüssel (GitHub › Settings › SSH keys).

```bash
git config --global user.name  "Ihr Name"
git config --global user.email "ihre@mail.de"

unzip feuerix.zip && cd feuerix
./scripts/github_einrichten.sh git@github.com:IHR-NAME/feuerix.git
```

Das Skript entspricht diesen Befehlen:

```bash
git init -b main
git add -A
git commit -m "Erstversion"
git remote add origin git@github.com:IHR-NAME/feuerix.git
git push -u origin main
```

Mit GitHub-CLI geht es noch kürzer: `gh repo create feuerix --private --source=. --push`

## Danach
* **Actions-Reiter** öffnen: der erste CI-Lauf zeigt, ob alles startet. Der Code selbst ist durch die mitgelieferte
  Testsuite bereits geprüft – treten beim allerersten Lauf trotzdem Fehler auf, liegt das meist an umgebungs-
  spezifischen Dingen (z. B. Secrets/Umgebungsvariablen in den Actions-Einstellungen) – die Log-Ausgabe des roten
  Schritts hier einfügen, dann werden sie gezielt behoben.
* **Migrationen einchecken:** Nach dem ersten Start (`makemigrations`, siehe INSTALL.md) liegen Dateien in `apps/*/migrations/`.
  Diese **gehören ins Repository** (`git add apps/*/migrations && git commit`).
* **Nie einchecken:** `.env`, `openslides/secrets/`, Datenbank-Dumps, Backups. Bei versehentlichem Commit Passwörter/Schlüssel
  sofort ändern (das bloße Löschen der Datei genügt nicht, die Historie bleibt).
* Empfohlen: Branch `main` schützen (Settings › Branches), Änderungen über Pull Requests, Releases mit Tags (`v0.1.0`),
  Dependabot für Sicherheitsupdates aktivieren (Settings › Code security).
* Lizenz: ohne `LICENSE`-Datei gilt das Projekt als „alle Rechte vorbehalten“. Für die Weitergabe an andere Vereine
  bewusst eine Lizenz wählen (z. B. AGPL-3.0 oder MIT).

## Kann Claude direkt committen?
Kommt auf die Umgebung an: In **Claude Code** (diese CLI/IDE-Umgebung) mit Zugriff auf ein bereits eingerichtetes
Git-Repository samt Push-Zugangsdaten kann Claude ganz normal committen und pushen, wenn Sie es explizit darum
bitten – das ist der übliche Arbeitsweise für laufende Änderungen an einem bestehenden Repository. Für die
**einmalige Ersteinrichtung** (Repository auf GitHub anlegen, allererster Push) braucht es dagegen weiterhin
einen Zugang mit Schreibrechten für genau dieses neue Repository; ist der noch nicht vorhanden bzw. nicht mit der
Umgebung verbunden, erledigen Sie diesen einen Schritt wie oben beschrieben über Ihren eigenen Rechner – danach
kann Claude mit demselben Repository normal weiterarbeiten. In einer reinen Chat-Umgebung ohne verbundenes
Repository (z. B. claude.ai ohne Connector) ist direktes Committen generell nicht möglich.
