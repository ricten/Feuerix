# Feuerix – Club Management for Fire Brigade Support Associations (Django · PostgreSQL · Docker)

*This is the English translation of [README.md](README.md); the German version is authoritative for this
project.*

"Feuerix" is the software brand (`PRODUCT_NAME` in `config/settings.py`) – separate from the name/logo of the
individual club, which every fire brigade uploads itself and which remains the primary brand on its own
instance.

Club management: members, honours/anniversaries, fees, invoices, payments, bank transactions, inventory with
lending and stock-taking, donation receipts, expense allowances, event planning, permissions/roles, a
complete audit trail, reports with CSV/Excel export.

> **Status:** an automated test suite (`python manage.py test`, ~440 tests) and a GitHub Actions CI check
> every change against a real PostgreSQL database. The FinTS fetch (plain transaction fetching) and the
> Paperless-ngx integration (document submission) have been successfully tested against a real bank and a
> running Paperless instance, respectively. Not yet verified against a production instance is the OpenSlides
> integration (implemented following the official documentation) – plan a test phase before relying on it.

**Handbook:** a detailed user guide for the board, treasurer, secretary & co. is available in
**[docs/HANDBUCH.en.md](docs/HANDBUCH.en.md)**.

**Development with AI assistance:** a substantial part of the code in this repository was written with the
help of AI coding tools (Claude Code) – requirements, architectural decisions, code review and overall
responsibility for the result rest with the human author. The software itself contains no AI functionality
at runtime; this notice is for transparency, not because of a legal labelling requirement.

**Version:** the `VERSION` file contains the current version number following Semantic Versioning
(`MAJOR.MINOR.PATCH`), incremented on every noteworthy deploy: **PATCH** for bug fixes (`1.0.0` → `1.0.1`),
**MINOR** for new features (`1.0.0` → `1.1.0`), **MAJOR** for major structural changes (`1.0.0` → `2.0.0`).
It's shown in the footer of every page and helps identify the running version when troubleshooting/support.

## Getting started

Detailed step-by-step instructions for the server, HTTPS and the optional integrations (OpenSlides,
Paperless-ngx): **[INSTALL.en.md](INSTALL.en.md)**. Quick version:

```bash
cp .env.example .env          # fill in SECRET_KEY, FIELD_ENCRYPTION_KEY, POSTGRES_PASSWORD, ADMIN_*
# Generate migrations once and keep them in the project (important for later updates):
docker compose build
docker compose run --rm --no-deps --user root -v "$PWD/apps:/app/apps" web python manage.py makemigrations
docker compose up -d
```

Then: http://localhost:8000 – log in with `ADMIN_USER` / `ADMIN_PASSWORD`. On the very first start, the club
is created from `VEREIN_NAME` together with the data-protection-bylaw roles/tags (see docs/HANDBUCH.en.md
chapter 2), membership types (sample amounts!), honour types and anniversary rules. Please adjust the amounts
under *Administration › Membership Types / Fees*.

## Users and permissions

* Club administrators manage their own users (*Administration › Users*).
* Permissions: role + individual, per-user extra rights per module (view/create/edit/delete).

## Web interface design

Navigation, buttons and links use the per-club configurable **accent colour** (*Administration ›
Club/Settings*, the same colour as on letters/PDFs) – the text colour in the navigation bar is calculated
automatically for readability, and coloured hover effects mark the active/hovered menu item. Icons come from
[Bootstrap Icons](https://icons.getbootstrap.com/), served locally like Bootstrap/HTMX (no CDN,
GDPR-friendly); almost every button automatically gets a matching icon based on its label
(`apps/core/crud.py::_icon_fuer`), and every sub-page additionally shows the icon of its navigation group,
top right. Cards are consistently rounded with a soft shadow and accent-coloured details (key-figure cards
with a coloured line on the left, slightly tinted table headers, cards with a link target lift slightly on
hover). From the `xl` breakpoint up, detail pages use a two-column layout (core data as a sidebar on the
left, linked lists on the right) instead of a single long column, to make better use of wide screens.

## Language and cookie notice

