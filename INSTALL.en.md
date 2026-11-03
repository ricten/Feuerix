# Installation Guide – Feuerix (+ optional OpenSlides, + optional Paperless-ngx)

*This is the English translation of [INSTALL.md](INSTALL.md); the German version is authoritative for this
project.*

This guide sets up Feuerix on **one server** and serves it over HTTPS. OpenSlides (online general meetings)
and Paperless-ngx (document archive) are two mutually independent, completely optional building blocks –
neither is a prerequisite for running Feuerix:

```
Internet ──► Caddy (ports 80/443, automatic HTTPS)
                ├─► verein.example.org       ──► Feuerix             127.0.0.1:8000  (Django, PostgreSQL, Redis, Celery)
                ├─► versammlung.example.org  ──► OpenSlides 4        127.0.0.1:9000  (its own Docker stack, optional)
                └─► paperless.example.org    ──► Paperless-ngx       127.0.0.1:10000 (its own Docker stack, optional)
```

> **Note on status:** an automated test suite and GitHub Actions CI check Feuerix against a real PostgreSQL
> database on every change. The Paperless-ngx integration has been successfully tested against a running
> instance (document submission); for a new instance, a quick test is still recommended (section 10). The
> OpenSlides integration (implemented following the official documentation) has been tried out with an OpenSlides 4.3
> instance (connection test, member sync, creating a meeting, retrieving attendance, elections and votes); further parts
> are still only implemented according to the documentation – plan a test phase (section 10) if you use it. The OpenSlides
> installation steps match the official `INSTALL.md` (OpenSlides 4.x, the `osmanage` tool); the Paperless
> installation steps match the official Docker Compose installation.

---

## 1. Prerequisites

