"""
routes/chat.py — Chat and messaging endpoints for Ariadne.

Two endpoints:
  POST /api/engagements/{id}/chat         — full response (non-streaming)
  POST /api/engagements/{id}/chat/stream  — streaming via SSE

Why two endpoints?
  The streaming endpoint is what the frontend uses for the chat UI
  so the analyst sees the response appearing in real time.
  The non-streaming endpoint is useful for testing, scripting,
  and any future automated pipeline that needs the full response
  before proceeding.

SSE (Server-Sent Events):
  SSE is a one-way stream from server to client over HTTP.
  The client opens a connection and the server pushes data as it
  becomes available. Simpler than WebSockets for this use case
  because we only need server-to-client streaming, not bidirectional.

  The frontend uses the EventSource API or fetch with a ReadableStream
  to consume the SSE stream.

  Each SSE message is formatted as:
    data: <content chunk>\n\n

  The final message carries metadata (suggestions, message_id)
  prefixed with __META__: so the frontend can distinguish it.

URL structure:
  POST /api/engagements/{id}/chat          — full response
  POST /api/engagements/{id}/chat/stream   — streaming SSE
  GET  /api/engagements/{id}/messages      — message history
  DELETE /api/engagements/{id}/messages    — clear chat context
"""

import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from db.database_service import DatabaseService
from ai.ai import ai_controller
from models.schemas import MessageCreate, MessageResponse

router = APIRouter(tags=["chat"])

db = DatabaseService()


@router.post(
    "/engagements/{engagement_id}/chat",
    tags=["chat"]
)
async def chat(engagement_id: int, payload: MessageCreate):
    """
    Send a message and receive the full response at once.

    Flow:
      1. Validate engagement exists
      2. Pass message to ai_controller.chat()
      3. ai_controller builds context, calls Groq, saves to DB,
         extracts suggestions
      4. Return full response with metadata

    Response includes:
      content     — the assistant's full response text
      message_id  — DB id of the saved assistant message
      suggestions — list of new [SUGGEST] items extracted
      tokens      — token usage for this exchange
    """
    engagement = db.get_engagement(engagement_id)
    if engagement is None:
        raise HTTPException(
            status_code=404,
            detail=f"Engagement {engagement_id} not found"
        )

    result = ai_controller.chat(
        engagement_id=engagement_id,
        user_message=payload.content,
    )

    return result


@router.post(
    "/engagements/{engagement_id}/chat/stream",
    tags=["chat"]
)
async def chat_stream(engagement_id: int, payload: MessageCreate):
    """
    Send a message and stream the response via SSE.

    This is the endpoint the frontend chat UI calls.
    Returns a StreamingResponse with content-type text/event-stream.

    The client receives a stream of SSE events:
      data: Hello\n\n
      data:  there\n\n
      data: , here is my analysis...\n\n
      ...
      data: __META__:{"message_id": 42, "suggestions": [...]}\n\n

    The frontend assembles content chunks into the displayed message.
    When it sees __META__: it parses the JSON and updates the
    suggestions sidebar without triggering another API call.

    Why StreamingResponse instead of WebSocket?
      WebSockets are bidirectional and require connection management.
      SSE is simpler — HTTP request in, stream out. Perfect for chat
      where the client sends one message and receives one streamed reply.
    """
    engagement = db.get_engagement(engagement_id)
    if engagement is None:
        raise HTTPException(
            status_code=404,
            detail=f"Engagement {engagement_id} not found"
        )

    def generate():
        """
        Generator that yields SSE-formatted chunks.

        SSE format requires each message to be:
          data: <content>\n\n

        The double newline is the SSE message delimiter — the client
        knows a message is complete when it sees \n\n.

        We encode each chunk from ai_controller.chat_stream() into
        this format before yielding it to StreamingResponse.
        """
        for chunk in ai_controller.chat_stream(
            engagement_id=engagement_id,
            user_message=payload.content,
        ):
            # Check if this is the metadata trailer
            if chunk.startswith("__META__:"):
                # Send as a special SSE event type
                # The frontend listens for event: meta
                yield f"event: meta\ndata: {chunk[9:]}\n\n"
            else:
                # Escape newlines within content chunks
                # SSE uses \n\n as delimiter so raw newlines break parsing
                safe_chunk = chunk.replace("\n", "\\n")
                yield f"data: {safe_chunk}\n\n"

        # Send a final done event so the frontend knows the stream ended
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            # Prevent buffering — we want chunks delivered immediately
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@router.get(
    "/engagements/{engagement_id}/messages",
    response_model=list[MessageResponse],
    tags=["chat"]
)
async def list_messages(engagement_id: int):
    """
    Return full message history for an engagement.

    The frontend calls this on load to restore the chat thread.
    Returns messages oldest-first — correct order for display.
    """
    engagement = db.get_engagement(engagement_id)
    if engagement is None:
        raise HTTPException(
            status_code=404,
            detail=f"Engagement {engagement_id} not found"
        )

    return db.list_messages(engagement_id)


@router.delete(
    "/engagements/{engagement_id}/messages",
    status_code=204,
    tags=["chat"]
)
async def clear_messages(engagement_id: int):
    """
    Delete all messages for an engagement.

    This is the Clear Chat button. Resets the LLM context window
    for a fresh start without losing artifacts, IoCs, or notes.

    Use this when:
      - The conversation has gone stale or circular
      - You want to start a new line of inquiry
      - The context window is getting large

    Does NOT delete artifacts, IoCs, timeline events, or notes.
    The system prompt context (artifacts, IoCs, notes, suggestions)
    is rebuilt fresh on the next message regardless.
    """
    engagement = db.get_engagement(engagement_id)
    if engagement is None:
        raise HTTPException(
            status_code=404,
            detail=f"Engagement {engagement_id} not found"
        )

    db.clear_messages(engagement_id)
    return None