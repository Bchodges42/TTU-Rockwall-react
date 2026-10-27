"""Hours pipeline, booking window, check-in codes, emails and cancellation."""
from datetime import datetime, timedelta
from email import message_from_bytes, policy

import pytest

from conftest import open_all_week
from support import booking, day, login
from test_database_integration import legacy_database
from backend.app.api.routes.appointments import CODE_ALPHABET
from backend.app.services.database_service import database_path, db_session, initialize_database
from backend.app.services.email_service import deliver_pending
from backend.app.services.hours_sync import parse_hours, parse_range, sync_hours
from backend.app.services.time_service import now_utc, wall_zone

TTU_PAGE = """<table><thead><tr><td>Day</td><td><strong>Building Hours</strong></td>
<td><strong>Climbing Wall Hours</strong></td><td>Pool and Sauna Hours</td></tr></thead><tbody>
<tr><td><strong>Monday</strong></td><td>6 AM - 11 PM</td><td>2 PM - 7 PM</td><td>6 AM - 12 PM/4 PM- 8 PM</td></tr>
<tr><td><strong>Tuesday</strong></td><td>6 AM - 11 PM</td><td>2 PM - 7 PM</td><td>x</td></tr>
<tr><td><strong>Wednesday</strong></td><td>6 AM - 11 PM</td><td>2:30 PM - 7 PM</td><td>x</td></tr>
<tr><td><strong>Thursday</strong></td><td>6 AM - 11 PM</td><td>2 PM - 7 PM</td><td>x</td></tr>
<tr><td><strong>Friday</strong></td><td>6 AM - 8 PM</td><td>Closed</td><td>x</td></tr>
<tr><td><strong>Saturday</strong></td><td>9 AM - 8 PM</td><td>Closed</td><td>x</td></tr>
<tr><td><strong>Sunday</strong></td><td>1 PM - 10 PM</td><td>Closed</td><td>x</td></tr></tbody></table>"""


def weekly(db):
    return {r[0]: (r[1], r[2]) for r in db.execute("SELECT weekday,opens,closes FROM operating_hours")}


def emails():
    deliver_pending()
    outbox = database_path().parent / "outbox"
    return [message_from_bytes(p.read_bytes(), policy=policy.default) for p in sorted(outbox.glob("*.eml"))]


def manage_token(message):
    text = message.get_body(("plain",)).get_content()
    return text.split("/booking#token=")[1].split()[0]


# ---------- hours pipeline ----------

def test_parse_ttu_hours_page():
    hours = parse_hours(TTU_PAGE)
    assert hours[0] == ("14:00", "19:00") and hours[2] == ("14:30", "19:00")
    assert hours[4] is hours[5] is hours[6] is None
    assert parse_range("Noon – 5 p.m.") == ("12:00", "17:00")
    with pytest.raises(ValueError):
        parse_range("6 AM - 12 PM/4 PM- 8 PM")  # split ranges are reported, never guessed
    with pytest.raises(ValueError):
        parse_hours(TTU_PAGE.replace("Climbing Wall", "Pool"))


def test_sync_updates_hours_and_keeps_last_good_on_failure(client):
    open_all_week()
    assert "Changed" in sync_hours(fetch=lambda: TTU_PAGE)
    with db_session() as db:
        assert weekly(db)[4] == (None, None) and weekly(db)[0] == ("14:00", "19:00")
    status = sync_hours(fetch=lambda: "<html>redesigned page</html>")
    assert status.startswith("Sync failed")
    with db_session() as db:
        assert weekly(db)[0] == ("14:00", "19:00")
    login(client, "admin@example.test", role="admin")
    assert client.get("/api/admin/hours").json()["sync_status"] == status


def test_booking_window_drops_closed_days_and_follows_hour_changes(client):
    with db_session(write=True) as db:  # TTU's current pattern: Friday–Sunday closed
        db.execute("UPDATE operating_hours SET opens=NULL,closes=NULL WHERE weekday>=4")
    days = client.get("/api/hours").json()["days"]
    assert days and all(d["weekday"] not in ("Friday", "Saturday", "Sunday") for d in days)
    closed = next(d for d in range(1, 8) if (datetime.now(wall_zone()) + timedelta(days=d)).weekday() == 5)
    assert booking(client, closed).status_code == 422
    # The wall starts opening Saturdays: the window picks it up with no code change.
    with db_session(write=True) as db:
        db.execute("UPDATE operating_hours SET opens='10:00',closes='16:00' WHERE weekday=5")
    assert "Saturday" in {d["weekday"] for d in client.get("/api/hours").json()["days"]}
    assert booking(client, closed, "11:00", "12:00").status_code == 201


