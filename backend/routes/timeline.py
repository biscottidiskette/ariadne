from fastapi import APIRouter, HTTPException
from db.database_service import DatabaseService
from models.schemas import TimelineEventCreate, TimelineEventResponse

router = APIRouter(tags=["timeline"])
db = DatabaseService()


@router.get("/engagements/{engagement_id}/timeline", response_model=list[TimelineEventResponse])
async def list_timeline(engagement_id: int):
    engagement = db.get_engagement(engagement_id)
    if engagement is None:
        raise HTTPException(status_code=404, detail=f"Engagement {engagement_id} not found")
    return db.list_timeline_events(engagement_id)


@router.post("/engagements/{engagement_id}/timeline", response_model=TimelineEventResponse, status_code=201)
async def create_timeline_event(engagement_id: int, payload: TimelineEventCreate):
    engagement = db.get_engagement(engagement_id)
    if engagement is None:
        raise HTTPException(status_code=404, detail=f"Engagement {engagement_id} not found")
    return db.create_timeline_event(
        engagement_id=engagement_id,
        event_time=payload.event_time,
        event_type=payload.event_type.value,
        description=payload.description,
        host=payload.host,
        actor=payload.actor,
        process=payload.process,
        ioc_id=payload.ioc_id,
        source_artifact_id=payload.source_artifact_id,
    )
