from fastapi import APIRouter, Header, HTTPException
from typing import Optional
from app.services.database_service import get_connection
from app.services.auth_service import require_admin
from app.models.request_models import EventIn, EventPatch, ensure_no_profanity

router = APIRouter(tags=["events"])


@router.get("/events")
def list_events():
    return [dict(r) for r in get_connection().execute("SELECT * FROM events ORDER BY id").fetchall()]

@router.post("/admin/events")
def admin_create_event(body: EventIn, x_admin: Optional[str] = Header(None)):
    require_admin(x_admin)
    if not body.name.strip(): raise HTTPException(400, "name required")
    c = get_connection(); c.execute("INSERT INTO events(name,spots_total,spots_filled,next_date,link) VALUES (?,?,?,?,?)", (body.name.strip(), body.spots_total, body.spots_filled, body.next_date, body.link)); c.commit()
    row = c.execute("SELECT * FROM events WHERE id=last_insert_rowid()").fetchone(); c.close()
    return dict(row)

@router.patch("/admin/events/{event_id}")
def admin_patch_event(event_id: int, patch: EventPatch, x_admin: Optional[str] = Header(None)):
    require_admin(x_admin)
    db = get_connection()
    if not db.execute("SELECT 1 FROM events WHERE id=?", (event_id,)).fetchone():
        db.close(); raise HTTPException(404, "Event not found.")
    updates = {k: v for k, v in patch.model_dump().items() if v is not None}
    if updates:
        if "name" in updates:
            ensure_no_profanity(updates["name"])
        set_clause = ", ".join(f"{k}=?" for k in updates)
        db.execute(f"UPDATE events SET {set_clause} WHERE id=?", (*updates.values(), event_id))
        db.commit()
    row = dict(db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()); db.close(); return row

@router.delete("/admin/events/{event_id}")
def admin_delete_event(event_id: int, x_admin: Optional[str] = Header(None)):
    require_admin(x_admin)
    db = get_connection()
    if not db.execute("SELECT 1 FROM events WHERE id=?", (event_id,)).fetchone(): db.close(); raise HTTPException(404, "Event not found.")
    db.execute("DELETE FROM events WHERE id=?", (event_id,)); db.commit(); db.close()
    return {"message": "Event deleted."}
