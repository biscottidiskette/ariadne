"""
routes/artifacts.py — Artifact ingestion endpoints.

Both ingestion paths (paste and upload) now run through the
parser registry which normalizes content and auto-extracts
IoCs and timeline events on ingest.

URL structure:
  GET  /api/engagements/{id}/artifacts         — list all
  POST /api/engagements/{id}/artifacts/upload  — file upload
  POST /api/engagements/{id}/artifacts/paste   — paste text
  GET  /api/engagements/{id}/artifacts/{a_id}  — get one
"""

import json
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from db.database_service import DatabaseService
from parsers.parser_registry import parse_artifact
from models.schemas import ArtifactResponse

router = APIRouter(tags=["artifacts"])
db = DatabaseService()

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


@router.get(
    "/engagements/{engagement_id}/artifacts",
    response_model=list[ArtifactResponse]
)
async def list_artifacts(engagement_id: int):
    """Return all artifacts for an engagement, newest first."""
    engagement = db.get_engagement(engagement_id)
    if engagement is None:
        raise HTTPException(status_code=404, detail=f"Engagement {engagement_id} not found")
    return db.list_artifacts(engagement_id)


@router.get(
    "/engagements/{engagement_id}/artifacts/{artifact_id}",
    response_model=ArtifactResponse
)
async def get_artifact(engagement_id: int, artifact_id: int):
    """Fetch a single artifact by ID."""
    engagement = db.get_engagement(engagement_id)
    if engagement is None:
        raise HTTPException(status_code=404, detail=f"Engagement {engagement_id} not found")

    artifact = db.get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail=f"Artifact {artifact_id} not found")
    return artifact


@router.post(
    "/engagements/{engagement_id}/artifacts/paste",
    response_model=ArtifactResponse,
    status_code=201
)
async def paste_artifact(
    engagement_id: int,
    content: str = Form(...),
    artifact_type: str = Form("paste"),
):
    """
    Ingest a pasted artifact.

    Runs through the parser registry to normalize content,
    then auto-saves any extracted IoCs and timeline events.
    """
    engagement = db.get_engagement(engagement_id)
    if engagement is None:
        raise HTTPException(status_code=404, detail=f"Engagement {engagement_id} not found")

    if not content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")

    # Parse through registry
    parse_result = parse_artifact(
        raw_content=content,
        artifact_type=artifact_type,
    )

    # Store artifact with parsed output
    artifact = db.create_artifact(
        engagement_id=engagement_id,
        artifact_type=artifact_type,
        raw_content=content,
        parsed_content=parse_result['parsed_content'],
        summary=parse_result['summary'],
        filename=None,
    )

    # Auto-save extracted IoCs
    for ioc in parse_result.get('iocs', []):
        try:
            db.create_ioc(
                engagement_id=engagement_id,
                ioc_type=ioc['ioc_type'],
                value=ioc['value'],
                context=ioc.get('context'),
                source_artifact_id=artifact['id'],
            )
        except Exception:
            pass  # Skip duplicates or invalid IoCs silently

    # Auto-save timeline events
    for event in parse_result.get('timeline_events', []):
        try:
            db.create_timeline_event(
                engagement_id=engagement_id,
                event_time=event['event_time'],
                event_type=event['event_type'],
                description=event['description'],
                host=event.get('host'),
                actor=event.get('actor'),
                process=event.get('process'),
                source_artifact_id=artifact['id'],
            )
        except Exception:
            pass

    return artifact


@router.post(
    "/engagements/{engagement_id}/artifacts/upload",
    response_model=ArtifactResponse,
    status_code=201
)
async def upload_artifact(
    engagement_id: int,
    file: UploadFile = File(...),
    artifact_type: str = Form("other"),
):
    """
    Upload an artifact file.

    Runs through the parser registry which detects type from
    filename and content, then auto-saves IoCs and timeline events.
    """
    engagement = db.get_engagement(engagement_id)
    if engagement is None:
        raise HTTPException(status_code=404, detail=f"Engagement {engagement_id} not found")

    raw_bytes = await file.read()

    if len(raw_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 50MB.")

    # Decode to string for text-based formats
    # Binary formats (EVTX) are passed as bytes to the parser
    try:
        raw_content = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raw_content = f"[BINARY FILE: {file.filename}, {len(raw_bytes)} bytes]"

    # Parse through registry — pass raw_bytes for EVTX support
    parse_result = parse_artifact(
        raw_content=raw_content,
        artifact_type=artifact_type,
        filename=file.filename,
        file_bytes=raw_bytes,
    )

    # Store artifact
    artifact = db.create_artifact(
        engagement_id=engagement_id,
        artifact_type=artifact_type,
        raw_content=raw_content,
        parsed_content=parse_result['parsed_content'],
        summary=parse_result['summary'],
        filename=file.filename,
    )

    # Auto-save extracted IoCs
    for ioc in parse_result.get('iocs', []):
        try:
            db.create_ioc(
                engagement_id=engagement_id,
                ioc_type=ioc['ioc_type'],
                value=ioc['value'],
                context=ioc.get('context'),
                source_artifact_id=artifact['id'],
            )
        except Exception:
            pass

    # Auto-save timeline events
    for event in parse_result.get('timeline_events', []):
        try:
            db.create_timeline_event(
                engagement_id=engagement_id,
                event_time=event['event_time'],
                event_type=event['event_type'],
                description=event['description'],
                host=event.get('host'),
                actor=event.get('actor'),
                process=event.get('process'),
                source_artifact_id=artifact['id'],
            )
        except Exception:
            pass

    return artifact
