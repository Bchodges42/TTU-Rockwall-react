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

## Verification

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests -q
backend/.venv/Scripts/python.exe -m backend.test_profanity_guard
npm --prefix frontend run build
```

The integration tests cover fresh startup, both legacy layouts, failed-upgrade
rollback, data preservation, password/session handling, moderator permissions,
receipt flows, capacity races, cleanup, and online backup restoration.
