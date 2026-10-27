# TTU Rockwall — React + FastAPI

The backend uses Jonah Irwin's original five SQLite tables:
`tableSignInInfo`, `tableTrustedUsers`, `visitorsSignedUp`,
`visitorsWalkIn`, and `visitorsInQueue`.

Events, FAQs, equipment, climbing routes, feedback, leaderboard, visit statistics,
settings, and editable site content remain in additional tables in the same database.
The React API response shapes and existing reservation receipts are preserved.

## Local development (PowerShell, from the repository root)

Requires Python 3.11+ and Node.js 20+.

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt
backend/.venv/Scripts/python.exe -m backend.manage init
backend/.venv/Scripts/python.exe -m backend.manage create-admin you@example.com
backend/.venv/Scripts/python.exe -m uvicorn backend.main:app --reload --port 8000
```

In another terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. The development proxy forwards `/api` to FastAPI.
There are no shared demo credentials. `create-admin` prompts for a password;
existing accounts can be promoted with
`python -m backend.manage set-role you@example.com admin` using the backend environment.

## Database design and upgrade

[Database reference](docs/DATABASE.md) describes retained identifiers, added fields,
permissions, and data migration behavior. Jonah's source design is
[Jirwin42/TTU-Rockwall-Repo-2026, 7d6aa27](https://github.com/Jirwin42/TTU-Rockwall-Repo-2026/commit/7d6aa276d61846ab46bf962f285060cb1cc748be).

On startup (or `manage init`), the versioned upgrade accepts either the old website
database or Jonah's original prototype. It backs up existing data with SQLite's
online backup API, upgrades in one transaction, preserves content tables and old
receipts, hashes legacy passwords, and rolls back if conversion fails. Running
the upgrade again does nothing.

By default the app reuses `backend/app/schema/rockwall.db` if present; otherwise it
creates `backend/data/rockwall.db`. Set `ROCKWALL_DB_PATH` explicitly on the server.
Do not overwrite an existing website database with the prototype's sample file.

## Laptop-server setup

Stop the old Rockwall backend before the first upgrade. Use the same absolute
database path in the Windows service environment and every administration command.
Keep the database on the laptop's local disk, outside the deployed checkout.

```powershell
$env:ROCKWALL_DB_PATH = 'C:/ProgramData/TTURockwall/Data/rockwall.db'
$env:ROCKWALL_TIMEZONE = 'America/Chicago'
$env:ROCKWALL_COOKIE_SECURE = '1'
$env:ROCKWALL_ALLOWED_ORIGINS = 'https://YOUR-ROCKWALL-HOST'
backend/.venv/Scripts/python.exe -m backend.manage init
backend/.venv/Scripts/python.exe -m backend.manage check
npm --prefix frontend ci
npm --prefix frontend run build
backend/.venv/Scripts/python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Provision an administrator with `create-admin` or promote an existing registered
account with `set-role` before opening the staff portal. Neither the old special
email address nor a browser-supplied admin header grants access.

FastAPI serves both the built frontend and `/api/*` on this port. Point the existing
HTTPS reverse proxy/tunnel at it. Keep the service's working directory at the
repository root. The variables above must be configured persistently in that
service; setting them in a terminal only affects that terminal. Secure cookies
require HTTPS; leave `ROCKWALL_COOKIE_SECURE=0` for local HTTP testing.

For a database upgrade, stop all older backend processes, update the code/install
dependencies/build the frontend, run `manage init` and `manage check`, then start
the new service. Do not run the old schema's code against an upgraded database.
A code rollback also requires restoring the pre-upgrade database backup while
the backend is stopped; retain the upgraded database separately if it has new writes.

The running backend checks due reservations and housekeeping every minute.
Expired temporary walk-in records are removed after local midnight while anyone
still checked in is retained. Aggregated visit counts survive this cleanup.
Housekeeping can also be invoked with `python -m backend.manage cleanup`.

Schedule `python -m backend.manage backup` nightly in Task Scheduler, using the
same backend Python executable and database environment. Backups are written
under the database directory's `backups/` folder unless `--output` is supplied.
Protect that directory like production data: the first backup contains the
original records, including any legacy plaintext passwords. No database files
or backups belong in Git.

Health check: `GET /api/health`. Database integrity:
`python -m backend.manage check`. Review any `migration_issues` before rollout;
prototype staff without accounts become disabled placeholders, and invalid
queue entries are retained as diagnostic records instead of being silently lost.

## Booking, hours, email and check-in

**Hours pipeline.** Weekly climbing-wall hours live in `operating_hours` and sync
from the "Climbing Wall Hours" column of https://www.tntech.edu/recreation/hours.php
every 6 hours (and on demand from Admin → Hours → *Sync from TTU now*). Closed days
never appear in the booking window, the homepage open/closed line and booking
validation read the same data, so if TTU changes the days the wall is open the site
follows on the next sync. If the page can't be read, the last good hours stay in
place and Admin → Hours shows why. Admins can add one-off closures (holidays,
resets) or edit the week by hand. A manual edit turns auto-sync off so it isn't
overwritten. Set `ROCKWALL_HOURS_SYNC=0` to disable network syncing.

**Bookings.** Visitors choose a day, an arrival and a departure on a half-hour
grid inside the posted hours. Online bookings are capped per half hour at the
*Bookable online* setting (default 10, never above the wall's maximum) so walk-ins
keep room. Each booking gets a 4-character check-in code (no vowels or look-alike
characters, unique among active bookings).

**Email.** Confirmation emails carry the code, a QR code, Google Calendar and
`.ics` calendar links, and a *Manage or cancel* link. Cancelling sends a second
email. Messages are queued in `email_outbox` in the same transaction as the
booking and sent in the background with retries, so a mail outage never blocks
or loses a booking. Configure:

```powershell
$env:ROCKWALL_PUBLIC_URL = 'https://tntechclimb.com'      # used in email links
$env:ROCKWALL_SMTP_HOST = 'smtp.office365.com'           # or your relay
$env:ROCKWALL_SMTP_PORT = '587'
$env:ROCKWALL_SMTP_SECURITY = 'starttls'                 # starttls | ssl | none
$env:ROCKWALL_SMTP_USER = 'rockwall@tntech.edu'
$env:ROCKWALL_SMTP_PASSWORD = '…'                        # keep out of Git
$env:ROCKWALL_SMTP_FROM = 'TTU Rockwall <rockwall@tntech.edu>'
```

Without `ROCKWALL_SMTP_HOST`, emails are written as `.eml` files to `outbox/`
next to the database. Open one in Outlook or Mail to preview it.

**Cancelling.** From the email link (`/booking?token=…`, which shows the booking
and needs a second click to cancel, so link-scanning mail filters can't cancel
anything), from *My bookings* when signed in, or by staff in Admin → Reservations.

**Desk check-in.** Staff → *Check in*: type the code or scan the QR. Any USB
"2D barcode scanner" (about $25–45) works with no setup because it acts as a
keyboard: it types the code and presses Enter. On Chrome/Edge for Android or
desktop with a camera, *Scan with camera* uses the built-in barcode detector.

## Verification

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests -q
backend/.venv/Scripts/python.exe -m backend.test_profanity_guard
npm --prefix frontend run build
```

The integration tests cover fresh startup, both legacy layouts, failed-upgrade
rollback, data preservation, password/session handling, moderator permissions,
receipt flows, capacity races, cleanup, and online backup restoration.
`test_booking_features.py` covers the hours sync and parser, closed-day handling,
the booking grid and online limits, check-in codes, desk check-in, emails and
both cancellation paths, and the 003 upgrade on an existing database.
