from fastapi import APIRouter, Depends, HTTPException
from backend.app.models.request_models import EventIn, EventPatch, ensure_no_profanity
from backend.app.services.auth_service import require_admin
from backend.app.services.database_service import db_session

router = APIRouter(tags=["events"])


def validate_event(event):
    if not event["name"].strip():
        raise HTTPException(422, "Event name is required.")
    ensure_no_profanity(event["name"])
    if not 0 <= event["spots_filled"] <= event["spots_total"] or event["spots_total"] < 1:
        raise HTTPException(422, "Filled spaces must be between zero and total spaces.")
    if event["link"] and not event["link"].startswith(("https://", "http://")):
        raise HTTPException(422, "Use an http or https event link.")


@router.get("/events")
def list_events():
    with db_session() as db:
        return [dict(r) for r in db.execute("SELECT * FROM events ORDER BY id")]


@router.post("/admin/events", status_code=201)
def admin_create_event(body: EventIn, user=Depends(require_admin)):
    validate_event(body.model_dump())
    with db_session(write=True) as db:
        cur = db.execute("INSERT INTO events(name,spots_total,spots_filled,next_date,link) VALUES (?,?,?,?,?)",
                         (body.name.strip(), body.spots_total, body.spots_filled, body.next_date, body.link))
        return dict(db.execute("SELECT * FROM events WHERE id=?", (cur.lastrowid,)).fetchone())


@router.patch("/admin/events/{event_id}")
def admin_patch_event(event_id: int, body: EventPatch, user=Depends(require_admin)):
    with db_session(write=True) as db:
        row = db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Event not found.")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        merged = {**dict(row), **updates}
        validate_event(merged)
        if updates:
            # Keys come only from the fixed Pydantic model.
            clause = ",".join(f"{key}=?" for key in updates)
            db.execute(f"UPDATE events SET {clause} WHERE id=?", (*updates.values(), event_id))
        return dict(db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone())


@router.delete("/admin/events/{event_id}")
def admin_delete_event(event_id: int, user=Depends(require_admin)):
    with db_session(write=True) as db:
        if not db.execute("DELETE FROM events WHERE id=?", (event_id,)).rowcount:
            raise HTTPException(404, "Event not found.")
    return {"message": "Event deleted."}
