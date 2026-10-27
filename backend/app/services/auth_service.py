"""Opaque, revocable sessions with permissions read from Jonah's staff table."""
from fastapi import Depends, HTTPException, Request
from .database_service import db_session
from .security import token_hash
from .time_service import now_utc

COOKIE = "rockwall_session"


def current_user(request: Request):
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    with db_session() as db:
        row = db.execute("""
          SELECT a.UniqueID,a.Username,a.UserEmail,a.FirstName,a.LastName,
            COALESCE(t."Moderator?",0) AS moderator,
            COALESCE(t."Super-Moderator?",0) AS super_moderator
          FROM sessions s JOIN tableSignInInfo a ON a.UniqueID=s.account_id
          LEFT JOIN tableTrustedUsers t ON t.UniqueID=a.UniqueID
          WHERE s.token_hash=? AND s.expires_at>? AND a.IsActive=1
        """, (token_hash(token), now_utc())).fetchone()
    if row is None:
        return None
    return {"id": row["UniqueID"], "email": row["UserEmail"], "username": row["Username"],
            "name": f"{row['FirstName']} {row['LastName']}".strip(),
            "role": "admin" if row["super_moderator"] else "moderator" if row["moderator"] else "student"}


def require_user(user=Depends(current_user)):
    if user is None:
        raise HTTPException(401, "Please sign in.")
    return user


def require_admin(user=Depends(require_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Super-moderator permission required.")
    return user


def require_staff(user=Depends(require_user)):
    if user["role"] not in ("admin", "moderator"):
        raise HTTPException(403, "Staff permission required.")
    return user
