import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from backend.app.models.request_models import Login, Register
from backend.app.services.auth_service import COOKIE, require_user
from backend.app.services.database_service import db_session
from backend.app.services.security import hash_password, token_hash, verify_password
from backend.app.services.time_service import now_utc

router = APIRouter(tags=["auth"])


@router.post("/register", status_code=201)
def register(body: Register):
    try:
        with db_session(write=True) as db:
            db.execute("""INSERT INTO tableSignInInfo
              (Username,PasswordHash,LastName,FirstName,UserPhone,UserEmail,CreatedAt)
              VALUES (?,?,?,?,?,?,?)""", (body.email.lower().strip(), hash_password(body.password),
              body.lastname.strip(), body.firstname.strip(), body.phone or None,
              body.email.lower().strip(), now_utc()))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "An account with that email already exists.")
    return {"message": "Account created successfully!"}


@router.post("/login")
def login(body: Login, response: Response):
    with db_session() as db:
        row = db.execute("""SELECT * FROM tableSignInInfo
          WHERE Username=? COLLATE NOCASE OR UserEmail=? COLLATE NOCASE""",
          (body.email.strip(), body.email.strip())).fetchone()
    if row is None or not row["IsActive"] or not verify_password(body.password, row["PasswordHash"]):
        raise HTTPException(401, "Invalid email or password.")
    token = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
    with db_session(write=True) as db:
        db.execute("DELETE FROM sessions WHERE expires_at<=?", (now_utc(),))
        db.execute("INSERT INTO sessions VALUES (?,?,?)", (token_hash(token), row["UniqueID"], expires))
        staff = db.execute('SELECT * FROM tableTrustedUsers WHERE UniqueID=?', (row["UniqueID"],)).fetchone()
        if staff:
            db.execute('UPDATE tableTrustedUsers SET "Most_recent_clock-in"=? WHERE UniqueID=?',
                       (now_utc(), row["UniqueID"]))
    role = "admin" if staff and staff["Super-Moderator?"] else "moderator" if staff and staff["Moderator?"] else "student"
    response.set_cookie(COOKIE, token, httponly=True, samesite="strict", max_age=43200, path="/",
                        secure=os.environ.get("ROCKWALL_COOKIE_SECURE", "0") == "1")
    response.headers["Cache-Control"] = "no-store"
    return {"message": "Login successful", "role": role}


@router.get("/me")
def me(response: Response, user=Depends(require_user)):
    response.headers["Cache-Control"] = "no-store"
    return user


@router.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE)
    if token:
        with db_session(write=True) as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash(token),))
    response.delete_cookie(COOKIE, path="/")
    return {"message": "Signed out."}
