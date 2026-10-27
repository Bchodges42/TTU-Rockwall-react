"""Integration checks for data preservation, permissions, and physical occupancy."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3

import pytest
from support import PASSWORD, booking, login, register
from backend.app.services.database_service import (
    CORE, backup_database, database_path, db_session, get_connection, initialize_database,
)
from backend.app.services.security import verify_password
from backend.app.services.time_service import now_utc, wall_zone
from backend.app.services.visits import cleanup_database
from backend.manage import set_role

BACKEND = Path(__file__).resolve().parents[1]


def test_fresh_schema_and_idempotency(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/capacity").json() == {"active": 0, "max": 20, "online": 10}
    assert initialize_database() == {"upgraded": False}
    with db_session() as db:
        names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert set(CORE) <= names
        assert not {"users", "appointments"} & names
        assert not db.execute("PRAGMA foreign_key_check").fetchall()


def test_guest_receipts_repeat_bookings_and_occupancy(client):
    first, second = booking(client), booking(client, 2)
    assert first.status_code == second.status_code == 201
    receipt = first.json()["receipt"]
    assert receipt != second.json()["receipt"]
    assert client.get("/api/appointments/" + receipt).json()["name"] == "T*** C***"
    assert client.get("/api/capacity").json()["active"] == 0
    assert client.get("/api/appointments").status_code == 401


def test_sessions_hashing_permissions_and_revocation(client):
    result = login(client)
    assert "HttpOnly" in result.headers["set-cookie"]
    assert client.get("/api/me").json()["role"] == "student"
    with db_session() as db:
        row = db.execute("SELECT PasswordHash FROM tableSignInInfo").fetchone()
        assert row[0] != PASSWORD and verify_password(PASSWORD, row[0])
        assert len(db.execute("SELECT token_hash FROM sessions").fetchone()[0]) == 64
    assert client.put("/api/admin/capacity", json={"max": 10}).status_code == 403
    assert client.get("/api/queue").status_code == 403
    assert client.post("/api/logout").status_code == 200
    assert client.get("/api/me").status_code == 401


def test_no_demo_admin_or_forged_headers(client):
    assert client.post("/api/login", json={"email": "admin@tntech.edu", "password": "anything"}).status_code == 401
    assert client.put("/api/admin/capacity", json={"max": 10},
                      headers={"X-Admin": "admin@tntech.edu"}).status_code == 401
    assert register(client, "ADMIN@TNTECH.EDU").status_code == 201
    assert client.post("/api/login", json={"email": "admin@tntech.edu", "password": PASSWORD}).json()["role"] == "student"


def test_session_survives_restart_and_role_is_rechecked(client):
    login(client, role="admin")
    assert initialize_database() == {"upgraded": False}
    assert client.get("/api/me").json()["role"] == "admin"
    with db_session(write=True) as db:
        account = db.execute("SELECT UniqueID FROM tableSignInInfo").fetchone()[0]
        set_role(db, account, "student")
    assert client.get("/api/me").status_code == 401


def test_cross_site_writes_rejected(client):
    assert register(client).status_code == 201
    result = client.post("/api/login", json={"email": "student@example.test", "password": PASSWORD},
                         headers={"Origin": "https://attacker.example"})
    assert result.status_code == 403


def test_moderator_can_manage_visitors_but_not_content(client):
    login(client, role="moderator")
    assert client.get("/api/queue").status_code == 200
    assert client.post("/api/queue", json={"firstname": "Guest"}).status_code == 201
    assert client.post("/api/admin/faqs", json={"q": "Hours?", "a": "Afternoon."}).status_code == 403
    assert client.get("/api/appointments").status_code == 403


def test_atomic_capacity_and_checkout(client):
    login(client, role="admin")
    assert client.put("/api/admin/capacity", json={"max": 1}).status_code == 200
    ids = [client.post("/api/queue", json={"firstname": "Guest"}).json()["id"] for _ in range(2)]
    def admit(identifier):
        return client.patch(f"/api/queue/{identifier}", json={"action": "admit"}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(admit, ids))
    assert sorted(statuses) == [200, 409]
    assert client.get("/api/capacity").json() == {"active": 1, "max": 1, "online": 1}
    admitted = next(r for r in client.get("/api/queue").json() if r["status"] == "admitted")
    assert client.patch(f"/api/queue/{admitted['id']}", json={"action": "cancel"}).status_code == 409
    assert client.patch(f"/api/queue/{admitted['id']}", json={"action": "checkout"}).status_code == 200
    assert client.get("/api/capacity").json()["active"] == 0
    assert sum(r["count"] for r in client.get("/api/peak").json()) == 1


def test_reservation_status_edit_delete_and_slot_limit(client):
    login(client, role="admin")
    client.put("/api/admin/capacity", json={"max": 1})
    receipt = booking(client).json()["receipt"]
    assert booking(client).status_code == 409
    assert client.patch("/api/appointments/" + receipt, json={"status": "cancelled"}).status_code == 200
    assert booking(client).status_code == 201
    assert client.patch("/api/appointments/" + receipt, json={"status": "confirmed"}).status_code == 409
    assert client.delete("/api/appointments/" + receipt).status_code == 200
    assert client.get("/api/appointments/" + receipt).status_code == 404


def test_reservation_checkin_and_duplicate_queue(client):
    login(client, role="admin")
    receipt = booking(client).json()["receipt"]
    # Simulate a reservation due now without a fragile time-of-day test.
    with db_session(write=True) as db:
        db.execute("UPDATE visitorsSignedUp SET Arrival_Time=?", (now_utc(),))
    rows = client.get("/api/queue").json()
    assert len(rows) == 1
    assert len(client.get("/api/queue").json()) == 1
    assert client.post("/api/queue", json={"receipt": receipt}).status_code == 409
    assert client.patch(f"/api/queue/{rows[0]['id']}", json={"action": "admit"}).status_code == 200
    assert client.delete("/api/appointments/" + receipt).status_code == 409
    assert client.patch(f"/api/queue/{rows[0]['id']}", json={"action": "checkout"}).status_code == 200
    assert client.get("/api/appointments/" + receipt).json()["status"] == "completed"


def test_website_content_features(client):
    login(client, role="admin")
    assert client.post("/api/admin/faqs", json={"q": "Hours?", "a": "3 to 8 PM"}).status_code == 201
    assert client.get("/api/faqs").json()[0]["q"] == "Hours?"
    assert client.put("/api/admin/site-content", json={"k": "hero_title", "v": "Come climb."}).status_code == 200
    assert client.get("/api/site-content").json()["hero_title"] == "Come climb."
    event = client.post("/api/admin/events", json={"name": "Intro climbing", "spots_total": 4}).json()
    assert client.patch(f"/api/admin/events/{event['id']}", json={"name": "Learn to climb"}).status_code == 200
    assert client.get("/api/events").json()[0]["name"] == "Learn to climb"
    assert client.patch(f"/api/admin/events/{event['id']}", json={"spots_filled": 5}).status_code == 422
    with db_session(write=True) as db:
        db.execute("INSERT INTO routes(name,grade,setter) VALUES ('Blue','V2','Staff')")
        db.execute("INSERT INTO equipment(name,status,note) VALUES ('Shoes','Available','All sizes')")
        db.execute("INSERT INTO leaderboard(name,score) VALUES ('Climber',10)")
    assert client.post("/api/feedback", json={"route": "Blue", "rating": 5, "comment": "Fun route!"}).status_code == 201
    assert len(client.get("/api/feedback").json()) == 1
    for endpoint in ("equipment", "routes", "leaderboard"):
        assert len(client.get("/api/" + endpoint).json()) == 1


def test_cleanup_retains_aggregates_and_admitted_visitors(client):
    login(client, role="moderator")
    entries = [client.post("/api/queue", json={}).json()["id"] for _ in range(2)]
    client.patch(f"/api/queue/{entries[0]}", json={"action": "admit"})
    with db_session(write=True) as db:
        db.execute("UPDATE visitorsWalkIn SET Arrival_Time='2000-01-01T00:00:00+00:00'")
    result = cleanup_database()
    assert result["walkins_removed"] == 1
    assert client.get("/api/capacity").json()["active"] == 1
    assert sum(r["count"] for r in client.get("/api/peak").json()) == 1


def test_constraints_reject_missing_both_and_orphan_identities(client):
    for sql in (
        "INSERT INTO visitorsInQueue DEFAULT VALUES",
        'INSERT INTO visitorsInQueue(UniqueID_SignedUp,"UniqueID_Walk-in") VALUES (1,2)',
        "INSERT INTO visitorsInQueue(UniqueID_SignedUp) VALUES (99999)",
    ):
        with pytest.raises(sqlite3.IntegrityError):
            with db_session(write=True) as db:
                db.execute(sql)


def legacy_database(bad_date=False):
    db = sqlite3.connect(database_path())
    db.executescript((BACKEND / "app/schema/migrations/001_schema.sql").read_text(encoding="utf-8"))
    db.execute("INSERT INTO users VALUES ('old@example.test','Old','User','0123','old-password')")
    db.execute("INSERT INTO appointments VALUES ('original-receipt','Old User',?,'15:00','confirmed')",
               ("invalid" if bad_date else "2030-10-27",))
    db.execute("INSERT INTO settings VALUES ('capacity','1/12')")
    db.execute("INSERT INTO site_content VALUES ('site_title','Existing wall')")
    db.execute("INSERT INTO faqs(q,a) VALUES ('Question','Answer')")
    db.execute("INSERT INTO events(name,spots_total,spots_filled) VALUES ('Existing event',20,2)")
    db.execute("INSERT INTO equipment(name,status,note) VALUES ('Shoes','Available','Existing inventory')")
    db.execute("INSERT INTO routes(name,grade,setter) VALUES ('Existing route','V2','Staff')")
    db.execute("INSERT INTO feedback VALUES ('existing-feedback','Existing route',4,'Good route','Anonymous','2026-10-01')")
    db.execute("INSERT INTO leaderboard(name,score) VALUES ('Existing climber',12)")
    db.execute("INSERT INTO peak_visits(hour,count) VALUES (15,7)")
    db.commit()
    db.close()


def test_legacy_upgrade_preserves_content_receipts_and_headcount():
    legacy_database()
    result = initialize_database()
    assert result["upgraded"] and Path(result["backup"]).exists()
    with db_session() as db:
        assert db.execute("SELECT ReceiptCode FROM visitorsSignedUp").fetchone()[0] == "original-receipt"
        assert db.execute("SELECT v FROM settings WHERE k='capacity_max'").fetchone()[0] == "12"
        assert db.execute("SELECT count(*) FROM visitorsInQueue WHERE Status='admitted'").fetchone()[0] == 1
        assert db.execute("SELECT v FROM site_content WHERE k='site_title'").fetchone()[0] == "Existing wall"
        assert db.execute("SELECT count(*) FROM faqs").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM events").fetchone()[0] == 1
        for table in ("equipment","routes","feedback","leaderboard","peak_visits"):
            assert db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 1
        assert db.execute("SELECT count FROM peak_visits").fetchone()[0] == 7
        assert verify_password("old-password", db.execute("SELECT PasswordHash FROM tableSignInInfo").fetchone()[0])
    assert initialize_database() == {"upgraded": False}
    with sqlite3.connect(result["backup"]) as backup:
        assert backup.execute("SELECT count(*) FROM users").fetchone()[0] == 1


def test_failed_migration_rolls_back():
    legacy_database(bad_date=True)
    with pytest.raises(ValueError):
        initialize_database()
    with sqlite3.connect(database_path()) as db:
        assert db.execute("SELECT password FROM users").fetchone()[0] == "old-password"
        assert db.execute("SELECT count(*) FROM appointments").fetchone()[0] == 1
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='schema_migrations'").fetchone()
    assert list((database_path().parent / "backups").glob("*.db"))


def test_jonah_prototype_upgrade_retains_original_names_and_valid_records():
    # Original five-table layout, including its unusual quoted identifiers.
    with sqlite3.connect(database_path()) as db:
        db.executescript("""
          CREATE TABLE tableSignInInfo(Username TEXT,TEMPPASSWORD TEXT,LastName TEXT,FirstName TEXT,UniqueID INTEGER PRIMARY KEY,UserPhone INTEGER,UserEmail TEXT);
          CREATE TABLE tableTrustedUsers(UniqueID INTEGER PRIMARY KEY,LastName TEXT,FirstName TEXT,"Moderator?" INTEGER,"Super-Moderator?" INTEGER,"Most_recent_clock-in" TEXT);
          CREATE TABLE visitorsSignedUp(UniqueID INTEGER PRIMARY KEY,Username TEXT,LastName TEXT,FirstName TEXT,Arrival_Time TEXT);
          CREATE TABLE visitorsWalkIn(UniqueID INTEGER PRIMARY KEY,LastName TEXT,FirstName TEXT,Arrival_Time TEXT);
          CREATE TABLE visitorsInQueue(UniqueID_SignedUp INTEGER,"UniqueID_Walk-in" INTEGER,Arrival_Time_SignUp INTEGER,"Arrival_Time_Walk-in" INTEGER);
          INSERT INTO tableSignInInfo VALUES ('jonah','temporary','User','Test',1,123,'jonah@example.test');
          INSERT INTO tableTrustedUsers VALUES (1,'User','Test',1,1,NULL);
          INSERT INTO tableTrustedUsers VALUES (2,'Staff','Orphan',1,0,NULL);
          INSERT INTO visitorsSignedUp VALUES (1,'jonah','User','Test','2030-10-27T15:00:00Z');
          INSERT INTO visitorsWalkIn VALUES (12345678,'Guest','Test','2030-10-27T15:00:00Z');
          INSERT INTO visitorsInQueue VALUES (1,NULL,'2030-10-27T15:00:00Z',NULL);
          INSERT INTO visitorsInQueue VALUES (NULL,NULL,NULL,NULL);
        """)
    result = initialize_database()
    assert result["issues"] == 2
    with db_session() as db:
        assert db.execute("SELECT Username FROM tableSignInInfo WHERE UniqueID=1").fetchone()[0] == "jonah"
        assert db.execute("SELECT IsActive FROM tableSignInInfo WHERE UniqueID=2").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM visitorsInQueue").fetchone()[0] == 1
        assert db.execute("SELECT AccountID FROM visitorsSignedUp").fetchone()[0] == 1
        assert verify_password("temporary", db.execute("SELECT PasswordHash FROM tableSignInInfo WHERE UniqueID=1").fetchone()[0])
        assert "TEMPPASSWORD" not in {r[1] for r in db.execute("PRAGMA table_info(tableSignInInfo)")}


def test_backup_includes_committed_wal_contents(client, tmp_path):
    connection = get_connection()
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("INSERT INTO faqs(q,a) VALUES ('WAL record','Committed')")
        connection.commit()
        saved = backup_database(tmp_path / "online-copy.db")
        with sqlite3.connect(saved) as restored:
            assert restored.execute("SELECT q FROM faqs").fetchone()[0] == "WAL record"
    finally:
        connection.close()


def test_mixed_database_orphan_staff_cannot_grant_legacy_user_permissions():
    legacy_database()
    with sqlite3.connect(database_path()) as db:
        db.execute('CREATE TABLE tableTrustedUsers(UniqueID INTEGER PRIMARY KEY,LastName TEXT,FirstName TEXT,"Moderator?" INTEGER,"Super-Moderator?" INTEGER,"Most_recent_clock-in" TEXT)')
        db.execute("INSERT INTO tableTrustedUsers VALUES (1,'Orphan','Staff',1,1,NULL)")
    initialize_database()
    with db_session() as db:
        user = db.execute("SELECT UniqueID FROM tableSignInInfo WHERE UserEmail='old@example.test'").fetchone()
        assert user[0] != 1
        assert db.execute("SELECT IsActive FROM tableSignInInfo WHERE UniqueID=1").fetchone()[0] == 0
        assert not db.execute("SELECT 1 FROM tableTrustedUsers WHERE UniqueID=?", (user[0],)).fetchone()


def test_invalid_local_dst_time_is_rejected(client):
    response = client.post("/api/appointments", json={
        "name": "Test Climber", "date": "2030-03-10", "time": "02:30",
    })
    assert response.status_code == 422
