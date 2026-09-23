# Installationsanleitung – Feuerix (+ optional OpenSlides, + optional Paperless-ngx)

Diese Anleitung richtet auf **einem Server** Feuerix ein und stellt es per HTTPS bereit. OpenSlides
(Mitgliederversammlung online) und Paperless-ngx (Dokumentenarchiv) sind zwei unabhängig voneinander komplett
optionale Bausteine – nichts davon ist Voraussetzung für den Betrieb von Feuerix:

```
Internet ──► Caddy (Ports 80/443, automatisches HTTPS)
                ├─► verein.example.org       ──► Feuerix             127.0.0.1:8000  (Django, PostgreSQL, Redis, Celery)
                ├─► versammlung.example.org  ──► OpenSlides 4        127.0.0.1:9000  (eigener Docker-Stack, optional)
                └─► paperless.example.org    ──► Paperless-ngx       127.0.0.1:10000 (eigener Docker-Stack, optional)
```

> **Hinweis zum Stand:** Eine automatisierte Testsuite und GitHub-Actions-CI prüfen Feuerix bei jeder
> Änderung gegen eine echte PostgreSQL-Datenbank. Nicht gegen eine laufende Instanz geprüft sind die OpenSlides- und
> die Paperless-ngx-Anbindung (beide nach offizieller Dokumentation umgesetzt) – planen Sie dafür eine Testphase ein
> (Abschnitt 11), falls Sie eines der beiden nutzen. Die OpenSlides-Installationsschritte entsprechen der offiziellen
> `INSTALL.md` (OpenSlides 4.x, Werkzeug `osmanage`); die Paperless-Installationsschritte der offiziellen
> Docker-Compose-Installation.

---

## 1. Voraussetzungen

