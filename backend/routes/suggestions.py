"""
routes/suggestions.py — Suggestion management endpoints.

Suggestions are the core of the anti-circular engine.
The frontend sidebar displays these and lets the analyst
update their status as they work through the investigation.

URL structure:
  GET   /api/engagements/{id}/suggestions              — list all
  PATCH /api/engagements/{id}/suggestions/{s_id}       — update status
"""

from fastapi import APIRouter, HTTPException
from db.database_service import DatabaseService
from models.schemas import SuggestionResponse, SuggestionStatusUpdate

router = APIRouter(tags=["suggestions"])
db = DatabaseService()


@router.get(
    "/engagements/{engagement_id}/suggestions",
    response_model=list[SuggestionResponse]
)
async def list_suggestions(engagement_id: int):
    """
    Return all suggestions for an engagement, newest first.

    The frontend sidebar polls this (or loads on mount) to display
    the full suggestion list with their current statuses.
    """
    engagement = db.get_engagement(engagement_id)
    if engagement is None:
        raise HTTPException(
            status_code=404,
            detail=f"Engagement {engagement_id} not found"
        )
    return db.list_suggestions(engagement_id)


@router.patch(
    "/engagements/{engagement_id}/suggestions/{suggestion_id}",
    response_model=SuggestionResponse
)
async def update_suggestion_status(
    engagement_id: int,
    suggestion_id: int,
    payload: SuggestionStatusUpdate
):
    """
    Update a suggestion's status.

    This is the primary analyst interaction on the suggestions sidebar.
    As the analyst works through suggestions they mark them:
      pending     → in_progress  (starting to investigate)
      in_progress → worked       (confirmed useful)
      in_progress → failed       (dead end)
      any         → dismissed    (not pursuing this)

    Once marked failed/worked/dismissed, the LLM will not suggest
    this path again — it appears in the system prompt as a hard
    constraint on the next request.
    """
    engagement = db.get_engagement(engagement_id)
    if engagement is None:
        raise HTTPException(
            status_code=404,
            detail=f"Engagement {engagement_id} not found"
        )

    updated = db.update_suggestion_status(
        suggestion_id=suggestion_id,
        status=payload.status.value
    )

    if updated is None:
        raise HTTPException(
            status_code=404,
            detail=f"Suggestion {suggestion_id} not found"
        )

    return updated