#!/bin/sh
# Sicherung von Datenbank und Medien:  docker compose exec web /app/scripts/backup.sh
set -e
STAMP=$(date +%Y%m%d-%H%M%S)
DIR=/data/backups
PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -h "$POSTGRES_HOST" -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$DIR/db-$STAMP.sql.gz"
tar -czf "$DIR/media-$STAMP.tar.gz" -C /data media
# nur die letzten 14 Sicherungen behalten
ls -1t $DIR/db-*.sql.gz 2>/dev/null | tail -n +15 | xargs -r rm --
ls -1t $DIR/media-*.tar.gz 2>/dev/null | tail -n +15 | xargs -r rm --
echo "Sicherung abgeschlossen: $DIR (*-$STAMP)"
echo "WICHTIG: FIELD_ENCRYPTION_KEY aus der .env separat sichern!"
