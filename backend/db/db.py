"""
db.py — SQLite connection manager and schema definition for Ariadne.

This module has two responsibilities and two only:
  1. Provide a get_connection() function that returns a configured
     SQLite connection to the rest of the application.
  2. Define and initialize the full database schema via init_db().

Nothing else belongs here. No business logic. No queries. No services.
Those live in database_service.py which imports from here.

Why raw SQLite and not an ORM?
  SQLAlchemy and Tortoise-ORM are powerful but they hide what's
  actually happening. For a security tool where you need to reason
  clearly about your data, explicit SQL is easier to audit and debug.
  We can add an ORM layer later if the project grows.
"""

import sqlite3
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------
# __file__ is the absolute path to this db.py file.
# .parent gives us the db/ directory.
# .parent again gives us backend/.
# We store the .db file in backend/ so it stays out of the source tree
# but close to the code that uses it.

BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "ariadne.db"


def get_connection() -> sqlite3.Connection:
    """
    Open and return a configured SQLite connection.

    Called by database_service.py every time it needs to talk to the DB.
    We configure three things on every connection:

    - row_factory: Makes rows behave like dictionaries (row["column_name"])
      instead of tuples (row[0]). Much easier to work with in services
      and when serializing to JSON for the API.

    - WAL mode (Write-Ahead Logging): SQLite's default journal mode locks
      the entire database for writes, blocking all reads. WAL mode allows
      concurrent reads while a write is happening. This matters because
      FastAPI is async — multiple requests can be in flight at once.

    - Foreign keys: SQLite does NOT enforce foreign key constraints by
      default. You must explicitly enable them per connection. Without
      this, you could delete an engagement and leave orphaned artifacts
      in the database with no parent. We don't want that.
    """
    conn = sqlite3.connect(DB_PATH)

    # Rows as dicts
    conn.row_factory = sqlite3.Row

    # Enable WAL mode for concurrent read access
    conn.execute("PRAGMA journal_mode=WAL;")

    # Enforce foreign key constraints
    conn.execute("PRAGMA foreign_keys=ON;")

    return conn


