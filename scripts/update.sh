#!/bin/bash
# Feuerix auf dem Server aktualisieren (laeuft auf dem HOST, nicht im Container).
#
# Ablauf: Sicherung -> git pull -> docker compose build -> docker compose up -> warten, bis die Anmeldeseite antwortet.
# Gestartet wird es von Hand (./scripts/update.sh), vom systemd-Dienst feuerix-update (Knopf "Jetzt aktualisieren" im Admin legt dafuer
# die Auftragsdatei update/auftrag an) oder vom optionalen Timer (--nur-wenn-neu: nichts tun, wenn es nichts Neues gibt).
# Einrichtung: scripts/update_einrichten.sh. Der Stand steht in update/status.json, die Ausgabe in update/update.log.
#
# Sicherheit: Der Inhalt der Auftragsdatei wird nie gelesen oder ausgefuehrt - sie loest nur diesen festen Ablauf aus.
set -u
cd "$(dirname "$0")/.." || exit 1
PROJ="$PWD"
UPDATE_DIR="${UPDATE_DIR:-$PROJ/update}"
NUR_WENN_NEU=0
[ "${1:-}" = "--nur-wenn-neu" ] && NUR_WENN_NEU=1

mkdir -p "$UPDATE_DIR"
exec 9>"$UPDATE_DIR/.lock"
flock -n 9 || { echo "Es läuft bereits ein Update."; exit 0; }
rm -f "$UPDATE_DIR/auftrag"           # Auftrag angenommen (der Container darf einen neuen anlegen)

LOG="$UPDATE_DIR/update.log"
VON=""
NACH=""
GESTARTET=""
ABGESCHLOSSEN=0
jetzt() { date -u +%Y-%m-%dT%H:%M:%SZ; }
json_text() { printf '%s' "${1:-}" | tr -d '"\\' | tr '\n\r\t' '   ' | cut -c1-500; }
status() { # status ZUSTAND SCHRITT [MELDUNG] [ENDE]
  local tmp="$UPDATE_DIR/.status.tmp"
  printf '{"zustand": "%s", "schritt": "%s", "meldung": "%s", "von": "%s", "nach": "%s", "gestartet": "%s", "beendet": "%s"}\n' \
    "$1" "$(json_text "$2")" "$(json_text "${3:-}")" "$(json_text "$VON")" "$(json_text "$NACH")" "$GESTARTET" "${4:-}" > "$tmp" \
    && mv -f "$tmp" "$UPDATE_DIR/status.json"
}
beginnen() {
  GESTARTET="$(jetzt)"
  : > "$LOG"
  exec > >(tee -a "$LOG") 2>&1
  echo "=== Feuerix-Update gestartet: $GESTARTET ==="
}
fertig() { ABGESCHLOSSEN=1; status "$1" "$2" "$3" "$(jetzt)"; echo "=== $3 ==="; sleep 0.3; }
abbruch() { # unerwartetes Ende (Signal, Fehler im Skript): der Stand darf nicht auf "laeuft" stehen bleiben
  if [ "$ABGESCHLOSSEN" = 0 ] && [ -n "$GESTARTET" ]; then
    status fehler "Abgebrochen" "Das Update wurde unerwartet abgebrochen (Protokoll: update/update.log)." "$(jetzt)"
  fi
}
trap abbruch EXIT
fehler() { # fehler MELDUNG SCHRITT
  echo "FEHLER: $1"
  fertig fehler "$2" "$1"
  exit 1
}
env_wert() { sed -n "s/^$1=//p" "$PROJ/.env" 2>/dev/null | tail -1 | tr -d "\"'"; }
migrationen_zaehlen() { # Anzahl der angewendeten Datenbank-Migrationen; leer, wenn sie sich nicht ermitteln laesst
  local n
  n="$(docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT count(*) FROM django_migrations"' 2>/dev/null < /dev/null | tr -d '[:space:]')"
  case "$n" in ''|*[!0-9]*) n="";; esac
  echo "$n"
}
warten_bis_oben() { # 0 = Feuerix antwortet auf der Anmeldeseite
  local port host
  port="$(env_wert WEB_PORT)"; port="${port:-8000}"
  host="$(env_wert ALLOWED_HOSTS | cut -d, -f1)"; host="${host:-localhost}"
  if ! command -v curl >/dev/null 2>&1; then
    echo "Hinweis: curl fehlt, die Erreichbarkeit wird nicht geprüft."
    return 0
  fi
  for _ in $(seq 1 60); do
    if curl -fsS -o /dev/null -m 5 -H "Host: $host" -H "X-Forwarded-Proto: https" "http://127.0.0.1:$port/login/" 2>/dev/null; then return 0; fi
    sleep 3
  done
  return 1
}
zurueckrollen() { # Code und Container auf den Stand vor dem Update zuruecksetzen (nur aufrufen, wenn die Datenbank nicht migriert wurde)
  local ziel="$NACH"
  status laeuft "Rollback: zurück auf die vorherige Version"
  echo "Feuerix antwortet nicht und die Datenbank wurde noch nicht migriert: setze automatisch auf den Stand vor dem Update zurück."
  git reset --keep "$ALT_COMMIT" >/dev/null 2>&1 || fehler "Der automatische Rollback ist fehlgeschlagen (git reset). Rückweg: git reset --hard $ALT_COMMIT, dann docker compose build und up -d." "Rollback"
  docker compose build || fehler "Der automatische Rollback ist fehlgeschlagen (Bauen). Rückweg: docker compose build und up -d; Sicherung: Menü Datensicherung." "Rollback"
  docker compose up -d || fehler "Der automatische Rollback ist fehlgeschlagen (Neustart). Rückweg: docker compose up -d; Sicherung: Menü Datensicherung." "Rollback"
  status laeuft "Rollback: warte, bis die vorherige Version antwortet"
  warten_bis_oben || fehler "Auch die vorherige Version antwortet nach dem Rollback nicht (docker compose logs web). Sicherung: Menü Datensicherung." "Rollback"
  NACH="$ziel"
  fertig zurueckgesetzt "Zurückgesetzt" "Das Update auf $ziel ist fehlgeschlagen (Feuerix antwortete nicht). Es wurde automatisch auf $VON zurückgesetzt, die Datenbank war noch nicht migriert. Ursache: docker compose logs web."
  exit 1
}