| Was | Empfehlung |
|---|---|
| Server | Linux (Ubuntu 24.04 LTS oder Debian 12), **mind. 1 CPU / 2 GB RAM** für Feuerix allein, 20 GB Platz |
| Domain | ein Name, der auf die Server-IP zeigt (DNS-A-Eintrag): z. B. `verein.example.org` – **Pflicht** |
| Domains zusätzlich | je ein weiterer Name nur bei Bedarf: `versammlung.example.org` für OpenSlides (Abschnitt 5), `paperless.example.org` für Paperless-ngx (Abschnitt 9) |
| RAM zusätzlich | +2 GB, falls OpenSlides mitbetrieben wird (viele Container); +1 GB, falls Paperless-ngx über Abschnitt 9 (Weg A) mitbetrieben wird (eigene Postgres-Instanz, OCR-Verarbeitung) |
| Ports | 80 und 443 eingehend frei (für HTTPS/Let's Encrypt) |
| Zugang | SSH-Zugang mit sudo-Rechten |
| E-Mail | SMTP-Zugangsdaten (für Rechnungs- und Serienbrief-Versand), optional |

Zum Ausprobieren auf dem eigenen Rechner genügt Docker; Domains/HTTPS sind dann nicht nötig (Abschnitt 4 mit
`http://localhost:8000`; für OpenSlides bzw. Paperless-ngx entsprechend `http://127.0.0.1:9000`/`:10000`, für
OpenSlides im Browser allerdings HTTPS nötig – siehe Abschnitt 7).

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

## 3. Feuerix konfigurieren

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
* `VEREIN_DOMAIN`, `ACME_EMAIL` (für den Proxy) – `OPENSLIDES_DOMAIN`/`PAPERLESS_DOMAIN` nur, falls Abschnitt 5
  bzw. 9 genutzt wird, sonst leer lassen
* E-Mail: `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`

## 4. Feuerix starten

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

## 5. OpenSlides installieren (optional)

Komplett optional – wer keine Online-Mitgliederversammlung braucht, überspringt diesen Abschnitt und Abschnitt 8
(dann in Abschnitt 3 `OPENSLIDES_DOMAIN` einfach leer lassen).

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

Danach erreichbar: `https://verein.example.org` (Feuerix) – **immer**. Zusätzlich
`https://versammlung.example.org` (OpenSlides) bzw. `https://paperless.example.org` (Paperless-ngx), aber jeweils
nur, wenn `OPENSLIDES_DOMAIN` bzw. `PAPERLESS_DOMAIN` in der `.env` gesetzt sind – leere Variablen lässt Caddy
automatisch weg (kein Fehler, die Domain existiert dann einfach nicht). OpenSlides **benötigt HTTPS** (der
Browser-Client funktioniert nicht ohne Verschlüsselung), falls genutzt.

**Zertifikat: automatisch (Let's Encrypt) oder eigenes hinterlegtes Zertifikat.** Ohne weitere Einrichtung
holt Caddy für jede konfigurierte Domain automatisch ein Let's-Encrypt-Zertifikat (Voraussetzung: Domain zeigt
per DNS auf den Server, Ports 80/443 offen). Alternativ kann ein eigenes Zertifikat verwendet werden (z. B. von
einer kommunalen/eigenen Zertifizierungsstelle):

1. Zertifikat (PEM) und privaten Schlüssel (PEM, unverschlüsselt) nach `deploy/certs/` legen (siehe
   `deploy/certs/README.md`).
2. In der `.env` die Dateinamen eintragen, z. B. `VEREIN_TLS_CERT=verein.crt`, `VEREIN_TLS_KEY=verein.key`
   (entsprechend `OPENSLIDES_TLS_CERT`/`OPENSLIDES_TLS_KEY` bzw. `PAPERLESS_TLS_CERT`/`PAPERLESS_TLS_KEY`).
3. Proxy neu erzeugen: `docker compose -f docker-compose.proxy.yml up -d --force-recreate`.

Alle drei Wege lassen sich je Domain unabhängig wählen (z. B. eigenes Zertifikat für Feuerix,
Let's Encrypt für die anderen). Bei leeren `*_TLS_CERT`/`*_TLS_KEY`-Variablen bleibt es beim automatischen
Zertifikat.

## 7. Erste Schritte in Feuerix

1. **Verwaltung › Verein / Einstellungen / Logo:** Vereinsdaten ausfüllen, **Logo hochladen** (PNG oder JPG, am besten mit
   transparentem oder weißem Hintergrund), Unterschriftszeilen eintragen (z. B. „Max Mustermann, 1. Vorsitzender“), IBAN,
   Finanzamt/Steuernummer/Bescheid (für Spendenquittungen). Das Logo erscheint danach oben rechts auf allen PDFs.
2. **Verwaltung › Benutzer:** Vorstand, Kassenwart usw. mit passender Rolle anlegen.
3. **Verwaltung › Mitgliedsarten / Beiträge** und **Beitragsregeln:** Beispielbeträge anpassen.
4. **Schriftverkehr › Vorlagen:** Standardvorlagen prüfen und an die Satzung anpassen (z. B. Einladungsfristen).
5. Mitglieder erfassen – einzeln oder per **Import aus Excel/CSV** (Button „Import“ auf der Mitgliederliste,
   mit Testlauf und herunterladbarer Vorlage).

Eine ausführliche Bedienungsanleitung für alle Module steht in **[docs/HANDBUCH.md](docs/HANDBUCH.md)**.

## 8. OpenSlides mit Feuerix verbinden (nur falls Abschnitt 5 genutzt wird)

1. In OpenSlides als `superadmin` anmelden, Passwort ändern.
2. **Konten › Neues Konto:** technischen Benutzer anlegen (z. B. `verein-sync`, langes Passwort) und ihm die
   Organisationsverwaltungsebene **„Organisationsverwalter“** geben. Falls das Anlegen von Versammlungen mit einem
   Berechtigungsfehler scheitert: zusätzlich Ausschussverwaltung im Ausschuss oder – notfalls – Superadmin.
3. Ausschuss-ID ermitteln: in OpenSlides den Ausschuss öffnen, die Zahl in der Adresszeile (`…/committees/<ID>`) notieren.
   Ebenso die Konto-ID des Administrators, der neue Versammlungen verwalten soll (Standard: `1` = superadmin).
4. In Feuerix **Verwaltung › OpenSlides-Anbindung:** Adresse (`https://versammlung.example.org`), technischer
   Benutzer, Passwort, Ausschuss-ID, Administrator-IDs eintragen, „Anbindung aktiv“ setzen, speichern → **Verbindung testen**.
5. **Mitglieder abgleichen:** legt Konten mit Startpasswort an (läuft im Hintergrund, Ergebnis auf der Seite).
6. Zugangsdaten verteilen: **Schriftverkehr › Serienbriefe** mit der Vorlage „Zugangsdaten OpenSlides“ (per Brief oder E-Mail),
   danach **Startpasswörter löschen**.
7. In einer **Veranstaltung** (Mitgliederversammlung) Tagesordnung pflegen → **„In OpenSlides anlegen“**. Die Teilnehmer
   werden anschließend in OpenSlides der Versammlung zugeordnet (Teilnehmer › vorhandene Konten hinzufügen).

## 9. Paperless-ngx einrichten und verbinden (optional)

Komplett optional – wer das nicht braucht, überspringt diesen Abschnitt. Zwei Wege:

**A) Paperless-ngx über diesen Server mitbetreiben** (eigener Docker-Compose-Stack, analog OpenSlides):

```bash
cd /opt/verein/vereinsverwaltung/paperless
cp .env.example .env
nano .env              # PAPERLESS_SECRET_KEY, POSTGRES_PASSWORD, PAPERLESS_ADMIN_USER/_PASSWORD, PAPERLESS_URL setzen
./install.sh
```

Läuft danach lokal auf `127.0.0.1:10000`. Damit es auch über den Reverse Proxy erreichbar ist, in der **`.env` von
Feuerix** (nicht die von `paperless/`!) `PAPERLESS_DOMAIN=paperless.example.org` setzen und den Proxy
neu erzeugen (Abschnitt 6: `docker compose -f docker-compose.proxy.yml up -d --force-recreate`). Details, Backup
und Update stehen in [paperless/README.md](paperless/README.md).

**B) Eine bereits vorhandene, separate Paperless-ngx-Instanz nutzen** (eigener Server oder vorhandene Installation) –
dann Schritt A überspringen und direkt mit Schritt 1 unten weitermachen.

