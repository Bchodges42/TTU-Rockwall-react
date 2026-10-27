"""Database connections and transactional upgrades to Jonah Irwin's schema."""
from contextlib import contextmanager
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import sqlite3
import uuid

from .security import hash_password
from .time_service import booking_time, normalize_time, now_utc, wall_zone

CORE = ("tableSignInInfo", "tableTrustedUsers", "visitorsSignedUp", "visitorsWalkIn", "visitorsInQueue")
VERSION = "002_jonah"
BACKEND = Path(__file__).resolve().parents[2]


def database_path():
    if os.environ.get("ROCKWALL_DB_PATH"):
        return Path(os.environ["ROCKWALL_DB_PATH"]).expanduser().resolve()
    legacy = BACKEND / "app/schema/rockwall.db"
    return legacy if legacy.exists() else BACKEND / "data/rockwall.db"


def get_connection():
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=15000")
    return db


@contextmanager
def db_session(write=False):
    db = get_connection()
    try:
        if write:
            db.execute("BEGIN IMMEDIATE")
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def backup_database(destination=None):
    path = database_path()
    if not path.exists():
        raise FileNotFoundError(path)
    destination = Path(destination or path.parent / "backups" / f"{path.stem}-{datetime.now():%Y%m%d-%H%M%S-%f}.db").resolve()
    if destination.exists() or destination == path:
        raise ValueError("Backup destination must be a new file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source, target = sqlite3.connect(path), sqlite3.connect(destination)
    try:
        source.backup(target)
        if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Backup integrity check failed")
    finally:
        target.close()
        source.close()
    return destination


def _issue(db, table, row, reason):
    clean = {k: v for k, v in row.items() if k.lower() not in ("password", "temppassword", "passwordhash")}
    db.execute("INSERT INTO migration_issues(source_table,record_id,reason,record_json) VALUES (?,?,?,?)",
               (table, str(row.get("UniqueID", row.get("id", ""))), reason, json.dumps(clean)))


def _import(db, old):
    stamp = now_utc()
    for r in old.get("tableSignInInfo", []):
        password = r.get("TEMPPASSWORD") or ""
        db.execute("""INSERT INTO tableSignInInfo
          (UniqueID,Username,PasswordHash,LastName,FirstName,UserPhone,UserEmail,IsActive,CreatedAt)
          VALUES (?,?,?,?,?,?,?,?,?)""",
          (r["UniqueID"], r["Username"], hash_password(password) if password else "!",
           r["LastName"], r["FirstName"], str(r["UserPhone"]) if r.get("UserPhone") is not None else None,
           r.get("UserEmail") or None, int(bool(password)), stamp))
    for r in old.get("tableTrustedUsers", []):
        if not db.execute("SELECT 1 FROM tableSignInInfo WHERE UniqueID=?", (r["UniqueID"],)).fetchone():
            db.execute("""INSERT INTO tableSignInInfo
              (UniqueID,Username,PasswordHash,LastName,FirstName,IsActive,CreatedAt) VALUES (?,?,'!',?,?,0,?)""",
              (r["UniqueID"], f"legacy-staff-{r['UniqueID']}", r["LastName"], r["FirstName"], stamp))
            _issue(db, "tableTrustedUsers", r, "Staff has no account: disabled placeholder retained")
        db.execute("INSERT INTO tableTrustedUsers VALUES (?,?,?,?,?,?)",
          (r["UniqueID"], r["LastName"], r["FirstName"], int(bool(r.get("Moderator?"))),
           int(bool(r.get("Super-Moderator?"))), r.get("Most_recent_clock-in") or None))
    # Reserve original staff IDs before allocating IDs to legacy website users;
    # an orphan staff row must never accidentally grant privileges to a new user.
    for r in old.get("users", []):
        db.execute("""INSERT INTO tableSignInInfo
          (Username,PasswordHash,LastName,FirstName,UserPhone,UserEmail,CreatedAt) VALUES (?,?,?,?,?,?,?)""",
          (r["email"].lower(), hash_password(r.get("password") or ""), r.get("lastname") or "",
           r.get("firstname") or "", r.get("phone"), r["email"].lower(), stamp))
    for r in old.get("visitorsSignedUp", []):
        account = db.execute("SELECT UniqueID FROM tableSignInInfo WHERE Username=? COLLATE NOCASE",
                             (r["Username"],)).fetchone()
        db.execute("""INSERT INTO visitorsSignedUp
          (UniqueID,AccountID,Username,LastName,FirstName,Arrival_Time,ReceiptCode,CreatedAt,UpdatedAt)
          VALUES (?,?,?,?,?,?,?,?,?)""", (r["UniqueID"], account[0] if account else None,
          r["Username"], r["LastName"], r["FirstName"],
          normalize_time(r["Arrival_Time"]), str(uuid.uuid4()), stamp, stamp))
    for r in old.get("appointments", []):
        names = ((r.get("name") or "").strip() or "Guest").split(maxsplit=1)
        db.execute("""INSERT INTO visitorsSignedUp
          (Username,LastName,FirstName,Arrival_Time,ReceiptCode,Status,CreatedAt,UpdatedAt)
          VALUES (?,?,?,?,?,?,?,?)""", ("Guest", names[1] if len(names) > 1 else "", names[0],
          booking_time(r["date"], r["time"]), r["id"], r.get("status") or "confirmed", stamp, stamp))
    for r in old.get("visitorsWalkIn", []):
        db.execute("INSERT INTO visitorsWalkIn VALUES (?,?,?,?)",
          (r["UniqueID"], r["LastName"], r["FirstName"], normalize_time(r["Arrival_Time"])))
    for r in old.get("visitorsInQueue", []):
        signed, walkin = r.get("UniqueID_SignedUp"), r.get("UniqueID_Walk-in")
        if (signed is None) == (walkin is None):
            _issue(db, "visitorsInQueue", r, "Queue must identify exactly one visitor")
            continue
        try:
            db.execute("""INSERT INTO visitorsInQueue
              (UniqueID_SignedUp,"UniqueID_Walk-in",Arrival_Time_SignUp,"Arrival_Time_Walk-in")
              VALUES (?,?,?,?)""", (signed, walkin,
              normalize_time(r["Arrival_Time_SignUp"]) if r.get("Arrival_Time_SignUp") else None,
              normalize_time(r["Arrival_Time_Walk-in"]) if r.get("Arrival_Time_Walk-in") else None))
        except sqlite3.IntegrityError:
            _issue(db, "visitorsInQueue", r, "Duplicate queue entry or missing visitor")


def _run_script(db, filename):
    statement = ""
    for line in (BACKEND / "app/schema/migrations" / filename).read_text(encoding="utf-8").splitlines():
        statement += line + "\n"
        if sqlite3.complete_statement(statement):
            db.execute(statement)
            statement = ""


def _backfill_departures(db):
    for row in db.execute("SELECT UniqueID,Arrival_Time FROM visitorsSignedUp WHERE Departure_Time IS NULL").fetchall():
        departure = datetime.fromisoformat(row["Arrival_Time"]) + timedelta(hours=1)
        db.execute("UPDATE visitorsSignedUp SET Departure_Time=? WHERE UniqueID=?", (departure.isoformat(), row["UniqueID"]))


# Applied in order after the 002_jonah rebuild; each runs once in its own transaction.
INCREMENTAL = (("003_booking", _backfill_departures),)


def initialize_database():
    result = _upgrade_to_jonah()
    applied = _apply_incremental()
    if applied:
        result = {**result, "upgraded": True, "applied": applied}
    return result


def _apply_incremental():
    db = get_connection()
    applied = []
    try:
        for name, hook in INCREMENTAL:
            if db.execute("SELECT 1 FROM schema_migrations WHERE name=?", (name,)).fetchone():
                continue
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM schema_migrations WHERE name=?", (name,)).fetchone():
                db.rollback()
                continue
            if db.execute("SELECT 1 FROM visitorsSignedUp LIMIT 1").fetchone():
                backup_database()
            _run_script(db, f"{name}.sql")
            hook(db)
            db.execute("INSERT INTO schema_migrations VALUES (?,?)", (name, now_utc()))
            db.commit()
            applied.append(name)
        return applied
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def _upgrade_to_jonah():
    db = get_connection()
    try:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "schema_migrations" in tables and db.execute(
            "SELECT 1 FROM schema_migrations WHERE name=?", (VERSION,)).fetchone():
            return {"upgraded": False}
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='schema_migrations'").fetchone():
            if db.execute("SELECT 1 FROM schema_migrations WHERE name=?", (VERSION,)).fetchone():
                db.rollback()
                return {"upgraded": False}
        # Hold the writer lock so backup and upgrade see the same committed data.
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        backup = backup_database() if tables else None
        old = {t: [dict(r) for r in db.execute(f'SELECT * FROM "{t}"')]
               for t in (*CORE, "users", "appointments") if t in tables}
        for t in reversed(CORE):
            if t in tables:
                db.execute(f'DROP TABLE "{t}"')
        _run_script(db, "002_jonah.sql")
        _import(db, old)
        legacy = db.execute("SELECT v FROM settings WHERE k='capacity'").fetchone()
        if legacy:
            active, maximum = map(int, legacy[0].split("/"))
            if maximum < 1 or not 0 <= active <= maximum:
                raise ValueError("Invalid legacy capacity")
            db.execute("UPDATE settings SET v=? WHERE k='capacity_max'", (str(maximum),))
            for i in range(active):
                cur = db.execute("INSERT INTO visitorsWalkIn(LastName,FirstName,Arrival_Time) VALUES (?,?,?)",
                                 (str(i + 1), "Imported Guest", now_utc()))
                db.execute("""INSERT INTO visitorsInQueue("UniqueID_Walk-in","Arrival_Time_Walk-in",Status,CheckedInAt)
                    VALUES (?,?,'admitted',?)""", (cur.lastrowid, now_utc(), now_utc()))
            db.execute("DELETE FROM settings WHERE k='capacity'")
        for t in ("appointments", "users"):
            if t in tables:
                db.execute(f'DROP TABLE "{t}"')
        db.execute("CREATE TABLE IF NOT EXISTS schema_migrations(name TEXT PRIMARY KEY,applied_at TEXT NOT NULL)")
        db.execute("INSERT INTO schema_migrations VALUES (?,?)", (VERSION, now_utc()))
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("Invalid references after migration")
        db.commit()
        return {"upgraded": True, "backup": str(backup) if backup else None,
                "issues": db.execute("SELECT count(*) FROM migration_issues").fetchone()[0]}
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def get_capacity(db=None):
    if db is None:
        with db_session() as connection:
            return get_capacity(connection)
    active = db.execute("SELECT count(*) FROM visitorsInQueue WHERE Status='admitted'").fetchone()[0]
    maximum = int(db.execute("SELECT v FROM settings WHERE k='capacity_max'").fetchone()[0])
    return active, maximum


def appointment_view(row):
    local = datetime.fromisoformat(row["Arrival_Time"]).astimezone(wall_zone())
    leave = datetime.fromisoformat(row["Departure_Time"]).astimezone(wall_zone())
    return {"id": row["ReceiptCode"], "code": row["PickupCode"], "name": f"{row['FirstName']} {row['LastName']}".strip(),
            "date": local.date().isoformat(), "time": local.strftime("%H:%M"),
            "departure": leave.strftime("%H:%M"), "status": row["Status"]}