VON="$(cat "$PROJ/VERSION" 2>/dev/null)"
if [ "$NUR_WENN_NEU" = 0 ]; then       # Knopf/von Hand: sofort melden, dass der Auftrag angenommen ist (keine Luecke fuer die Oberflaeche)
  beginnen
  status laeuft "Auftrag angenommen"
fi
UPSTREAM="$(git rev-parse --abbrev-ref '@{u}' 2>/dev/null || true)"

if [ "$NUR_WENN_NEU" = 1 ]; then       # Timer: still bleiben, wenn es nichts zu tun gibt
  [ -n "$UPSTREAM" ] || exit 1
  git fetch --quiet origin || exit 1
  [ "$(git rev-parse HEAD)" = "$(git rev-parse "$UPSTREAM")" ] && exit 0
fi

if [ "$NUR_WENN_NEU" = 1 ]; then beginnen; fi
status laeuft "Prüfe auf eine neue Version"
[ -n "$UPSTREAM" ] || fehler "Kein Branch ausgecheckt (z. B. nach git checkout auf einen Commit) - automatisches Aktualisieren nicht möglich. Zurück auf den Branch: git checkout main, dann erneut aktualisieren." "Prüfung"
git fetch --quiet origin || fehler "git fetch fehlgeschlagen (Netzwerk oder Zugangsdaten zum Repository prüfen)." "Prüfung"
ALT_COMMIT="$(git rev-parse HEAD)"
NACH="$(git show "$UPSTREAM:VERSION" 2>/dev/null | head -1)"
if [ "$ALT_COMMIT" = "$(git rev-parse "$UPSTREAM")" ]; then
  NACH="$VON"
  fertig aktuell "Prüfung" "Feuerix ist bereits auf dem neuesten Stand ($VON)."
  exit 0
fi
echo "Aktualisiere von $VON auf ${NACH:-?}."

status laeuft "Sicherung von Datenbank und Medien"
docker compose exec -T web /app/scripts/backup.sh || fehler "Die Sicherung vor dem Update ist fehlgeschlagen - es wurde nichts verändert." "Sicherung"
MIG_VORHER="$(migrationen_zaehlen)"       # Stand der Datenbank vor dem Update: entscheidet spaeter, ob ein automatischer Rollback sicher ist
echo "Angewendete Migrationen vor dem Update: ${MIG_VORHER:-unbekannt}"

status laeuft "Neuen Code holen (git pull)"
git pull --ff-only --quiet || fehler "git pull ist fehlgeschlagen (lokale Änderungen an versionierten Dateien? git status prüfen) - es wurde nichts verändert." "git pull"

status laeuft "Neues Image bauen (das dauert einige Minuten)"
if ! docker compose build; then
  git reset --keep "$ALT_COMMIT" >/dev/null 2>&1      # Code zurueck auf den laufenden Stand; die laufenden Container waren nie betroffen
  fehler "Das Bauen des neuen Images ist fehlgeschlagen. Der Code wurde auf den bisherigen Stand zurückgesetzt, Feuerix läuft unverändert weiter." "Bauen"
fi

status laeuft "Feuerix neu starten (Datenbank-Migrationen laufen beim Start)"
docker compose up -d || fehler "docker compose up ist fehlgeschlagen. Sicherung: Menü Datensicherung; Fehlersuche: docker compose logs web." "Neustart"

status laeuft "Warte, bis Feuerix antwortet"
if ! warten_bis_oben; then
  # Automatischer Rueckweg nur, wenn die Datenbank nachweislich noch nicht migriert wurde (gleiche Zahl angewendeter Migrationen wie
  # vorher): Dann passt der alte Code noch zur Datenbank. Ist sie schon migriert oder nicht pruefbar, bleibt es bei der Meldung.
  MIG_NACHHER="$(migrationen_zaehlen)"
  echo "Angewendete Migrationen nach dem Fehlstart: ${MIG_NACHHER:-unbekannt}"
  if [ -n "$MIG_VORHER" ] && [ "$MIG_VORHER" = "$MIG_NACHHER" ]; then
    zurueckrollen
  fi
  if [ -z "$MIG_VORHER" ] || [ -z "$MIG_NACHHER" ]; then
    GRUND="Der Migrationsstand war nicht prüfbar, deshalb kein automatischer Rückweg."
  else
    GRUND="Die Datenbank wurde schon migriert, deshalb kein automatischer Rückweg."
  fi
  fehler "Feuerix antwortet nach dem Update nicht (docker compose logs web). $GRUND Sicherung: Menü Datensicherung. Rückweg: git reset --hard $ALT_COMMIT, dann docker compose build und up -d." "Neustart"
fi

NACH="$(cat "$PROJ/VERSION" 2>/dev/null)"
docker image prune -f >/dev/null 2>&1 || true
fertig ok "Fertig" "Feuerix wurde von $VON auf $NACH aktualisiert."
