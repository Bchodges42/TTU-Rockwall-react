"""Admin control of the hours pipeline: auto-sync from TTU, manual override, one-off closures."""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from backend.app.models.request_models import ClosureIn, HoursUpdate
from backend.app.services.auth_service import require_admin
from backend.app.services.database_service import db_session
from backend.app.services.hours_sync import SOURCE_URL, sync_hours
from backend.app.services.schedule_service import WEEKDAYS, setting
from backend.app.services.time_service import booking_time, now_utc, wall_zone

router = APIRouter(tags=["hours"])


def hours_state(db):
    today = datetime.now(wall_zone()).date().isoformat()
    return {
        "weekly": [{"weekday": r["weekday"], "name": WEEKDAYS[r["weekday"]], "opens": r["opens"], "closes": r["closes"]}
                   for r in db.execute("SELECT * FROM operating_hours ORDER BY weekday")],
        "closures": [dict(r) for r in db.execute("SELECT * FROM closures WHERE day>=? ORDER BY day", (today,))],
        "auto_sync": setting(db, "hours_auto_sync") == "1",
        "synced_at": setting(db, "hours_synced_at") or None,
        "sync_status": setting(db, "hours_sync_status"),
        "source": SOURCE_URL,
    }


@router.get("/admin/hours")
def get_hours(user=Depends(require_admin)):
    with db_session() as db:
        return hours_state(db)


@router.put("/admin/hours")
def update_hours(body: HoursUpdate, user=Depends(require_admin)):
    """Saving weekly hours by hand turns auto-sync off, so the next sync doesn't undo the edit."""
    with db_session(write=True) as db:
        if body.weekly is not None:
            if sorted(d.weekday for d in body.weekly) != list(range(7)):
                raise HTTPException(422, "Send hours for each day of the week once.")
            for d in body.weekly:
                db.execute("UPDATE operating_hours SET opens=?,closes=? WHERE weekday=?", (d.opens, d.closes, d.weekday))
            db.execute("UPDATE settings SET v='Edited by an admin.' WHERE k='hours_sync_status'")
            db.execute("UPDATE settings SET v=? WHERE k='hours_synced_at'", (now_utc(),))
        auto = body.auto_sync if body.auto_sync is not None else (False if body.weekly is not None else None)
        if auto is not None:
            db.execute("UPDATE settings SET v=? WHERE k='hours_auto_sync'", ("1" if auto else "0",))
    if body.auto_sync:
        sync_hours(force=True)  # turning auto-sync back on pulls TTU's hours right away
    with db_session() as db:
        return hours_state(db)


@router.post("/admin/hours/sync")
async def sync_now(user=Depends(require_admin)):
    status = await run_in_threadpool(sync_hours, True)
    with db_session() as db:
        return {**hours_state(db), "message": status}


@router.post("/admin/closures", status_code=201)
def add_closure(body: ClosureIn, user=Depends(require_admin)):
    try:
        date.fromisoformat(body.day)
    except ValueError:
        raise HTTPException(422, "Enter a valid date.")
    with db_session(write=True) as db:
        db.execute("INSERT INTO closures(day,reason) VALUES (?,?) ON CONFLICT(day) DO UPDATE SET reason=excluded.reason",
                   (body.day, body.reason.strip() or "Closed"))
        booked = db.execute("""SELECT count(*) FROM visitorsSignedUp WHERE Status IN ('pending','confirmed')
          AND Arrival_Time>=? AND Arrival_Time<?""", (booking_time(body.day, "00:00"),
          booking_time((date.fromisoformat(body.day) + timedelta(days=1)).isoformat(), "00:00"))).fetchone()[0]
        return {**hours_state(db), "message": f"Closed {body.day}." + (
            f" {booked} booking(s) that day still need to be cancelled in Reservations." if booked else "")}


@router.delete("/admin/closures/{day}")
def remove_closure(day: str, user=Depends(require_admin)):
    with db_session(write=True) as db:
        db.execute("DELETE FROM closures WHERE day=?", (day,))
        return hours_state(db)
