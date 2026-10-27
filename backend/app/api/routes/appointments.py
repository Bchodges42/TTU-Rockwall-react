"""Keep the website's receipt API while storing bookings in visitorsSignedUp."""
from datetime import datetime, timedelta
import uuid
from fastapi import APIRouter, Depends, HTTPException, Response
from backend.app.models.request_models import Appointment, AppointmentPatch
from backend.app.services.auth_service import current_user, require_admin
from backend.app.services.database_service import appointment_view, db_session
from backend.app.services.time_service import booking_time, now_utc, wall_zone

router = APIRouter(tags=["appointments"])


def scheduled(day, clock):
    try:
        result = booking_time(day, clock)
    except (ValueError, TypeError):
        raise HTTPException(422, "Enter a valid date and time at the wall.")
    if result <= now_utc():
        raise HTTPException(422, "Choose a future appointment time.")
    return result


def split_name(name):
    names = name.strip().split(maxsplit=1)
    if not names:
        raise HTTPException(422, "Name is required.")
    return names[0], names[1] if len(names) > 1 else ""


def require_slot(db, arrival, exclude=None):
    maximum = int(db.execute("SELECT v FROM settings WHERE k='capacity_max'").fetchone()[0])
    count = db.execute("""SELECT count(*) FROM visitorsSignedUp
      WHERE Arrival_Time=? AND Status IN ('pending','confirmed') AND (? IS NULL OR UniqueID<>?)""",
      (arrival, exclude, exclude)).fetchone()[0]
    if count >= maximum:
        raise HTTPException(409, "This appointment time is fully booked.")


@router.get("/availability")
def availability(date: str):
    try:
        start = datetime.fromisoformat(booking_time(date, "00:00"))
    except ValueError:
        raise HTTPException(422, "Enter a valid date.")
    next_day = (start.astimezone(wall_zone()).date() + timedelta(days=1)).isoformat()
    end = booking_time(next_day, "00:00")
    with db_session() as db:
        maximum = int(db.execute("SELECT v FROM settings WHERE k='capacity_max'").fetchone()[0])
        rows = db.execute("""SELECT Arrival_Time,count(*) AS booked FROM visitorsSignedUp
          WHERE Arrival_Time>=? AND Arrival_Time<? AND Status IN ('pending','confirmed')
          GROUP BY Arrival_Time""", (start.isoformat(), end)).fetchall()
    slots = [{"time": datetime.fromisoformat(r["Arrival_Time"]).astimezone(wall_zone()).strftime("%H:%M"),
              "remaining": max(0, maximum-r["booked"])} for r in rows]
    return {"message": f"Reservations for {date}. Each appointment time allows up to {maximum} climbers.",
            "max": maximum, "reserved_slots": slots}


@router.post("/appointments", status_code=201)
def book(body: Appointment, user=Depends(current_user)):
    arrival, receipt = scheduled(body.date, body.time), str(uuid.uuid4())
    first, last = split_name(body.name)
    with db_session(write=True) as db:
        require_slot(db, arrival)
        db.execute("""INSERT INTO visitorsSignedUp
          (AccountID,Username,LastName,FirstName,Arrival_Time,ReceiptCode,CreatedAt,UpdatedAt)
          VALUES (?,?,?,?,?,?,?,?)""", (user["id"] if user else None, user["username"] if user else "Guest",
          last, first, arrival, receipt, now_utc(), now_utc()))
        row = db.execute("SELECT * FROM visitorsSignedUp WHERE ReceiptCode=?", (receipt,)).fetchone()
    return {"message": "Appointment booked successfully!", "receipt": receipt, "appointment": appointment_view(row)}


@router.get("/appointments")
def list_appointments(user=Depends(require_admin)):
    with db_session() as db:
        return [appointment_view(r) for r in db.execute("SELECT * FROM visitorsSignedUp ORDER BY Arrival_Time")]


@router.get("/appointments/{receipt}")
def get_appointment(receipt: str, response: Response, user=Depends(current_user)):
    response.headers["Cache-Control"] = "no-store"
    with db_session() as db:
        row = db.execute("SELECT * FROM visitorsSignedUp WHERE ReceiptCode=?", (receipt,)).fetchone()
    if row is None:
        raise HTTPException(404, "Receipt not found.")
    result = appointment_view(row)
    if not user or (user["role"] != "admin" and user["id"] != row["AccountID"]):
        result["name"] = " ".join(part[0] + "***" for part in result["name"].split())
    return result


@router.patch("/appointments/{receipt}")
def patch_appointment(receipt: str, body: AppointmentPatch, user=Depends(require_admin)):
    with db_session(write=True) as db:
        row = db.execute("SELECT * FROM visitorsSignedUp WHERE ReceiptCode=?", (receipt,)).fetchone()
        if row is None:
            raise HTTPException(404, "Appointment not found.")
        old = appointment_view(row)
        arrival = scheduled(body.date or old["date"], body.time or old["time"]) if body.date or body.time else row["Arrival_Time"]
        status = body.status or row["Status"]
        active = db.execute("SELECT * FROM visitorsInQueue WHERE UniqueID_SignedUp=? AND Status IN ('waiting','admitted')",
                            (row["UniqueID"],)).fetchone()
        if active and active["Status"] == "admitted" and (arrival != row["Arrival_Time"] or status != row["Status"]):
            raise HTTPException(409, "Check this visitor out before changing their booking.")
        if status in ("pending", "confirmed"):
            require_slot(db, arrival, row["UniqueID"])
        first, last = split_name(body.name or old["name"])
        db.execute("""UPDATE visitorsSignedUp SET FirstName=?,LastName=?,Arrival_Time=?,Status=?,UpdatedAt=?
          WHERE UniqueID=?""", (first, last, arrival, status, now_utc(), row["UniqueID"]))
        if active and (status != "confirmed" or arrival != row["Arrival_Time"]):
            db.execute("UPDATE visitorsInQueue SET Status='cancelled' WHERE QueueID=?", (active["QueueID"],))
        return appointment_view(db.execute("SELECT * FROM visitorsSignedUp WHERE UniqueID=?", (row["UniqueID"],)).fetchone())


@router.delete("/appointments/{receipt}")
def delete_appointment(receipt: str, user=Depends(require_admin)):
    with db_session(write=True) as db:
        row = db.execute("SELECT UniqueID FROM visitorsSignedUp WHERE ReceiptCode=?", (receipt,)).fetchone()
        if row is None:
            raise HTTPException(404, "Appointment not found.")
        if db.execute("SELECT 1 FROM visitorsInQueue WHERE UniqueID_SignedUp=? AND Status='admitted'", (row[0],)).fetchone():
            raise HTTPException(409, "Check this visitor out before deleting their booking.")
        db.execute("DELETE FROM visitorsInQueue WHERE UniqueID_SignedUp=?", (row[0],))
        db.execute("DELETE FROM visitorsSignedUp WHERE UniqueID=?", (row[0],))
    return {"message": "Appointment deleted."}
