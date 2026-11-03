#!/bin/bash
# Richtet auf dem Server das Update per Weboberflaeche ein (einmalig, mit sudo-Rechten):
#
#   ./scripts/update_einrichten.sh                 Knopf "Jetzt aktualisieren" im Admin ermoeglichen
#   ./scripts/update_einrichten.sh --automatisch   zusaetzlich jede Nacht um ca. 03:30 Uhr automatisch aktualisieren, wenn es etwas Neues gibt
#   ./scripts/update_einrichten.sh --entfernen     alles wieder entfernen
#
# Was eingerichtet wird: der Ordner update/ (Austausch zwischen Container und Server: Auftrag, Stand, Protokoll),
# SOFTWAREUPDATE_PER_WEB=1 in der .env und ein systemd-Pfad-Dienst (feuerix-update.path), der beim Erscheinen von update/auftrag
# scripts/update.sh startet. Der Container bekommt dabei KEINEN Zugriff auf Docker oder den Host.
set -e
cd "$(dirname "$0")/.."
DIR="$PWD"
BENUTZER="$(id -un)"
[ "$(id -u)" != 0 ] || { echo "FEHLER: Bitte ohne sudo starten (./scripts/update_einrichten.sh) - die Dienste laufen als dieser Benutzer."; exit 1; }
command -v docker >/dev/null || { echo "FEHLER: Docker fehlt."; exit 1; }
[ -d .git ] || { echo "FEHLER: $DIR ist kein Git-Checkout. Feuerix muss per 'git clone' installiert sein (siehe INSTALL.md, Abschnitt 2), sonst gibt es nichts zum Aktualisieren."; exit 1; }
id -nG | tr ' ' '\n' | grep -qx docker || echo "Hinweis: $BENUTZER ist nicht in der Gruppe 'docker' - das Update braucht Docker-Rechte."

if [ "${1:-}" = "--entfernen" ]; then
  sudo systemctl disable --now feuerix-update.path feuerix-update-auto.timer 2>/dev/null || true
  sudo rm -f /etc/systemd/system/feuerix-update.path /etc/systemd/system/feuerix-update.service \
             /etc/systemd/system/feuerix-update-auto.timer /etc/systemd/system/feuerix-update-auto.service
  sudo systemctl daemon-reload
  rm -f update/host_bereit
  sed -i '/^SOFTWAREUPDATE_PER_WEB=/d' .env 2>/dev/null || true
  echo "Entfernt. Zum Uebernehmen: docker compose up -d"
  exit 0
fi

mkdir -p update
# Der Container-Benutzer (app) und der Host-Benutzer muessen beide Dateien in update/ anlegen und loeschen koennen.
# Der Ordner enthaelt nur die Auftragsdatei, den Stand und das Protokoll - nichts Geheimes.
chmod 0777 update
touch update/.gitkeep

if [ -f .env ]; then
  grep -q '^SOFTWAREUPDATE_PER_WEB=' .env && sed -i 's/^SOFTWAREUPDATE_PER_WEB=.*/SOFTWAREUPDATE_PER_WEB=1/' .env \
    || printf '\nSOFTWAREUPDATE_PER_WEB=1\n' >> .env
else
  echo "FEHLER: .env fehlt - erst Feuerix konfigurieren (INSTALL.md, Abschnitt 3)."; exit 1
fi

sudo tee /etc/systemd/system/feuerix-update.service >/dev/null <<EOF
[Unit]
Description=Feuerix aktualisieren (ausgeloest ueber die Weboberflaeche)
After=docker.service
Wants=docker.service

[Service]
Type=oneshot
User=$BENUTZER
WorkingDirectory=$DIR
ExecStart=/bin/bash $DIR/scripts/update.sh
TimeoutStartSec=3600
EOF
sudo tee /etc/systemd/system/feuerix-update.path >/dev/null <<EOF
[Unit]
Description=Auf einen Update-Auftrag aus der Feuerix-Weboberflaeche warten

[Path]
PathExists=$DIR/update/auftrag
Unit=feuerix-update.service

[Install]
WantedBy=multi-user.target
EOF

if [ "${1:-}" = "--automatisch" ]; then
  sudo tee /etc/systemd/system/feuerix-update-auto.service >/dev/null <<EOF
[Unit]
Description=Feuerix automatisch aktualisieren, wenn es eine neue Version gibt
After=docker.service
Wants=docker.service

[Service]
Type=oneshot
User=$BENUTZER
WorkingDirectory=$DIR
ExecStart=/bin/bash $DIR/scripts/update.sh --nur-wenn-neu
TimeoutStartSec=3600
EOF
  sudo tee /etc/systemd/system/feuerix-update-auto.timer >/dev/null <<EOF
[Unit]
Description=Feuerix jede Nacht auf Updates pruefen

[Timer]
OnCalendar=*-*-* 03:30:00
RandomizedDelaySec=15min
Persistent=true

[Install]
WantedBy=timers.target
EOF
fi

sudo systemctl daemon-reload
sudo systemctl enable --now feuerix-update.path
[ "${1:-}" = "--automatisch" ] && sudo systemctl enable --now feuerix-update-auto.timer

date -u +%Y-%m-%dT%H:%M:%SZ > update/host_bereit
echo
echo "Eingerichtet. Jetzt Feuerix einmal neu starten, damit die Einstellung greift:  docker compose up -d"
echo "Danach: Verwaltung > Software-Update im Admin (nur Superadministratoren)."
[ "${1:-}" = "--automatisch" ] && echo "Automatisch: jede Nacht ca. 03:30 Uhr (Pruefen: systemctl list-timers feuerix-update-auto.timer)."
echo "Stand nachlesen: journalctl -u feuerix-update -n 50   bzw.   $DIR/update/update.log"
