import secrets
import sqlite3
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Response
from backend.app.models.request_models import QueueAction, QueueEntry
from backend.app.services.auth_service import require_staff
from backend.app.services.database_service import db_session, get_capacity
from backend.app.services.time_service import now_utc, wall_zone
from backend.app.services.visits import enqueue_due

router = APIRouter(tags=["queue"])


@router.get("/queue")
def list_queue(response: Response, user=Depends(require_staff)):
    response.headers["Cache-Control"] = "no-store"
    with db_session(write=True) as db:
        enqueue_due(db)
        rows = db.execute("""
          SELECT q.QueueID AS id,q.Status AS status,q.CheckedInAt AS checked_in_at,
            COALESCE(r.FirstName,w.FirstName) AS firstname,
            COALESCE(r.LastName,w.LastName) AS lastname,
            CASE WHEN r.UniqueID IS NULL THEN 'walk-in' ELSE 'reservation' END AS kind
          FROM visitorsInQueue q
          LEFT JOIN visitorsSignedUp r ON r.UniqueID=q.UniqueID_SignedUp
          LEFT JOIN visitorsWalkIn w ON w.UniqueID=q."UniqueID_Walk-in"
          WHERE q.Status IN ('waiting','admitted') ORDER BY q.QueueID
        """).fetchall()
    return [dict(r) for r in rows]


@router.post("/queue", status_code=201)
def add_queue(body: QueueEntry, user=Depends(require_staff)):
    with db_session(write=True) as db:
        if body.receipt:
            row = db.execute("SELECT * FROM visitorsSignedUp WHERE ReceiptCode=?", (body.receipt,)).fetchone()
            if row is None:
                raise HTTPException(404, "Reservation not found.")
            if row["Status"] != "confirmed":
                raise HTTPException(409, "Only confirmed reservations can join the queue.")
            if datetime.fromisoformat(row["Arrival_Time"]).astimezone(wall_zone()).date() != datetime.now(wall_zone()).date():
                raise HTTPException(409, "This reservation is for a different day.")
            try:
                cursor = db.execute("INSERT INTO visitorsInQueue(UniqueID_SignedUp,Arrival_Time_SignUp) VALUES (?,?)",
                                    (row["UniqueID"], row["Arrival_Time"]))
            except sqlite3.IntegrityError:
                raise HTTPException(409, "This reservation is already in the queue.")
        else:
            while True:
                walk_id = secrets.randbelow(90_000_000) + 10_000_000
                if not db.execute("SELECT 1 FROM visitorsWalkIn WHERE UniqueID=?", (walk_id,)).fetchone():
                    break
            first, last = body.firstname.strip() or "Guest", body.lastname.strip()
            if first == "Guest" and not last:
                number = int(db.execute("SELECT v FROM settings WHERE k='guest_sequence'").fetchone()[0]) + 1
                db.execute("UPDATE settings SET v=? WHERE k='guest_sequence'", (str(number),))
                last = str(number)
            db.execute("INSERT INTO visitorsWalkIn VALUES (?,?,?,?)", (walk_id, last, first, now_utc()))
            cursor = db.execute("""INSERT INTO visitorsInQueue("UniqueID_Walk-in","Arrival_Time_Walk-in")
                                   VALUES (?,?)""", (walk_id, now_utc()))
    return {"id": cursor.lastrowid, "status": "waiting"}


@router.patch("/queue/{entry_id}")
def change_queue(entry_id: int, body: QueueAction, user=Depends(require_staff)):
    with db_session(write=True) as db:
        row = db.execute("SELECT * FROM visitorsInQueue WHERE QueueID=?", (entry_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Queue entry not found.")
        if body.action == "admit":
            if row["Status"] != "waiting":
                raise HTTPException(409, "Only waiting visitors can be admitted.")
            active, maximum = get_capacity(db)
            if active >= maximum:
                raise HTTPException(409, "The wall is at capacity.")
            stamp = now_utc()
            db.execute("UPDATE visitorsInQueue SET Status='admitted',CheckedInAt=? WHERE QueueID=?", (stamp, entry_id))
            hour = datetime.fromisoformat(stamp).astimezone(wall_zone()).hour
            updated = db.execute("""UPDATE peak_visits SET count=count+1
                WHERE rowid=(SELECT rowid FROM peak_visits WHERE hour=? LIMIT 1)""", (hour,)).rowcount
            if not updated:
                db.execute("INSERT INTO peak_visits(hour,count) VALUES (?,1)", (hour,))
        elif body.action == "checkout":
            if row["Status"] != "admitted":
                raise HTTPException(409, "Only admitted visitors can check out.")
            db.execute("UPDATE visitorsInQueue SET Status='completed',CheckedOutAt=? WHERE QueueID=?", (now_utc(), entry_id))
            if row["UniqueID_SignedUp"] is not None:
                db.execute("UPDATE visitorsSignedUp SET Status='completed',UpdatedAt=? WHERE UniqueID=?",
                           (now_utc(), row["UniqueID_SignedUp"]))
        else:
            if row["Status"] != "waiting":
                raise HTTPException(409, "Only waiting entries can be cancelled. Check admitted visitors out.")
            db.execute("UPDATE visitorsInQueue SET Status='cancelled' WHERE QueueID=?", (entry_id,))
    return {"message": "Visitor updated."}
