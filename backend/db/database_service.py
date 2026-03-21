"""
database_service.py — Database abstraction controller for Ariadne.

This is the ONLY file the rest of the application imports from when
it needs to talk to the database. Services, routes, and ai.py never
import from db.py directly.

Why this abstraction layer?
  Right now we use SQLite. Post-MVP we may move to PostgreSQL as the
  team grows or as load increases. When that happens, we swap the
  implementation inside this file — the rest of the application
  doesn't change at all because the interface stays identical.

  This is the Repository pattern. The application talks to an
  interface, not to a specific database driver.

Current backend: SQLite via db.py
Swap point:      Replace get_db() internals and each method below
                 with a PostgreSQL implementation (asyncpg, psycopg2,
                 or SQLAlchemy) without touching a single service file.

Usage:
    from db.database_service import DatabaseService

    db = DatabaseService()
    engagement = db.get_engagement(1)
"""

import sqlite3
from typing import Optional
from db.db import get_connection, init_db


class DatabaseService:
    """
    Abstraction layer over the raw SQLite connection.

    Each method maps to a specific database operation. Methods are
    grouped by domain: engagements, artifacts, messages, suggestions,
    iocs, timeline, playbook, sigma, notes.

    Every method follows the same pattern:
      1. Get a connection
      2. Execute the query
      3. Commit if writing, fetch if reading
      4. Close the connection in finally block
      5. Return Python dicts (not sqlite3.Row objects)

    Why close the connection every time instead of keeping one open?
      SQLite with WAL mode handles this fine for a single-user tool.
      A persistent connection would need thread-safety handling because
      FastAPI runs async. Keeping connections short-lived is simpler
      and safer for now.
    """

    def __init__(self):
        """
        Initialize the database, creating tables if they don't exist.
        Safe to call multiple times — uses IF NOT EXISTS on all tables.
        """
        init_db()

    # -----------------------------------------------------------------------
    # HELPER
    # -----------------------------------------------------------------------

    def _row_to_dict(self, row: sqlite3.Row) -> Optional[dict]:
        """
        Convert a sqlite3.Row to a plain Python dict.

        sqlite3.Row objects behave like dicts but are not dicts.
        Pydantic models, JSON serialization, and general Python code
        all work more predictably with plain dicts.

        Returns None if row is None, so callers can do:
            result = db.get_engagement(999)
            if result is None:
                raise HTTPException(404)
        """
        if row is None:
            return None
        return dict(row)

    def _rows_to_list(self, rows: list) -> list[dict]:
        """
        Convert a list of sqlite3.Row objects to a list of plain dicts.
        Returns empty list if rows is None or empty.
        """
        if not rows:
            return []
        return [dict(row) for row in rows]

    # -----------------------------------------------------------------------
    # ENGAGEMENTS
    # -----------------------------------------------------------------------

    def create_engagement(
        self,
        name: str,
        description: Optional[str] = None,
        status: str = "active",
        lead_id: Optional[str] = None
    ) -> dict:
        """
        Create a new engagement (case) and return it as a dict.

        The database sets created_at and updated_at automatically
        via DEFAULT (datetime('now')) in the schema.
        """
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO engagements (name, description, status, lead_id)
                VALUES (?, ?, ?, ?)
            """, (name, description, status, lead_id))
            conn.commit()

            # Fetch and return the newly created row
            # cursor.lastrowid gives us the auto-incremented ID
            row = cursor.execute(
                "SELECT * FROM engagements WHERE id = ?",
                (cursor.lastrowid,)
            ).fetchone()
            return self._row_to_dict(row)

        finally:
            conn.close()

    def get_engagement(self, engagement_id: int) -> Optional[dict]:
        """
        Fetch a single engagement by ID.
        Returns None if not found — caller handles the 404.
        """
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM engagements WHERE id = ?",
                (engagement_id,)
            ).fetchone()
            return self._row_to_dict(row)
        finally:
            conn.close()

    def list_engagements(self) -> list[dict]:
        """
        Return all engagements ordered by most recently updated.
        This drives the landing page engagement list.
        """
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM engagements ORDER BY updated_at DESC"
            ).fetchall()
            return self._rows_to_list(rows)
        finally:
            conn.close()

    def update_engagement(
        self,
        engagement_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        lead_id: Optional[str] = None
    ) -> Optional[dict]:
        """
        Partial update — only updates fields that are provided.

        We build the SET clause dynamically so callers can update just
        the status without having to send the full engagement object.
        This is the PATCH pattern (partial update) vs PUT (full replace).

        updated_at is always refreshed on any update.
        """
        conn = get_connection()
        try:
            # Build only the fields that were actually passed in
            fields = []
            values = []

            if name is not None:
                fields.append("name = ?")
                values.append(name)
            if description is not None:
                fields.append("description = ?")
                values.append(description)
            if status is not None:
                fields.append("status = ?")
                values.append(status)
            if lead_id is not None:
                fields.append("lead_id = ?")
                values.append(lead_id)

            if not fields:
                # Nothing to update — return the existing record
                return self.get_engagement(engagement_id)

            # Always update the timestamp
            fields.append("updated_at = datetime('now')")
            values.append(engagement_id)

            conn.execute(
                f"UPDATE engagements SET {', '.join(fields)} WHERE id = ?",
                values
            )
            conn.commit()
            return self.get_engagement(engagement_id)

        finally:
            conn.close()

    def delete_engagement(self, engagement_id: int) -> bool:
        """
        Delete an engagement and all its related data.

        Because we defined ON DELETE CASCADE on all child tables,
        deleting an engagement automatically deletes all its:
        artifacts, iocs, messages, suggestions, timeline_events,
        playbook_steps, sigma_rules, and notes.

        Returns True if a row was deleted, False if ID didn't exist.
        """
        conn = get_connection()
        try:
            cursor = conn.execute(
                "DELETE FROM engagements WHERE id = ?",
                (engagement_id,)
            )
            conn.commit()
            # rowcount tells us how many rows were affected
            return cursor.rowcount > 0
        finally:
            conn.close()

    # -----------------------------------------------------------------------
    # ARTIFACTS
    # -----------------------------------------------------------------------

    def create_artifact(
        self,
        engagement_id: int,
        artifact_type: str,
        raw_content: Optional[str] = None,
        parsed_content: Optional[str] = None,
        summary: Optional[str] = None,
        filename: Optional[str] = None
    ) -> dict:
        """
        Store an ingested artifact.

        raw_content:    Original text as received.
        parsed_content: JSON string from the appropriate parser.
        summary:        Short LLM-generated summary for context injection.
        filename:       Original filename if uploaded, None if pasted.
        """
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO artifacts
                    (engagement_id, artifact_type, filename,
                     raw_content, parsed_content, summary)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (engagement_id, artifact_type, filename,
                  raw_content, parsed_content, summary))
            conn.commit()

            row = cursor.execute(
                "SELECT * FROM artifacts WHERE id = ?",
                (cursor.lastrowid,)
            ).fetchone()
            return self._row_to_dict(row)
        finally:
            conn.close()

    def list_artifacts(self, engagement_id: int) -> list[dict]:
        """Return all artifacts for an engagement, newest first."""
        conn = get_connection()
        try:
            rows = conn.execute("""
                SELECT * FROM artifacts
                WHERE engagement_id = ?
                ORDER BY created_at DESC
            """, (engagement_id,)).fetchall()
            return self._rows_to_list(rows)
        finally:
            conn.close()

    def get_artifact(self, artifact_id: int) -> Optional[dict]:
        """Fetch a single artifact by ID."""
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM artifacts WHERE id = ?",
                (artifact_id,)
            ).fetchone()
            return self._row_to_dict(row)
        finally:
            conn.close()

    # -----------------------------------------------------------------------
    # MESSAGES
    # -----------------------------------------------------------------------

    def create_message(
        self,
        engagement_id: int,
        role: str,
        content: str,
        token_count: Optional[int] = None
    ) -> dict:
        """
        Persist a chat message.

        role must be 'user', 'assistant', or 'system'.
        Called after every LLM exchange — both the user message
        and the assistant response get stored.
        """
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO messages
                    (engagement_id, role, content, token_count)
                VALUES (?, ?, ?, ?)
            """, (engagement_id, role, content, token_count))
            conn.commit()

            row = cursor.execute(
                "SELECT * FROM messages WHERE id = ?",
                (cursor.lastrowid,)
            ).fetchone()
            return self._row_to_dict(row)
        finally:
            conn.close()

    def list_messages(self, engagement_id: int) -> list[dict]:
        """
        Return full message history for an engagement, oldest first.

        Oldest first is critical — this is the order the LLM expects
        when we reconstruct the conversation for context.
        """
        conn = get_connection()
        try:
            rows = conn.execute("""
                SELECT * FROM messages
                WHERE engagement_id = ?
                ORDER BY created_at ASC
            """, (engagement_id,)).fetchall()
            return self._rows_to_list(rows)
        finally:
            conn.close()

    def clear_messages(self, engagement_id: int) -> bool:
        """
        Delete all messages for an engagement.
        This is the 'Clear Chat' button — resets context for a fresh start.
        Does NOT delete artifacts, IoCs, or other data. Chat only.
        """
        conn = get_connection()
        try:
            conn.execute(
                "DELETE FROM messages WHERE engagement_id = ?",
                (engagement_id,)
            )
            conn.commit()
            return True
        finally:
            conn.close()

    # -----------------------------------------------------------------------
    # SUGGESTIONS
    # -----------------------------------------------------------------------

    def create_suggestion(
        self,
        engagement_id: int,
        canonical_text: str,
        full_text: Optional[str] = None,
        source_message_id: Optional[int] = None
    ) -> dict:
        """
        Record a new suggestion from the LLM.
        Status defaults to 'pending'.
        """
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO suggestions
                    (engagement_id, canonical_text, full_text,
                     source_message_id)
                VALUES (?, ?, ?, ?)
            """, (engagement_id, canonical_text, full_text,
                  source_message_id))
            conn.commit()

            row = cursor.execute(
                "SELECT * FROM suggestions WHERE id = ?",
                (cursor.lastrowid,)
            ).fetchone()
            return self._row_to_dict(row)
        finally:
            conn.close()

    def list_suggestions(self, engagement_id: int) -> list[dict]:
        """Return all suggestions for an engagement, newest first."""
        conn = get_connection()
        try:
            rows = conn.execute("""
                SELECT * FROM suggestions
                WHERE engagement_id = ?
                ORDER BY created_at DESC
            """, (engagement_id,)).fetchall()
            return self._rows_to_list(rows)
        finally:
            conn.close()

    def get_suggestions_for_prompt(self, engagement_id: int) -> list[dict]:
        """
        Return only the suggestions the LLM needs to know about.

        This is injected into the system prompt to prevent circular
        suggestions. We exclude 'dismissed' because the analyst has
        explicitly said they don't want to pursue it — no need to
        tell the LLM about it either.

        We include everything else so the LLM knows:
          - What's been tried (tried/worked/failed)
          - What's in flight (pending/in_progress)
        """
        conn = get_connection()
        try:
            rows = conn.execute("""
                SELECT canonical_text, status
                FROM suggestions
                WHERE engagement_id = ?
                AND status != 'dismissed'
                ORDER BY created_at ASC
            """, (engagement_id,)).fetchall()
            return self._rows_to_list(rows)
        finally:
            conn.close()

    def update_suggestion_status(
        self,
        suggestion_id: int,
        status: str
    ) -> Optional[dict]:
        """
        Update a suggestion's status.
        Valid values: pending | in_progress | tried | worked |
                      failed | dismissed
        """
        conn = get_connection()
        try:
            conn.execute("""
                UPDATE suggestions
                SET status = ?, updated_at = datetime('now')
                WHERE id = ?
            """, (status, suggestion_id))
            conn.commit()

            row = conn.execute(
                "SELECT * FROM suggestions WHERE id = ?",
                (suggestion_id,)
            ).fetchone()
            return self._row_to_dict(row)
        finally:
            conn.close()

    # -----------------------------------------------------------------------
    # IoCs
    # -----------------------------------------------------------------------

    def create_ioc(
        self,
        engagement_id: int,
        ioc_type: str,
        value: str,
        context: Optional[str] = None,
        source_artifact_id: Optional[int] = None,
        first_seen: Optional[str] = None,
        last_seen: Optional[str] = None
    ) -> dict:
        """Store an extracted or manually added IoC."""
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO iocs
                    (engagement_id, ioc_type, value, context,
                     source_artifact_id, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (engagement_id, ioc_type, value, context,
                  source_artifact_id, first_seen, last_seen))
            conn.commit()

            row = cursor.execute(
                "SELECT * FROM iocs WHERE id = ?",
                (cursor.lastrowid,)
            ).fetchone()
            return self._row_to_dict(row)
        finally:
            conn.close()

    def list_iocs(self, engagement_id: int) -> list[dict]:
        """Return all IoCs for an engagement."""
        conn = get_connection()
        try:
            rows = conn.execute("""
                SELECT * FROM iocs
                WHERE engagement_id = ?
                ORDER BY created_at DESC
            """, (engagement_id,)).fetchall()
            return self._rows_to_list(rows)
        finally:
            conn.close()

    # -----------------------------------------------------------------------
    # TIMELINE
    # -----------------------------------------------------------------------

    def create_timeline_event(
        self,
        engagement_id: int,
        event_time: str,
        event_type: str,
        description: str,
        host: Optional[str] = None,
        actor: Optional[str] = None,
        process: Optional[str] = None,
        ioc_id: Optional[int] = None,
        source_artifact_id: Optional[int] = None
    ) -> dict:
        """Add an event to the engagement timeline."""
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO timeline_events
                    (engagement_id, event_time, event_type, description,
                     host, actor, process, ioc_id, source_artifact_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (engagement_id, event_time, event_type, description,
                  host, actor, process, ioc_id, source_artifact_id))
            conn.commit()

            row = cursor.execute(
                "SELECT * FROM timeline_events WHERE id = ?",
                (cursor.lastrowid,)
            ).fetchone()
            return self._row_to_dict(row)
        finally:
            conn.close()

    def list_timeline_events(self, engagement_id: int) -> list[dict]:
        """
        Return all timeline events ordered by event_time ascending.
        event_time is when it happened in the environment — not when
        it was added to Ariadne. This gives us the true attack timeline.
        """
        conn = get_connection()
        try:
            rows = conn.execute("""
                SELECT * FROM timeline_events
                WHERE engagement_id = ?
                ORDER BY event_time ASC
            """, (engagement_id,)).fetchall()
            return self._rows_to_list(rows)
        finally:
            conn.close()

    # -----------------------------------------------------------------------
    # PLAYBOOK
    # -----------------------------------------------------------------------

    def create_playbook_step(
        self,
        engagement_id: int,
        step_order: int,
        phase: str,
        title: str,
        description: str
    ) -> dict:
        """Add a single generated playbook step."""
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO playbook_steps
                    (engagement_id, step_order, phase, title, description)
                VALUES (?, ?, ?, ?, ?)
            """, (engagement_id, step_order, phase, title, description))
            conn.commit()

            row = cursor.execute(
                "SELECT * FROM playbook_steps WHERE id = ?",
                (cursor.lastrowid,)
            ).fetchone()
            return self._row_to_dict(row)
        finally:
            conn.close()

    def list_playbook_steps(self, engagement_id: int) -> list[dict]:
        """Return playbook steps in order."""
        conn = get_connection()
        try:
            rows = conn.execute("""
                SELECT * FROM playbook_steps
                WHERE engagement_id = ?
                ORDER BY step_order ASC
            """, (engagement_id,)).fetchall()
            return self._rows_to_list(rows)
        finally:
            conn.close()

    def update_playbook_step_status(
        self,
        step_id: int,
        status: str,
        notes: Optional[str] = None
    ) -> Optional[dict]:
        """
        Update a playbook step's completion status.
        Valid: pending | in_progress | complete | skipped
        """
        conn = get_connection()
        try:
            conn.execute("""
                UPDATE playbook_steps
                SET status = ?,
                    notes = COALESCE(?, notes),
                    updated_at = datetime('now')
                WHERE id = ?
            """, (status, notes, step_id))
            conn.commit()

            row = conn.execute(
                "SELECT * FROM playbook_steps WHERE id = ?",
                (step_id,)
            ).fetchone()
            return self._row_to_dict(row)
        finally:
            conn.close()

    def clear_playbook(self, engagement_id: int) -> bool:
        """
        Delete all playbook steps for an engagement.
        Called before regenerating the playbook with updated context.
        """
        conn = get_connection()
        try:
            conn.execute(
                "DELETE FROM playbook_steps WHERE engagement_id = ?",
                (engagement_id,)
            )
            conn.commit()
            return True
        finally:
            conn.close()

    # -----------------------------------------------------------------------
    # SIGMA RULES
    # -----------------------------------------------------------------------

    def create_sigma_rule(
        self,
        engagement_id: int,
        title: str,
        rule_yaml: str,
        description: Optional[str] = None,
        ioc_id: Optional[int] = None
    ) -> dict:
        """Store a generated Sigma rule."""
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sigma_rules
                    (engagement_id, title, rule_yaml,
                     description, ioc_id)
                VALUES (?, ?, ?, ?, ?)
            """, (engagement_id, title, rule_yaml, description, ioc_id))
            conn.commit()

            row = cursor.execute(
                "SELECT * FROM sigma_rules WHERE id = ?",
                (cursor.lastrowid,)
            ).fetchone()
            return self._row_to_dict(row)
        finally:
            conn.close()

    def list_sigma_rules(self, engagement_id: int) -> list[dict]:
        """Return all Sigma rules for an engagement."""
        conn = get_connection()
        try:
            rows = conn.execute("""
                SELECT * FROM sigma_rules
                WHERE engagement_id = ?
                ORDER BY created_at DESC
            """, (engagement_id,)).fetchall()
            return self._rows_to_list(rows)
        finally:
            conn.close()

    # -----------------------------------------------------------------------
    # NOTES
    # -----------------------------------------------------------------------

    def create_note(
        self,
        engagement_id: int,
        content: str,
        hits_context: bool = True
    ) -> dict:
        """
        Append a timestamped note to an engagement.
        hits_context=True means it will be injected into LLM prompts.
        """
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO notes
                    (engagement_id, content, hits_context)
                VALUES (?, ?, ?)
            """, (engagement_id, content, int(hits_context)))
            conn.commit()

            row = cursor.execute(
                "SELECT * FROM notes WHERE id = ?",
                (cursor.lastrowid,)
            ).fetchone()
            return self._row_to_dict(row)
        finally:
            conn.close()

    def list_notes(self, engagement_id: int) -> list[dict]:
        """Return all notes oldest first — append-only log convention."""
        conn = get_connection()
        try:
            rows = conn.execute("""
                SELECT * FROM notes
                WHERE engagement_id = ?
                ORDER BY created_at ASC
            """, (engagement_id,)).fetchall()
            return self._rows_to_list(rows)
        finally:
            conn.close()

    def list_context_notes(self, engagement_id: int) -> list[dict]:
        """
        Return only notes flagged for LLM context injection.
        Called by chat_service.py when building the system prompt.
        """
        conn = get_connection()
        try:
            rows = conn.execute("""
                SELECT * FROM notes
                WHERE engagement_id = ?
                AND hits_context = 1
                ORDER BY created_at ASC
            """, (engagement_id,)).fetchall()
            return self._rows_to_list(rows)
        finally:
            conn.close()