German/English can be switched via the language selector at the top of the menu bar (also on the login page)
– standard Django i18n (`django.middleware.locale.LocaleMiddleware`, choice stored via a cookie). Translated:
navigation, login/logout, dashboard, the generic list/detail/form pages. To add new translations:
`django-admin makemessages -l en`, fill in the texts in `locale/en/LC_MESSAGES/django.po`, then
`django-admin compilemessages` (needs GNU `gettext`; the resulting `.mo` file is checked in). Since a language
preference is stored as a cookie, the page shows a one-time cookie notice (only strictly necessary cookies:
login, CSRF protection, language – no tracking cookies).

## Modules

| Module | Core features |
|---|---|
| Members | **Import** from Excel/CSV (dry run, updating existing members, error report, template file) and **full export** (Excel/CSV, bank details only with the fees permission, logged); record including encrypted IBAN, SEPA mandate, family/family payer, departments, roles, versioned documents, data request (JSON), anonymisation; **self-service** – members maintain their address/phone/email/bank details themselves online, see [docs/SELBSTDATENPFLEGE.en.md](docs/SELBSTDATENPFLEGE.en.md) |
| Honours | Honour types, honours, configurable anniversary rules, anniversary list with direct creation |
| Fees | Membership types, rules (age, family, validity years, priority), individual fees, fee years with an invoice run; amounts are frozen into the invoice |
| Invoices | Number series `RE-YYYY-000001`, draft → issue (unchangeable afterwards), PDF, **e-invoice (ZUGFeRD/Factur-X PDF, EN16931, XSD-validated)**, email, cancellation (with a bookable **refund** for already-paid invoices), credit note, reminder stages with PDF; **VAT per line item** (0% standard, mixed rates on one invoice too) for non-charitable clubs/a taxable commercial operation, with a net/tax/gross breakdown on the PDF and e-invoice |
| Payments/Bank | Payments per invoice including reversed direct debits, bank statement import in **CSV, MT940 and CAMT.053** (format detected automatically) with duplicate detection, automatic matching (invoice no. → member no. → IBAN), a "manual matching required" list; **SEPA bulk direct-debit export** (pain.008/CORE) for open invoices with a SEPA mandate, automatic first/recurring direct-debit detection; **FinTS fetch** directly from the web interface including the TAN prompt (tested against a real bank, see below) as an alternative to manual bank-statement import |
| Cash book | Accounts (bank/cash), posting categories with a tax category, entries with a receipt number and receipt upload, import from payments/donations/expense allowances/events (idempotent), **import e-invoice** (read in XRechnung/ZUGFeRD and file as a pre-filled expense with the receipt), **add receipt to archive** (additionally file it in the general document archive) |
| Cash report | Period report with account overview, income/expenses by category and tax category, year-over-year comparison, target/actual reconciliation, auditor's remarks, signature lines, cash-book attachment; PDF + Excel; closing locks the period and files the PDF in the archive |
| Inventory | Inventory numbers `INV-000001`, categories, locations, condition, warranty, photos/documents, **import** from Excel/CSV (like members), label printing with a **QR code** per item |
| Lending | Reservation → issue → return, conflict checking (overlaps, defective, overdue), deposit/fee, condition on issue/return, loan-slip PDF, linked to events; **lending cart** (scan QR labels with a phone) and bulk lending of several items as one **transaction** (shared issue/return/invoice/loan slip); on return, choose whether a deposit is refunded or kept (→ invoice) |
| Stock-taking | A snapshot of stock, ticking off items (found / not found / damaged), closing, history is kept |
| Donations | Donations (cash/in kind/waived expenses/fee), individual and collective receipts, issuing with number series `ZB-YYYY-000001`, cancellation, PDF, a check of the club's details |
| Expense allowances | Volunteer/instructor flat-rate allowance, expense reimbursement, approval workflow, tax-free-allowance overview per person/year, waiving an expense → donation |
| Events | Planning, tasks, shift schedule with staffing, registrations, budget (planned/actual), inventory reservation, iCal export |
| Correspondence | Club logo (on every PDF), editable templates (invitation, minutes, mail merge …) with placeholders, individual documents with PDF and Word export, mail merges with a recipient filter (a single PDF or email with a PDF attachment) – see [docs/SCHRIFTVERKEHR.en.md](docs/SCHRIFTVERKEHR.en.md) |
| Archive | Folder structure (category/year), versioned documents, linked to events, protected file access; generated PDFs are filed automatically; optional submission to **Paperless-ngx** (individually or in bulk); individual documents can be marked **public** (privacy policy, intake form, etc.) – they then appear without login on a public downloads page |
| OpenSlides | Integration with OpenSlides 4: creating/syncing member accounts, creating a meeting + agenda from an event, **retrieving election results** (vote distribution of completed personnel elections flows back into the event, also directly into the minutes via the `{wahlergebnisse}` placeholder) (implemented following the documentation, untested) |
| Paperless-ngx | A connection per club (address, API token stored encrypted, connection test); send archive documents to an existing Paperless instance via a button or in bulk (correspondent/document type/tags are created there automatically if needed) |
| Audit trail | Every change: who, when, IP, field old → new, an optional reason; sensitive fields masked |

