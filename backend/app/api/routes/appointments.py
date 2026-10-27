"""Bookings stored in Jonah's visitorsSignedUp table.

A booking has an arrival and departure inside the posted hours, a 4-character check-in code
for the desk, and a secret manage link (emailed) that lets the visitor cancel without an account.
"""
from datetime import date, datetime, timedelta
import io
import re
import secrets
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
import segno

from backend.app.models.request_models import Appointment, AppointmentPatch, CancelByToken
from backend.app.services.auth_service import current_user, require_admin, require_user
from backend.app.services.database_service import appointment_view, db_session
from backend.app.services.email_service import build_cancellation, build_confirmation, deliver_pending, queue_email
from backend.app.services.schedule_service import (
    FullError, booking_days, check_capacity, day_hours, online_limit, slot_usage, status_now, validate_window,
)
from backend.app.services.security import token_hash
from backend.app.services.time_service import booking_time, now_utc, wall_zone

router = APIRouter(tags=["appointments"])

# No vowels (so codes never spell words) and no look-alikes (0/O, 1/I, 5/S).
CODE_ALPHABET = "BCDFGHJKLMNPQRTVWXZ2346789"
ACTIVE = ("pending", "confirmed")
MAX_UPCOMING = 3  # per email address, so one person can't hold every online space


def new_code(db):
    for _ in range(50):
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(4))
        if not db.execute("SELECT 1 FROM visitorsSignedUp WHERE PickupCode=? AND Status IN ('pending','confirmed')",
                          (code,)).fetchone():
            return code
    raise HTTPException(503, "Could not create a check-in code. Please try again.")


def clean_code(text):
    """Accepts 'k7qx', 'K7-QX', or whatever a QR scanner types (e.g. a URL ending in the code)."""
    text = text.strip().rstrip("/").split("/")[-1].split("=")[-1]
    return re.sub(r"[\s-]", "", text).upper()


def find(db, identifier):
    """Look up by 4-character check-in code (active booking first) or by full receipt."""
    code = clean_code(identifier)
    if len(code) == 4:
        return db.execute("""SELECT * FROM visitorsSignedUp WHERE PickupCode=?
          ORDER BY Status IN ('pending','confirmed') DESC, Arrival_Time DESC LIMIT 1""", (code,)).fetchone()
    return db.execute("SELECT * FROM visitorsSignedUp WHERE ReceiptCode=?", (identifier.strip(),)).fetchone()


def split_name(name):
    names = name.strip().split(maxsplit=1)
    if not names:
        raise HTTPException(422, "Name is required.")
    return names[0], names[1] if len(names) > 1 else ""


def window(db, day, arrival, departure, exclude=None):
    if departure is None:
        departure = (datetime.strptime(arrival, "%H:%M") + timedelta(hours=1)).strftime("%H:%M")
    try:
        return validate_window(db, day, arrival, departure, exclude)
    except FullError as error:
        raise HTTPException(409, str(error))
    except ValueError as error:
        raise HTTPException(422, str(error))


def masked(view):
    return {**view, "name": " ".join(part[0] + "***" for part in view["name"].split())}


def cancel_reservation(db, row):
    if row["Status"] not in ACTIVE:
        raise HTTPException(409, f"This booking is already {row['Status']}.")
    if db.execute("SELECT 1 FROM visitorsInQueue WHERE UniqueID_SignedUp=? AND Status='admitted'",
                  (row["UniqueID"],)).fetchone():
        raise HTTPException(409, "You're checked in right now. Ask the desk to check you out.")
    db.execute("UPDATE visitorsSignedUp SET Status='cancelled',UpdatedAt=? WHERE UniqueID=?", (now_utc(), row["UniqueID"]))
    db.execute("UPDATE visitorsInQueue SET Status='cancelled' WHERE UniqueID_SignedUp=? AND Status='waiting'", (row["UniqueID"],))
    if row["Email"]:
        queue_email(db, "cancellation", row, build_cancellation(row))
    return db.execute("SELECT * FROM visitorsSignedUp WHERE UniqueID=?", (row["UniqueID"],)).fetchone()


@router.get("/hours")
def hours():
    """Everything the homepage and booking window need: open now?, and the open days ahead."""
    with db_session() as db:
        today = datetime.now(wall_zone()).date()
        return {"timezone": str(wall_zone()), "now": status_now(db), "today": day_hours(db, today),
                "days": booking_days(db), "online_capacity": online_limit(db)}


