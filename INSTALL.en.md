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
> instance (document submission); for a new instance, a quick test is still recommended (section 11). Not
> yet verified against a production instance is the OpenSlides integration (implemented following the
> official documentation) – be sure to plan a test phase for it (section 11) if you use it. The OpenSlides
> installation steps match the official `INSTALL.md` (OpenSlides 4.x, the `osmanage` tool); the Paperless
> installation steps match the official Docker Compose installation.

---

## 1. Prerequisites

| What | Recommendation |
|---|---|
| Server | Linux (Ubuntu 24.04 LTS or Debian 12), **at least 1 CPU / 2 GB RAM** for Feuerix alone, 20 GB of space |
| Domain | a name pointing at the server's IP (DNS A record): e.g. `verein.example.org` – **required** |
| Additional domains | one more name each, only if needed: `versammlung.example.org` for OpenSlides (section 5), `paperless.example.org` for Paperless-ngx (section 9) |
| Additional RAM | +2 GB if OpenSlides is also run (many containers); +1 GB if Paperless-ngx is run via section 9 (route A) (its own Postgres instance, OCR processing) |
| Ports | 80 and 443 open inbound (for HTTPS/Let's Encrypt) |
| Access | SSH access with sudo rights |
| Email | SMTP credentials (for sending invoices and mail merges), optional |

To try it out on your own computer, Docker alone is enough; domains/HTTPS are then not needed (section 4
with `http://localhost:8000`; for OpenSlides or Paperless-ngx, accordingly `http://127.0.0.1:9000`/`:10000`
– though OpenSlides does need HTTPS in the browser, see section 7).

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

```bash
sudo mkdir -p /opt/verein && sudo chown $USER /opt/verein
# upload and unzip the ZIP -> /opt/verein/vereinsverwaltung
cd /opt/verein/vereinsverwaltung
```

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
* `VEREIN_DOMAIN`, `ACME_EMAIL` (for the proxy) – `OPENSLIDES_DOMAIN`/`PAPERLESS_DOMAIN` only if section 5 or
  9 is used, otherwise leave empty
* Email: `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`

## 4. Starting Feuerix

```bash
docker compose build
# one-time: generate database migrations and keep them in the project (important for later updates)
docker compose run --rm --no-deps --user root -v "$PWD/apps:/app/apps" web python manage.py makemigrations
docker compose up -d
docker compose logs -f web         # wait until "Listening at: http://0.0.0.0:8000"
```

Test: `curl -I http://127.0.0.1:8000/login/` → HTTP 200. Log in with `ADMIN_USER`/`ADMIN_PASSWORD`. On the
first start, the club is created from `VEREIN_NAME` with the data-protection-bylaw roles/tags, sample core
data, **archive folders and default templates** (invitations, minutes, mail merges).

## 5. Installing OpenSlides (optional)

Completely optional – if you don't need an online general meeting, skip this section and section 8 (then
just leave `OPENSLIDES_DOMAIN` empty in section 3).

```bash
cd /opt/verein/vereinsverwaltung/openslides
./install.sh
```

The script downloads the `osmanage` management tool and the Compose template, generates the configuration
including secrets (`secrets/`), starts the containers and creates the initial data. At the end it shows the
password of the `superadmin` user. Manually, this corresponds to:

```bash
wget https://github.com/OpenSlides/openslides-cli/releases/download/latest/osmanage && chmod +x osmanage
wget https://raw.githubusercontent.com/OpenSlides/openslides-cli/refs/heads/main/contrib/docker-compose.yml.tmpl
./osmanage setup -c config.yml -t docker-compose.yml.tmpl .
docker compose pull && docker compose up --detach
./osmanage initial-data --superadmin-password-file secrets/superadmin
```

`config.yml` binds OpenSlides to `127.0.0.1:9000` and turns off its own HTTPS (Caddy takes care of that).
**Setting the version:** `config.yml` has a `defaults.tag` entry; set it to the current version from
<https://github.com/OpenSlides/OpenSlides/releases>.

## 6. HTTPS / Reverse Proxy (Caddy)

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

## 7. First steps in Feuerix

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

## 8. Connecting OpenSlides to Feuerix (only if section 5 is used)

1. Log in to OpenSlides as `superadmin`, change the password.
2. **Accounts › New account:** create a technical user (e.g. `verein-sync`, a long password) and give it the
   organisation management level **"Organisation Admin"**. If creating meetings fails with a permissions
   error: additionally give it committee management in the committee, or – as a last resort – Superadmin.
3. Determine the committee ID: open the committee in OpenSlides, note the number in the address bar
   (`…/committees/<ID>`). Likewise note the account ID of the administrator who should manage new meetings
   (default: `1` = superadmin).
4. In Feuerix, **Administration › OpenSlides Integration:** enter the address
   (`https://versammlung.example.org`), the technical user, password, committee ID, administrator IDs, set
   "Integration active", save → **test the connection**.
5. **Sync members:** creates accounts with a starting password (runs in the background, result shown on the
   page).
6. Distribute credentials: **Correspondence › Mail merges** using the "OpenSlides login credentials"
   template (by letter or email), then **delete starting passwords**.
7. In an **event** (general meeting), maintain the agenda → **"Create in OpenSlides"**. Participants are then
   assigned to the meeting in OpenSlides (Participants › add existing accounts).

## 9. Setting up and connecting Paperless-ngx (optional)

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
the proxy (section 6: `docker compose -f docker-compose.proxy.yml up -d --force-recreate`). Details, backup
and updating are covered in [paperless/README.md](paperless/README.md).

**B) Use an already existing, separate Paperless-ngx instance** (your own server, or an existing
installation) – then skip route A and continue directly with step 1 below.

**Connecting (the same for both routes):**

