from fastapi import APIRouter, Depends, HTTPException
from backend.app.models.request_models import CapacityIn
from backend.app.services.auth_service import require_admin
from backend.app.services.database_service import db_session, get_capacity

router = APIRouter(tags=["capacity"])


@router.get("/capacity")
def capacity():
    active, maximum = get_capacity()
    return {"active": active, "max": maximum}


@router.put("/admin/capacity")
def admin_capacity(body: CapacityIn, user=Depends(require_admin)):
    with db_session(write=True) as db:
        active, _ = get_capacity(db)
        if body.max < active:
            raise HTTPException(409, "Check out climbers before lowering capacity below current occupancy.")
        db.execute("UPDATE settings SET v=? WHERE k='capacity_max'", (str(body.max),))
    return {"active": active, "max": body.max}