@router.get("/availability")
def availability(date: str):
    try:
        day = datetime.fromisoformat(date).date()
    except ValueError:
        raise HTTPException(422, "Enter a valid date.")
    with db_session() as db:
        info = day_hours(db, day)
        limit = online_limit(db)
        slots = slot_usage(db, info)
    message = (f"{info['weekday']}: open {info['opens']}–{info['closes']}. Up to {limit} online climbers at a time."
               if info["open"] else f"Closed on {info['weekday']}.")
    return {**info, "message": message, "online_capacity": limit, "slots": slots}


@router.post("/appointments", status_code=201)
def book(body: Appointment, background: BackgroundTasks, user=Depends(current_user)):
    email = body.email or (user or {}).get("email")
    if not email:
        raise HTTPException(422, "Enter your email so we can send your check-in code.")
    first, last = split_name(body.name)
    receipt, token = str(uuid.uuid4()), secrets.token_urlsafe(24)
    with db_session(write=True) as db:
        arrival, departure = window(db, body.date, body.time, body.departure)
        upcoming = db.execute("""SELECT count(*) FROM visitorsSignedUp WHERE Email=? COLLATE NOCASE
          AND Status IN ('pending','confirmed') AND Departure_Time>?""", (email, now_utc())).fetchone()[0]
        if upcoming >= MAX_UPCOMING:
            raise HTTPException(409, f"You already have {MAX_UPCOMING} upcoming bookings. Cancel one to book another.")
        code = new_code(db)
        db.execute("""INSERT INTO visitorsSignedUp
          (AccountID,Username,LastName,FirstName,Arrival_Time,Departure_Time,ReceiptCode,PickupCode,Email,
           CancelTokenHash,CreatedAt,UpdatedAt) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
          (user["id"] if user else None, user["username"] if user else "Guest", last, first, arrival, departure,
           receipt, code, email, token_hash(token), now_utc(), now_utc()))
        row = db.execute("SELECT * FROM visitorsSignedUp WHERE ReceiptCode=?", (receipt,)).fetchone()
        queue_email(db, "confirmation", row, build_confirmation(row, token))
    background.add_task(deliver_pending)
    return {"message": "You're booked!", "receipt": receipt, "code": code, "email": email,
            "appointment": appointment_view(row)}


@router.get("/appointments")
def list_appointments(user=Depends(require_admin)):
    with db_session() as db:
        return [{**appointment_view(r), "email": r["Email"]}
                for r in db.execute("SELECT * FROM visitorsSignedUp ORDER BY Arrival_Time")]


@router.get("/my/appointments")
def my_appointments(response: Response, user=Depends(require_user)):
    response.headers["Cache-Control"] = "no-store"
    since = booking_time(datetime.now(wall_zone()).date().isoformat(), "00:00")
    with db_session() as db:
        rows = db.execute("""SELECT * FROM visitorsSignedUp WHERE AccountID=? AND Arrival_Time>=?
          ORDER BY Arrival_Time""", (user["id"], since)).fetchall()
    return [appointment_view(r) for r in rows]


@router.post("/booking/manage")
def manage_booking(body: CancelByToken):
    """Details for the emailed manage link. Read-only: cancelling is a separate request,
    so mail scanners that open links can't cancel anyone's booking. The token travels in
    the body, never the URL, to keep it out of server logs."""
    with db_session() as db:
        row = db.execute("SELECT * FROM visitorsSignedUp WHERE CancelTokenHash=?", (token_hash(body.token),)).fetchone()
    if row is None:
        raise HTTPException(404, "This link isn't valid. Check the latest email for your booking.")
    return {**appointment_view(row), "can_cancel": row["Status"] in ACTIVE and row["Arrival_Time"] > now_utc()}


@router.post("/booking/cancel")
def cancel_by_token(body: CancelByToken, background: BackgroundTasks):
    with db_session(write=True) as db:
        row = db.execute("SELECT * FROM visitorsSignedUp WHERE CancelTokenHash=?", (token_hash(body.token),)).fetchone()
        if row is None:
            raise HTTPException(404, "This link isn't valid. Check the latest email for your booking.")
        row = cancel_reservation(db, row)
    background.add_task(deliver_pending)
    return {"message": "Your booking is cancelled.", "appointment": appointment_view(row)}


@router.post("/appointments/{receipt}/cancel")
def cancel_own(receipt: str, background: BackgroundTasks, user=Depends(require_user)):
    with db_session(write=True) as db:
        row = find(db, receipt)
        if row is None or (row["AccountID"] != user["id"] and user["role"] != "admin"):
            raise HTTPException(404, "Booking not found.")
        row = cancel_reservation(db, row)
    background.add_task(deliver_pending)
    return {"message": "Booking cancelled.", "appointment": appointment_view(row)}


@router.get("/appointments/{receipt}/qr.svg")
def qr_svg(receipt: str):
    with db_session() as db:
        row = find(db, receipt)
    if row is None or not row["PickupCode"]:
        raise HTTPException(404, "Booking not found.")
    svg = io.BytesIO()  # standalone SVG (with xmlns) so it works in an <img> tag
    segno.make(row["PickupCode"], error="m").save(svg, kind="svg", scale=8, border=2, dark="#2B1A4A", xmldecl=False)
    return Response(svg.getvalue(), media_type="image/svg+xml")


@router.get("/appointments/{receipt}")
def get_appointment(receipt: str, response: Response, user=Depends(current_user)):
    response.headers["Cache-Control"] = "no-store"
    with db_session() as db:
        row = find(db, receipt)
    if row is None:
        raise HTTPException(404, "Booking not found. Check the code and try again.")
    result = appointment_view(row)
    if not user or (user["role"] != "admin" and user["id"] != row["AccountID"]):
        result = masked(result)
    return result


@router.patch("/appointments/{receipt}")
def patch_appointment(receipt: str, body: AppointmentPatch, user=Depends(require_admin)):
    with db_session(write=True) as db:
        row = find(db, receipt)
        if row is None:
            raise HTTPException(404, "Appointment not found.")
        old = appointment_view(row)
        status = body.status or row["Status"]
        if body.date or body.time or body.departure:
            arrival, departure = window(db, body.date or old["date"], body.time or old["time"],
                                        body.departure or (old["departure"] if not body.time else None), row["UniqueID"])
        else:
            arrival, departure = row["Arrival_Time"], row["Departure_Time"]
            if status in ACTIVE and row["Status"] not in ACTIVE:
                try:
                    check_capacity(db, day_hours(db, date.fromisoformat(old["date"])), old["time"], old["departure"], row["UniqueID"])
                except FullError as error:
                    raise HTTPException(409, str(error))
        active = db.execute("SELECT * FROM visitorsInQueue WHERE UniqueID_SignedUp=? AND Status IN ('waiting','admitted')",
                            (row["UniqueID"],)).fetchone()
        if active and active["Status"] == "admitted" and (arrival != row["Arrival_Time"] or status != row["Status"]):
            raise HTTPException(409, "Check this visitor out before changing their booking.")
        code = row["PickupCode"]
        if status in ACTIVE and row["Status"] not in ACTIVE and code and db.execute(
                "SELECT 1 FROM visitorsSignedUp WHERE PickupCode=? AND Status IN ('pending','confirmed')", (code,)).fetchone():
            code = new_code(db)  # the old code was handed to someone else while this booking was inactive
        first, last = split_name(body.name or old["name"])
        db.execute("""UPDATE visitorsSignedUp SET FirstName=?,LastName=?,Arrival_Time=?,Departure_Time=?,Status=?,
          PickupCode=?,UpdatedAt=? WHERE UniqueID=?""",
          (first, last, arrival, departure, status, code, now_utc(), row["UniqueID"]))
        if active and (status != "confirmed" or arrival != row["Arrival_Time"]):
            db.execute("UPDATE visitorsInQueue SET Status='cancelled' WHERE QueueID=?", (active["QueueID"],))
        return appointment_view(db.execute("SELECT * FROM visitorsSignedUp WHERE UniqueID=?", (row["UniqueID"],)).fetchone())


@router.delete("/appointments/{receipt}")
def delete_appointment(receipt: str, user=Depends(require_admin)):
    with db_session(write=True) as db:
        row = find(db, receipt)
        if row is None:
            raise HTTPException(404, "Appointment not found.")
        if db.execute("SELECT 1 FROM visitorsInQueue WHERE UniqueID_SignedUp=? AND Status='admitted'", (row[0],)).fetchone():
            raise HTTPException(409, "Check this visitor out before deleting their booking.")
        db.execute("DELETE FROM visitorsInQueue WHERE UniqueID_SignedUp=?", (row[0],))
        db.execute("DELETE FROM visitorsSignedUp WHERE UniqueID=?", (row[0],))
    return {"message": "Appointment deleted."}
