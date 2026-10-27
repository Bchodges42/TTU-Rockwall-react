"""Local/server administration. Run from repository root: python -m backend.manage."""
import argparse
import getpass
import json

from backend.app.services.database_service import backup_database, database_path, db_session, initialize_database
from backend.app.services.security import hash_password
from backend.app.services.time_service import now_utc
from backend.app.services.visits import cleanup_database


def set_role(db, account_id, role):
    row = db.execute("SELECT * FROM tableSignInInfo WHERE UniqueID=?", (account_id,)).fetchone()
    if row is None:
        raise ValueError("Account not found")
    if role == "student":
        db.execute("DELETE FROM tableTrustedUsers WHERE UniqueID=?", (account_id,))
    else:
        db.execute("""INSERT INTO tableTrustedUsers(UniqueID,LastName,FirstName,"Moderator?","Super-Moderator?")
          VALUES (?,?,?,?,?) ON CONFLICT(UniqueID) DO UPDATE
          SET "Moderator?"=excluded."Moderator?","Super-Moderator?"=excluded."Super-Moderator?" """,
          (account_id, row["LastName"], row["FirstName"], 1, int(role == "admin")))
    # A role change invalidates existing sessions; user signs in again.
    db.execute("DELETE FROM sessions WHERE account_id=?", (account_id,))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", help="Explicit durable SQLite path")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    commands.add_parser("cleanup")
    commands.add_parser("check")
    backup = commands.add_parser("backup")
    backup.add_argument("--output")
    admin = commands.add_parser("create-admin")
    admin.add_argument("email")
    admin.add_argument("--firstname", default="Rockwall")
    admin.add_argument("--lastname", default="Administrator")
    role = commands.add_parser("set-role")
    role.add_argument("email")
    role.add_argument("role", choices=["student", "moderator", "admin"])
    args = parser.parse_args()
    if args.database:
        import os
        os.environ["ROCKWALL_DB_PATH"] = args.database
    if args.command == "backup":
        print(backup_database(args.output))
        return
    if args.command == "check" and not database_path().is_file():
        raise SystemExit("Database does not exist; check ROCKWALL_DB_PATH or run init explicitly.")
    result = initialize_database() if args.command != "check" else None
    if args.command == "init":
        print(json.dumps(result))
    elif args.command == "cleanup":
        print(json.dumps(cleanup_database()))
    elif args.command == "check":
        with db_session() as db:
            integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
            refs = db.execute("PRAGMA foreign_key_check").fetchall()
            issues = db.execute("SELECT count(*) FROM migration_issues").fetchone()[0]
        print(json.dumps({"integrity": integrity, "invalid_references": len(refs), "migration_issues": issues}))
        if integrity != "ok" or refs:
            raise SystemExit(1)
    elif args.command == "create-admin":
        password = getpass.getpass("New administrator password (at least 8 characters): ")
        if len(password) < 8 or len(password) > 128:
            raise SystemExit("Password must contain 8–128 characters")
        if password != getpass.getpass("Confirm password: "):
            raise SystemExit("Passwords do not match")
        with db_session(write=True) as db:
            email = args.email.lower().strip()
            if "@" not in email:
                raise SystemExit("Enter an email address")
            if db.execute("SELECT 1 FROM tableSignInInfo WHERE UserEmail=? OR Username=?", (email, email)).fetchone():
                raise SystemExit("Account already exists; use set-role instead")
            cur = db.execute("""INSERT INTO tableSignInInfo
              (Username,PasswordHash,LastName,FirstName,UserEmail,CreatedAt) VALUES (?,?,?,?,?,?)""",
              (email, hash_password(password), args.lastname, args.firstname, email, now_utc()))
            set_role(db, cur.lastrowid, "admin")
        print("Administrator created.")
    elif args.command == "set-role":
        with db_session(write=True) as db:
            row = db.execute("SELECT UniqueID FROM tableSignInInfo WHERE UserEmail=? COLLATE NOCASE", (args.email,)).fetchone()
            if row is None:
                raise SystemExit("Account not found")
            set_role(db, row[0], args.role)
        print("Role updated.")


if __name__ == "__main__":
    main()