1. Log in to Paperless-ngx, generate a token under **My Profile › API Token**.
2. In Feuerix, **Administration › Paperless Integration:** enter the address of the Paperless instance (e.g.
   `https://paperless.example.org`, without a trailing `/`) and the API token. Optionally set a default
   correspondent, document type and/or tags – these are created automatically in Paperless if they don't
   already exist there.
3. Set "Integration active", save → **test the connection**.
4. Every document in the **archive** then shows a "Send to Paperless" button, plus a bulk-send option for
   several documents at once (*Archive › Bulk Send to Paperless*).

**Note:** submission is a one-way upload – status or metadata subsequently changed in Paperless does not
flow back into Feuerix.

## 10. Adding OpenSlides or Paperless-ngx later (or removing it)

Neither building block has to be present from the very first setup – they can be added at any later time
without touching Feuerix's running operation: the app containers (`web`/`worker`/`db`/`redis`) stay
untouched, only the reverse-proxy container is briefly recreated (a few seconds of interruption for **all**
domains running through that proxy – not just the newly added one).

**Adding OpenSlides later:**

1. Create a DNS A record for the desired domain (e.g. `versammlung.example.org`) pointing at the server's
   IP, if not already done.
2. Carry out section 5: `cd openslides && ./install.sh`.
3. In **Feuerix's `.env`** (the project root, not `openslides/config.yml`), enter
   `OPENSLIDES_DOMAIN=versammlung.example.org` (optionally `OPENSLIDES_TLS_CERT`/`_KEY`, see section 6).
4. Recreate the proxy so the domain becomes active: `cd deploy && docker compose -f docker-compose.proxy.yml up -d --force-recreate`.
5. Carry out section 8 (set up and test the connection in Feuerix).

**Adding Paperless-ngx later:** the same, just with section 9 instead of 5/8 – i.e. carry out route A or B,
set `PAPERLESS_DOMAIN` in Feuerix's `.env`, recreate the proxy (step 4 above), then connect (steps 1–4 in
section 9).

**Removing again:** in reverse order – in Feuerix, under *Administration › OpenSlides/Paperless
Integration*, deselect "Integration active" (otherwise detail pages keep showing dead buttons), clear
`OPENSLIDES_DOMAIN` or `PAPERLESS_DOMAIN` in `.env` again, recreate the proxy (step 4 above), then stop the
respective stack: `cd openslides` or `cd paperless && docker compose down` (add `-v` to also permanently
delete the associated database/file volumes – back up first, see section 12).

## 11. Test phase (strongly recommended)

Before entering real member data: create a test club and check it – generate a fee invoice and view it as a
PDF, mail-merge preview, archive, OpenSlides connection test (if used), Paperless connection test (if used),
backup **and restore** on a second machine.

## 12. Backups

```bash
# Feuerix (database + uploaded files)
docker compose exec -T web /app/scripts/backup.sh          # places files in the "backups" volume
# OpenSlides (only if section 5 is used)
cd openslides && docker compose exec --user postgres postgres pg_dump -U openslides --clean > /opt/verein/os-$(date +%F).sql
# Paperless-ngx (only if self-hosted via route A in section 9)
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

## 13. Updates

* **Feuerix:** deploy the new project files (keep `.env` and `apps/*/migrations`), then
  `docker compose build && docker compose run --rm --no-deps --user root -v "$PWD/apps:/app/apps" web python manage.py makemigrations && docker compose up -d`
  (migrations are applied automatically on startup). Always back up first!
* **OpenSlides** (only if used): bump `defaults.tag` in `config.yml`, then
  `./osmanage config --force --config config.yml --template docker-compose.yml.tmpl .`,
  `docker compose up --detach`, and if needed `./osmanage migrations stats|migrate|finalize`. Read the
  release notes in the official INSTALL.md (some versions require manual steps).
* **Paperless-ngx** (only if self-hosted): `cd paperless && docker compose pull && docker compose up --detach`.
  Read the release notes in the official Paperless-ngx release notes.

## 14. Troubleshooting

| Problem | Solution |
|---|---|
| Feuerix doesn't start | `docker compose logs web` – often `SECRET_KEY`/`FIELD_ENCRYPTION_KEY` is missing in `.env` |
| "CSRF verification failed" | check `CSRF_TRUSTED_ORIGINS` (with `https://`) and `ALLOWED_HOSTS` |
| No emails | check `EMAIL_HOST…`; without `EMAIL_HOST`, emails are only written to the log (`docker compose logs worker`) |
| Sending mail merges/OpenSlides sync does nothing | is the worker running? `docker compose ps`, `docker compose logs worker` |
| OpenSlides connection test fails (if used) | address with `https://`, user/password, `docker compose logs` in the OpenSlides folder; is the certificate valid? |
| Paperless connection test/submission fails | address with `https://` (no trailing `/`), API token copied correctly, Paperless instance reachable from the server (`docker compose exec web curl -I https://paperless.example.org`) |
| Paperless stack (route A) doesn't start | `cd paperless && docker compose logs` – often `PAPERLESS_SECRET_KEY`/`POSTGRES_PASSWORD` is missing in `paperless/.env` |
| Port 8000/9000/10000 in use | change the ports in `.env` (`WEB_PORT`) or `openslides/config.yml`/`PAPERLESS_PORT` and adjust the Caddyfile |
| Logo doesn't appear in the PDF | PNG/JPG only; file not corrupted; appears top right in the PDF (approx. max. 55 × 28 mm) |

## 15. Data protection notes (brief)

Handling member and bank data brings GDPR obligations: a data processing agreement with your hoster, a
record of processing activities, access rights via roles (already built in), data requests/anonymisation per
member (built in), observing retention periods (invoices, donation-receipt copies). Consider having the
concept reviewed by your data protection officer.
