from fastapi import APIRouter, Header, HTTPException
from typing import Optional
import uuid
from datetime import datetime
from app.services.database_service import get_connection
from app.services.auth_service import require_admin
from app.models.request_models import FaqIn, FeedbackIn, SiteContentIn, ensure_no_profanity

router = APIRouter(tags=["content"])

@router.get("/faqs")
def faqs(): return [dict(r) for r in get_connection().execute("SELECT * FROM faqs").fetchall()]

@router.post("/admin/faqs")
def admin_create_faq(body: FaqIn, x_admin: Optional[str] = Header(None)):
    require_admin(x_admin)
    ensure_no_profanity(body.q); ensure_no_profanity(body.a)
    c = get_connection(); c.execute("INSERT INTO faqs(q,a) VALUES (?,?)", (body.q.strip(), body.a.strip())); c.commit()
    row = c.execute("SELECT * FROM faqs WHERE id=last_insert_rowid()").fetchone(); c.close(); return dict(row)

@router.delete("/admin/faqs/{faq_id}")
def admin_delete_faq(faq_id: int, x_admin: Optional[str] = Header(None)):
    require_admin(x_admin)
    db = get_connection()
    if not db.execute("SELECT 1 FROM faqs WHERE id=?", (faq_id,)).fetchone(): db.close(); raise HTTPException(404, "FAQ not found.")
    db.execute("DELETE FROM faqs WHERE id=?", (faq_id,)); db.commit(); db.close()
    return {"message": "FAQ deleted."}

@router.get("/site-content")
def site_content(): return {r["k"]: r["v"] for r in get_connection().execute("SELECT * FROM site_content").fetchall()}

@router.put("/admin/site-content")
def admin_site_content(body: SiteContentIn, x_admin: Optional[str] = Header(None)):
    require_admin(x_admin)
    if not body.k.strip(): raise HTTPException(400, "key required")
    c = get_connection(); c.execute("INSERT INTO site_content(k,v) VALUES (?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (body.k.strip(), body.v)); c.commit(); c.close()
    return {"k": body.k, "v": body.v}

@router.get("/equipment")
def equipment(): return [dict(r) for r in get_connection().execute("SELECT * FROM equipment").fetchall()]

@router.get("/peak")
def peak(): return [dict(r) for r in get_connection().execute("SELECT * FROM peak_visits ORDER BY hour").fetchall()]

@router.get("/leaderboard")
def leaderboard(): return [dict(r) for r in get_connection().execute("SELECT * FROM leaderboard ORDER BY score DESC").fetchall()]

@router.get("/routes")
def routes(): return [dict(r) for r in get_connection().execute("SELECT * FROM routes").fetchall()]

@router.get("/feedback")
def list_feedback(): return [dict(r) for r in get_connection().execute("SELECT * FROM feedback ORDER BY created DESC").fetchall()]

@router.post("/feedback")
def add_feedback(f: FeedbackIn):
    if not (1 <= f.rating <= 5): raise HTTPException(400, "Rating must be 1–5.")
    fid = str(uuid.uuid4()); c = get_connection()
    c.execute("INSERT INTO feedback VALUES (?,?,?,?,?,?)", (fid, f.route, f.rating, f.comment, f.author or "Anonymous", datetime.now().isoformat())); c.commit(); c.close()
    return {"message": "Feedback saved.", "id": fid}
