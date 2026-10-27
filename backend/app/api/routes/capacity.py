from fastapi import APIRouter, Depends, HTTPException
from backend.app.models.request_models import CapacityIn
from backend.app.services.auth_service import require_admin
from backend.app.services.database_service import db_session, get_capacity
from backend.app.services.schedule_service import online_limit

router = APIRouter(tags=["capacity"])


@router.get("/capacity")
def capacity():
    with db_session() as db:
        active, maximum = get_capacity(db)
        online = online_limit(db)
    return {"active": active, "max": maximum, "online": online}


@router.put("/admin/capacity")
def admin_capacity(body: CapacityIn, user=Depends(require_admin)):
    with db_session(write=True) as db:
        active, _ = get_capacity(db)
        if body.max < active:
            raise HTTPException(409, "Check out climbers before lowering capacity below current occupancy.")
        db.execute("UPDATE settings SET v=? WHERE k='capacity_max'", (str(body.max),))
        if body.online is not None:
            if body.online > body.max:
                raise HTTPException(422, "Online spaces can't be more than the wall's maximum.")
            db.execute("UPDATE settings SET v=? WHERE k='online_capacity'", (str(body.online),))
        online = online_limit(db)
    return {"active": active, "max": body.max, "online": online}
