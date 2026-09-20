#!/bin/sh
# Installiert OpenSlides 4 in DIESEM Verzeichnis (Docker + osmanage).
# Quelle: https://github.com/OpenSlides/OpenSlides/blob/main/INSTALL.md
set -e
cd "$(dirname "$0")"

[ -x ./osmanage ] || { wget -q https://github.com/OpenSlides/openslides-cli/releases/download/latest/osmanage && chmod +x osmanage; }
[ -f docker-compose.yml.tmpl ] || wget -q https://raw.githubusercontent.com/OpenSlides/openslides-cli/refs/heads/main/contrib/docker-compose.yml.tmpl

if [ ! -f docker-compose.yml ]; then
  ./osmanage setup -c config.yml -t docker-compose.yml.tmpl .
fi

docker compose pull
docker compose up --detach

echo ">>> Warte auf den Start der Dienste (bis zu 3 Minuten) ..."
i=0
until ./osmanage initial-data --superadmin-password-file secrets/superadmin; do
  i=$((i+1)); [ "$i" -ge 18 ] && { echo "initial-data fehlgeschlagen - 'docker compose logs' prüfen"; exit 1; }
  sleep 10
done

echo
echo "OpenSlides läuft lokal auf 127.0.0.1:9000."
echo "Anmeldung: Benutzer 'superadmin', Passwort:"
cat secrets/superadmin; echo
echo "Passwort nach der ersten Anmeldung ändern!"
