# Self-Service Data for Members

> Part of the [Handbook](HANDBUCH.en.md) – see chapter 3 "Member Management" there for the full picture.

Members can maintain selected data about themselves online, without gaining access to the rest of the
administration area. This is a separate, lightweight login – independent of the role/permission system for
staff (*Administration › Users*).

## Setting it up as a board member

1. On a member's detail page (requires an email address on file), click
   **"Send self-service access credentials"**.
2. The system creates a user account if needed (username = email address), generates a random starting
   password, and emails both directly to the member.
3. The member logs in at `/login/`, lands automatically on **"My Data"** (not on the administration
   dashboard), and should change the password promptly (top right, under "Password").

Clicking the button again generates a new starting password and resends it (e.g. if the email never arrived,
or the member forgot their password).

## What members can change themselves

Street/postal code/city, phone, mobile, email, payment method, account holder, IBAN, BIC. All other fields
(status, membership type, individual fee, member number, join/leave date, roles, documents …) remain editable
only for staff with the matching permission. Every change is logged automatically in the audit trail as usual.
**Note on payment method:** switching to "SEPA direct debit" alone is not enough – a valid SEPA mandate
(reference and date) is still required, which only the board/treasurer can set up.

## Locking access / deleting the starting password

* **"Lock self-service access"**: deactivates the user account (login no longer possible). Sending
  credentials again reactivates it with a new password.
* **"Delete stored starting password"**: removes the most recently issued starting password from the
  database (it is stored encrypted until deleted – similar to the OpenSlides integration).

## Permissions

A dedicated module, **"Self-service (manage member accounts)"**, granted via the permission matrix or tags
(see Handbook chapter 2, "Access via tags"). The six data-protection-bylaw (DSO) roles as well as
Administrator have it in full by default (row "Club software / Administration" in the permission matrix); in
addition there is the lightweight tag **"Member management"** (just this module plus read access to members)
for people who should manage accounts only, without other board permissions.

## Setting up an administration account directly from a member

Anyone who, as staff, needs full access to the administration area (i.e. an account with a role, as would
otherwise be set up under *Administration › Users*) no longer has to be created there separately – provided
the person is already recorded as a member:

1. On the member's detail page (requires an email address on file), click **"Set up administration
   account"**.
2. Choose a role (e.g. 1st Chair, Treasurer, Secretary …) and save.
3. Login credentials (username = email address, random starting password) are emailed automatically.

If the member already has a self-service account (see above), that **same** user account is reused – the
person then has both administration access and access to "My Data" with a single login. If an administration
account already exists, a link to edit the role appears instead (leading to the normal page under
*Administration › Users*). Permissions: requires the **"Administration"** module (same as creating one under
*Administration › Users*) – the six DSO roles and Administrator have this in full by default, and so does the
Superadministrator (as a permissions bypass).