def init_db() -> None:
    """
    Create all tables if they do not already exist.

    Uses IF NOT EXISTS on every table so this function is safe to call
    repeatedly — on every application startup, for example. It will
    never destroy existing data.

    Table creation order matters here because of foreign keys.
    A table cannot reference another table that doesn't exist yet.
    Order: engagements → artifacts → iocs → messages → suggestions
           → timeline_events → playbook_steps → sigma_rules → notes
    """
    conn = get_connection()

    try:
        cursor = conn.cursor()

        # -------------------------------------------------------------------
        # ENGAGEMENTS
        # The top-level container for everything. Every artifact, message,
        # IoC, timeline event, and playbook belongs to an engagement.
        #
        # lead_id: Stubbed as TEXT for now. Post-MVP this becomes a foreign
        #          key to a users table when we add authentication.
        #
        # status: One of: active | contained | closed | archived
        #         Drives the color coding on the frontend dashboard.
        # -------------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS engagements (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                description TEXT,
                status      TEXT    NOT NULL DEFAULT 'active',
                lead_id     TEXT,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            );
        """)

        # -------------------------------------------------------------------
        # ARTIFACTS
        # Any piece of evidence ingested into an engagement.
        # Covers both file uploads and direct pastes.
        #
        # artifact_type: evtx | chainsaw | ioc | edr | siem | sigma |
        #                prefetch | registry | memory | scheduled_task |
        #                paste | other
        #
        # raw_content:    The original text/content exactly as received.
        # parsed_content: JSON string. The normalized form after parsing.
        #                 This is what gets injected into LLM context.
        #                 We store both so you can always re-parse if the
        #                 parser improves.
        #
        # filename:       Original filename if uploaded, NULL if pasted.
        # -------------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS artifacts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                engagement_id   INTEGER NOT NULL,
                artifact_type   TEXT    NOT NULL,
                filename        TEXT,
                raw_content     TEXT,
                parsed_content  TEXT,
                summary         TEXT,
                created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (engagement_id)
                    REFERENCES engagements(id)
                    ON DELETE CASCADE
            );
        """)

        # -------------------------------------------------------------------
        # IOCS (Indicators of Compromise)
        # Extracted from artifacts or added manually.
        #
        # ioc_type: ip | domain | hash_md5 | hash_sha1 | hash_sha256 |
        #           file_path | registry_key | email | url | mutex | other
        #
        # value:    The actual IoC string. e.g. "192.168.1.1" or
        #           "4d5e6f..." (a hash)
        #
        # source_artifact_id: Which artifact this IoC was extracted from.
        #                     NULL if manually added.
        #
        # first_seen / last_seen: Timestamps from the evidence, not from
        #                         when it was added to Ariadne. These drive
        #                         the timeline.
        # -------------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS iocs (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                engagement_id       INTEGER NOT NULL,
                source_artifact_id  INTEGER,
                ioc_type            TEXT    NOT NULL,
                value               TEXT    NOT NULL,
                context             TEXT,
                first_seen          TEXT,
                last_seen           TEXT,
                created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (engagement_id)
                    REFERENCES engagements(id)
                    ON DELETE CASCADE,
                FOREIGN KEY (source_artifact_id)
                    REFERENCES artifacts(id)
                    ON DELETE SET NULL
            );
        """)

        # -------------------------------------------------------------------
        # MESSAGES
        # Full chat history per engagement.
        #
        # role: 'user' | 'assistant' | 'system'
        #       Mirrors the OpenAI/Groq message format so we can pass
        #       history directly to the LLM without transformation.
        #
        # token_count: Approximate tokens for this message. Used by the
        #              context window manager in ai.py to trim history
        #              when we approach the model's context limit.
        # -------------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                engagement_id   INTEGER NOT NULL,
                role            TEXT    NOT NULL,
                content         TEXT    NOT NULL,
                token_count     INTEGER,
                created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (engagement_id)
                    REFERENCES engagements(id)
                    ON DELETE CASCADE
            );
        """)

        # -------------------------------------------------------------------
        # SUGGESTIONS
        # Every actionable suggestion the LLM makes gets recorded here.
        # This is the anti-circular engine.
        #
        # How it works:
        #   1. LLM responds with suggestions embedded in its answer.
        #   2. ai.py extracts them and writes a row here per suggestion.
        #   3. Before every subsequent LLM call, chat_service.py queries
        #      this table and injects the results into the system prompt:
        #      "DO NOT suggest: [list of canonical_text values]"
        #   4. The analyst marks suggestions as they work through them.
        #
        # status: pending | in_progress | tried | worked | failed | dismissed
        #
        # canonical_text: Short normalized form of the suggestion used for
        #                 deduplication and LLM injection. e.g.
        #                 "Check lateral movement from 10.1.1.5 via 4624"
        #
        # source_message_id: Which assistant message this came from.
        #                    Lets you trace a suggestion back to its context.
        # -------------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS suggestions (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                engagement_id       INTEGER NOT NULL,
                source_message_id   INTEGER,
                canonical_text      TEXT    NOT NULL,
                full_text           TEXT,
                status              TEXT    NOT NULL DEFAULT 'pending',
                created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
                updated_at          TEXT    NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (engagement_id)
                    REFERENCES engagements(id)
                    ON DELETE CASCADE,
                FOREIGN KEY (source_message_id)
                    REFERENCES messages(id)
                    ON DELETE SET NULL
            );
        """)

        # -------------------------------------------------------------------
        # TIMELINE EVENTS
        # The chronological spine of the investigation.
        #
        # event_time: The actual time the event occurred in the environment.
        #             NOT when it was added to Ariadne. This is what we
        #             sort and display on the timeline.
        #
        # event_type: process_creation | network_connection | file_write |
        #             registry_modification | logon | service_install |
        #             scheduled_task | lateral_movement | persistence |
        #             exfiltration | manual | other
        #
        # host:       The machine this event occurred on.
        # actor:      The user or process that triggered the event.
        #
        # source_artifact_id: Auto-populated when extracted from an artifact.
        #                     NULL for manually added events.
        # -------------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS timeline_events (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                engagement_id       INTEGER NOT NULL,
                source_artifact_id  INTEGER,
                event_time          TEXT    NOT NULL,
                event_type          TEXT    NOT NULL,
                description         TEXT    NOT NULL,
                host                TEXT,
                actor               TEXT,
                process             TEXT,
                ioc_id              INTEGER,
                created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (engagement_id)
                    REFERENCES engagements(id)
                    ON DELETE CASCADE,
                FOREIGN KEY (source_artifact_id)
                    REFERENCES artifacts(id)
                    ON DELETE SET NULL,
                FOREIGN KEY (ioc_id)
                    REFERENCES iocs(id)
                    ON DELETE SET NULL
            );
        """)

        # -------------------------------------------------------------------
        # PLAYBOOK STEPS
        # LLM-generated IR playbook steps, specific to the engagement.
        #
        # Each engagement can have one active playbook — a set of steps
        # generated by the LLM based on the accumulated artifact context.
        # The playbook can be regenerated as new artifacts are added.
        #
        # step_order:  Integer sequence for display ordering.
        # phase:       PICERL phase this step belongs to:
        #              preparation | identification | containment |
        #              eradication | recovery | lessons_learned
        # status:      pending | in_progress | complete | skipped
        # -------------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS playbook_steps (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                engagement_id   INTEGER NOT NULL,
                step_order      INTEGER NOT NULL,
                phase           TEXT    NOT NULL,
                title           TEXT    NOT NULL,
                description     TEXT    NOT NULL,
                status          TEXT    NOT NULL DEFAULT 'pending',
                notes           TEXT,
                created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
                updated_at      TEXT    NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (engagement_id)
                    REFERENCES engagements(id)
                    ON DELETE CASCADE
            );
        """)

        # -------------------------------------------------------------------
        # SIGMA RULES
        # LLM-drafted detection rules in portable Sigma format.
        # Sigma converts to Splunk SPL, Elastic EQL, QRadar, etc.
        #
        # rule_yaml:   The full Sigma rule in YAML format.
        # ioc_id:      The IoC this rule was generated to detect.
        #              NULL if generated from broader context.
        # is_validated: Whether the YAML structure has been checked.
        #               Full logic testing is post-MVP.
        # -------------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sigma_rules (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                engagement_id   INTEGER NOT NULL,
                ioc_id          INTEGER,
                title           TEXT    NOT NULL,
                description     TEXT,
                rule_yaml       TEXT    NOT NULL,
                is_validated    INTEGER NOT NULL DEFAULT 0,
                created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
                updated_at      TEXT    NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (engagement_id)
                    REFERENCES engagements(id)
                    ON DELETE CASCADE,
                FOREIGN KEY (ioc_id)
                    REFERENCES iocs(id)
                    ON DELETE SET NULL
            );
        """)

        # -------------------------------------------------------------------
        # NOTES
        # Timestamped freeform analyst notes per engagement.
        # Append-only by convention — we never update or delete notes.
        #
        # These are different from chat messages. Notes are things the
        # analyst wants to record that don't fit a parser: observations,
        # gut feelings, phone call summaries, escalation decisions.
        #
        # hits_context: Boolean. If 1, this note gets injected into the
        #               LLM system prompt so the model has full awareness.
        #               Analyst controls this per note.
        # -------------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                engagement_id   INTEGER NOT NULL,
                content         TEXT    NOT NULL,
                hits_context    INTEGER NOT NULL DEFAULT 1,
                created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (engagement_id)
                    REFERENCES engagements(id)
                    ON DELETE CASCADE
            );
        """)

        conn.commit()
        print(f"[db] Database initialized at {DB_PATH}")

    except sqlite3.Error as e:
        # Roll back any partial schema creation on error
        conn.rollback()
        print(f"[db] Schema initialization failed: {e}")
        raise

    finally:
        # Always close the connection whether we succeeded or failed
        conn.close()


# ---------------------------------------------------------------------------
# Allow running this file directly to initialize the database
# python3 db.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    init_db()