"""
main.py — FastAPI application entry point for Ariadne.

This file:
  1. Creates the FastAPI app instance
  2. Configures CORS so the React frontend can talk to the backend
  3. Registers route modules as they are built
  4. Provides the /health endpoint
  5. Initializes the database on startup

Build strategy:
  We wire routes one at a time as each service is built.
  Right now: health only.
  Each future Epic will add one import + one app.include_router() line.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from db.database_service import DatabaseService
from ai.ai import ai_controller
from models.schemas import HealthResponse
from db.db import DB_PATH

from routes.artifacts import router as artifacts_router
from routes.chat import router as chat_router
from routes.engagements import router as engagements_router
from routes.iocs import router as iocs_router
from routes.notes import router as notes_router
from routes.suggestions import router as suggestions_router
from routes.timeline import router as timeline_router
from routes.playbook import router as playbook_router

# ---------------------------------------------------------------------------
# Lifespan — runs on startup and shutdown
# Using lifespan instead of the deprecated @app.on_event("startup")
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Code before 'yield' runs on startup.
    Code after 'yield' runs on shutdown.

    On startup we initialize the database. This creates the tables
    if they don't exist yet. Safe to call on every boot.
    """
    print("[ariadne] Starting up...")
    db = DatabaseService()
    print("[ariadne] Database ready.")
    print(f"[ariadne] DB path: {DB_PATH}")
    print("[ariadne] Ariadne is ready.")
    yield
    # Shutdown logic goes here post-MVP (close connection pools, etc.)
    print("[ariadne] Shutting down.")


# ---------------------------------------------------------------------------
# App instance
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Ariadne IR Decision Engine",
    description="LLM-assisted Incident Response platform",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# CORS
# Allows the React dev server (port 5173) to call this API (port 8000).
# In production this would be locked to your actual domain.
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite dev server
        "http://localhost:3000",   # fallback
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# ROUTES
# ---------------------------------------------------------------------------
app.include_router(artifacts_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(engagements_router, prefix="/api")
app.include_router(iocs_router, prefix="/api")
app.include_router(notes_router, prefix="/api")
app.include_router(suggestions_router, prefix="/api")
app.include_router(timeline_router, prefix="/api")
app.include_router(playbook_router, prefix="/api")

# ---------------------------------------------------------------------------
# HEALTH ENDPOINT
# First endpoint. Verifies:
#   - FastAPI is running
#   - Database is reachable
#   - Groq API is connected
#
# The frontend will poll this to show the connection status indicator.
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health_check():
    """
    System health check.

    Checks FastAPI, database connection, and Groq API connectivity.
    Returns status 'ok' if all systems are operational.
    """
    # Check Groq connectivity
    groq_status = ai_controller.groq.health_check()

    return HealthResponse(
        status="ok" if groq_status["status"] == "connected" else "degraded",
        version="0.1.0",
        db_path=str(DB_PATH),
    )


# ---------------------------------------------------------------------------
# ROUTES — wired one at a time as each feature is built
#
# Pattern for adding a new route:
#   from routes.engagements import router as engagements_router
#   app.include_router(engagements_router, prefix="/api")
#
# Current:  health only
# Next:     engagements router (E7-02)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Entry point — run with: python main.py
# Or the standard way:    uvicorn main:app --reload
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,     # Auto-restart on file changes during development
    )