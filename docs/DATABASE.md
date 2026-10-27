# Jonah database integration

Source: Jonah Irwin's `rockwallDatabaseTest.db`, commit `7d6aa27`, 2026-09-03.
The source database is a design reference; its sample records are not seeded into
new installations. Runtime SQLite files stay out of Git.

## Core tables

| Original table | Retained design and necessary extensions |
|---|---|
| `tableSignInInfo` | Keeps `UniqueID`, `Username`, names, phone, and email. `PasswordHash` replaces plaintext `TEMPPASSWORD`; phone is text; usernames and non-null emails are unique without case sensitivity. Adds active flag and creation time. |
| `tableTrustedUsers` | Keeps staff names, `UniqueID`, `Moderator?`, `Super-Moderator?`, and `Most_recent_clock-in`. Staff ID references the login account. Role flags accept only 0/1. |
| `visitorsSignedUp` | Keeps `UniqueID`, username, names, and `Arrival_Time`. `UniqueID` identifies a reservation; nullable `AccountID` links an account so repeated and guest bookings work. Adds receipt, status, and creation/update times. |
| `visitorsWalkIn` | Keeps original four columns and eight-digit IDs for newly entered walk-ins. Anonymous names follow Guest 1, Guest 2, etc. |
| `visitorsInQueue` | Keeps both original visitor-ID and arrival-time columns, including the database's spelling `Arrival_Time_SignUp`. Adds queue ID, status, check-in, and checkout. Exactly one visitor identity is required; foreign keys and partial unique indexes prevent invalid or duplicate active entries. |

New code always enables foreign keys and a busy timeout. Writes that check capacity
or modify visits use `BEGIN IMMEDIATE`, so two simultaneous admissions cannot both
take the last space. Booking a future reservation does not increase current occupancy.
Occupancy is the count of admitted queue entries; the maximum is a setting.

A reservation is confirmed or pending until changed/cancelled, checked out
(completed), or marked no-show after its day has passed. Due confirmed reservations
join the queue automatically; staff can add same-day receipts earlier.
Reservations are limited by the configured maximum at the same appointment start
time. The existing app has no authored slot duration or opening-hours schedule;
interval-overlap scheduling is not inferred from the homepage's hours text.

## Additional website tables

`events`, `faqs`, `equipment`, `routes`, `feedback`, `leaderboard`,
`peak_visits`, `settings`, and `site_content` retain the website's existing shapes
and data. New installs seed actual configuration defaults only, not fake occupancy,
events, scores, equipment, or visitor accounts.

`sessions` stores hashes of opaque login tokens, account links, and expiration
times. Browser cookies are HttpOnly and SameSite=Strict; HTTPS deployments enable
Secure cookies. Logout revokes the session. Staff permissions are checked from the
database on every request. Public registration cannot assign permissions.
A moderator may manage the queue; only a super-moderator (API role `admin`) may
read all reservations or edit website content/settings. Ordinary receipt lookup
masks names unless performed by the account owner or a super-moderator.

`schema_migrations` records the applied upgrade.
`migration_issues` retains records that could not become valid active records,
excluding plaintext password fields. It is available to local administration,
not through a public endpoint.

## Upgrade compatibility

The transactional upgrade lives in `database_service.initialize_database`, using
`002_jonah.sql`. The old `001_schema.sql` is retained as the legacy layout,
not applied on new installations.

- Existing website accounts are moved into `tableSignInInfo`, with hashed
  passwords. Existing receipts and content are preserved. The old count/max setting
  becomes a capacity maximum and anonymous admitted visits, retaining the displayed
  headcount without guessing which reservations correspond to people present.
- Jonah's original core-table rows keep their IDs. Existing usernames can link
  reservations to accounts. Missing-login staff become disabled placeholders,
  never new usable administrator credentials. Invalid queue rows are recorded
  in `migration_issues`.
- Successful upgrades remove the old `users` and `appointments` tables; there
  is one active account/reservation system. The pre-upgrade database backup
  retains the original data. A conversion error rolls back all schema/data changes.
- All new stored times are UTC ISO 8601. Website date/time fields are interpreted
  in `ROCKWALL_TIMEZONE`, default America/Chicago, including daylight saving time.
- Temporary walk-ins from previous days are cleared by backend housekeeping;
  admitted visitors are preserved until checked out. Peak counts are recorded
  at admission and survive cleanup.

Use the explicit server path and upgrade/restore instructions in the root README.
