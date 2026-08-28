from typing import Optional

from fastapi import Header, HTTPException

ADMIN_EMAIL = "admin@tntech.edu"


def require_admin(x_admin: Optional[str] = Header(None)) -> None:
    if x_admin != ADMIN_EMAIL:
        raise HTTPException(403, "Admin only — sign in as admin@tntech.edu.")