**Verbinden (bei beiden Wegen gleich):**

1. In Paperless-ngx anmelden, unter **Mein Profil › API-Token** einen Token erzeugen.
2. In Feuerix **Verwaltung › Paperless-Anbindung:** Adresse der Paperless-Instanz
   (z. B. `https://paperless.example.org`, ohne `/` am Ende) und den API-Token eintragen. Optional einen
   Standard-Korrespondenten, -Dokumenttyp und/oder Tags festlegen – diese werden in Paperless automatisch angelegt,
   falls sie dort noch nicht existieren.
3. „Anbindung aktiv“ setzen, speichern → **Verbindung testen**.
4. Danach erscheint bei jedem Dokument in der **Ablage** der Knopf „An Paperless senden“ sowie ein Sammelversand für
   mehrere Dokumente gleichzeitig (*Ablage › Sammelversand an Paperless*).

**Hinweis:** Der Versand ist reines Hochladen (Einweg) – Status oder Metadaten, die anschließend in Paperless
geändert werden, fließen nicht in Feuerix zurück.

## 10. OpenSlides oder Paperless-ngx nachträglich hinzufügen (oder entfernen)

Beide Bausteine müssen nicht gleich beim ersten Einrichten dabei sein – sie lassen sich jederzeit später ergänzen,
ohne den laufenden Betrieb von Feuerix anzutasten: Die App-Container (`web`/`worker`/`db`/`redis`) bleiben unberührt,
nur der Reverse-Proxy-Container wird kurz neu erzeugt (einige Sekunden Unterbrechung für **alle** Domains, die
über diesen Proxy laufen – nicht nur die neu hinzugefügte).