def test_one_off_closure_and_manual_override(client):
    login(client, "admin@example.test", role="admin")
    target = day(2)
    assert client.post("/api/admin/closures", json={"day": target, "reason": "Wall inspection"}).status_code == 201
    assert target not in {d["date"] for d in client.get("/api/hours").json()["days"]}
    response = booking(client, 2)
    assert response.status_code == 422 and "Wall inspection" in response.json()["detail"]
    client.delete(f"/api/admin/closures/{target}")
    assert booking(client, 2).status_code == 201
    week = [{"weekday": d, "opens": "15:00", "closes": "18:00"} for d in range(7)]
    state = client.put("/api/admin/hours", json={"weekly": week}).json()
    assert state["auto_sync"] is False  # a manual edit isn't overwritten by the next sync
    assert client.put("/api/admin/hours", json={"weekly": week[:6]}).status_code == 422


def test_status_line_open_and_next_open(client):
    status = client.get("/api/hours").json()["now"]
    assert status["open"] or status["next"]["opens"] == "06:00"
    with db_session(write=True) as db:
        db.execute("UPDATE operating_hours SET opens=NULL,closes=NULL")
    assert client.get("/api/hours").json()["now"] == {"open": False, "closes": None, "next": None}


# ---------- booking window ----------

def test_times_must_be_on_the_grid_inside_hours(client):
    assert booking(client, 1, "15:15", "16:00").status_code == 422
    assert booking(client, 1, "05:00", "06:00").status_code == 422
    assert booking(client, 1, "21:30", "22:30").status_code == 422
    assert booking(client, 1, "16:00", "15:00").status_code == 422
    assert booking(client, 30).status_code == 422  # beyond the booking window
    assert client.post("/api/appointments", json={"name": "No Email", "date": day(), "time": "15:00"}).status_code == 422


def test_online_spaces_count_overlapping_visits(client):
    login(client, "admin@example.test", role="admin")
    assert client.put("/api/admin/capacity", json={"max": 20, "online": 1}).json()["online"] == 1
    assert booking(client, 1, "15:00", "16:00").status_code == 201
    assert booking(client, 1, "15:30", "16:30").status_code == 409
    assert booking(client, 1, "16:00", "17:00").status_code == 201
    slots = {s["time"]: s for s in client.get(f"/api/availability?date={day()}").json()["slots"]}
    assert slots["15:00"]["remaining"] == 0 and slots["17:00"]["remaining"] == 1
    assert client.put("/api/admin/capacity", json={"max": 5, "online": 6}).status_code == 422


def test_check_in_codes_are_short_unambiguous_and_findable(client):
    result = booking(client).json()
    code = result["code"]
    assert len(code) == 4 and set(code) <= set(CODE_ALPHABET)
    assert client.get(f"/api/appointments/{code.lower()}").json()["name"] == "T*** C***"
    assert client.get(f"/api/appointments/{result['receipt']}").json()["code"] == code
    qr = client.get(f"/api/appointments/{code}/qr.svg")
    assert qr.headers["content-type"].startswith("image/svg") and b'xmlns="http://www.w3.org/2000/svg"' in qr.content


# ---------- desk check-in ----------

def test_desk_check_in_by_code_or_scanned_text(client):
    code = booking(client).json()["code"]
    login(client, "staff@example.test", role="moderator")
    assert client.post("/api/queue/check-in", json={"code": code}).status_code == 409  # tomorrow's booking
    with db_session(write=True) as db:
        db.execute("UPDATE visitorsSignedUp SET Arrival_Time=?", (now_utc(),))
    result = client.post("/api/queue/check-in", json={"code": f"https://climb.example.test/b/{code.lower()}\n"})
    assert result.status_code == 200 and result.json()["active"] == 1
    assert client.post("/api/queue/check-in", json={"code": code}).status_code == 409  # already in
    assert client.post("/api/queue/check-in", json={"code": "ZZZZ"}).status_code == 404
    assert client.get("/api/capacity").json()["active"] == 1


def test_check_in_requires_staff(client):
    code = booking(client).json()["code"]
    login(client)
    assert client.post("/api/queue/check-in", json={"code": code}).status_code == 403


# ---------- emails and cancellation ----------

