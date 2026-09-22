#!/bin/sh
# Startet Paperless-ngx in DIESEM Verzeichnis (eigener Docker-Compose-Stack, siehe README.md).
set -e
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Bitte zuerst .env ausfuellen (Passwoerter, Admin-Zugang, ggf. PAPERLESS_URL), dann install.sh erneut ausfuehren."
  exit 1
fi

docker compose pull
docker compose up --detach

echo
echo "Paperless-ngx laeuft lokal auf 127.0.0.1:10000 (bzw. ueber den Reverse Proxy unter PAPERLESS_URL, falls gesetzt)."
echo "Anmeldung mit PAPERLESS_ADMIN_USER / PAPERLESS_ADMIN_PASSWORD aus der .env."
echo "Als Naechstes: in der Vereinsverwaltung unter Verwaltung > Paperless-Anbindung Adresse und API-Token eintragen."