**OpenSlides nachträglich hinzufügen:**

1. DNS-A-Eintrag für die gewünschte Domain (z. B. `versammlung.example.org`) auf die Server-IP anlegen, falls noch
   nicht geschehen.
2. Abschnitt 5 durchführen: `cd openslides && ./install.sh`.
3. In der **`.env` von Feuerix** (Projektwurzel, nicht `openslides/config.yml`) `OPENSLIDES_DOMAIN=versammlung.example.org`
   eintragen (optional `OPENSLIDES_TLS_CERT`/`_KEY`, siehe Abschnitt 6).
4. Proxy neu erzeugen, damit die Domain aktiv wird: `cd deploy && docker compose -f docker-compose.proxy.yml up -d --force-recreate`.
5. Abschnitt 8 durchführen (Verbindung in Feuerix einrichten und testen).

**Paperless-ngx nachträglich hinzufügen:** genauso, nur mit Abschnitt 9 statt 5/8 – also Weg A oder B durchführen,
`PAPERLESS_DOMAIN` in der `.env` von Feuerix setzen, Proxy neu erzeugen (Schritt 4 oben), dann verbinden
(Schritte 1–4 in Abschnitt 9).

**Wieder entfernen:** in umgekehrter Reihenfolge – in Feuerix unter *Verwaltung ›
OpenSlides-/Paperless-Anbindung* „Anbindung aktiv“ abwählen (sonst zeigen Detailseiten weiter tote Knöpfe an),
`OPENSLIDES_DOMAIN` bzw. `PAPERLESS_DOMAIN` in der `.env` wieder leeren, Proxy neu erzeugen (Schritt 4 oben), dann
den jeweiligen Stack stoppen: `cd openslides` bzw. `cd paperless && docker compose down` (mit zusätzlich `-v`, um
auch die zugehörigen Datenbank-/Dateivolumes unwiderruflich zu löschen – vorher Backup, siehe Abschnitt 12).

## 11. Testphase (dringend empfohlen)

Bevor echte Mitgliederdaten eingegeben werden: Testverein anlegen und prüfen – Beitragsrechnung erzeugen und als PDF ansehen,
Serienbrief-Vorschau, Ablage, OpenSlides-Verbindungstest (falls genutzt), Paperless-Verbindungstest (falls genutzt),
Backup **und Wiederherstellung** auf einem zweiten Rechner.

## 12. Datensicherung

```bash
# Feuerix (Datenbank + hochgeladene Dateien)
docker compose exec -T web /app/scripts/backup.sh          # legt Dateien im Volume "backups" ab
# OpenSlides (nur falls Abschnitt 5 genutzt wird)
cd openslides && docker compose exec --user postgres postgres pg_dump -U openslides --clean > /opt/verein/os-$(date +%F).sql
# Paperless-ngx (nur falls über Weg A in Abschnitt 9 selbst betrieben)
cd paperless && docker compose exec -T db pg_dump -U paperless --clean > /opt/verein/paperless-$(date +%F).sql
```

Als Cronjob (täglich 03:00), danach die Dateien **auf einen anderen Rechner/Speicher kopieren**:

```cron
0 3 * * * cd /opt/verein/vereinsverwaltung && docker compose exec -T web /app/scripts/backup.sh
15 3 * * * cd /opt/verein/vereinsverwaltung/openslides && docker compose exec -T --user postgres postgres pg_dump -U openslides --clean > /opt/verein/os-$(date +\%F).sql
30 3 * * * cd /opt/verein/vereinsverwaltung/paperless && docker compose exec -T db pg_dump -U paperless --clean > /opt/verein/paperless-$(date +\%F).sql
```