## Important notes

* **Back up `FIELD_ENCRYPTION_KEY`!** Without it, encrypted IBANs cannot be read. Backup:
  `docker compose exec web /app/scripts/backup.sh`.
* **Update notification:** Superadministrators see a notice banner as soon as a newer Feuerix version has
  been released – checked in the background (Celery), at most once a day, triggered on the next page load
  (`UPDATE_CHECK_URL`/`UPDATE_CHECK_INTERVALL_STUNDEN` in `.env`, leave empty to disable, e.g. without
  internet access). Only triggers a notice, never updates anything automatically.
* **License notice:** the footer of every page links to the AGPL-3.0 license and the source code
  (`PRODUCT_SOURCE_URL` in `.env`) – for your own fork, please adjust it to your own source code address, see
  the "License" section.
* **Donation receipts:** the PDF text blocks follow the structure of the official template, but do not
  replace a review against it. Check against the current official (BMF) template or a tax advisor/tax office
  before first real use. The club's details (tax office, tax number, determination date, purposes) must be
  maintained under *Administration › Club*.
* **Tax-free allowances** (default: €3,300 instructor, €960 volunteer) are configurable per club – please
  check they're up to date. The overview only knows about payments from this club.
* **Legal notice:** the text field under *Administration › Club* is shown, without any review, on a public
  page that doesn't require login (required under § 5 TMG) – the content must be entered correctly and
  completely by the club itself.
* **Fee run:** charges the full annual fee for every member active at some point during the year (no pro-rata
  calculation).
