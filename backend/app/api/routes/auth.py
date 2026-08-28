from fastapi import APIRouter, Header, HTTPException
from typing import Optional
import uuid
from app.services.database_service import get_connection
from app.services.auth_service import require_admin
from app.models.request_models import Register, Login

router = APIRouter(tags=["auth"])

ADMIN_EMAIL = "admin@tntech.edu"

@router.post("/register")
def register(r: Register):
    if r.email.lower() == ADMIN_EMAIL: raise HTTPException(400, "An account with that email already exists.")
    db = get_connection()
    if db.execute("SELECT 1 FROM users WHERE email=?", (r.email.lower(),)).fetchone(): db.close(); raise HTTPException(400, "An account with that email already exists.")
    db.execute("INSERT INTO users VALUES (?,?,?,?,?)", (r.email.lower(), r.firstname, r.lastname, r.phone, r.password)); db.commit(); db.close()
    return {"message": "Account created successfully!"}

@router.post("/login")
def login(l: Login):
    if l.email.lower() == ADMIN_EMAIL: return {"message": "Admin login", "role": "admin"}
    row = get_connection().execute("SELECT * FROM users WHERE email=?", (l.email.lower(),)).fetchone()
    if not row or row["password"] != l.password: raise HTTPException(401, "Invalid email or password.")
    return {"message": "Login successful", "role": "student"}
