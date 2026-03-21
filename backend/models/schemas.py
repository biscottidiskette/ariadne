"""
schemas.py — Pydantic models for Ariadne.

These models serve three purposes:
  1. Request validation  — FastAPI uses them to validate incoming JSON.
                           If a required field is missing or the wrong
                           type, FastAPI returns a 422 automatically
                           before your code even runs.

  2. Response shaping    — FastAPI serializes return values through these
                           models, ensuring the API always returns a
                           consistent structure.

  3. Documentation       — FastAPI auto-generates OpenAPI docs from these.
                           Visit /docs when the server is running to see
                           the full interactive API documentation.

Naming convention used here:
  - Base      — shared fields between create and read
  - Create    — fields required/allowed when creating a resource (POST)
  - Update    — fields allowed when updating (PATCH) — all Optional
  - Response  — what the API returns — includes id, timestamps, etc.

Why separate Create and Response?
  You never want the client to set id, created_at, or updated_at.
  Those are server-controlled. Keeping Create and Response separate
  makes that boundary explicit and enforced by the type system.
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


# ---------------------------------------------------------------------------
# ENUMS
# Defining valid values as enums means:
#   - FastAPI validates them automatically
#   - Your editor autocompletes them
#   - They're documented in /docs
# ---------------------------------------------------------------------------

class EngagementStatus(str, Enum):
    """Lifecycle states for an engagement."""
    active          = "active"
    contained       = "contained"
    closed          = "closed"
    archived        = "archived"


class SuggestionStatus(str, Enum):
    """
    Lifecycle states for an LLM suggestion.
    This is the core of the anti-circular engine.
    pending     — LLM just suggested it, analyst hasn't acted yet
    in_progress — analyst is currently investigating this path
    tried       — attempted but inconclusive, may revisit
    worked      — confirmed useful finding
    failed      — dead end, do not revisit
    dismissed   — analyst explicitly doesn't want to pursue this
    """
    pending     = "pending"
    in_progress = "in_progress"
    tried       = "tried"
    worked      = "worked"
    failed      = "failed"
    dismissed   = "dismissed"


class ArtifactType(str, Enum):
    """All artifact types Ariadne can ingest."""
    evtx            = "evtx"
    chainsaw        = "chainsaw"
    ioc             = "ioc"
    edr             = "edr"
    siem            = "siem"
    sigma           = "sigma"
    prefetch        = "prefetch"
    registry        = "registry"
    memory          = "memory"
    scheduled_task  = "scheduled_task"
    paste           = "paste"
    other           = "other"


class IocType(str, Enum):
    """Classification of an Indicator of Compromise."""
    ip              = "ip"
    domain          = "domain"
    hash_md5        = "hash_md5"
    hash_sha1       = "hash_sha1"
    hash_sha256     = "hash_sha256"
    file_path       = "file_path"
    registry_key    = "registry_key"
    email           = "email"
    url             = "url"
    mutex           = "mutex"
    other           = "other"


class TimelineEventType(str, Enum):
    """Classification of a timeline event."""
    process_creation        = "process_creation"
    network_connection      = "network_connection"
    file_write              = "file_write"
    registry_modification   = "registry_modification"
    logon                   = "logon"
    service_install         = "service_install"
    scheduled_task          = "scheduled_task"
    lateral_movement        = "lateral_movement"
    persistence             = "persistence"
    exfiltration            = "exfiltration"
    manual                  = "manual"
    other                   = "other"


class PlaybookPhase(str, Enum):
    """
    PICERL IR phases.
    Standard IR lifecycle used to categorize playbook steps.
    """
    preparation     = "preparation"
    identification  = "identification"
    containment     = "containment"
    eradication     = "eradication"
    recovery        = "recovery"
    lessons_learned = "lessons_learned"


class PlaybookStepStatus(str, Enum):
    """Completion state of a playbook step."""
    pending     = "pending"
    in_progress = "in_progress"
    complete    = "complete"
    skipped     = "skipped"


class MessageRole(str, Enum):
    """Chat message roles — mirrors Groq/OpenAI format exactly."""
    user        = "user"
    assistant   = "assistant"
    system      = "system"


# ---------------------------------------------------------------------------
# ENGAGEMENTS
# ---------------------------------------------------------------------------

class EngagementCreate(BaseModel):
    """
    Fields the client sends when creating a new engagement.
    name is required. Everything else is optional.
    """
    name:           str             = Field(..., min_length=1, max_length=200)
    description:    Optional[str]   = Field(None, max_length=2000)
    status:         EngagementStatus = EngagementStatus.active
    lead_id:        Optional[str]   = Field(None, max_length=100)


class EngagementUpdate(BaseModel):
    """
    All fields optional — client sends only what they want to change.
    This is the PATCH pattern.
    """
    name:           Optional[str]               = Field(None, min_length=1, max_length=200)
    description:    Optional[str]               = Field(None, max_length=2000)
    status:         Optional[EngagementStatus]  = None
    lead_id:        Optional[str]               = Field(None, max_length=100)


class EngagementResponse(BaseModel):
    """
    What the API returns for an engagement.
    Includes server-set fields: id, created_at, updated_at.
    """
    id:             int
    name:           str
    description:    Optional[str]
    status:         str
    lead_id:        Optional[str]
    created_at:     str
    updated_at:     str

    class Config:
        # Allows creating this model from a dict (e.g. from database row)
        from_attributes = True


# ---------------------------------------------------------------------------
# ARTIFACTS
# ---------------------------------------------------------------------------

class ArtifactCreate(BaseModel):
    """
    Used for paste-based artifact ingestion.
    File uploads are handled separately via multipart form.
    """
    engagement_id:  int
    artifact_type:  ArtifactType
    raw_content:    str             = Field(..., min_length=1)
    filename:       Optional[str]   = None


class ArtifactResponse(BaseModel):
    """What the API returns for an artifact."""
    id:             int
    engagement_id:  int
    artifact_type:  str
    filename:       Optional[str]
    raw_content:    Optional[str]
    parsed_content: Optional[str]
    summary:        Optional[str]
    created_at:     str

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# MESSAGES
# ---------------------------------------------------------------------------

class MessageCreate(BaseModel):
    """
    Sent by the frontend when the analyst submits a chat message.
    engagement_id tells the backend which context to load.
    content is the analyst's message text.
    """
    engagement_id:  int
    content:        str = Field(..., min_length=1)


class MessageResponse(BaseModel):
    """A single chat message as returned by the API."""
    id:             int
    engagement_id:  int
    role:           str
    content:        str
    token_count:    Optional[int]
    created_at:     str

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# SUGGESTIONS
# ---------------------------------------------------------------------------

class SuggestionResponse(BaseModel):
    """A single suggestion as returned by the API."""
    id:                 int
    engagement_id:      int
    source_message_id:  Optional[int]
    canonical_text:     str
    full_text:          Optional[str]
    status:             str
    created_at:         str
    updated_at:         str

    class Config:
        from_attributes = True


class SuggestionStatusUpdate(BaseModel):
    """
    Sent by the frontend when the analyst updates a suggestion status.
    This is the primary interaction on the suggested next queries sidebar.
    """
    status: SuggestionStatus


# ---------------------------------------------------------------------------
# IoCs
# ---------------------------------------------------------------------------

class IocCreate(BaseModel):
    """For manually adding an IoC outside of artifact parsing."""
    engagement_id:      int
    ioc_type:           IocType
    value:              str = Field(..., min_length=1, max_length=500)
    context:            Optional[str]   = None
    source_artifact_id: Optional[int]   = None
    first_seen:         Optional[str]   = None
    last_seen:          Optional[str]   = None


class IocResponse(BaseModel):
    """An IoC as returned by the API."""
    id:                 int
    engagement_id:      int
    source_artifact_id: Optional[int]
    ioc_type:           str
    value:              str
    context:            Optional[str]
    first_seen:         Optional[str]
    last_seen:          Optional[str]
    created_at:         str

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# TIMELINE EVENTS
# ---------------------------------------------------------------------------

class TimelineEventCreate(BaseModel):
    """For manually adding a timeline event."""
    engagement_id:      int
    event_time:         str = Field(..., description="ISO 8601 datetime string")
    event_type:         TimelineEventType
    description:        str = Field(..., min_length=1)
    host:               Optional[str] = None
    actor:              Optional[str] = None
    process:            Optional[str] = None
    ioc_id:             Optional[int] = None
    source_artifact_id: Optional[int] = None


class TimelineEventResponse(BaseModel):
    """A timeline event as returned by the API."""
    id:                 int
    engagement_id:      int
    source_artifact_id: Optional[int]
    event_time:         str
    event_type:         str
    description:        str
    host:               Optional[str]
    actor:              Optional[str]
    process:            Optional[str]
    ioc_id:             Optional[int]
    created_at:         str

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# PLAYBOOK
# ---------------------------------------------------------------------------

class PlaybookStepResponse(BaseModel):
    """A single playbook step as returned by the API."""
    id:             int
    engagement_id:  int
    step_order:     int
    phase:          str
    title:          str
    description:    str
    status:         str
    notes:          Optional[str]
    created_at:     str
    updated_at:     str

    class Config:
        from_attributes = True


class PlaybookStepStatusUpdate(BaseModel):
    """Sent by the frontend when checking off or updating a playbook step."""
    status: PlaybookStepStatus
    notes:  Optional[str] = None


class PlaybookGenerateRequest(BaseModel):
    """
    Request to generate a new playbook for an engagement.
    Sending this triggers the LLM to produce steps based on
    all accumulated context for the engagement.
    clear_existing controls whether to wipe the current playbook first.
    """
    engagement_id:  int
    clear_existing: bool = True


# ---------------------------------------------------------------------------
# SIGMA RULES
# ---------------------------------------------------------------------------

class SigmaRuleResponse(BaseModel):
    """A Sigma rule as returned by the API."""
    id:             int
    engagement_id:  int
    ioc_id:         Optional[int]
    title:          str
    description:    Optional[str]
    rule_yaml:      str
    is_validated:   int
    created_at:     str
    updated_at:     str

    class Config:
        from_attributes = True


class SigmaGenerateRequest(BaseModel):
    """
    Request to generate a Sigma rule.
    If ioc_id is provided, the rule is targeted at that specific IoC.
    If None, the LLM generates a rule based on broader engagement context.
    """
    engagement_id:  int
    ioc_id:         Optional[int] = None
    context_hint:   Optional[str] = Field(
        None,
        description="Optional extra context to guide rule generation"
    )


# ---------------------------------------------------------------------------
# NOTES
# ---------------------------------------------------------------------------

class NoteCreate(BaseModel):
    """For adding a timestamped analyst note."""
    engagement_id:  int
    content:        str = Field(..., min_length=1)
    hits_context:   bool = True


class NoteResponse(BaseModel):
    """A note as returned by the API."""
    id:             int
    engagement_id:  int
    content:        str
    hits_context:   int
    created_at:     str

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# GRAPH
# Artifact relationship graph — nodes and edges for the frontend
# force-directed graph visualization.
# ---------------------------------------------------------------------------

class GraphNode(BaseModel):
    """
    A node in the artifact relationship graph.
    node_type drives the color/icon on the frontend:
      ioc | process | host | event_id | artifact
    """
    id:         str
    label:      str
    node_type:  str
    metadata:   Optional[dict] = None


class GraphEdge(BaseModel):
    """
    A directed edge connecting two nodes.
    label describes the relationship: 'observed_on', 'spawned',
    'connected_to', 'modified', etc.
    """
    source:     str
    target:     str
    label:      Optional[str] = None


class GraphResponse(BaseModel):
    """Full graph payload for the frontend visualization."""
    nodes:  list[GraphNode]
    edges:  list[GraphEdge]


# ---------------------------------------------------------------------------
# API HEALTH
# Used by the health check endpoint we'll wire first in main.py
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    """Health check response."""
    status:     str
    version:    str
    db_path:    str