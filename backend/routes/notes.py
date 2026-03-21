"""
routes/notes.py — Analyst notes endpoints.

Notes are append-only timestamped observations that feed directly
into the LLM system prompt. They capture things that don't fit a
structured parser — phone call summaries, gut feelings, escalation
decisions, out-of-band information.

URL structure:
  GET  /api/engagements/{id}/notes   — list all notes
  POST /api/engagements/{id}/notes   — append a new note
"""

from fastapi import APIRouter, HTTPException
from db.database_service import DatabaseService
from models.schemas import NoteCreate, NoteResponse

router = APIRouter(tags=["notes"])

db = DatabaseService()


@router.get(
    "/engagements/{engagement_id}/notes",
    response_model=list[NoteResponse]
)
async def list_notes(engagement_id: int):
    """
    Return all notes for an engagement, oldest first.

    Oldest first preserves the chronological narrative — notes tell
    the story of the investigation in the order it happened.
    """
    # Verify engagement exists
    engagement = db.get_engagement(engagement_id)
    if engagement is None:
        raise HTTPException(
            status_code=404,
            detail=f"Engagement {engagement_id} not found"
        )

    return db.list_notes(engagement_id)


@router.post(
    "/engagements/{engagement_id}/notes",
    response_model=NoteResponse,
    status_code=201
)
async def create_note(engagement_id: int, payload: NoteCreate):
    """
    Append a timestamped note to an engagement.

    hits_context controls whether this note gets injected into the
    LLM system prompt. Default is True — most notes are relevant.
    Set to False for administrative notes you don't want the LLM
    to see (e.g. internal escalation tracking).
    """
    engagement = db.get_engagement(engagement_id)
    if engagement is None:
        raise HTTPException(
            status_code=404,
            detail=f"Engagement {engagement_id} not found"
        )

    note = db.create_note(
        engagement_id=engagement_id,
        content=payload.content,
        hits_context=payload.hits_context,
    )
    return note