| What | Recommendation |
| --- | --- |
| Server | Linux (Ubuntu 24.04 LTS or Debian 12), **at least 1 CPU / 2 GB RAM** for Feuerix alone (a tight floor: 4 containers – Postgres, Redis, 3 Gunicorn workers, 1 Celery worker – already use roughly 700–900 MB at idle; for comfortable operation with headroom, e.g. during a larger fee run or mail-merge send, **4 GB is recommended**), 20 GB of space |
| Domain | a name pointing at the server's IP (DNS A record): e.g. `verein.example.org` – **required** |
| Additional domains | one more name each, only if needed: `versammlung.example.org` for OpenSlides (section 8), `paperless.example.org` for Paperless-ngx (section 7) |
| Additional RAM | +2 GB if OpenSlides is also run (many containers); +1 GB if Paperless-ngx is run via section 7 (route A) (its own Postgres instance, OCR processing) |
| Ports | 80 and 443 open inbound (for HTTPS/Let's Encrypt) |
| Access | SSH access with sudo rights |
| Email | SMTP credentials (for sending invoices and mail merges), optional |

To try it out on your own computer, Docker alone is enough; domains/HTTPS are then not needed (section 4
with `http://localhost:8000`; for OpenSlides or Paperless-ngx, accordingly `http://127.0.0.1:9000`/`:10000`
– though OpenSlides does need HTTPS in the browser, see section 6).

## 2. Preparing the server

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y ca-certificates curl wget ufw git

# Firewall: only SSH and web
sudo ufw allow OpenSSH && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw enable

# Install Docker + Compose (official script)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER      # then log out and back in once
docker info                        # must run without errors
```

Place the project (example `/opt/verein`):

> **Always install as a Git checkout** (not as a ZIP and not as unpacked files) when Feuerix does **not** run through the Portal administration. Only
> then can updates be applied with `git pull` (section 12), and the installed state can be traced by its version. If Feuerix runs through the
> Portal administration, this step is not needed: it creates the checkout itself (`FEUERIX_REPO_PFAD`) and updates the instances.

```bash
sudo mkdir -p /opt/verein && sudo chown $USER /opt/verein
cd /opt/verein
git clone https://github.com/ricten/Feuerix.git vereinsverwaltung
cd vereinsverwaltung
```

* Configuration lives only in `.env` (excluded from Git and untouched by updates). **Do not change versioned files**, otherwise `git pull` aborts
  with a conflict during an update.
* The folder name determines the Docker Compose project name and thus the names of the database and media volumes. Do not rename or move the
  folder later, or Feuerix starts with empty volumes (the data stays in the old ones).
* If the repository is not publicly reachable, set up credentials or an SSH key (deploy key) first and clone the SSH address.

**Converting an existing ZIP installation to Git** (once, back up first, section 11):

```bash
cd /opt/verein/vereinsverwaltung
git init -b main && git remote add origin https://github.com/ricten/Feuerix.git
git fetch origin && git reset origin/main     # files stay, only the Git history is linked
git status                                    # shows differences; "nothing to commit" = everything identical
```

If `git status` lists changed files, they are local customisations or an older state: inspect with `git diff`, save your own changes, then
`git checkout -- .` (resets the files to the GitHub state; `.env` stays untouched).

## 3. Configuring Feuerix

```bash
cp .env.example .env
nano .env
```

Important (set all values yourself):

* `SECRET_KEY` – a long random string (`openssl rand -base64 48`)
* `FIELD_ENCRYPTION_KEY` – `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
  (or after the build: `docker compose run --rm --no-deps web python -c "..."`). **Back up this key
  separately** – without it, encrypted data (IBAN, OpenSlides passwords) cannot be read.
* `POSTGRES_PASSWORD`, `ADMIN_USER`, `ADMIN_PASSWORD`, `VEREIN_NAME`
* `ALLOWED_HOSTS=verein.example.org`
* `CSRF_TRUSTED_ORIGINS=https://verein.example.org`
* `HTTPS=1` and `USE_X_FORWARDED_FOR=1` (because the proxy sits in front)
* `VEREIN_DOMAIN`, `ACME_EMAIL` (for the proxy) – `OPENSLIDES_DOMAIN`/`PAPERLESS_DOMAIN` only if section 8 or
  7 is used, otherwise leave empty
* Email: `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`

## 4. Starting Feuerix

```bash
docker compose build
docker compose up -d
docker compose logs -f web         # wait until "Listening at: http://0.0.0.0:8000"
```

The database migrations are part of the repository and are applied automatically on startup – no separate step is needed.

Test: `curl -I http://127.0.0.1:8000/login/` → HTTP 200. Log in with `ADMIN_USER`/`ADMIN_PASSWORD`. On the
first start, the club is created from `VEREIN_NAME` with the data-protection-bylaw roles/tags, sample core
data, **archive folders and default templates** (invitations, minutes, mail merges).

## 5. HTTPS / Reverse Proxy (Caddy)

```bash
cd /opt/verein/vereinsverwaltung/deploy
docker compose --env-file ../.env -f docker-compose.proxy.yml up -d
docker compose -f docker-compose.proxy.yml logs -f      # certificates are fetched automatically
```

Afterwards reachable at: `https://verein.example.org` (Feuerix) – **always**. Additionally
`https://versammlung.example.org` (OpenSlides) or `https://paperless.example.org` (Paperless-ngx), but only
if `OPENSLIDES_DOMAIN` or `PAPERLESS_DOMAIN` are set in `.env` – Caddy automatically skips empty variables
(no error, the domain simply doesn't exist then). OpenSlides **requires HTTPS** (the browser client doesn't
work without encryption), if used.

**Certificate: automatic (Let's Encrypt) or your own supplied certificate.** Without further setup, Caddy
automatically obtains a Let's Encrypt certificate for every configured domain (requires: the domain points
to the server via DNS, ports 80/443 open). Alternatively, you can use your own certificate (e.g. from a
municipal/internal certificate authority):

1. Place the certificate (PEM) and private key (PEM, unencrypted) in `deploy/certs/` (see
   `deploy/certs/README.md`).
2. Enter the file names in `.env`, e.g. `VEREIN_TLS_CERT=verein.crt`, `VEREIN_TLS_KEY=verein.key`
   (correspondingly `OPENSLIDES_TLS_CERT`/`OPENSLIDES_TLS_KEY` or `PAPERLESS_TLS_CERT`/`PAPERLESS_TLS_KEY`).
3. Recreate the proxy: `docker compose -f docker-compose.proxy.yml up -d --force-recreate`.

All three approaches can be chosen independently per domain (e.g. your own certificate for Feuerix, Let's
Encrypt for the others). With empty `*_TLS_CERT`/`*_TLS_KEY` variables, it stays with the automatic
certificate.

## 6. First steps in Feuerix

1. **Administration › Club / Settings / Logo:** fill in the club's details, **upload a logo** (PNG or JPG,
   ideally with a transparent or white background), enter signature lines (e.g. "Jane Doe, 1st Chair"),
   IBAN, tax office/tax number/determination notice (for donation receipts). The logo then appears top right
   on every PDF.
