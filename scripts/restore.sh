#!/bin/sh
# Wiederherstellung:  docker compose exec web /app/scripts/restore.sh db-XXXX.sql.gz [media-XXXX.tar.gz]
set -e
[ -n "$1" ] || { echo "Aufruf: restore.sh db-....sql.gz [media-....tar.gz]"; exit 1; }
gunzip -c "/data/backups/$1" | PGPASSWORD="$POSTGRES_PASSWORD" psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" "$POSTGRES_DB"
[ -z "$2" ] || tar -xzf "/data/backups/$2" -C /data
echo "Wiederherstellung abgeschlossen."
