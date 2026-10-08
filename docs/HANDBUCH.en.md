# Handbook – Feuerix (Version 1.45.0)

This handbook describes how to use Feuerix, the club management software for fire brigade support
associations ("Fördervereine"), for the board, treasurer, secretary and everyone else at the club. It
complements the technical documents [README.en.md](../README.en.md) (overview, installation) and
[INSTALL.en.md](../INSTALL.en.md) (step-by-step setup on the server) with the day-to-day use of the software.

For individual topics there are more detailed documents, referenced from the relevant chapter:
[Self-service data](SELBSTDATENPFLEGE.en.md), [Cash book & member import](KASSE_UND_IMPORT.en.md),
[Correspondence & templates](SCHRIFTVERKEHR.en.md).

The currently running version is shown in the footer of every page (e.g. "Version 1.0.0") – handy when
describing an error to support.

This handbook and the detailed documents are also available directly in the web interface under **Help**
(top of the navigation, visible to every logged-in user) – no separate file needed.

## Contents

1. [Login and interface](#1-login-and-interface)
2. [Roles and permissions](#2-roles-and-permissions)
3. [Member management](#3-member-management)
4. [Fees, invoices and payments](#4-fees-invoices-and-payments)
5. [Cash book and cash report](#5-cash-book-and-cash-report)
6. [Inventory and lending](#6-inventory-and-lending)
7. [Donations and donation receipts](#7-donations-and-donation-receipts)
8. [Expense allowances](#8-expense-allowances)
9. [Events](#9-events)
10. [Honours and anniversaries](#10-honours-and-anniversaries)
11. [Correspondence, templates, document archive and corporate design](#11-correspondence-templates-document-archive-and-corporate-design)
12. [OpenSlides integration](#12-openslides-integration)
13. [Paperless-ngx integration](#13-paperless-ngx-integration)
14. [Reports and audit trail](#14-reports-and-audit-trail)
15. [Club settings](#15-club-settings)
16. [Data protection and security](#16-data-protection-and-security)
17. [Known limitations](#17-known-limitations)

---

## 1. Login and interface

After logging in, staff with an administration account land on the **dashboard** – a personal greeting with
the date at the top, followed by member counts, this year's fee status, upcoming anniversaries/honours,
overdue loans, upcoming dates, open tasks and expense requests. Members who only have self-service access
(see chapter 3) instead land directly on "My Data".

**Preview:** the detail pages of invoices, reminders, donation receipts, cash reports, documents and mail
merges (there, the first letter) show the generated PDF right on the page; in the archive this applies to
PDF and image files. The preview only appears for logged-in users with read permission and can only be
embedded within Feuerix itself.

**Permissions under the data protection bylaws (permission matrix):** under *Administration › Permission
matrix*, access rights are displayed exactly as in the data protection bylaws' permission matrix and are
**editable per cell**: rows are the data areas (core member data, date of birth, fee data, bank details and
SEPA mandates, payment transactions, event data, participant lists, club communication, newsletters/mailing
lists, club software/administration, data-protection documentation, data breaches, deletion of personal
data), columns are the roles; levels are: **V** full access, **B** edit, **L** read, **–** no access.
**Deleting** personal data is granted exclusively via the "Deletion of personal data" row (so, for example,
the treasurer may delete while the secretary may not). Date of birth and bank details/SEPA mandate are their
own permission areas: without the permission, these fields are invisible or read-only in the record, form,
export, data request and import. For new clubs (and retroactively via the "Create data-protection-bylaw
roles and tags" button) the six roles **1st Chair, 2nd Chair, Treasurer, Deputy Treasurer, Secretary, Deputy
Secretary** are created (suffixed "(DSO)") together with identically named tags carrying the bylaws' values.
Deputies hold the permissions of their role. Granting and revoking runs via tags: whoever receives the tag
for a role and has an administration account automatically gets the role; if the tag is removed or the
member leaves, the account is **deactivated** (§ 17: revoke rights immediately, never delete). The page warns
about more than six people with access (§ 6), unfilled or multiply filled roles, and accounts without a
role. Newsletters (mail merges) and participant lists (registrations) are their own permission areas;
existing roles keep their previous behaviour.

The navigation at the top is grouped by topic (Members, Correspondence, Finance, Cash, Inventory, Events,
Reports, Administration) and only shows the entries for which your own role has at least read access.

**Language:** top right in the menu bar (also on the login page, before signing in) you can switch between
**German** and **English**. The choice is stored in a cookie and applies browser-wide until changed again.
Currently translated: the navigation, login/logout, the dashboard, the list/detail/form pages (buttons,
filters, messages), and all the stand-alone special pages (e.g. anniversaries, reports, import wizards,
OpenSlides/Paperless settings); the domain-specific field names of individual modules (e.g. a member's form
fields) are being translated gradually.

**Sorting lists:** in every table you can click a column header to sort by it (an arrow shows the direction);
clicking again reverses the direction. This works for every column backed by a real data field (not for
purely computed columns such as "Borrower" in the lending list).

## 2. Roles and permissions

Every administration account (*Administration › Users*) is assigned a **role** per club. A role determines
which modules an account may **view**, **create**, **edit** or **delete**. If needed, an individual account
can also be given extra, individual permissions.

*Administration › Roles (advanced)* shows these roles in technical detail – labelled accordingly in the
navigation, since for everyday use the **tags** (see "Access via tags" below) and the permission matrix are
simpler. The role list remains important for two cases: an administration account without an associated
member (e.g. a purely technical account – tags can only be assigned to members) and the Superadministrator
itself, which deliberately appears neither in the permission matrix nor as a tag.

There is no longer a fixed set of default roles; permissions are granted via the **permission matrix based on
the data protection bylaws** (chapter 1, section "Permissions under the data protection bylaws") and set
there, per role and data area, **directly in the web interface**. The following roles are created
automatically for every club (permissions: see the permission matrix, also editable there):

| Role | Typical use |
|---|---|
| **Superadministrator** | Technical support; bypasses permission checks, does not appear in the permission matrix |
| **1st Chair (DSO) / 2nd Chair (DSO)** | Chairing |
| **Treasurer (DSO) / Deputy Treasurer (DSO)** | Managing the finances |
| **Secretary (DSO) / Deputy Secretary (DSO)** | Minutes/correspondence |
| **Administrator** | Full rights on all data areas (e.g. for technical support of the software); not itself part of the data protection bylaws, but counted among the people with access under them (§ 6) |
| **Auditor, Inventory Manager, Event Planner, Member Administration, Read-only User** | Additional roles for finer distinctions (e.g. a read-only auditor); likewise not part of the data protection bylaws and, unlike the six DSO roles, not required to be filled |

All roles are also automatically created as a same-named **tag** (see "Access via tags" below) – including
the additional roles; whoever carries a tag with a role automatically receives that role when an
administration account is set up. Missing roles/tags can be added later via a button under
*Administration › Permission matrix*.

Under the data protection bylaws, all six DSO roles get **full rights on "Club software / Administration"**
(users, roles, club settings, OpenSlides/Paperless integration, "set up administration account") – in a
small, volunteer-run club the elected officers are at the same time the people looking after the software.
Anyone who wants to restrict this adjusts the relevant role in the permission matrix (set the "Club software /
Administration" row to "Read" or "–").

**Access via tags:** instead of assigning roles one by one, members are given **tags** (*Administration ›
Roles: Tags (access rights)*, right next to *Roles* in the navigation). Each tag determines which **role** in
this software, which **Paperless group** and which **OpenSlides group** (in meetings) its holders receive. In
addition to the six DSO roles, Administrator and the additional roles, there is the **Assessor** tag: a board
member without further rights in this software (Paperless group "Board", OpenSlides group "Staff", but no
role – and therefore not counted among the six people with software access under § 6). In a member's record,
tags appear in the edit form as a **checkbox list** (multiple selection, not a dropdown) and are shown on the
detail page in the "Roles (tags/access rights)" section – right next to the historised roles with their
from/to dates.

**Creating new tags:** via *Administration › Roles: Tags › Add* you can create a new tag – either **with its
own rights** (tick "Has its own rights in this software", below which are the same per-module rights
checkboxes as for a role; a same-named role is automatically created in the background, or updated on a
later change) or **without rights** (a purely organisational label, like Assessor). A name clash with an
existing role is reported clearly when saving.

If a member carries a tag with a role but doesn't yet have an administration account, the record points this
out (as does the permission matrix, club-wide). For the six DSO roles (which, under the data protection
bylaws, only one person should hold each) the edit form shows "(already held by: …)" right next to the
checkbox if another active member already carries that tag – not for Administrator and the additional roles,
since those aren't limited to one person. This is a notice, not a block: a double assignment (e.g. during a
handover) can still be saved. How tags synchronise Paperless and OpenSlides accounts is covered in chapter 12
(OpenSlides integration) and chapter 13 (Paperless-ngx integration).

## 3. Member management

**Markers in a member's record:** three checkboxes identify members: **Board member**, **Senior/honorary
section** and **Active member of the response unit**. All three appear in the member list, are filterable
there, and are taken into account on import/export (columns "Board member", "Senior/honorary section",
"Active member of the response unit"; "yes" or "x"). **Board member** is not a manual choice here – it is
derived automatically from tags (see chapter 2, "Access via tags"): whoever carries one of the six DSO roles
or the **Assessor** tag counts as a board member; the checkbox follows automatically. For each of these tags
a separate historised role (from/to) is kept – under the name of the respective tag (e.g. "Treasurer" or
"Assessor"), not a shared placeholder, so that two different offices remain distinguishable in the member's
record. This also drives the Paperless sync. The "Board member" column is therefore ignored on import (noted
in the import report).

Under *Members*, personal data, address, bank details (SEPA), membership type, family membership,
departments (as checkboxes, multiple selection) and roles held (e.g. "1st Chair", with a period) are
maintained. The member number is assigned automatically, but can also be set manually.

**Families**: under *Members › Families* you can create a family (just a name/label, e.g. "The Smith
Family"). A family's detail page shows its current members directly and offers two ways to add more:
"Add" in the "Members of this family" section opens the normal member-creation form with the family already
pre-filled (for brand-new members); the "Add existing members" picker below it lets you assign several
existing active members to this family at once via a multi-select (showing "already in: …" as a hint for
someone already assigned elsewhere). Either way, each family member's own record carries the "Family" field;
additionally, the "Pays the family fee" checkbox marks exactly the one person who pays for the whole family
(see the family fee tier further below, under fee rules).

**Import/export**: via *Administration › Member import* (not on the member list itself, since it's usually
only needed once, when setting up the club) you can read in a spreadsheet – with a **dry run** (nothing is
saved, only checked), matching existing members by member number or by first name + last name + date of
birth, and the option to automatically create unknown membership types/departments. A template with a sample
row and notes is available for download. "Full export (Excel)" on the member list exports all members,
optionally including bank details (fee permission required).

**On a member's detail page** (depending on your own permissions):
- "Data request (JSON)" – a complete GDPR data request, including invoices, payments, donations, expenses,
  honours, documents.
- "Anonymise" – irreversibly deletes personal data, photo and documents; invoices remain for tax record-
  keeping reasons. Only possible with delete permission on members. If the member has a linked **OpenSlides
  account**, it is adjusted too (name/username/email overwritten, account deactivated) – not just
  deactivated locally. If the OpenSlides integration is unreachable or not set up, a warning appears asking
  you to check the account there manually; the local anonymisation is carried out regardless.
- "Send self-service access credentials" / "Lock access" / "Delete starting password" – see
  [Self-service data](SELBSTDATENPFLEGE.en.md).
- "Set up administration account" – sets up a full administration account with a role directly from the
  member (instead of via *Administration › Users*), also see [Self-service data](SELBSTDATENPFLEGE.en.md).
  Requires the `verwaltung` permission.

The detail page also shows – depending on your own permissions – sub-lists with the member's fees/invoices,
roles, honours, documents, lending transactions, donations and expense allowances.

## 4. Fees, invoices and payments

**Fee run**: under *Finance › Fee years* a **fee year** is created once a year (due date, cut-off date for
age-based rules). The "Generate fee invoices" button automatically creates an invoice for every member liable
for fees (active/dormant during that period) – amount by priority: the member's individual fee > the first
matching fee rule (*Administration › Fee rules*, e.g. age or family tiers) > the membership type's standard
fee. Members without a fee/rule are reported by name as skipped. The fee run can be triggered repeatedly
without risk – anyone who already has an invoice for the year is not billed twice. **Note:** the full annual
fee is always charged; there is no pro-rata calculation for joining mid-year.

**Family fee tier**: a fee rule with "Family memberships only" applies only to members with an assigned
family (see chapter 3). During the fee run, the full rule amount is charged exclusively to the person marked
in their record as "Pays the family fee"; every other member of the same family gets 0 € with the note
"included in the family fee" on the invoice. Without a family-payer checkbox set within the family, no one is
charged – this should be checked before running the fee run.

**Invoices** (which can also be created individually or as a collective invoice) go through the stages
*Draft* → *Issue* (assigns the final number `RE-YYYY-000001`, unchangeable afterwards) → *Open* → *Partly
paid/Paid*. Depending on status and permission, an invoice offers: "PDF", "E-invoice (ZUGFeRD PDF)" (issued
invoices only), "Issue", "Send by email", "Cancel", "Create reminder", "Record payment" (the amount is
pre-filled with the outstanding amount).

**VAT** (for non-charitable clubs, or a club's taxable commercial operation): under *Administration ›
Club/Settings*, "Subject to VAT" can be enabled – new invoice line items then suggest 19% as the tax rate,
but every line item still has its **own** VAT rate (0% for e.g. the non-profit core purpose, 19%/7% for a
taxable commercial operation) and so can be mixed on a single invoice. As soon as an invoice contains VAT,
the PDF and e-invoice automatically show the net/tax/gross breakdown; without VAT liability and without a set
tax rate, an invoice remains, as before, a simple amount column. A custom **tax note** (e.g. "No VAT is
charged pursuant to § 19 UStG") can likewise be stored in the club settings; without custom text, the
standard note "Tax-exempt under § 4 UStG (non-profit core purpose)" still appears at 0%. A **VAT ID** can
also be maintained there (it then appears on the e-invoice). None of this replaces tax advice – in
particular, which club activities are actually subject to VAT should be clarified with a tax advisor/tax
office.

**E-invoice (ZUGFeRD PDF)**: generates a ZUGFeRD/Factur-X file (EN16931 profile) from the invoice for
download – this is the normal PDF invoice with an additional, machine-readable XML file embedded. Intended
for the rare case where an invoice goes to a recipient subject to e-invoicing requirements (e.g. a public
authority or a company); the PDF can be opened and printed as usual, while e-invoice-capable accounting
systems additionally read the embedded XML. The embedded XML is automatically validated against the official
EN16931/CII schema (XSD) when generated – real structural validation. **Not** checked are the full EN16931
business rules (Schematron – which would additionally require a Java validation tool or Saxon server,
deliberately not included) and the PDF/A-3 conformance of the carrier file itself (no veraPDF check). VAT
rates per line item (see above) are correctly carried over into the e-invoice as separate tax groups (mixed
rates too). Before sending to a recipient subject to e-invoicing requirements, please still run it through an
official validation tool (e.g. the KoSIT validator) or consult a tax advisor.

**Cancellation and refund**: "Cancel" creates a cancellation invoice with the opposite sign; the original
invoice is marked *cancelled*. If the invoice had already been (partly) paid, the cancellation invoice shows
a "Refund to payer still open" notice and a **"Record refund"** button – this records the actual
reimbursement to the member/external payer as its own "Refund" payment type. This entry is later correctly
booked as an **expense** in the cash book (not as a negative income).

**Bank transactions**: import a bank statement – **CSV** (common German bank export formats), **MT940**
(SWIFT statement, usually `.sta`) and **CAMT.053** (ISO 20022 XML) are recognised automatically; duplicates
are detected and skipped based on date/amount/IBAN/reference. Afterwards, "Auto-match" assigns transactions
via the invoice number in the reference text, otherwise via the member number, otherwise via a unique IBAN
match. Reversed direct debits (negative amounts) are only auto-matched if the text recognisably sounds like
one; otherwise they're marked "manual" for follow-up. **Note:** for MT940, the reference field (`:86:`) is
searched using the German field identifiers customary since the SEPA changeover (`SVWZ+`, `ABWA+`/`ABWE+`,
`IBAN+`); if a bank deviates from this, the entire text ends up unchanged in the reference field instead of
in individual fields. If at least one FinTS access is set up, this page additionally shows a "Fetch
transactions" button per access as a shortcut to the FinTS fetch (see below). A bank transaction can also be
**deleted** (e.g. an accidental duplicate import) – a payment that was matched to it is kept, it just loses
the reference to this transaction. Fetching the same period again recreates the deleted transaction, since
duplicate detection only knows about transactions present in the database.

**FinTS fetch** (tested against a real bank, see chapter 17): an alternative to manually importing a bank
statement – under *Administration › FinTS accesses*, create one or more accesses (label, bank sort code,
online-banking login, and the bank's FinTS address; these details are in your online-banking documentation
or can be obtained from your bank) – a club can maintain **several accesses**, e.g. if it has accounts at
different banks. This also requires a free FinTS product ID, which the operator of the instance registers
once with the German Banking Industry Committee (not shipped with the software) and stores either as an
environment variable or – encrypted, and changeable without server access – under `/admin/` › System
settings (for technical administrators only, not part of normal club administration). Each cash-book
**account** (*Cash › Accounts*) can optionally be linked to one of these accesses – accounts without a link
continue to run via manual bank-statement import as before.
On an access's detail page there is "Fetch account data" (shows the IBAN/BIC of the accounts held at the
bank – useful for checking the connection and finding the right match to a cash-book account, without
importing transactions yet) and "Fetch now" for the actual transaction fetch. Both ask for the PIN – if the
bank requires a TAN (common), the bank's prompt appears in the next step (text, or for chipTAN a graphic to
scan) together with an input field. After confirmation, "Fetch now" creates new account movements as bank
transactions, just like with the file import (duplicates are skipped), and they can then be matched as
usual. The bank PIN is **never stored**.

**Storage:** of the FinTS access data, only the **online-banking login** (the login name, not the PIN) ends
up in the database – encrypted like the IBAN and API tokens (`VerschluesseltesTextField`, Fernet encryption
using the server-side `FIELD_ENCRYPTION_KEY`). Label, bank sort code and FinTS address are uncritical,
publicly known bank details and remain unencrypted. The **FinTS product ID** is likewise encrypted if it was
stored under `/admin/` › System settings (alternative: unencrypted as the `FINTS_PRODUCT_ID` environment
variable, in which case it lives outside the database, in the server configuration). The bank PIN itself is –
as described above – never stored at all, not even encrypted.

An online-banking access often covers several accounts (e.g. the club account together with private accounts
under the same login) – "Fetch now" would otherwise fetch **all** of them. On the "Fetch account data" page
you can therefore tick which IBAN(s) should be considered going forward ("Save selection"); "Fetch all
accounts (no restriction)" resets this back to the default (all accounts of the access). An active
restriction is shown as a notice on the access's detail page.

**SEPA direct debits**: under *Finance › SEPA direct debits* → "Create new collection", all open/partly paid
invoices from members with payment method "SEPA direct debit" and a complete mandate (IBAN, mandate
reference, mandate date) are offered for selection (amount = the outstanding balance in each case). After
entering the due date, the software generates a SEPA bulk direct-debit file (`pain.008`, CORE format) to
upload to the club's online banking – for this, the club's IBAN and creditor ID must be stored under
*Administration › Club*. Whether a member is collected as a first (FRST) or recurring (RCUR) direct debit is
determined automatically by the software, based on whether they were already included in an earlier
collection. **Important:** the file only contains the collection instruction – whether the money has
actually arrived (or come back as a reversed direct debit) is only shown by the later bank-statement import;
the software does not automatically book a payment just because a collection was created.

## 5. Cash book and cash report

Described in detail in [Cash book & member import](KASSE_UND_IMPORT.en.md). In brief: entries are either
recorded manually or pulled automatically from other modules via "Import from payments/donations/events"
(can be triggered repeatedly; transactions already imported are not booked twice). Every entry belongs to an
**account** (bank/cash) and a **posting category**, which in turn is assigned to one of the four tax
**categories** (non-profit core purpose, asset management, tax-privileged commercial operation, taxable
commercial operation – please align with your tax advisor/tax office).

**Import e-invoice**: via the button of the same name on the cash-book list, you can read in a received
electronic invoice – as a plain XML file (XRechnung) or as a PDF with embedded XML (ZUGFeRD/Factur-X).
Invoice number, date, amount and issuer are recognised automatically and pre-filled as an expense in the cash
book; the original file is attached directly as the receipt. Please check the account and category
afterwards (default: the first bank account, category "Other expenses"). If no known format is recognised,
the file is still filed as a receipt – please enter the remaining details manually in that case.

**Add receipt to archive**: a receipt uploaded to an entry (scan/photo) initially only lives on that entry
and does not automatically appear in the general document archive (*Correspondence › Archive*). The "Add
receipt to archive" button on the entry's detail page additionally files it there if needed (folder
"Receipts"/year) – e.g. to find it alongside other documents, or to forward it to Paperless-ngx. The button
then disappears and a notice shows where the receipt was filed.

A **cash report** over a period shows an account overview, income/expenses by category with a year-over-year
comparison, and a target/actual reconciliation against the counted cash/account balance. "Close" permanently
locks all entries in the period against later changes (corrections afterwards only via a reversing entry) and
automatically files the PDF in the archive.

## 6. Inventory and lending

**Items** (*Inventory*) automatically get an inventory number (`INV-000001`), a condition (new/good/
signs of wear/defective/retired), a category and location, optionally a deposit/lending fee and a
"lendable" checkbox.

**Import**: just like member import – dry run, matching via inventory number, optionally auto-creating
unknown categories/locations.

**Labels with QR code:** "Print label" (single) or "Print labels (all)" on the list generates a PDF with
stickers (inventory number + QR code per item). The QR code points to a scanning address in the system. Label
size and layout can be adjusted under *Administration › Club/Settings* ("label width/height", "labels per
row"/"label rows per page") – by default a multi-column A4 sheet (3 × 6, 58 × 40 mm). If both "labels per
row" and "label rows per page" are set to 1, the PDF page is instead cropped exactly to the configured label
size (one label = one page) – which lets you print directly on a continuous-roll label printer such as a
Dymo LabelWriter 450 (standard address label, 89 × 28 mm). Besides the inventory number and description, the
storage location is printed too, if one is set. The layout adapts automatically to the label's shape: if a
label is noticeably taller than it is wide (e.g. a narrow roll used in portrait orientation), the content is
rotated 90° so the QR code makes use of the long side instead of the short one. If a label (possibly after
rotating) is very flat and wide, the QR code and text are placed side by side instead of stacked – otherwise
the QR code would end up unnecessarily small on the short height.

**Starting a loan:**
- *Manually* via "Create loan/reservation" on an item (the full form, including adjusting the deposit/
  lending fee for this particular loan).
- *By scanning*: scan the sticker with a phone (logged in to the system) – the item lands in the **lending
  cart**. This lets you scan several items one after another (e.g. a pavilion, benches, a projector for an
  event) before using "Start loan" to create **one shared transaction** with a single form (borrower,
  period, purpose entered once).
- "Lend multiple items" on the lending list lets you start the same bulk transaction without scanning, via a
  checkbox selection.

Several items lent out together are linked as a **transaction**: from the transaction page you can issue all
items together, take them all back together, print a shared loan slip, and – see below – they end up on
**one** shared invoice instead of many individual ones.

**Recording a return** is a form (for a single item as well as within a transaction): for each item, the
**condition on return** is chosen (this immediately affects the item itself too, so the inventory overview
stays accurate) and – if a deposit was taken – whether it is **refunded** or **kept**. This is a deliberate,
independent decision and is not automatically derived from "defective". If the deposit is to be refunded but
hasn't been paid out yet, a "Deposit refunded" button appears to tick off.

**Billing**: if a returned item has a lending fee, an invoice to the borrower (member or external person) is
created automatically on return. Deposits that are kept are added as an extra line item on the same invoice.
If several items belong to one transaction, everything ends up on **one shared invoice** in the end – even if
the items are returned one after another instead of all at once.

**Stock takes**: "Create stock take" creates a snapshot of the current stock (every item that hasn't been
retired), recording each item's current location as its "location (expected)". On the stock-take page, items
are marked with a click as ✓ found, ✗ not found, or ⚠ damaged; each row also has a dropdown (picked from the
club's configured locations) for the "location (actual)" found during the count (e.g. if an item was moved) –
the save button alone stores just the location
without changing the result. Clicking any of these buttons returns you to that same row instead of jumping to
the top of the page. "Close stock take" fixes the result permanently.

## 7. Donations and donation receipts

Individual **donations** (money, donations in kind, a membership fee donated, a waived expense allowance) are
recorded and can be linked to a **donation receipt**: "Create individual receipt" directly on a donation, or
via *Donations › Create collective receipts* – there, all cash donations not yet confirmed for the year are
grouped by donor and created as collective receipts with one click (donations in kind always get an
individual receipt). Before "Issuing" (which assigns the number `ZB-YYYY-000001` and freezes the club's tax
details as of the time of issuing), the system warns if the tax office/tax number/determination date are
missing from the club's settings, or if the determination is older than three years.

> The wording of the donation receipt follows the official template but does not replace a legal review –
> please check it against the current official template or a tax advisor before the first real use.

## 8. Expense allowances

Requests (volunteer flat-rate allowance, instructor flat-rate allowance, expense reimbursement against a
receipt, other compensation) go through *Requested* → *Approved* → *Paid out* (or *Rejected*). The treasurer
and Administrator can approve/reject/mark as paid out; under the data protection bylaws, the chairs only have
read access to payment transactions (editable in the permission matrix). "Annual overview of tax-free
allowances" shows, per recipient and year, the totals against the tax-free allowances stored for the club
(volunteer/instructor flat-rate allowance) and warns if an allowance is exceeded, or if no declaration is yet
on file that the flat rate hasn't already been used up elsewhere. An approved expense reimbursement can be
converted into a donation via "Waive → donate the expense".

## 9. Events

The event detail page is a hub: agenda (including a "standard agenda" for general meetings with ten common
items), tasks, a shift schedule with staffing status, registrations (members or guests, with a headcount),
budget (planned/actual per line item), reserved inventory, as well as documents/mail merges and archive
documents generated for the event. Directly from here: "Reserve inventory" opens the multi-select picker
(check off several items at once, pre-filled with the event's dates) - no borrower is needed here since the
association itself is reserving them. "Create invitation"/"Invitation to members (mail merge)"/"Create minutes" (from the
respective default template), and, with an OpenSlides integration set up, "Create in OpenSlides"/"Transfer
agenda". Every date can be exported as a calendar file (.ics).

## 10. Honours and anniversaries

Under *Anniversaries*, every member who reaches one of the configured anniversary thresholds this year
(*Administration › Anniversary rules*, e.g. "25 years") appears with a pre-filled "Create honour" link and a
note on whether they've already been honoured. Types of honour are freely configurable under
*Administration › Honour types*.

## 11. Correspondence, templates, document archive and corporate design

Described in detail in [Correspondence & templates](SCHRIFTVERKEHR.en.md). In brief: **templates** contain
placeholders such as `{vorname}`, `{briefanrede}`, `{verein}`, `{veranstaltung_datum}` or `{tagesordnung}`
(full list under *Correspondence › Placeholder help*); a set of default templates (invitations, minutes,
member newsletters …) is pre-installed and can be topped up via "Reload default templates", without
overwriting your own changes. A template produces either a single **document** or a **mail merge** to a
filtered recipient list (status/membership type/department/role/email address required); both can be output
as PDF or Word (.docx), sent by email, and archived automatically in the **document archive** (with
versioning: the same title in the same folder creates a new version, older ones remain viewable).

**Uploading external documents:** the archive is not limited to documents generated by this software – via
*Correspondence › Archive › "New"* you can upload any externally created file (PDF, Word, a scanned document,
a photo …) and give it a title, category, folder, date, description and tags. The same versioning as for
automatically archived documents applies here too (same title in the same folder = a new version, older
versions remain viewable).

**Corporate design:** PDF and Word output automatically use the same layout per club – the club name large,
top left; the logo top right (uploadable under *Administration › Club/Settings*); a dividing line in the
**accent colour**; and a footer with the register entry/email, authorised representative/address and bank
details – separated by a second dividing line in the optional **second accent colour** (falls back to the
first if not set). No template coding needed: the design results automatically from the club settings. The
same accent colour is also used in the **web interface** by default (navigation bar, buttons, links, a
coloured hover effect when moving over menu items) – but a separate **"Accent colour (web interface)"** field
lets you set a different colour just for the application, independent of letters/PDFs (e.g. one colour for
the app, another for the letterhead). Logo, navigation and icons (Bootstrap Icons) still give a consistent
look. Almost every button in the application automatically gets a matching icon based on its text; every
sub-page additionally shows the icon of its navigation group again, top right. The default accent colour is a
fire-brigade red (#AF2B1E); below the colour fields in the club settings, a small set of common fire-brigade
colours (two shades of red, black, charcoal, signal yellow, dark blue) is offered as one-click presets – any
other colour can still be typed in freely at any time. The navigation bar, buttons, stat cards and card
headers use colour gradients rather than a single flat colour for more depth, built from one **main colour**
and two **accent colours** (all configurable under *Administration › Club/Settings*): "Main colour (web
interface)" drives navigation/buttons/links, "Accent colour 1" is the second gradient stop (falls back to an
automatically derived darker shade of the main colour if not set), and "Accent colour 2" highlights the icon
backgrounds on the stat cards as well as the heading underline (default: signal yellow). The text/icon colour
on top of these is always calculated automatically for sufficient contrast – text stays readable even with
very light accent colours, whatever colour is entered. The logo and club name in the navigation bar are also
a bit larger than typical for club-management interfaces.

**Public documents:** when creating/editing an archive document, "Publicly visible on the start page" can be
enabled (default: off). A document marked this way – e.g. the privacy policy or an intake form for
prospective members – then appears on a public downloads page reachable **without logging in**, linked in the
footer of every page (including the login page). All other archive documents remain visible, as usual, only
to logged-in users with the archive permission. See also chapter 15 (legal notice).

## 12. OpenSlides integration

Under *Administration › OpenSlides integration*, the connection to an OpenSlides instance is stored once per
club (URL, technical account, committee ID, language; optionally a role that the member sync is restricted
to). "Test connection" checks the credentials. "Sync members" creates missing OpenSlides accounts for active
members (credentials can be sent out using the "OpenSlides login credentials" template), updates existing
ones, and deactivates accounts for members no longer in scope. For a linked event, "Create in OpenSlides"
transfers a new meeting with its agenda, and "Transfer agenda" afterwards transfers only newly added items.
"Delete starting passwords" removes all stored OpenSlides initial passwords (e.g. once all credentials have
been distributed).

Under the data protection bylaws, all six DSO roles (row "Club software / Administration" of the permission
matrix) as well as the Superadministrator and Administrator may set up the OpenSlides integration.

**Retrieving election results:** if an event is linked to an OpenSlides meeting, its page additionally shows
"Import election results from OpenSlides". This fetches the vote distribution of every personnel election
already completed in OpenSlides (ballot status "finished" or "published" – elections still in progress
naturally yield no result) and stores it per office/ballot as an "election result" on the event (section
"Election results (from OpenSlides)"). Only the plain yes/no/abstain distribution per candidate is shown –
who was actually elected must be determined and entered based on the bylaws (majority requirements, handling
ties) yourselves; the software deliberately does not decide this automatically. Via the `{wahlergebnisse}`
placeholder, the vote distribution can also be pulled directly into a set of minutes (the supplied "Minutes
of General Meeting" template already uses it). Fetching again fully replaces previously imported results for
that event. **Not** included are results of votes on motions, or a feed of attendance.

## 13. Paperless-ngx integration

Under *Administration › Paperless integration*, the connection to an existing Paperless-ngx instance is
stored once per club (address, API token – stored encrypted; optionally a default correspondent, document
type and tags). "Test connection" checks the address and token. Once activated, every document in the
**archive** (chapter 11) shows a "Send to Paperless" button; the archive list additionally offers "Bulk send
to Paperless" for several documents at once. A missing correspondent/document type/tag is created
automatically in Paperless. Sending runs in the background; the result or an error message appears on the
respective document (reload the page if needed).

**Duplicate protection:** the same file is never submitted twice. Before sending, the club software checks,
via the file checksum, whether exactly this version has already been submitted or already exists in
Paperless; if so, nothing is sent and a notice appears on the document. A changed file, or a new version, is
submitted normally. "Resend to Paperless" (on a document), or the checkbox in bulk sending, lets you
deliberately bypass this protection.

**Tags on a document:** every archive document has a "Tags" field (comma-separated). New documents
automatically get the **type of document and the year** entered there (e.g. "Minutes, 2026") – freely
editable. On submission, these tags are set in Paperless together with the integration's default tags.
Documents without their own tags automatically get the type and year on sending (can be turned off under
"Automatically set type and year as a tag").

**Display in the system:** the archive's detail view shows the document's own tags, the tags most recently
submitted to Paperless ("Tags in Paperless"), and the checksum of the submitted file; in bulk sending the
tags appear as labels. For PDF and image files, the detail view additionally shows a **preview** right on the
page (other file types have no preview and are downloaded as before).

**Confirmation:** whether Paperless has finished processing the document is checked via Paperless's task
query and additionally via the file checksum; previously submitted documents are also confirmed
retroactively when opened.

**Document type:** every submission also sets the document type: by default the type of document (e.g.
invoice, minutes, cash report); it can be overridden in the document's "Document type (Paperless)" field.
Only for "Miscellaneous" does the integration's default document type apply. Paperless creates missing types
automatically.

**Automatic submission:** if "Automatically submit finished documents" is enabled in the integration
(default), the following documents are submitted without any further click, as soon as they're finished –
including archiving, tags, document type and live status:
invoices (on issuing or during a fee run, on cancellation and credit notes; as an e-invoice/ZUGFeRD PDF,
otherwise as a normal PDF), donation receipts (on issuing), closed cash reports, documents filed in the
archive (status "Final" only), mail merges and posting receipts. Manually uploaded archive documents are
still submitted via the button. Submission never blocks finishing a document – errors appear on the archive
document. New versions of a document are created via "Upload new version" or re-filing, and are submitted as
well.

Under *Administration › Paperless integration*, "Sync board" (or tag sync, see chapter 2, "Access via tags")
synchronises Paperless users: holders of a tag with a Paperless group get an account (without administrator
rights) in the groups of their tags; a missing group is created if needed (view, upload, edit – or view only,
if "Paperless read-only" is set on the tag; never delete, never manage). Anyone without a tag any more is
removed from the groups managed by tags, and self-created accounts are deactivated; an account is never
deleted. Existing accounts with a matching username are only assigned to the groups, never changed or
deactivated. Starting passwords for new accounts are shown (stored encrypted) on the page and can be deleted
after being handed over. Requires the API token of a Paperless administrator; on a GDPR anonymisation, the
account is adjusted too. **Note:** whether a holder can see documents uploaded by others depends on
Paperless's own document permissions (not tested).

**OpenSlides via tags:** when creating a meeting from an event (and on every further agenda transfer),
holders of tags with an "OpenSlides group" (e.g. Admin, Delegates, Staff) automatically get that group in the
meeting. This requires an OpenSlides account ("Sync members"). Members with such a tag are always considered
during the sync.

**Superadministrators:** every active administration account with the "Superadministrator" role automatically
gets a Paperless account in the Administrator group during "Sync board", and an OpenSlides account with the
"Admin" group in every meeting during "Sync members" – independent of their own tags. This also applies to
Superadministrators **without** their own member record (e.g. a purely technical support account): name and
email then come from the administration account itself rather than from a member record. If the
Superadministrator role is revoked, or the account is deactivated, these automatically granted rights
disappear again on the next sync. If the administration account, or its underlying user account, is deleted
outright (rather than just deactivated), the linked Paperless/OpenSlides account is deactivated immediately,
not only on the next sync.

**Live status:** after "Send to Paperless" (including in bulk sending), the page shows progress without a
manual reload: queued → sending → processed by Paperless → filed, or an error message. While submission is
in progress, the send buttons are hidden. Once submission succeeds, "Send to Paperless" disappears; only then
does "Resend to Paperless" appear.

Under the data protection bylaws, all six DSO roles (row "Club software / Administration" of the permission
matrix) as well as the Superadministrator and Administrator may set up the Paperless integration; the send
button itself can be used by any role with archive edit rights (e.g. the Secretary).

## 14. Reports and audit trail

*Reports* shows membership development (joins/leaves per year, cumulative count), age structure, fee revenue
per year (planned/actual/outstanding), reversed direct debits per year, inventory value, donations per year
and (with the expenses permission) expense allowances per year. The **audit trail** (*Reports › Audit
trail*, viewable only with the `audit` permission) automatically records every creation/change/deletion with
the user, timestamp, IP address and changed fields; sensitive fields such as IBAN or passwords are masked.

## 15. Club settings

Under *Administration › Club/Settings* (requires the `verwaltung` permission, see chapter 2), you maintain:
club name/address/contact, register entry, bank details including creditor ID, tax office/tax number and
details of the non-profit determination notice (for donation receipts), VAT liability/VAT ID/tax note
(chapter 4, for non-charitable clubs or a taxable commercial operation), payment terms and invoice texts, the
configurable tax-free allowances for expense allowances, as well as the logo, accent colour(s) and the
signature lines for the letterhead (chapter 11).

**Legal notice ("Impressum"):** the "Legal notice" field contains the full text required under § 5 TMG/§ 18
MStV (the responsible person, address, contact, authorised representatives, VAT ID if applicable) and is
shown **without any review** on a publicly reachable page, linked in the footer of every page (even before
login). Please check the text against your bylaws/the register of associations beforehand – the software
does not perform any legal review.

**License notice:** also in the footer of every page is a notice that Feuerix is free software (AGPL-3.0),
with a link to the source code. This fulfils the AGPL's obligation to give users of a (even modified) version
offered over a network access to the matching source code (§ 13 AGPL) – if you modify the code yourself, the
operator must change the address (`PRODUCT_SOURCE_URL` in `.env`) to their own, actually matching source
code location; see the README.

## 16. Data protection and security

- IBANs (members' and the club's own) are stored encrypted in the database, not in plain text.
- Every change is traceably recorded in the audit trail (see chapter 14).
- Member data can be exported at any time as a complete GDPR data request, or anonymised (chapter 3).
- Permission checks are consistently performed server-side, per module and action (view/create/edit/delete)
  – not just by hiding menu items.
- **Cookies:** only strictly necessary cookies are set (login/session, CSRF protection, language setting) –
  no tracking or marketing cookies. A corresponding notice appears once at the bottom of the screen (even
  without logging in), until it is acknowledged.
- **Update notification:** Superadministrators see a dismissible banner as soon as a newer Feuerix version has
  been released. The check runs in the background (Celery), at most once a day, triggered on a
  Superadministrator's next page load – nothing is downloaded or installed automatically, it's just a notice.
  Configurable or disabled via `UPDATE_CHECK_URL` and `UPDATE_CHECK_INTERVALL_STUNDEN` in `.env` (leave empty
  for installations without internet access). The last known state can also be viewed under `/admin/` ›
  System settings.

## 17. Known limitations

Currently **not** included: an automatic feed of voting results on motions from OpenSlides back into the
minutes (results of personnel elections already do flow back, see chapter 12), a REST API, pro-rata fee
calculation for joining/leaving mid-year, and a user interface for database restores (restoring happens via
the command line, see INSTALL.en.md). The SEPA direct debit feature (chapter 4) only generates the collection
file; there is no return channel that automatically detects whether a direct debit actually arrived or was
reversed – that still runs via the normal bank-statement import. The OpenSlides integration follows the
official documentation but has not been verified against a production instance – please check it in a test
run before relying on it. The Paperless-ngx integration was implemented following the official REST API
documentation and has been successfully tested against a running instance (document submission) – for a new
instance, a quick check with "Test connection" and a test document is still recommended. The **FinTS fetch**
(*Administration › FinTS accesses*, see chapter 4) was implemented following the documentation of the
`python-fints` library, also covers the TAN prompt (app/SMS/chipTAN), and has been successfully tested
against a real bank (plain transaction fetching – for which many banks don't require a TAN anyway, since only
payment-initiating actions like transfers require strong customer authentication). Since FinTS implementations
can vary between banks, a first test fetch with your own bank is still recommended before going live. The
bank PIN is never stored in the process, but requested again on every fetch. A free FinTS product ID, which
the operator must register themselves, is additionally required (`FINTS_PRODUCT_ID`, or encrypted under
`/admin/` › System settings) – it is not provided automatically.