2. **Administration › Users:** create accounts for the board, treasurer etc. with the matching role.
3. **Administration › Membership Types / Fees** and **Fee Rules:** adjust the sample amounts.
4. **Correspondence › Templates:** review the default templates and adapt them to your bylaws (e.g.
   invitation deadlines).
5. Record members – individually, or via **import from Excel/CSV** (the "Import" button on the member list,
   with a dry run and a downloadable template).

A detailed user guide for every module is in **[docs/HANDBUCH.en.md](docs/HANDBUCH.en.md)**.

## 7. Setting up and connecting Paperless-ngx (optional)

Completely optional – skip this section if you don't need it. Two routes:

**A) Run Paperless-ngx alongside, on this server** (its own Docker Compose stack, similar to OpenSlides):

```bash
cd /opt/verein/vereinsverwaltung/paperless
cp .env.example .env
nano .env              # set PAPERLESS_SECRET_KEY, POSTGRES_PASSWORD, PAPERLESS_ADMIN_USER/_PASSWORD, PAPERLESS_URL
./install.sh
```

Afterwards runs locally on `127.0.0.1:10000`. To make it reachable via the reverse proxy too, set
`PAPERLESS_DOMAIN=paperless.example.org` in **Feuerix's `.env`** (not the one in `paperless/`!) and recreate
the proxy (section 5: `docker compose -f docker-compose.proxy.yml up -d --force-recreate`). Details, backup
and updating are covered in [paperless/README.md](paperless/README.md).

**B) Use an already existing, separate Paperless-ngx instance** (your own server, or an existing
installation) – then skip route A and continue directly with step 1 below.

**Connecting (the same for both routes):**

1. Log in to Paperless-ngx, generate a token under **My Profile › API Token**.
2. In Feuerix, **Administration › External integrations › Paperless-ngx (Set up):** enter the address of the Paperless instance (e.g.
   `https://paperless.example.org`, without a trailing `/`) and the API token. Optionally set a default
   correspondent, document type and/or tags – these are created automatically in Paperless if they don't
   already exist there.
3. Set "Integration active", save → **test the connection**.
4. Every document in the **archive** then shows a "Send to Paperless" button, plus a bulk-send option for
   several documents at once (*Archive › Bulk Send to Paperless*).

**Note:** submission is a one-way upload – status or metadata subsequently changed in Paperless does not
flow back into Feuerix.

## 8. Setting up and connecting OpenSlides (optional)

Completely optional – if you don't need an online general meeting, skip this section (then just leave `OPENSLIDES_DOMAIN` empty in
section 3). Like Paperless-ngx (section 7), OpenSlides runs as its own Docker Compose stack.

**Installing:**

```bash
cd /opt/verein/vereinsverwaltung/openslides
./install.sh
```

The script downloads the `osmanage` tool and the Compose template, generates the configuration and secrets (`secrets/`), starts the containers,
creates the initial data and sets up **autostart** (otherwise individual services stay down after a server restart; the connection test in Feuerix
then shows "HTTP 502"). At the end the password of the `superadmin` user is shown. OpenSlides runs locally on `127.0.0.1:9000` (Caddy takes care of
HTTPS). The version is in `openslides/config.yml` (`defaults.tag`, current versions: <https://github.com/OpenSlides/OpenSlides/releases>); the
script's individual commands are listed in [openslides/README.md](openslides/README.md).

To make OpenSlides reachable through the reverse proxy as well, set `OPENSLIDES_DOMAIN=versammlung.example.org` in **Feuerix's `.env`** (not
`openslides/config.yml`) and recreate the proxy (section 5: `docker compose -f docker-compose.proxy.yml up -d --force-recreate`).

**Connecting:**

1. Log in to OpenSlides as `superadmin`, change the password and, under **Accounts**, create a technical user (e.g. `verein-sync`, a long password)
   with the organisation management level **"Organisation Admin"**. If creating meetings later fails with a permissions error: additionally give it
   committee management in the committee, or – as a last resort – Superadmin.
2. Note the committee ID (the number in the address `…/committees/<ID>`) and the account ID of the administrator for new meetings
   (default: `1` = superadmin).
3. In Feuerix, **Administration › External integrations › OpenSlides (Set up):** enter the address (`https://versammlung.example.org`), user,
   password, committee ID and administrator IDs, set "Integration active", save → **test the connection**.
4. **Sync members** (creates accounts with a starting password, runs in the background). Distribute the credentials via **Correspondence › Mail
   merges** with the "OpenSlides login credentials" template (letter or email); then **delete starting passwords**.
