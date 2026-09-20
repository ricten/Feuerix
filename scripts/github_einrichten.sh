#!/bin/sh
# Legt das Projekt als Git-Repository an, macht den ersten Commit und lädt es zu GitHub hoch.
# Voraussetzung: auf GitHub existiert ein LEERES (am besten PRIVATES) Repository und Sie sind bei git/gh angemeldet.
# Aufruf:  ./scripts/github_einrichten.sh git@github.com:BENUTZER/vereinsverwaltung.git
#      oder ./scripts/github_einrichten.sh https://github.com/BENUTZER/vereinsverwaltung.git
set -e
cd "$(dirname "$0")/.."
[ -n "$1" ] || { echo "Aufruf: $0 <Repository-URL>"; exit 1; }

if [ -f .env ]; then echo "Hinweis: .env liegt im Ordner, wird aber durch .gitignore NICHT mit hochgeladen."; fi
[ -d .git ] || git init -b main
git config user.name  >/dev/null 2>&1 || { echo "Bitte zuerst: git config --global user.name  \"Ihr Name\"";  exit 1; }
git config user.email >/dev/null 2>&1 || { echo "Bitte zuerst: git config --global user.email \"ihre@mail.de\""; exit 1; }
git add -A
git status --short | head -20
git commit -m "Erstversion: Vereinsverwaltung (Mitglieder, Finanzen, Kassenbuch, Inventar, Schriftverkehr, OpenSlides)"
git remote add origin "$1" 2>/dev/null || git remote set-url origin "$1"
git push -u origin main
echo "Fertig. Prüfen Sie unter 'Actions' auf GitHub, ob der erste CI-Lauf grün ist."