* **E-invoices:** receiving (reading known core fields from XRechnung/ZUGFeRD, filing as a receipt) and
  issuing your own invoices as a **ZUGFeRD/Factur-X PDF** (EN16931 profile – the normal PDF invoice with
  embedded XML) are included. The embedded XML is generated via the [`factur-x`](https://github.com/akretion/factur-x)
  library and automatically validated against the official XML schema (XSD) in the process – real structural
  validation, not hand-written XML. **Not** checked are the full EN16931 business rules (Schematron – which
  would additionally require a Java validation tool or Saxon server, deliberately not included) and the
  PDF/A-3 conformance of the carrier file itself (no veraPDF check). Lacking per-line VAT rates otherwise, a
  blanket tax exemption under § 4 UStG (non-profit core purpose) is assumed; for actually VAT-liable
  transactions (taxable commercial operation) make sure to check before sending (or have it checked) and run
  the generated file through an official validation tool (e.g. the KoSIT validator). Usually irrelevant for
  ordinary membership invoices anyway, since members aren't businesses and so there's no B2B e-invoicing
  requirement.
* **OpenSlides election results:** "Import election results from OpenSlides" (on the event, once a meeting is
  linked) fetches the vote distribution of all **completed personnel elections** (status "finished"/
  "published") – not the results of votes on motions. The software deliberately does not decide itself who is
  elected (majority requirements/tie-break rules live in the bylaws) – only the plain yes/no/abstain
  distribution per candidate is shown, which can also be pulled directly into the minutes via the
  `{wahlergebnisse}` placeholder. Implemented technically via a single, nested query to the OpenSlides
  autoupdate service (following its documentation, likewise not tested against a real instance). Fetching
  again fully replaces previously imported results for the same event.
* **Paperless-ngx:** either use an already-running, separate instance (just enter the address and API token
  under *Administration › Paperless Integration*), or optionally run it alongside, on this server, via
  [paperless/](paperless/) as its own Docker Compose stack (see INSTALL.en.md, section 9). Submission is, in
  either case, a one-way upload – there is no sync of status/metadata back from Paperless into Feuerix.
* **Bank statement import:** CSV, MT940 and CAMT.053 are recognised automatically from the file extension/
  content; for MT940, the reference field is only searched using the common German SEPA field identifiers
  (`SVWZ+` and others) – if a bank deviates from this, the entire text ends up unstructured in the reference
  field.
* **FinTS fetch** (*Administration › FinTS Accesses*): fetch bank transactions directly from the web
  interface, including the TAN prompt (app/SMS/chipTAN, with a graphic display for chipTAN) – as an
  alternative to manual bank-statement import. A club can create **several FinTS accesses** (e.g. for
  different banks); each cash-book account (*Cash › Accounts*) can optionally be linked to one – accounts
  without a link continue to run via manual bank-statement import as before. "Fetch account data" on an
  access's detail page only shows the IBAN/BIC of the accounts held at the bank (connection test/matching
  aid, without importing transactions). The bank PIN is **never stored**, but requested again on every fetch,
  and only lives briefly (until the TAN process is complete) server-side in the session. Additionally
  requires a free FinTS product ID registered with the German Banking Industry Committee – **not** shipped
  with Feuerix; every operator registers their own and stores it either as `FINTS_PRODUCT_ID` in `.env` or
  (preferred, since it's encrypted in the database instead of in plain text in the configuration file) under
  `/admin/` › System settings. Implemented following the documentation of `python-fints` and successfully
  tested against a real bank (plain transaction fetching – for which many banks don't require a TAN anyway).
  Since FinTS implementations can vary between banks, a first test fetch with your own bank is still
  recommended before going live. Several TANs requested in a row are supported; a single fetch processes
  every account held at that bank.
* **Operations:** put it behind a reverse proxy with HTTPS and enable `HTTPS=1` in `.env`. Bootstrap/HTMX are
  bundled locally at build time (no external CDNs).

## Development

Tests: `python manage.py test --parallel` (needs PostgreSQL access as in `.env`; `--parallel` spreads the
tests across all CPU cores and speeds things up considerably). GitHub setup and CI:
[docs/GITHUB.en.md](docs/GITHUB.en.md).

**Test data:** `python manage.py beispieldaten --verein <code> [--anzahl 40] [--ohne-inventar]` creates
fictional members for an existing club, plus a fee-year invoice run with a realistic payment distribution
(fully paid / partly paid with a reminder / open and overdue) and sample inventory (fire-brigade equipment
and event technology with categories/locations) – for test/demo installations only, not intended for
production use.

## Not yet included

A feed of voting results on motions from OpenSlides back into the minutes – **election results** (personnel
elections) already flow back, see above –, a REST API (DRF), pro-rata fees, an update/restore interface.
SEPA direct debit only generates the collection file (pain.008) – the return channel (arrived/reversed) still
runs via the normal bank-statement import.

## License

Copyright (C) 2026 Rico Tengler

[GNU Affero General Public License v3.0](LICENSE) (an [unofficial German translation](LICENSE.de.md) is
available for better understanding – only the English original text is legally binding). If the code (even
modified) is operated as a network service, the source code of that version must be made accessible to its
users (§ 13 AGPL). Feuerix already ships a license notice with a source-code link in the footer of every page
for this (`PRODUCT_SOURCE_URL`) – if you make your own changes, please point that address to your own,
actually matching source code location, otherwise the AGPL obligation is not met.
