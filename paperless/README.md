# Paperless-ngx (Dokumentenarchiv, optional)

Dieses Verzeichnis enthält einen eigenständigen Docker-Compose-Stack für Paperless-ngx – läuft unabhängig von der
Vereinsverwaltung (eigene Datenbank, eigener Redis) und wird über ein API-Token angebunden (siehe
[../INSTALL.md](../INSTALL.md) Abschnitt 9). Komplett optional: ohne dieses Verzeichnis funktioniert die
Vereinsverwaltung normal weiter, nur der Paperless-Versand aus der Ablage fehlt dann. Wer bereits eine andere
Paperless-ngx-Instanz betreibt, kann dieses Verzeichnis ignorieren und direkt unter *Verwaltung ›
Paperless-Anbindung* deren Adresse eintragen.

```bash
cd paperless
cp .env.example .env
nano .env              # Passwörter, Admin-Zugang, ggf. PAPERLESS_URL eintragen
./install.sh
```

Danach erreichbar unter http://127.0.0.1:10000 (lokal) bzw. über den Reverse Proxy unter Ihrer Domain (siehe
../INSTALL.md).

* Backup: `docker compose exec -T db pg_dump -U paperless --clean > dump.sql` – zusätzlich die Docker-Volumes
  `data`/`media` sichern (dort liegen die eingescannten Dokumente und der Volltextindex).
* Update: `docker compose pull && docker compose up --detach`.
* Der Ordner `consume/` (wird beim ersten Start angelegt) kann für den klassischen Scanner-Workflow genutzt
  werden: Dateien dort ablegen, Paperless liest sie automatisch ein.
