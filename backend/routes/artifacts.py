"""
routes/artifacts.py — Artifact ingestion endpoints.

Artifacts are the evidence. Two ingestion paths:
  1. File upload  — analyst uploads a file (EVTX, JSON, CSV, etc.)
  2. Paste        — analyst pastes raw text directly

Both paths run through the parser registry which detects the
artifact type and normalizes the content for LLM context.

URL structure:
  GET  /api/engagements/{id}/artifacts         — list all
  POST /api/engagements/{id}/artifacts/upload  — file upload
  POST /api/engagements/{id}/artifacts/paste   — paste text
  GET  /api/engagements/{id}/artifacts/{a_id}  — get one
"""

import json
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from db.database_service import DatabaseService
from models.schemas import ArtifactResponse

router = APIRouter(tags=["artifacts"])
db = DatabaseService()

# Maximum file size: 50MB
# Large EVTX files can be substantial but we parse+summarize them
# so the raw content size doesn't directly affect LLM costs
MAX_FILE_SIZE = 50 * 1024 * 1024


@router.get(
    "/engagements/{engagement_id}/artifacts",
    response_model=list[ArtifactResponse]
)
async def list_artifacts(engagement_id: int):
    """Return all artifacts for an engagement, newest first."""
    engagement = db.get_engagement(engagement_id)
    if engagement is None:
        raise HTTPException(
            status_code=404,
            detail=f"Engagement {engagement_id} not found"
        )
    return db.list_artifacts(engagement_id)


@router.get(
    "/engagements/{engagement_id}/artifacts/{artifact_id}",
    response_model=ArtifactResponse
)
async def get_artifact(engagement_id: int, artifact_id: int):
    """Fetch a single artifact by ID."""
    engagement = db.get_engagement(engagement_id)
    if engagement is None:
        raise HTTPException(
            status_code=404,
            detail=f"Engagement {engagement_id} not found"
        )

    artifact = db.get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(
            status_code=404,
            detail=f"Artifact {artifact_id} not found"
        )
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

    The analyst pastes raw text — log output, EDR alert JSON,
    SIEM query results, malware strings, etc.

    artifact_type should be one of the ArtifactType enum values.
    If unsure, use 'paste' and the parser registry will attempt
    best-effort type detection from the content.

    Why Form() instead of JSON body?
      File uploads use multipart form data. Keeping paste as Form
      too means both endpoints have the same content-type on the
      frontend, simplifying the upload component.
    """
    engagement = db.get_engagement(engagement_id)
    if engagement is None:
        raise HTTPException(
            status_code=404,
            detail=f"Engagement {engagement_id} not found"
        )

    if not content.strip():
        raise HTTPException(
            status_code=400,
            detail="Content cannot be empty"
        )

    # Parser registry will be wired here in Epic 5
    # For now we store raw content with a placeholder summary
    # The full parser integration comes when we build parsers/
    parsed_content = json.dumps({"raw": content, "parsed": False})
    summary = f"Pasted {artifact_type} artifact — {len(content)} chars. Parser pending."

    artifact = db.create_artifact(
        engagement_id=engagement_id,
        artifact_type=artifact_type,
        raw_content=content,
        parsed_content=parsed_content,
        summary=summary,
        filename=None,
    )
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

    Accepts any file type. The parser registry routes it to the
    correct parser based on extension and content sniffing.

    Current parser support (Epic 5):
      .evtx  → evtx_parser.py
      .json  → chainsaw_parser.py (if Chainsaw format detected)
      .csv   → siem_parser.py / edr_parser.py
      .yml   → sigma_parser.py
      .txt   → paste_parser.py (best-effort)

    File size limit: 50MB. Large files are parsed and summarized —
    the raw content is stored but only the summary hits LLM context.
    """
    engagement = db.get_engagement(engagement_id)
    if engagement is None:
        raise HTTPException(
            status_code=404,
            detail=f"Engagement {engagement_id} not found"
        )

    # Read file content
    raw_bytes = await file.read()

    if len(raw_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is 50MB."
        )

    # Decode to string — most artifact types are text-based
    # Binary files (raw EVTX) need special handling in the parser
    try:
        raw_content = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        # Binary file — store as placeholder, parser handles it
        raw_content = f"[BINARY FILE: {file.filename}, {len(raw_bytes)} bytes]"

    # Parser registry will be wired here in Epic 5
    parsed_content = json.dumps({
        "raw": raw_content[:1000],  # Preview only for binary
        "parsed": False,
        "filename": file.filename,
    })
    summary = (
        f"Uploaded file: {file.filename} "
        f"({len(raw_bytes)} bytes, type: {artifact_type}). "
        f"Parser pending."
    )

    artifact = db.create_artifact(
        engagement_id=engagement_id,
        artifact_type=artifact_type,
        raw_content=raw_content,
        parsed_content=parsed_content,
        summary=summary,
        filename=file.filename,
    )
    return artifact