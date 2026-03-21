"""
routes/iocs.py — IoC management endpoints.

IoCs are automatically extracted from artifacts by the parsers,
or manually added by the analyst. They feed into the LLM system
prompt and drive Sigma rule generation.

URL structure:
  GET  /api/engagements/{id}/iocs   — list all
  POST /api/engagements/{id}/iocs   — manually add one
"""

from fastapi import APIRouter, HTTPException
from db.database_service import DatabaseService
from models.schemas import IocCreate, IocResponse

router = APIRouter(tags=["iocs"])
db = DatabaseService()


@router.get(
    "/engagements/{engagement_id}/iocs",
    response_model=list[IocResponse]
)
async def list_iocs(engagement_id: int):
    """Return all IoCs for an engagement."""
    engagement = db.get_engagement(engagement_id)
    if engagement is None:
        raise HTTPException(
            status_code=404,
            detail=f"Engagement {engagement_id} not found"
        )
    return db.list_iocs(engagement_id)


@router.post(
    "/engagements/{engagement_id}/iocs",
    response_model=IocResponse,
    status_code=201
)
async def create_ioc(engagement_id: int, payload: IocCreate):
    """
    Manually add an IoC to an engagement.

    Most IoCs will be auto-extracted by parsers on artifact ingest.
    This endpoint is for IoCs the analyst discovers out-of-band:
    threat intel feeds, vendor reports, phone calls, etc.
    """
    engagement = db.get_engagement(engagement_id)
    if engagement is None:
        raise HTTPException(
            status_code=404,
            detail=f"Engagement {engagement_id} not found"
        )

    ioc = db.create_ioc(
        engagement_id=engagement_id,
        ioc_type=payload.ioc_type.value,
        value=payload.value,
        context=payload.context,
        source_artifact_id=payload.source_artifact_id,
        first_seen=payload.first_seen,
        last_seen=payload.last_seen,
    )
    return ioc