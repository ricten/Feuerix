#!/bin/bash
# Sichert Paperless-ngx und OpenSlides (laufen als eigene Compose-Stacks neben Feuerix) in das Sicherungs-Volume
# von Feuerix. Laeuft auf dem HOST im Projektordner (nicht im Container), z. B. per Cron kurz VOR der Feuerix-
# Sicherung (Uhrzeit unter Verwaltung > Datensicherung, Standard 03:00):
#   30 2 * * * /opt/verein/vereinsverwaltung/scripts/backup-zusatz.sh
# Die Dateien (paperless-db-/paperless-data-/paperless-media-/openslides-db-*) erscheinen danach in der Liste der
# Datensicherung, sind dort herunterladbar und werden mit der naechsten Feuerix-Sicherung auf das externe Ziel
# (NAS) kopiert; die Aufbewahrung gilt je Art wie bei den Feuerix-Sicherungen.
# Nicht vorhandene Stacks (kein paperless/ bzw. openslides/ mit laufendem Dienst) werden uebersprungen.
set -euo pipefail
cd "$(dirname "$0")/.."
STAMP=$(date +%Y%m%d-%H%M%S)
FEHLER=0

WEB=$(docker compose ps -q web | head -n 1)
[ -n "$WEB" ] || { echo "Der Feuerix-Container 'web' laeuft nicht." >&2; exit 1; }
VOL=$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/data/backups"}}{{.Name}}{{end}}{{end}}' "$WEB")
[ -n "$VOL" ] || { echo "Das Volume fuer /data/backups wurde nicht gefunden." >&2; exit 1; }
IMG=$(docker inspect -f '{{.Image}}' "$WEB")   # das Feuerix-Image selbst: kein zusaetzlicher Download noetig

# Hilfscontainer als root mit dem Sicherungs-Volume (Paperless-Dateien gehoeren anderen Benutzern)
im_volume() { docker run --rm -i --user root --entrypoint sh -v "$VOL:/dst" "$IMG" -c "$1"; }
# schreibe NAME  - liest stdin in eine Hilfsdatei (NAME.part); erst fertig() macht daraus die eigentliche Datei,
# damit nie halbe oder leere Sicherungen als vollstaendig erscheinen
schreibe() { im_volume "cat > '/dst/$1.part'"; }
fertig() { im_volume "chmod 644 '/dst/$1.part' && mv '/dst/$1.part' '/dst/$1'"; }
verwerfe() { im_volume "rm -f '/dst/$1.part'"; }
# volume_von STACK DIENST PFAD  - Name des Docker-Volumes, das im Dienst unter PFAD eingebunden ist
volume_von() {
  local cid
  cid=$(docker compose -f "$1/docker-compose.yml" ps -q "$2" | head -n 1)
  docker inspect -f "{{range .Mounts}}{{if eq .Destination \"$3\"}}{{.Name}}{{end}}{{end}}" "$cid"
}
# sichere NAME BEFEHL...  - fuehrt BEFEHL aus (schreibt auf stdout), komprimiert/legt ab; Fehler -> Datei verwerfen
sichere() {
  local name=$1; shift
  if ( set -o pipefail; "$@" | schreibe "$name" ) && fertig "$name"; then
    echo "OK: $name"
  else
    verwerfe "$name" || true
    echo "FEHLER: $name konnte nicht gesichert werden." >&2
    FEHLER=1
  fi
}
dump_gz() { "$@" | gzip; }
tar_volume() { docker run --rm --user root --entrypoint tar -v "$1:/src:ro" "$IMG" -czf - -C /src .; }

if [ -f paperless/docker-compose.yml ] && [ -n "$(docker compose -f paperless/docker-compose.yml ps -q db)" ]; then
  echo "Paperless-ngx ..."
  sichere "paperless-db-$STAMP.sql.gz" dump_gz docker compose -f paperless/docker-compose.yml exec -T db \
    pg_dump -U paperless --clean --if-exists paperless
  for teil in data media; do
    v=$(volume_von paperless webserver "/usr/src/paperless/$teil")
    if [ -n "$v" ]; then
      sichere "paperless-$teil-$STAMP.tar.gz" tar_volume "$v"
    else
      echo "FEHLER: Paperless-Volume '$teil' nicht gefunden." >&2
      FEHLER=1
    fi
  done
fi

if [ -f openslides/docker-compose.yml ] && [ -n "$(docker compose -f openslides/docker-compose.yml ps -q postgres)" ]; then
  echo "OpenSlides ..."
  sichere "openslides-db-$STAMP.sql.gz" dump_gz docker compose -f openslides/docker-compose.yml exec -T \
    --user postgres postgres pg_dump -U openslides --clean --if-exists
fi

exit "$FEHLER"