Außerdem sichern: `.env` (enthält `FIELD_ENCRYPTION_KEY`!) und – falls genutzt – `openslides/secrets/` bzw.
`paperless/.env` sowie die Docker-Volumes `paperless_data`/`paperless_media` (dort liegen die eingescannten
Dokumente und der Volltextindex).
Wiederherstellung: `scripts/restore.sh` (Feuerix) bzw. laut OpenSlides-Anleitung
(`docker compose up --detach postgres`, dann `psql < dump.sql`); für Paperless-ngx analog
(`docker compose up --detach db`, dann `psql < dump.sql`).

## 13. Updates

* **Feuerix:** neue Projektdateien einspielen (`.env` und `apps/*/migrations` behalten), dann
  `docker compose build && docker compose run --rm --no-deps --user root -v "$PWD/apps:/app/apps" web python manage.py makemigrations && docker compose up -d`
  (Migrationen werden beim Start automatisch angewendet). Vorher immer Backup!
* **OpenSlides** (nur falls genutzt): `defaults.tag` in `config.yml` erhöhen, dann
  `./osmanage config --force --config config.yml --template docker-compose.yml.tmpl .`, `docker compose up --detach`,
  bei Bedarf `./osmanage migrations stats|migrate|finalize`. Versionshinweise in der offiziellen INSTALL.md lesen (bei
  einzelnen Versionen sind manuelle Schritte nötig).
* **Paperless-ngx** (nur falls selbst betrieben): `cd paperless && docker compose pull && docker compose up --detach`.
  Versionshinweise in den offiziellen Paperless-ngx-Release-Notes lesen.

## 14. Fehlersuche

| Problem | Lösung |
|---|---|
| Feuerix startet nicht | `docker compose logs web` – häufig fehlt `SECRET_KEY`/`FIELD_ENCRYPTION_KEY` in `.env` |
| „CSRF verification failed“ | `CSRF_TRUSTED_ORIGINS` (mit `https://`) und `ALLOWED_HOSTS` prüfen |
| Keine E-Mails | `EMAIL_HOST…` prüfen; ohne `EMAIL_HOST` werden Mails nur ins Log geschrieben (`docker compose logs worker`) |
| Serienbrief-Versand/OpenSlides-Abgleich tut nichts | Worker läuft? `docker compose ps`, `docker compose logs worker` |
| OpenSlides-Verbindungstest schlägt fehl (falls genutzt) | Adresse mit `https://`, Benutzer/Passwort, `docker compose logs` im OpenSlides-Ordner; Zertifikat gültig? |
| Paperless-Verbindungstest/Versand schlägt fehl | Adresse mit `https://` (ohne `/` am Ende), API-Token korrekt kopiert, Paperless-Instanz vom Server aus erreichbar (`docker compose exec web curl -I https://paperless.example.org`) |
| Paperless-Stack (Weg A) startet nicht | `cd paperless && docker compose logs` – häufig fehlt `PAPERLESS_SECRET_KEY`/`POSTGRES_PASSWORD` in `paperless/.env` |
| Port 8000/9000/10000 belegt | Ports in `.env` (`WEB_PORT`) bzw. `openslides/config.yml`/`PAPERLESS_PORT` ändern und Caddyfile anpassen |
| Logo erscheint nicht im PDF | Nur PNG/JPG; Datei nicht beschädigt; im PDF oben rechts (ca. max. 55 × 28 mm) |

## 15. Datenschutz-Hinweise (kurz)

Mit Mitglieds- und Bankdaten gelten DSGVO-Pflichten: Auftragsverarbeitungsvertrag mit dem Hoster, Verzeichnis von
Verarbeitungstätigkeiten, Zugriffsrechte über Rollen (bereits eingebaut), Datenauskunft/Anonymisierung pro Mitglied
(eingebaut), Aufbewahrungsfristen beachten (Rechnungen, Spendenquittungs-Doppel). Lassen Sie das Konzept ggf. von Ihrem
Datenschutzbeauftragten prüfen.
