# OpenSlides 4 (Mitgliederversammlung online)

Dieses Verzeichnis enthält nur die Konfiguration und das Installationsskript. OpenSlides läuft als eigener
Docker-Compose-Stack **neben** der Vereinsverwaltung.

```bash
cd openslides
./install.sh          # lädt osmanage + Vorlage, richtet ein, startet, legt Startdaten an
```

Danach erreichbar unter http://127.0.0.1:9000 (lokal) bzw. über den Reverse Proxy unter Ihrer Domain (siehe ../INSTALL.md).

* `autostart.sh` erzeugt `docker-compose.override.yml`, damit **alle** Dienste nach einem Neustart von Docker/Server
  wieder starten (die generierte Compose-Datei tut das nur für einzelne). `install.sh` ruft es selbst auf; bei einer
  bestehenden Installation einmalig: `./autostart.sh && docker compose up --detach`.
* `secrets/` enthält die generierten Passwörter – **sichern, nicht weitergeben**.
* Backup: `docker compose exec --user postgres postgres pg_dump -U openslides --clean > dump.sql`
* Update: neue Version in `config.yml` (`defaults.tag`) eintragen, dann
  `./osmanage config --force --config config.yml --template docker-compose.yml.tmpl .`
  `docker compose up --detach` und ggf. `./osmanage migrations migrate` / `finalize`
  (siehe Hinweise zur jeweiligen Version in der offiziellen INSTALL.md).
