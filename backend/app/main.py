import asyncio
from contextlib import asynccontextmanager, suppress
import logging
import os
from pathlib import Path
import sqlite3

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes import appointments, auth, capacity, events, queue, site_content
from backend.app.services.database_service import db_session, initialize_database
from backend.app.services.visits import cleanup_database

logger = logging.getLogger("rockwall")
DIST = Path(os.environ.get("ROCKWALL_WEB_DIST", Path(__file__).resolve().parents[2] / "frontend/dist"))
ORIGINS = [s.strip() for s in os.environ.get(
    "ROCKWALL_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if s.strip()]


async def housekeeping():
    while True:
        await asyncio.sleep(60)
        try:
            await asyncio.to_thread(cleanup_database)
        except Exception:
            logger.exception("Rockwall database housekeeping failed")


@asynccontextmanager
async def lifespan(app):
    result = initialize_database()
    logger.info("Database upgrade: %s", result)
    task = asyncio.create_task(housekeeping())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="TTU Rockwall API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_credentials=True,
                   allow_methods=["GET","POST","PATCH","PUT","DELETE"], allow_headers=["Content-Type"])


@app.middleware("http")
async def protect_requests(request: Request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin and origin not in {*ORIGINS, str(request.base_url).rstrip("/")}:
            return JSONResponse({"detail": "Untrusted request origin."}, status_code=403)
        if request.headers.get("content-length", "0") != "0" and not request.headers.get(
            "content-type", "").startswith("application/json"):
            return JSONResponse({"detail": "Send JSON request bodies."}, status_code=415)
    response = await call_next(request)
    if request.url.path.startswith("/api") or request.cookies.get("rockwall_session"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(sqlite3.IntegrityError)
async def constraint_error(request, exc):
    return JSONResponse({"detail": "This change conflicts with an existing record."}, status_code=409)


@app.get("/api/health")
def health_check():
    with db_session() as db:
        db.execute("SELECT name FROM schema_migrations").fetchall()
    return {"app": "TTU Rockwall API", "status": "ok"}


for module in (capacity, events, auth, appointments, queue, site_content):
    app.include_router(module.router, prefix="/api")
    # Compatibility with the original direct-to-backend endpoint paths.
    app.include_router(module.router, include_in_schema=False)


@app.get("/")
def homepage():
    if (DIST / "index.html").is_file():
        return FileResponse(DIST / "index.html")
    return {"app": "TTU Rockwall API", "status": "ok", "frontend": "Run npm run build in frontend."}


if (DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")
# Serve public root assets without allowing filesystem traversal.
@app.get("/{filename}")
def public_asset(filename: str):
    target = DIST / filename
    if filename != Path(filename).name or not target.is_file() or target.suffix not in (".jpg",".png",".svg",".ico",".webp",".txt"):
        return JSONResponse({"detail": "Not found."}, status_code=404)
    return FileResponse(target)
