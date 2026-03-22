from fastapi import APIRouter, HTTPException
from db.database_service import DatabaseService
from ai.ai import ai_controller
from models.schemas import PlaybookStepResponse, PlaybookStepStatusUpdate, PlaybookGenerateRequest

router = APIRouter(tags=["playbook"])
db = DatabaseService()


@router.get("/engagements/{engagement_id}/playbook", response_model=list[PlaybookStepResponse])
async def list_playbook(engagement_id: int):
    engagement = db.get_engagement(engagement_id)
    if engagement is None:
        raise HTTPException(status_code=404, detail=f"Engagement {engagement_id} not found")
    return db.list_playbook_steps(engagement_id)


@router.post("/engagements/{engagement_id}/playbook/generate", response_model=list[PlaybookStepResponse])
async def generate_playbook(engagement_id: int, payload: PlaybookGenerateRequest):
    engagement = db.get_engagement(engagement_id)
    if engagement is None:
        raise HTTPException(status_code=404, detail=f"Engagement {engagement_id} not found")
    if payload.clear_existing:
        db.clear_playbook(engagement_id)
    try:
        return ai_controller.generate_playbook(engagement_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Playbook generation failed: {e}")


@router.patch("/engagements/{engagement_id}/playbook/{step_id}", response_model=PlaybookStepResponse)
async def update_playbook_step(engagement_id: int, step_id: int, payload: PlaybookStepStatusUpdate):
    engagement = db.get_engagement(engagement_id)
    if engagement is None:
        raise HTTPException(status_code=404, detail=f"Engagement {engagement_id} not found")
    updated = db.update_playbook_step_status(step_id=step_id, status=payload.status.value, notes=payload.notes)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Step {step_id} not found")
    return updated
