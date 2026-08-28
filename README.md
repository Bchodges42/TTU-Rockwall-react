# TTU Rockwall — React + FastAPI rebuild
Rebuild of the DS4330 rockwall site in Vite/React (frontend) + FastAPI/Uvicorn (backend), matching the exact features of the original `TTU-Rockwall-Repo-2026` vanilla site.

## Run

```bash
# backend (http://localhost:8000)
uvicorn backend.main:app --reload

# frontend (http://localhost:5173)
npm run dev
```

Admin login (for admin view): `admin@tntech.edu` / any password.