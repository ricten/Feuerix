# Installationsanleitung – Vereinsverwaltung + OpenSlides

Diese Anleitung richtet auf **einem Server** beide Anwendungen ein und stellt sie per HTTPS bereit:

```
Internet ──► Caddy (Ports 80/443, automatisches HTTPS)
                ├─► verein.example.org       ──► Vereinsverwaltung   127.0.0.1:8000  (Django, PostgreSQL, Redis, Celery)
                └─► versammlung.example.org  ──► OpenSlides 4        127.0.0.1:9000  (eigener Docker-Stack)
```

> **Hinweis zum Stand:** Die Vereinsverwaltung wurde ohne Testlauf erstellt, die OpenSlides-Anbindung nach der offiziellen
> Dokumentation, aber nicht gegen eine laufende Instanz geprüft. Planen Sie eine Testphase ein (Abschnitt 9).
> Die OpenSlides-Installationsschritte entsprechen der offiziellen `INSTALL.md` (OpenSlides 4.x, Werkzeug `osmanage`).

---

## 1. Voraussetzungen

| Was | Empfehlung |
|---|---|
| Server | Linux (Ubuntu 24.04 LTS oder Debian 12), **mind. 2 CPU / 4 GB RAM** (Richtwert; OpenSlides besteht aus vielen Containern), 40 GB Platz |
| Domains | zwei Namen, die auf die Server-IP zeigen (DNS-A-Eintrag): z. B. `verein.example.org` und `versammlung.example.org` |
| Ports | 80 und 443 eingehend frei (für HTTPS/Let's Encrypt) |
| Zugang | SSH-Zugang mit sudo-Rechten |
| E-Mail | SMTP-Zugangsdaten (für Rechnungs- und Serienbrief-Versand), optional |

Zum Ausprobieren auf dem eigenen Rechner genügt Docker; Domains/HTTPS sind dann nicht nötig (Abschnitt 4 und 5 mit
`http://localhost:8000` bzw. `http://127.0.0.1:9000`, für OpenSlides im Browser allerdings HTTPS nötig – siehe Abschnitt 7).

## 2. Server vorbereiten

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y ca-certificates curl wget ufw git

# Firewall: nur SSH und Web
sudo ufw allow OpenSSH && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw enable

# Docker + Compose installieren (offizielles Skript)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER      # danach einmal ab- und wieder anmelden
docker info                        # muss ohne Fehler laufen
```

Projekt ablegen (Beispiel `/opt/verein`):

```bash
sudo mkdir -p /opt/verein && sudo chown $USER /opt/verein
# ZIP hochladen und entpacken -> /opt/verein/vereinsverwaltung
cd /opt/verein/vereinsverwaltung
```

## 3. Vereinsverwaltung konfigurieren

```bash
cp .env.example .env
nano .env
```

Wichtig (alle Werte selbst setzen):

* `SECRET_KEY` – lange Zufallszeichenfolge (`openssl rand -base64 48`)
* `FIELD_ENCRYPTION_KEY` – `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
  (oder nach dem Build: `docker compose run --rm --no-deps web python -c "..."`). **Diesen Schlüssel separat sichern** – ohne ihn sind
  verschlüsselte Daten (IBAN, OpenSlides-Passwörter) unlesbar.
* `POSTGRES_PASSWORD`, `ADMIN_USER`, `ADMIN_PASSWORD`, `VEREIN_NAME`
* `ALLOWED_HOSTS=verein.example.org`
* `CSRF_TRUSTED_ORIGINS=https://verein.example.org`
* `HTTPS=1` und `USE_X_FORWARDED_FOR=1` (weil der Proxy davor sitzt)
* `VEREIN_DOMAIN`, `OPENSLIDES_DOMAIN`, `ACME_EMAIL` (für den Proxy)
* E-Mail: `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`

## 4. Vereinsverwaltung starten

```bash
docker compose build
# einmalig: Datenbank-Migrationen erzeugen und im Projekt ablegen (wichtig für spätere Updates)
docker compose run --rm --no-deps --user root -v "$PWD/apps:/app/apps" web python manage.py makemigrations
docker compose up -d
docker compose logs -f web         # warten bis "Listening at: http://0.0.0.0:8000"
```

Test: `curl -I http://127.0.0.1:8000/login/` → HTTP 200. Anmeldung mit `ADMIN_USER`/`ADMIN_PASSWORD`.
Beim ersten Start wird der Verein aus `VEREIN_NAME` mit Standardrollen, Beispiel-Stammdaten, **Ablage-Ordnern und
Standardvorlagen** (Einladungen, Protokolle, Serienbriefe) angelegt.

## 5. OpenSlides installieren

```bash
cd /opt/verein/vereinsverwaltung/openslides
./install.sh
```

Das Skript lädt das Verwaltungswerkzeug `osmanage` und die Compose-Vorlage, erzeugt die Konfiguration samt Geheimnissen
(`secrets/`), startet die Container und legt die Startdaten an. Am Ende wird das Passwort des Benutzers `superadmin`
angezeigt. Manuell entspricht das:

```bash
wget https://github.com/OpenSlides/openslides-cli/releases/download/latest/osmanage && chmod +x osmanage
wget https://raw.githubusercontent.com/OpenSlides/openslides-cli/refs/heads/main/contrib/docker-compose.yml.tmpl
./osmanage setup -c config.yml -t docker-compose.yml.tmpl .
docker compose pull && docker compose up --detach
./osmanage initial-data --superadmin-password-file secrets/superadmin
```

`config.yml` bindet OpenSlides an `127.0.0.1:9000` und schaltet das eigene HTTPS aus (das übernimmt Caddy).
**Version festlegen:** In `config.yml` steht `defaults.tag`; setzen Sie dort die aktuelle Version von
<https://github.com/OpenSlides/OpenSlides/releases>.

## 6. HTTPS / Reverse Proxy (Caddy)

```bash
cd /opt/verein/vereinsverwaltung/deploy
docker compose --env-file ../.env -f docker-compose.proxy.yml up -d
docker compose -f docker-compose.proxy.yml logs -f      # Zertifikate werden automatisch geholt
```

Danach: `https://verein.example.org` (Vereinsverwaltung) und `https://versammlung.example.org` (OpenSlides).
OpenSlides **benötigt HTTPS** (der Browser-Client funktioniert nicht ohne Verschlüsselung).

**Zertifikat: automatisch (Let's Encrypt) oder eigenes hinterlegtes Zertifikat.** Ohne weitere Einrichtung
holt Caddy für beide Domains automatisch ein Let's-Encrypt-Zertifikat (Voraussetzung: Domain zeigt per DNS
auf den Server, Ports 80/443 offen). Alternativ kann ein eigenes Zertifikat verwendet werden (z. B. von einer
kommunalen/eigenen Zertifizierungsstelle):

1. Zertifikat (PEM) und privaten Schlüssel (PEM, unverschlüsselt) nach `deploy/certs/` legen (siehe
   `deploy/certs/README.md`).
2. In der `.env` die Dateinamen eintragen, z. B. `VEREIN_TLS_CERT=verein.crt`, `VEREIN_TLS_KEY=verein.key`
   (entsprechend `OPENSLIDES_TLS_CERT`/`OPENSLIDES_TLS_KEY` für die zweite Domain).
3. Proxy neu erzeugen: `docker compose -f docker-compose.proxy.yml up -d --force-recreate`.

Beide Wege lassen sich je Domain unabhängig wählen (z. B. eigenes Zertifikat für die Vereinsverwaltung,
Let's Encrypt für OpenSlides). Bei leeren `*_TLS_CERT`/`*_TLS_KEY`-Variablen bleibt es beim automatischen
Zertifikat.

## 7. Erste Schritte in der Vereinsverwaltung

1. **Verwaltung › Verein / Einstellungen / Logo:** Vereinsdaten ausfüllen, **Logo hochladen** (PNG oder JPG, am besten mit
   transparentem oder weißem Hintergrund), Unterschriftszeilen eintragen (z. B. „Max Mustermann, 1. Vorsitzender“), IBAN,
   Finanzamt/Steuernummer/Bescheid (für Spendenquittungen). Das Logo erscheint danach oben rechts auf allen PDFs.
2. **Verwaltung › Benutzer:** Vorstand, Kassenwart usw. mit passender Rolle anlegen.
3. **Verwaltung › Mitgliedsarten / Beiträge** und **Beitragsregeln:** Beispielbeträge anpassen.
4. **Schriftverkehr › Vorlagen:** Standardvorlagen prüfen und an die Satzung anpassen (z. B. Einladungsfristen).
5. Mitglieder erfassen (Import aus Excel ist noch nicht enthalten).

## 8. OpenSlides mit der Vereinsverwaltung verbinden

1. In OpenSlides als `superadmin` anmelden, Passwort ändern.
2. **Konten › Neues Konto:** technischen Benutzer anlegen (z. B. `verein-sync`, langes Passwort) und ihm die
   Organisationsverwaltungsebene **„Organisationsverwalter“** geben. Falls das Anlegen von Versammlungen mit einem
   Berechtigungsfehler scheitert: zusätzlich Ausschussverwaltung im Ausschuss oder – notfalls – Superadmin.
3. Ausschuss-ID ermitteln: in OpenSlides den Ausschuss öffnen, die Zahl in der Adresszeile (`…/committees/<ID>`) notieren.
   Ebenso die Konto-ID des Administrators, der neue Versammlungen verwalten soll (Standard: `1` = superadmin).
4. In der Vereinsverwaltung **Verwaltung › OpenSlides-Anbindung:** Adresse (`https://versammlung.example.org`), technischer
   Benutzer, Passwort, Ausschuss-ID, Administrator-IDs eintragen, „Anbindung aktiv“ setzen, speichern → **Verbindung testen**.
5. **Mitglieder abgleichen:** legt Konten mit Startpasswort an (läuft im Hintergrund, Ergebnis auf der Seite).
6. Zugangsdaten verteilen: **Schriftverkehr › Serienbriefe** mit der Vorlage „Zugangsdaten OpenSlides“ (per Brief oder E-Mail),
   danach **Startpasswörter löschen**.
7. In einer **Veranstaltung** (Mitgliederversammlung) Tagesordnung pflegen → **„In OpenSlides anlegen“**. Die Teilnehmer
   werden anschließend in OpenSlides der Versammlung zugeordnet (Teilnehmer › vorhandene Konten hinzufügen).

## 9. Testphase (dringend empfohlen)

Bevor echte Mitgliederdaten eingegeben werden: Testverein anlegen und prüfen – Beitragsrechnung erzeugen und als PDF ansehen,
Serienbrief-Vorschau, Ablage, OpenSlides-Verbindungstest, Backup **und Wiederherstellung** auf einem zweiten Rechner.

## 10. Datensicherung

```bash
# Vereinsverwaltung (Datenbank + hochgeladene Dateien)
docker compose exec -T web /app/scripts/backup.sh          # legt Dateien im Volume "backups" ab
# OpenSlides
cd openslides && docker compose exec --user postgres postgres pg_dump -U openslides --clean > /opt/verein/os-$(date +%F).sql
```

Als Cronjob (täglich 03:00), danach die Dateien **auf einen anderen Rechner/Speicher kopieren**:

```cron
0 3 * * * cd /opt/verein/vereinsverwaltung && docker compose exec -T web /app/scripts/backup.sh
15 3 * * * cd /opt/verein/vereinsverwaltung/openslides && docker compose exec -T --user postgres postgres pg_dump -U openslides --clean > /opt/verein/os-$(date +\%F).sql
```

Außerdem sichern: `.env` (enthält `FIELD_ENCRYPTION_KEY`!) und `openslides/secrets/`.
Wiederherstellung: `scripts/restore.sh` (Vereinsverwaltung) bzw. laut OpenSlides-Anleitung
(`docker compose up --detach postgres`, dann `psql < dump.sql`).

## 11. Updates

* **Vereinsverwaltung:** neue Projektdateien einspielen (`.env` und `apps/*/migrations` behalten), dann
  `docker compose build && docker compose run --rm --no-deps --user root -v "$PWD/apps:/app/apps" web python manage.py makemigrations && docker compose up -d`
  (Migrationen werden beim Start automatisch angewendet). Vorher immer Backup!
* **OpenSlides:** `defaults.tag` in `config.yml` erhöhen, dann
  `./osmanage config --force --config config.yml --template docker-compose.yml.tmpl .`, `docker compose up --detach`,
  bei Bedarf `./osmanage migrations stats|migrate|finalize`. Versionshinweise in der offiziellen INSTALL.md lesen (bei
  einzelnen Versionen sind manuelle Schritte nötig).

## 12. Fehlersuche

| Problem | Lösung |
|---|---|
| Vereinsverwaltung startet nicht | `docker compose logs web` – häufig fehlt `SECRET_KEY`/`FIELD_ENCRYPTION_KEY` in `.env` |
| „CSRF verification failed“ | `CSRF_TRUSTED_ORIGINS` (mit `https://`) und `ALLOWED_HOSTS` prüfen |
| Keine E-Mails | `EMAIL_HOST…` prüfen; ohne `EMAIL_HOST` werden Mails nur ins Log geschrieben (`docker compose logs worker`) |
| Serienbrief-Versand/OpenSlides-Abgleich tut nichts | Worker läuft? `docker compose ps`, `docker compose logs worker` |
| OpenSlides-Verbindungstest schlägt fehl | Adresse mit `https://`, Benutzer/Passwort, `docker compose logs` im OpenSlides-Ordner; Zertifikat gültig? |
| Port 8000/9000 belegt | Ports in `.env` (`WEB_PORT`) bzw. `openslides/config.yml` ändern und Caddyfile anpassen |
| Logo erscheint nicht im PDF | Nur PNG/JPG; Datei nicht beschädigt; im PDF oben rechts (ca. max. 55 × 28 mm) |

## 13. Datenschutz-Hinweise (kurz)

Mit Mitglieds- und Bankdaten gelten DSGVO-Pflichten: Auftragsverarbeitungsvertrag mit dem Hoster, Verzeichnis von
Verarbeitungstätigkeiten, Zugriffsrechte über Rollen (bereits eingebaut), Datenauskunft/Anonymisierung pro Mitglied
(eingebaut), Aufbewahrungsfristen beachten (Rechnungen, Spendenquittungs-Doppel). Lassen Sie das Konzept ggf. von Ihrem
Datenschutzbeauftragten prüfen.