5. In an **event** (general meeting), maintain the agenda → **"Create in OpenSlides"**. Afterwards assign the participants to the meeting in
   OpenSlides (Participants › add existing accounts).

## 9. Adding OpenSlides or Paperless-ngx later (or removing it)

Neither building block has to be present from the very first setup – they can be added at any later time
without touching Feuerix's running operation: the app containers (`web`/`worker`/`db`/`redis`) stay
untouched, only the reverse-proxy container is briefly recreated (a few seconds of interruption for **all**
domains running through that proxy – not just the newly added one).

**Adding OpenSlides later:**

1. Create a DNS A record for the desired domain (e.g. `versammlung.example.org`) pointing at the server's
   IP, if not already done.
2. In **Feuerix's `.env`** (the project root, not `openslides/config.yml`), enter
   `OPENSLIDES_DOMAIN=versammlung.example.org` (optionally `OPENSLIDES_TLS_CERT`/`_KEY`, see section 5).
3. Recreate the proxy so the domain becomes active: `cd deploy && docker compose -f docker-compose.proxy.yml up -d --force-recreate`.
4. Carry out section 8 (install OpenSlides, then set up and test the connection in Feuerix).

**Adding Paperless-ngx later:** the same, just with section 7 instead of 8 – i.e. carry out route A or B,
set `PAPERLESS_DOMAIN` in Feuerix's `.env`, recreate the proxy (step 3 above), then connect (steps 1–4 in
section 7).

**Removing again:** in reverse order – in Feuerix, under *Administration › OpenSlides/Paperless
Integration*, deselect "Integration active" (otherwise detail pages keep showing dead buttons), clear
`OPENSLIDES_DOMAIN` or `PAPERLESS_DOMAIN` in `.env` again, recreate the proxy (step 3 above), then stop the
respective stack: `cd openslides` or `cd paperless && docker compose down` (add `-v` to also permanently
delete the associated database/file volumes – back up first, see section 11).

## 10. Test phase (strongly recommended)

Before entering real member data: create a test club and check it – generate a fee invoice and view it as a
PDF, mail-merge preview, archive, OpenSlides connection test (if used), Paperless connection test (if used),
backup **and restore** on a second machine.

## 11. Backups

**Recommended:** In the web interface under *Administration › Data backup* (superadministrators only) switch on
the daily backup and, if needed, enter an external target (NAS via SFTP or SMB share); the backups can also be
downloaded there. This needs the `worker` service, which starts the schedule (`celery … worker -B`) and mounts
the `backups` volume - on an existing installation, take over the current `docker-compose.yml` and run
`docker compose up -d --build`.

**Paperless-ngx and OpenSlides** run as separate stacks and cannot be reached from the Feuerix container. Their
backup is done by the script `scripts/backup-zusatz.sh`, which runs **on the server (host)** and places the
database dumps (`paperless-db-…`, `openslides-db-…`) and the Paperless files (`paperless-data-…`,
`paperless-media-…`) into the same backup volume. There they show up in the data backup list (download) and are
copied to the external target together with the next Feuerix backup; retention applies per kind. Stacks that are
not set up are skipped. As a cron job **before** the Feuerix backup (default 03:00):

```cron
30 2 * * * /opt/verein/vereinsverwaltung/scripts/backup-zusatz.sh
```

Note: the Paperless files are packed while Paperless is running; for a perfectly clean copy, stop Paperless
briefly or additionally use the Paperless exporter (`document_exporter`).

Alternatively by hand (without the web interface):

```bash
# Feuerix (database + uploaded files)
docker compose exec -T web /app/scripts/backup.sh          # places files in the "backups" volume
# OpenSlides (only if section 8 is used)
cd openslides && docker compose exec --user postgres postgres pg_dump -U openslides --clean > /opt/verein/os-$(date +%F).sql
# Paperless-ngx (only if self-hosted via route A in section 7)
cd paperless && docker compose exec -T db pg_dump -U paperless --clean > /opt/verein/paperless-$(date +%F).sql
```

As a cron job (daily at 03:00), afterwards **copy the files to a different machine/storage**:

```cron
0 3 * * * cd /opt/verein/vereinsverwaltung && docker compose exec -T web /app/scripts/backup.sh
15 3 * * * cd /opt/verein/vereinsverwaltung/openslides && docker compose exec -T --user postgres postgres pg_dump -U openslides --clean > /opt/verein/os-$(date +\%F).sql
30 3 * * * cd /opt/verein/vereinsverwaltung/paperless && docker compose exec -T db pg_dump -U paperless --clean > /opt/verein/paperless-$(date +\%F).sql
```

