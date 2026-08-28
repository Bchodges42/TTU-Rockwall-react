from fastapi import APIRouter, Header, HTTPException
from typing import Optional
import uuid
from app.services.database_service import get_connection, get_capacity, set_capacity
from app.services.auth_service import require_admin
from app.models.request_models import Appointment, AppointmentPatch


def mask_name(name: str) -> str:
    parts = name.strip().split()
    return " ".join(part[0] + "***" for part in parts) if parts else "***"


def mask_if_not_admin(row: dict, x_admin: Optional[str]) -> dict:
    if x_admin != "admin@tntech.edu":
        row["name"] = mask_name(row["name"])
    return row


def adjust_capacity(delta: int) -> None:
    act, mx = get_capacity()
    if delta > 0 and act < mx:
        set_capacity(act + 1, mx)
    elif delta < 0 and act > 0:
        set_capacity(act - 1, mx)


router = APIRouter(tags=["appointments"])


@router.get("/availability")
def availability(date: str):
    return {"message": f"Time slots available for {date}!"}


@router.post("/appointments")
def book(a: Appointment):
    rid = str(uuid.uuid4())
    db = get_connection()
    db.execute(
        "INSERT INTO appointments(id, name, date, time, status) VALUES (?,?,?,?,?)",
        (rid, a.name, a.date, a.time, "confirmed"),
    )
    db.commit()
    db.close()
    adjust_capacity(1)
    return {"message": "Appointment booked successfully!", "receipt": rid, "appointment": {"id": rid, "name": a.name, "date": a.date, "time": a.time, "status": "confirmed"}}


@router.get("/appointments/{appointment_id}")
def get_appointment(appointment_id: str, x_admin: Optional[str] = Header(None)):
    row = get_connection().execute("SELECT * FROM appointments WHERE id=?", (appointment_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Receipt not found. Check the number and try again.")
    return mask_if_not_admin(dict(row), x_admin)


@router.get("/appointments")
def list_appointments(x_admin: Optional[str] = Header(None)):
    rows = [dict(r) for r in get_connection().execute("SELECT * FROM appointments ORDER BY date, time").fetchall()]
    return [mask_if_not_admin(r, x_admin) for r in rows]


@router.patch("/appointments/{appointment_id}")
def patch_appointment(appointment_id: str, patch: AppointmentPatch, x_admin: Optional[str] = Header(None)):
    require_admin(x_admin)
    db = get_connection()
    row = db.execute("SELECT * FROM appointments WHERE id=?", (appointment_id,)).fetchone()
    if not row:
        db.close()
        raise HTTPException(404, "Appointment not found.")
    prev_status = row["status"] or "confirmed"
    updates = {}
    if patch.name is not None:
        updates["name"] = patch.name.strip()
    if patch.date is not None:
        updates["date"] = patch.date
    if patch.time is not None:
        updates["time"] = patch.time
    if patch.status is not None:
        if patch.status not in ("pending", "confirmed", "cancelled"):
            db.close()
            raise HTTPException(400, "status must be pending/confirmed/cancelled")
        updates["status"] = patch.status
    if not updates:
        db.close()
        return dict(row)
    new_status = updates.get("status", prev_status)
    if prev_status != "cancelled" and new_status == "cancelled":
        adjust_capacity(-1)
    elif prev_status == "cancelled" and new_status != "cancelled":
        adjust_capacity(1)
    set_clause = ", ".join(f"{k}=?" for k in updates)
    db.execute(f"UPDATE appointments SET {set_clause} WHERE id=?", (*updates.values(), appointment_id))
    db.commit()
    out = dict(db.execute("SELECT * FROM appointments WHERE id=?", (appointment_id,)).fetchone())
    db.close()
    return out


@router.delete("/appointments/{appointment_id}")
def delete_appointment(appointment_id: str, x_admin: Optional[str] = Header(None)):
    require_admin(x_admin)
    db = get_connection()
    row = db.execute("SELECT * FROM appointments WHERE id=?", (appointment_id,)).fetchone()
    if not row:
        db.close()
        raise HTTPException(404, "Appointment not found.")
    if (row["status"] or "confirmed") != "cancelled":
        adjust_capacity(-1)
    db.execute("DELETE FROM appointments WHERE id=?", (appointment_id,))
    db.commit()
    db.close()
    return {"message": "Appointment deleted."}
