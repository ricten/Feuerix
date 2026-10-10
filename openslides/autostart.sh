#!/bin/sh
# Sorgt dafuer, dass ALLE OpenSlides-Dienste nach einem Neustart von Docker/Server automatisch wieder starten.
# Die von osmanage erzeugte docker-compose.yml setzt "restart: unless-stopped" nur fuer einzelne Dienste (search,
# projector) - nach einem Docker-Neustart (z. B. durch ein Update) bleiben sonst Proxy, Auth, Backend, Datenbank
# usw. aus, und OpenSlides ist nicht erreichbar (HTTP 502 beim Verbindungstest in Feuerix).
#
# Erzeugt docker-compose.override.yml (wird von "docker compose" automatisch zusammen mit der generierten
# docker-compose.yml gelesen und ueberdauert deren Neuerzeugung bei OpenSlides-Updates). Aufruf einmalig:
#   cd openslides && ./autostart.sh && docker compose up --detach
# (install.sh ruft das bei Neuinstallationen selbst auf.)
set -e
cd "$(dirname "$0")"
[ -f docker-compose.yml ] || { echo "docker-compose.yml fehlt - zuerst ./install.sh ausfuehren." >&2; exit 1; }

DIENSTE=$(docker compose -f docker-compose.yml config --services)
{
  echo "# Automatisch von autostart.sh erzeugt - startet alle OpenSlides-Dienste nach einem Neustart wieder."
  echo "services:"
  for dienst in $DIENSTE; do
    printf '  %s:\n    restart: unless-stopped\n' "$dienst"
  done
} > docker-compose.override.yml

echo "docker-compose.override.yml erzeugt ($(echo "$DIENSTE" | wc -l) Dienste). Zum Uebernehmen: docker compose up --detach"