Also back up: `.env` (contains `FIELD_ENCRYPTION_KEY`!) and – if used – `openslides/secrets/` or
`paperless/.env`, as well as the Docker volumes `paperless_data`/`paperless_media` (where the scanned
documents and the full-text index live).
Restoring: `scripts/restore.sh` (Feuerix), or per the OpenSlides instructions (`docker compose up --detach
postgres`, then `psql < dump.sql`); similarly for Paperless-ngx (`docker compose up --detach db`, then
`psql < dump.sql`).

### Restoring Feuerix

**Easiest way - in the web interface:** *Administration › Data backup › Restore backup* (superadministrator).
Choose the database backup (`db-…`) and optionally the matching files backup (`media-…`, same timestamp), enter
your own password and type `WIEDERHERSTELLEN`. On a freshly installed server, first put the backup files (from the
NAS or from the download) there via "Upload backup files" - the file names must not be changed. Sequence: the
current state is backed up automatically first (if that fails, nothing happens), the application goes into
maintenance mode, the database is replaced in a single transaction (on an error the existing one stays unchanged),
the files are unpacked (existing ones overwritten) and missing migrations are applied. Afterwards you may have to
log in again; the result is shown on the same page. The `worker` service must be running for this. Paperless and
OpenSlides can only be restored by hand (below).

**On the command line** (e.g. if the application itself no longer starts):

A backup consists of two files with the same timestamp: `db-YYYYMMDD-HHMMSS.sql.gz` (database) and
`media-YYYYMMDD-HHMMSS.tar.gz` (uploaded files). You need **both** to restore.
The dump contains `--clean --if-exists` and therefore replaces the existing tables (backups made before version
1.59.1 do not contain it: empty the database first, see below).

1. **New server:** install and start Feuerix as in sections 1-6, taking over the **old `.env`** - above all the
   **same `FIELD_ENCRYPTION_KEY`**, otherwise encrypted fields (IBAN, credentials) cannot be read.
2. **Put the backup files into the volume** (not needed if they are already in the `backups` volume). Copy them
   from the NAS or from the web interface download into the project folder, then:
   ```bash
   docker compose cp ./db-20261010-030000.sql.gz web:/data/backups/
   docker compose cp ./media-20261010-030000.tar.gz web:/data/backups/
   ```
3. **Stop the services and restore:**
   ```bash
   docker compose stop web worker
   docker compose run --rm web /app/scripts/restore.sh db-20261010-030000.sql.gz media-20261010-030000.tar.gz
   docker compose up -d
   ```
   On startup, missing migrations are applied automatically (even if the backup comes from an older version).
   The second file name (media) can be omitted if only the database is to be restored.
4. **Check:** log in, open a few members/invoices/documents, and trigger a new backup under *Administration ›
   Data backup*.

For a backup from before 1.59.1 (without `--clean`), or a dump that reports errors such as "relation already
exists": empty and recreate the database first (credentials are in the `.env`):
```bash
docker compose stop web worker
docker compose exec db psql -U verein -d postgres -c "DROP DATABASE vereinsverwaltung;" -c "CREATE DATABASE vereinsverwaltung OWNER verein;"
docker compose run --rm web /app/scripts/restore.sh db-....sql.gz media-....tar.gz
docker compose up -d
```
(`verein`/`vereinsverwaltung` are the defaults of `POSTGRES_USER`/`POSTGRES_DB`.)

**Practise a restore on a second machine at least once** before you need it - a backup that cannot be restored is
no backup. Also make sure the `FIELD_ENCRYPTION_KEY` is at hand: without it the backup is worthless for encrypted
fields.

### Restoring Paperless-ngx and OpenSlides

Put the backup files (from the web interface download, from the NAS or from the `backups` volume) into a folder
on the server, called `/path/` below.

**Paperless-ngx** (stack in `paperless/`; volumes `paperless_data` and `paperless_media`):
```bash
cd paperless
docker compose stop webserver
gunzip -c /path/paperless-db-YYYYMMDD-HHMMSS.sql.gz | docker compose exec -T db psql -U paperless paperless
docker run --rm -v paperless_data:/dst -v /path:/in:ro alpine tar -xzf /in/paperless-data-YYYYMMDD-HHMMSS.tar.gz -C /dst
docker run --rm -v paperless_media:/dst -v /path:/in:ro alpine tar -xzf /in/paperless-media-YYYYMMDD-HHMMSS.tar.gz -C /dst
docker compose up -d
```

