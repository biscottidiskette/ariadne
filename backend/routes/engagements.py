"""
routes/engagements.py — Engagement (case) CRUD endpoints.

These are the first real feature endpoints. They power:
  - The landing page engagement list
  - Creating new cases
  - Updating case status
  - Deleting cases

All endpoints follow the same pattern:
  1. Validate input via Pydantic (FastAPI does this automatically)
  2. Call database_service
  3. Handle the not-found case with a 404
  4. Return the response model

URL structure:
  GET    /api/engagements          — list all
  POST   /api/engagements          — create new
  GET    /api/engagements/{id}     — get one
  PATCH  /api/engagements/{id}     — partial update
  DELETE /api/engagements/{id}     — delete
"""

from fastapi import APIRouter, HTTPException
from db.database_service import DatabaseService
from models.schemas import (
    EngagementCreate,
    EngagementUpdate,
    EngagementResponse,
)

# APIRouter is FastAPI's way of grouping related endpoints.
# We register this router in main.py with a prefix of /api.
# That means every route defined here is automatically prefixed:
# "/" here becomes "/api/engagements" in the running app.
router = APIRouter(
    prefix="/engagements",
    tags=["engagements"],   # Groups these endpoints in /docs
)

db = DatabaseService()


@router.get("", response_model=list[EngagementResponse])
async def list_engagements():
    """
    Return all engagements ordered by most recently updated.
    This is what the landing page loads on mount.
    """
    return db.list_engagements()


@router.post("", response_model=EngagementResponse, status_code=201)
async def create_engagement(payload: EngagementCreate):
    """
    Create a new engagement.

    FastAPI automatically validates the request body against
    EngagementCreate. If name is missing or empty, FastAPI returns
    422 before this function runs.

    Returns 201 Created with the new engagement.
    """
    engagement = db.create_engagement(
        name=payload.name,
        description=payload.description,
        status=payload.status.value,
        lead_id=payload.lead_id,
    )
    return engagement


@router.get("/{engagement_id}", response_model=EngagementResponse)
async def get_engagement(engagement_id: int):
    """
    Fetch a single engagement by ID.
    Returns 404 if not found.
    """
    engagement = db.get_engagement(engagement_id)
    if engagement is None:
        raise HTTPException(
            status_code=404,
            detail=f"Engagement {engagement_id} not found"
        )
    return engagement


@router.patch("/{engagement_id}", response_model=EngagementResponse)
async def update_engagement(engagement_id: int, payload: EngagementUpdate):
    """
    Partial update — only the fields provided are changed.

    PATCH vs PUT:
      PUT   replaces the entire resource — you send everything
      PATCH updates only what you send — safer for status changes

    We use PATCH so the frontend can update just the status
    (e.g. active → contained) without resending the full object.
    """
    # Verify it exists first
    existing = db.get_engagement(engagement_id)
    if existing is None:
        raise HTTPException(
            status_code=404,
            detail=f"Engagement {engagement_id} not found"
        )

    updated = db.update_engagement(
        engagement_id=engagement_id,
        name=payload.name,
        description=payload.description,
        status=payload.status.value if payload.status else None,
        lead_id=payload.lead_id,
    )
    return updated


@router.delete("/{engagement_id}", status_code=204)
async def delete_engagement(engagement_id: int):
    """
    Delete an engagement and all its related data.

    ON DELETE CASCADE in the schema means this one call removes:
    artifacts, messages, suggestions, IoCs, timeline events,
    playbook steps, sigma rules, and notes.

    Returns 204 No Content on success (nothing to return after deletion).
    Returns 404 if the engagement doesn't exist.
    """
    deleted = db.delete_engagement(engagement_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Engagement {engagement_id} not found"
        )
    # 204 returns no body — just return None
    return None