def test_confirmation_email_has_code_qr_calendar_and_manage_link(client):
    code = booking(client, name="Ada Lovelace").json()["code"]
    [message] = emails()
    assert message["To"] == "climber@example.test" and code in message["Subject"]
    html = message.get_body(("html",)).get_content()
    assert "You're booked." in html and code[0] in html and "cid:" in html
    assert "https://climb.example.test/booking#token=" in html and "calendar.google.com" in html
    parts = {p.get_content_type(): p for p in message.walk()}
    assert "image/png" in parts and "text/calendar" in parts
    assert "BEGIN:VEVENT" in parts["text/calendar"].get_content()
    with db_session() as db:
        row = db.execute("SELECT status,message FROM email_outbox").fetchone()
        assert row["status"] == "saved" and row["message"] is None  # the manage link isn't kept
        assert manage_token(message) not in str(db.execute("SELECT * FROM visitorsSignedUp").fetchone()[:])


def test_cancel_from_email_link(client):
    booking(client)
    token = manage_token(emails()[0])
    details = client.post("/api/booking/manage", json={"token": token}).json()
    assert details["status"] == "confirmed" and details["can_cancel"] and details["name"] == "Test Climber"
    # Viewing the booking never cancels it; mail scanners pre-open links.
    assert client.post("/api/booking/manage", json={"token": token}).json()["status"] == "confirmed"
    assert client.post("/api/booking/cancel", json={"token": token}).json()["appointment"]["status"] == "cancelled"
    assert client.post("/api/booking/cancel", json={"token": token}).status_code == 409
    assert client.post("/api/booking/cancel", json={"token": "x" * 32}).status_code == 404
    assert [m["Subject"].split(":")[0] for m in emails()] == ["You're booked", "Cancelled"]
    assert client.get(f"/api/availability?date={day()}").json()["slots"][18]["booked"] == 0


def test_signed_in_climber_sees_and_cancels_own_bookings(client):
    login(client)
    code = client.post("/api/appointments", json={"name": "Test Climber", "date": day(), "time": "15:00",
                                                  "departure": "16:30"}).json()["code"]
    mine = client.get("/api/my/appointments").json()
    assert [b["code"] for b in mine] == [code] and mine[0]["departure"] == "16:30"
    client.post("/api/logout")
    login(client, "other@example.test")
    assert client.post(f"/api/appointments/{code}/cancel").status_code == 404
    client.post("/api/logout")
    client.post("/api/login", json={"email": "student@example.test", "password": "test-only-password"})
    assert client.post(f"/api/appointments/{code}/cancel").status_code == 200
    assert client.get("/api/my/appointments").json()[0]["status"] == "cancelled"


def test_reactivated_booking_gets_a_fresh_code_if_reused(client):
    login(client, "admin@example.test", role="admin")
    first = booking(client).json()
    client.patch(f"/api/appointments/{first['receipt']}", json={"status": "cancelled"})
    with db_session(write=True) as db:  # simulate the code being handed out again meanwhile
        db.execute("UPDATE visitorsSignedUp SET PickupCode=? WHERE ReceiptCode<>?",
                   (first["code"], first["receipt"]))
        db.execute("""INSERT INTO visitorsSignedUp(Username,LastName,FirstName,Arrival_Time,Departure_Time,
          ReceiptCode,PickupCode,CreatedAt,UpdatedAt) VALUES ('Guest','B','A',?,?,'other',?,?,?)""",
          (now_utc(), now_utc(), first["code"], now_utc(), now_utc()))
    again = client.patch(f"/api/appointments/{first['receipt']}", json={"status": "confirmed"}).json()
    assert again["status"] == "confirmed" and again["code"] != first["code"]


# ---------- migration ----------

def test_003_upgrade_backfills_departures_on_existing_database():
    legacy_database()
    result = initialize_database()
    assert "003_booking" in result["applied"]
    with db_session() as db:
        arrival, departure = db.execute("SELECT Arrival_Time,Departure_Time FROM visitorsSignedUp").fetchone()
        assert datetime.fromisoformat(departure) - datetime.fromisoformat(arrival) == timedelta(hours=1)
        assert db.execute("SELECT count(*) FROM operating_hours WHERE opens IS NULL").fetchone()[0] == 3
    assert initialize_database() == {"upgraded": False}


def test_one_email_cannot_hold_every_online_space(client):
    for hour in ("15", "16", "17"):
        assert booking(client, 1, f"{hour}:00", f"{hour}:30", email="Hoarder@example.test").status_code == 201
    response = booking(client, 1, "18:00", "18:30", email="hoarder@example.test")
    assert response.status_code == 409 and "3 upcoming" in response.json()["detail"]
    assert booking(client, 1, "18:00", "18:30", email="a,b@example.test").status_code == 422
