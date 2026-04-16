from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os

from app.database import init_db
from app.routers import candidates, sessions, chat
from app.routers import analytics, calendar_routes, settings_routes, export


# ─── DB initialization flag (for serverless fallback) ─────────────────────────
_db_initialized = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB on startup."""
    global _db_initialized
    await init_db()
    _db_initialized = True
    yield


app = FastAPI(
    title="AI Interview Scheduler",
    description="An AI-powered interview scheduling agent using Google Gemini — with dashboard, calendar, and candidate management",
    version="2.0.0",
    lifespan=lifespan,
)

# ─── CORS (allows browser requests from any origin) ───────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # In production, replace * with your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Serverless DB init middleware (Vercel doesn't always fire lifespan) ──────
@app.middleware("http")
async def ensure_db_initialized(request: Request, call_next):
    global _db_initialized
    if not _db_initialized:
        await init_db()
        _db_initialized = True
    return await call_next(request)

# ─── Core Routers ─────────────────────────────────────────────────────────────
app.include_router(candidates.router)
app.include_router(sessions.router)
app.include_router(chat.router)

# ─── Feature Routers ─────────────────────────────────────────────────────────
app.include_router(analytics.router)
app.include_router(calendar_routes.router)
app.include_router(settings_routes.router)
app.include_router(export.router)

# ─── Static files (frontend) ──────────────────────────────────────────────────
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", include_in_schema=False)
async def serve_frontend():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "AI Interview Scheduler API is running. Visit /docs for the API reference."}


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "AI Interview Scheduler", "version": "2.0.0"}
