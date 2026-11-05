#!/bin/sh
# Sicherung von Datenbank und Medien:  docker compose exec web /app/scripts/backup.sh
# Bricht mit Fehlercode ab, wenn die Sicherung nicht vollstaendig gelungen ist - und raeumt dann nichts Altes weg.
set -e
STAMP=$(date +%Y%m%d-%H%M%S)
DIR="${BACKUP_DIR:-/data/backups}"      # die Vorgaben gelten im Container; die Variablen gibt es nur fuer die Tests
DATA="${DATA_DIR:-/data}"
TMP="$DIR/.db-$STAMP.sql.tmp"

# pg_dump zuerst in eine Datei und erst danach packen: in einer Pipe ("pg_dump | gzip") ginge sein Fehlercode verloren (gzip meldet 0),
# und bei nicht erreichbarer Datenbank entstuende eine leere "Sicherung", die wie eine gute aussieht und bei der Aufbewahrung
# (nur die letzten 14) gute Sicherungen verdraengen koennte.
if ! PGPASSWORD="$POSTGRES_PASSWORD" pg_dump --clean --if-exists -h "$POSTGRES_HOST" -U "$POSTGRES_USER" "$POSTGRES_DB" > "$TMP"; then
  rm -f "$TMP"
  echo "FEHLER: Der Datenbank-Dump (pg_dump) ist fehlgeschlagen - es wurde nichts gesichert." >&2
  exit 1
fi
if [ ! -s "$TMP" ]; then
  rm -f "$TMP"
  echo "FEHLER: Der Datenbank-Dump ist leer - es wurde nichts gesichert." >&2
  exit 1
fi
gzip -c "$TMP" > "$DIR/db-$STAMP.sql.gz"
rm -f "$TMP"
tar -czf "$DIR/media-$STAMP.tar.gz" -C "$DATA" media

# nur die letzten 14 Sicherungen behalten (erst nach einer gelungenen Sicherung)
ls -1t "$DIR"/db-*.sql.gz 2>/dev/null | tail -n +15 | xargs -r rm --
ls -1t "$DIR"/media-*.tar.gz 2>/dev/null | tail -n +15 | xargs -r rm --
echo "Sicherung abgeschlossen: $DIR (*-$STAMP)"
echo "WICHTIG: FIELD_ENCRYPTION_KEY aus der .env separat sichern!"
