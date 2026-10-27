"""Helpers shared by the backend tests."""
from datetime import datetime, timedelta

from backend.app.services.database_service import db_session
from backend.app.services.time_service import wall_zone
from backend.manage import set_role

PASSWORD = "test-only-password"


def register(client, email="student@example.test"):
    return client.post("/api/register", json={
        "firstname": "Test", "lastname": "Climber", "phone": "+1 555 0100",
        "email": email, "password": PASSWORD,
    })


def login(client, email="student@example.test", role=None):
    assert register(client, email).status_code == 201
    if role:
        with db_session(write=True) as db:
            account_id = db.execute("SELECT UniqueID FROM tableSignInInfo WHERE UserEmail=?", (email,)).fetchone()[0]
            set_role(db, account_id, role)
    result = client.post("/api/login", json={"email": email, "password": PASSWORD})
    assert result.status_code == 200
    return result


def day(days=1):
    return (datetime.now(wall_zone()) + timedelta(days=days)).date().isoformat()


def booking(client, days=1, time="15:00", departure="16:00", email="climber@example.test", name="Test Climber"):
    return client.post("/api/appointments", json={
        "name": name, "email": email, "date": day(days), "time": time, "departure": departure})
