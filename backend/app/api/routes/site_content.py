import uuid
from fastapi import APIRouter, Depends, HTTPException
from backend.app.models.request_models import FaqIn, FeedbackIn, SiteContentIn, ensure_no_profanity
from backend.app.services.auth_service import require_admin
from backend.app.services.database_service import db_session
from backend.app.services.time_service import now_utc

router = APIRouter(tags=["content"])


def read_rows(sql):
    with db_session() as db:
        return [dict(r) for r in db.execute(sql)]


@router.get("/faqs")
def faqs():
    return read_rows("SELECT * FROM faqs ORDER BY id")


@router.post("/admin/faqs", status_code=201)
def admin_create_faq(body: FaqIn, user=Depends(require_admin)):
    if not body.q.strip() or not body.a.strip():
        raise HTTPException(422, "Question and answer are required.")
    ensure_no_profanity(body.q)
    ensure_no_profanity(body.a)
    with db_session(write=True) as db:
        cur = db.execute("INSERT INTO faqs(q,a) VALUES (?,?)", (body.q.strip(), body.a.strip()))
        return dict(db.execute("SELECT * FROM faqs WHERE id=?", (cur.lastrowid,)).fetchone())


@router.delete("/admin/faqs/{faq_id}")
def admin_delete_faq(faq_id: int, user=Depends(require_admin)):
    with db_session(write=True) as db:
        if not db.execute("DELETE FROM faqs WHERE id=?", (faq_id,)).rowcount:
            raise HTTPException(404, "FAQ not found.")
    return {"message": "FAQ deleted."}


@router.get("/site-content")
def site_content():
    return {r["k"]: r["v"] for r in read_rows("SELECT * FROM site_content")}


@router.put("/admin/site-content")
def admin_site_content(body: SiteContentIn, user=Depends(require_admin)):
    if not body.k.strip():
        raise HTTPException(422, "Key required.")
    with db_session(write=True) as db:
        db.execute("INSERT INTO site_content(k,v) VALUES (?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                   (body.k.strip(), body.v))
    return {"k": body.k, "v": body.v}


@router.get("/equipment")
def equipment():
    return read_rows("SELECT * FROM equipment ORDER BY id")


@router.get("/peak")
def peak():
    return read_rows("SELECT hour,SUM(count) AS count FROM peak_visits GROUP BY hour ORDER BY hour")


@router.get("/leaderboard")
def leaderboard():
    return read_rows("SELECT * FROM leaderboard ORDER BY score DESC,id")


@router.get("/routes")
def routes():
    return read_rows("SELECT * FROM routes ORDER BY id")


@router.get("/feedback")
def list_feedback():
    return read_rows("SELECT * FROM feedback ORDER BY created DESC")


@router.post("/feedback", status_code=201)
def add_feedback(body: FeedbackIn):
    if not 1 <= body.rating <= 5 or not body.comment.strip():
        raise HTTPException(422, "A rating from 1–5 and a comment are required.")
    identifier = str(uuid.uuid4())
    with db_session(write=True) as db:
        if not db.execute("SELECT 1 FROM routes WHERE name=?", (body.route,)).fetchone():
            raise HTTPException(422, "Choose an existing route.")
        db.execute("INSERT INTO feedback(id,route,rating,comment,author,created) VALUES (?,?,?,?,?,?)",
                   (identifier, body.route, body.rating, body.comment, body.author or "Anonymous", now_utc()))
    return {"message": "Feedback saved.", "id": identifier}
