from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import appointments, auth, capacity, events, site_content

app = FastAPI(title="TTU Rockwall API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def health_check():
    return {"app": "TTU Rockwall API", "status": "ok"}


for router in (capacity, events, auth, appointments, site_content):
    app.include_router(router.router)