**OpenSlides** (stack in `openslides/`):
```bash
cd openslides
docker compose stop
docker compose up --detach postgres
gunzip -c /path/openslides-db-YYYYMMDD-HHMMSS.sql.gz | docker compose exec -T --user postgres postgres psql -U openslides
docker compose up --detach
```
In addition, `openslides/secrets/` and `paperless/.env` are needed (not part of this backup, keep them
separately).

## 12. Updates

* **Feuerix (Git checkout, without the Portal administration):** always back up first (section 11), then in the project folder
  `git pull --ff-only && docker compose build && docker compose up -d`
  (migrations are applied automatically on startup). What is new is listed in `CHANGELOG.md`; the running version is shown in the footer.
  If `git pull` reports local changes or a conflict, a versioned file was modified (`git status`) – configuration belongs in `.env` only. If Feuerix
  was still installed from a ZIP, convert it to Git first (section 2). **With the Portal administration** it updates the instances itself
  ("Update available" and "Roll out update" in its web interface).
* **Update through the web interface (without the Portal administration, optional):** Set up once on the server in the Feuerix folder (Git checkout,
  user in the `docker` group, sudo required):

  ```bash
  ./scripts/update_einrichten.sh              # button in the admin; add --automatisch for a nightly update (about 03:30)
  docker compose up -d                        # mounts the update/ folder
  ```

  Afterwards *Administration › Software update* (superadministrators only) offers the "Update now" button, and when a new version exists the notice at
  the top links to it. The script `scripts/update.sh` backs up first (if that fails, **nothing** is changed), fetches the code
  (`git pull --ff-only`), builds the image (on errors the code is reset and the running version stays) and restarts. The status is in
  `update/status.json`, the output in `update/update.log` and in the journal (`journalctl -u feuerix-update`). The container gets **no** Docker
  access: it only creates the request file `update/auftrag`, and a systemd path service (`feuerix-update.path`) starts the script. The `update/`
  folder is deliberately writable for everyone (only request, status and log, nothing secret). The same works by hand with `./scripts/update.sh`.
  To remove: `./scripts/update_einrichten.sh --entfernen`.

* **OpenSlides** (only if used): bump `defaults.tag` in `config.yml`, then
  `./osmanage config --force --config config.yml --template docker-compose.yml.tmpl .`,
  `docker compose up --detach`, and if needed `./osmanage migrations stats|migrate|finalize`. Read the
  release notes in the official INSTALL.md (some versions require manual steps).
* **Paperless-ngx** (only if self-hosted): `cd paperless && docker compose pull && docker compose up --detach`.
  Read the release notes in the official Paperless-ngx release notes.

## 13. Troubleshooting

| Problem | Solution |
| --- | --- |
| Feuerix doesn't start | `docker compose logs web` – often `SECRET_KEY`/`FIELD_ENCRYPTION_KEY` is missing in `.env` |
| "CSRF verification failed" | check `CSRF_TRUSTED_ORIGINS` (with `https://`) and `ALLOWED_HOSTS` |
| No emails | check `EMAIL_HOST…`; without `EMAIL_HOST`, emails are only written to the log (`docker compose logs worker`) |
| Sending mail merges/OpenSlides sync does nothing | is the worker running? `docker compose ps`, `docker compose logs worker` |
| OpenSlides connection test fails (if used) | address with `https://`, user/password, `docker compose logs` in the OpenSlides folder; is the certificate valid? |
| Paperless connection test/submission fails | address with `https://` (no trailing `/`), API token copied correctly, Paperless instance reachable from the server (`docker compose exec web curl -I https://paperless.example.org`) |
| Paperless stack (route A) doesn't start | `cd paperless && docker compose logs` – often `PAPERLESS_SECRET_KEY`/`POSTGRES_PASSWORD` is missing in `paperless/.env` |
| Port 8000/9000/10000 in use | change the ports in `.env` (`WEB_PORT`) or `openslides/config.yml`/`PAPERLESS_PORT` and adjust the Caddyfile |
| Logo doesn't appear in the PDF | PNG/JPG only; file not corrupted; appears top right in the PDF (approx. max. 55 × 28 mm) |

## 14. Data protection notes (brief)

Handling member and bank data brings GDPR obligations: a data processing agreement with your hoster, a
record of processing activities, access rights via roles (already built in), data requests/anonymisation per
member (built in), observing retention periods (invoices, donation-receipt copies). Consider having the
concept reviewed by your data protection officer.
