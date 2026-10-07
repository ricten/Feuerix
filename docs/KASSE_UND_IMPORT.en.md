# Cash Book, Cash Report and Member Import/Export

> Part of the [Handbook](HANDBUCH.en.md) – see chapters 4/5 there for the full picture on fees, invoices
> and the cash book.

## Setting up the cash book (one-time)
1. **Cash › Accounts:** "Bank account" and "Petty cash" are already created. Enter an **opening balance** and
   **opening date** (the account/cash balance on the date bookkeeping starts in the system, e.g. Jan 1st).
2. **Cash › Posting categories:** review the suggestions; each category has a **tax category** (non-profit
   core purpose, asset management, tax-privileged commercial operation, taxable commercial operation).
   Please align the assignment (e.g. for a club festival) with your tax advisor/tax office.

## Recording entries
* **Cash › Cash book › New:** date, income/expense (amount always positive), account, category, text, scanned
  receipt. The receipt number `B-YYYY-000001` is assigned automatically.
* **"Import from payments/donations/events":** creates entries from payments against invoices (reversed
  direct debits as an expense), cash donations, paid-out expense allowances, and the actual figures from
  event budgets. Each source is only ever booked once; running it repeatedly is harmless.
* Not automatic: bank fees, interest, purchases, other account movements → book these manually (working
  through the bank statement).
* Automatically imported entries are locked for amount/date/type; corrections go through a reversing entry.
* **"Import e-invoice"** (*Cash › Cash book*): read in an incoming XRechnung (plain XML) or ZUGFeRD/Factur-X
  PDF – amount, date and issuer are extracted and a pre-filled expense entry is created with the file as its
  receipt (category/account still need to be assigned afterwards).
* **"Add receipt to archive"** (on an entry with an uploaded receipt): additionally files the receipt in the
  general document archive (*Correspondence › Archive*) – without this step it only lives on the entry itself.

## Cash report
1. **Cash › Cash reports › New:** title (e.g. "Cash Report 2026"), period, treasurer, auditor, optionally the
   counted cash balance and the account balance per statement as of the cut-off date (for the target/actual
   reconciliation).
2. Detail page: key figures, account overview, income/expenses by category with a **year-over-year
   comparison**, result by tax category; warnings for discrepancies against actual balances and for entries
   without a receipt.
3. **PDF** (with logo, signature lines, and the cash book attached as supporting documentation) and **Excel**.
4. Enter the auditors' remarks, print the PDF and have it signed.
5. **Close:** locks the period for entries and files the PDF in the **archive** (cash reports/year). "Reopen"
   is only possible with delete rights on the cash book module (and is logged).
* There is no longer a fixed role for cash auditing: the **Auditor** tag (*Administration › Roles: Tags*,
  read-only on cash, invoices, payments, bank, donations …) can be assigned to a member and automatically
  grants the matching role – see Handbook chapter 2 ("Access via tags").

## Member import
*Members › Member import* (or the button on the member list).
1. **Download the template** (Excel with all columns and notes) or use an existing list – common headers
   (birthday, email, street, joined …) are recognised. Required: **first name** and **last name**.
2. Start with **"Dry run only"** first: nothing is saved, the report shows new/updated/error per row.
3. Fix errors in the file, repeat the dry run, then import **without** the checkbox.
* Existing members are matched by member number, otherwise by first name + last name + date of birth. Blank
  cells never overwrite existing values. Rows with errors are skipped, all others are applied.
* Membership type and departments must already exist – or use the "create unknown ones" option.
* **Family:** a "Family" column assigns the member to a family (see Handbook chapter 3) – unlike membership
  type/departments, an unknown family is **always** created automatically, regardless of the "create unknown
  ones" option. A "Pays the family fee" column sets the family payer checkbox.
* The "Board member" column is ignored on import (noted in the report) – that checkbox is derived
  automatically from tags, see Handbook chapters 2/3.
* IBANs are checked against their checksum (warning) and stored encrypted. The import is recorded in the
  audit trail.

## Member export
*Member list › Full export (Excel)*: all core data; **"with bank details"** only for users with the fees
permission. Every export is recorded in the audit trail (proof for data-protection purposes). Filterable
partial exports (CSV/Excel) are also available on every list.
