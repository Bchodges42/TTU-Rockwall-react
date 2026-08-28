from fastapi import APIRouter, Header, HTTPException
from typing import Optional
from app.services.database_service import get_capacity, set_capacity
from app.services.auth_service import require_admin
from app.models.request_models import CapacityIn

router = APIRouter(tags=["capacity"])

@router.get("/capacity")
def capacity():
    active, maxv = get_capacity()
    return {"active": active, "max": maxv}

@router.put("/admin/capacity")
def admin_capacity(body: CapacityIn, x_admin: Optional[str] = Header(None)):
    require_admin(x_admin)
    if body.max < 1 or body.max > 200: raise HTTPException(400, "max must be 1–200")
    act, _ = get_capacity()
    if act > body.max: act = body.max
    set_capacity(act, body.max)
    return {"active": act, "max": body.max}
