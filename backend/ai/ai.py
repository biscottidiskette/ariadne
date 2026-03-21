"""
ai.py — LLM controller for Ariadne.

This is the only file that orchestrates LLM interactions.
Services never call groq.py directly — they call ai.py.

Responsibilities:
  1. Build the system prompt from engagement context
  2. Inject the anti-circular suggestion list (no more circles)
  3. Manage the context window — trim history to fit token limits
  4. Extract suggestions from LLM responses
  5. Route to the correct groq.py method (chat vs stream)
  6. Provide specialized prompts for playbook and sigma generation

Swap point:
  If we replace Groq with another provider, only groq.py changes.
  This file's interface stays identical — services are unaffected.
"""

import re
import json
from typing import Optional, Generator
from ai.groq import groq_client
from db.database_service import DatabaseService

# ---------------------------------------------------------------------------
# System prompt components
# Built as separate strings so they're easy to adjust individually
# without touching the assembly logic.
# ---------------------------------------------------------------------------

SYSTEM_CORE = """You are Ariadne, an expert Incident Response analyst assistant.
You are assisting a security analyst during an active IR engagement.

Your role:
- Analyze artifacts, logs, IoCs, and EDR alerts
- Suggest specific, actionable investigation steps
- Help build the timeline of the attack
- Generate detection rules and playbook steps
- Think like an experienced threat hunter

Your communication style:
- Be concise and direct — the analyst is under pressure
- Lead with the most critical finding or action
- Use specific technical detail (process names, event IDs, registry keys)
- Reference specific data from the artifacts when making suggestions
"""

SYSTEM_NO_CIRCLES = """
CRITICAL INSTRUCTION — SUGGESTION TRACKING:
The following suggestions have already been made or investigated.
DO NOT suggest these again under any circumstances.
If a path is marked 'failed' or 'worked', it is closed.
If marked 'pending' or 'in_progress', it is already being handled.

{suggestion_block}
"""

SYSTEM_NO_SUGGESTIONS_YET = """
SUGGESTION TRACKING: No suggestions have been made yet for this engagement.
As you make suggestions, they will be tracked here to prevent repetition.
"""

SYSTEM_CONTEXT_ARTIFACTS = """
INGESTED ARTIFACTS FOR THIS ENGAGEMENT:
{artifact_block}
"""

SYSTEM_CONTEXT_IOCS = """
KNOWN IoCs FOR THIS ENGAGEMENT:
{ioc_block}
"""

SYSTEM_CONTEXT_NOTES = """
ANALYST NOTES:
{notes_block}
"""

SYSTEM_SUGGESTION_INSTRUCTION = """
SUGGESTION FORMAT INSTRUCTION:
When you suggest an investigation action, prefix it with [SUGGEST] so it
can be tracked. Keep the suggestion to one line after the prefix.
Example: [SUGGEST] Check parent process of svchost.exe instances on HOST-01

You can have multiple [SUGGEST] lines in a response. Regular analysis
text does not need the prefix — only actionable next steps.
"""

# Prompt templates for specialized generation tasks
PLAYBOOK_PROMPT = """Based on all the evidence and context for this engagement,
generate a complete IR playbook following the PICERL framework.

For each step provide:
- phase: (preparation/identification/containment/eradication/recovery/lessons_learned)
- title: Short action title
- description: Specific actionable steps for THIS engagement based on the evidence

Format your response as a JSON array:
[
  {{
    "phase": "identification",
    "title": "Identify initial access vector",
    "description": "Review Event ID 4624 logon events on HOSTNAME..."
  }},
  ...
]

Generate between 8-15 steps. Be specific to the evidence — not generic IR steps.
"""

SIGMA_PROMPT = """Generate a Sigma detection rule based on the following context:

{context}

Requirements:
- Use proper Sigma YAML format
- Include title, description, status, logsource, detection, condition
- Set status to 'experimental'
- Be specific to the IoC/behavior observed
- Include falsepositives field

Return ONLY the YAML. No explanation before or after.
"""


class AIController:
    """
    Orchestrates all LLM interactions for Ariadne.

    Every method that talks to the LLM lives here.
    The database service is injected so we can load context.
    """

    def __init__(self):
        self.groq = groq_client
        self.db = DatabaseService()

    # -----------------------------------------------------------------------
    # CONTEXT BUILDERS
    # These methods assemble the system prompt from engagement data.
    # The system prompt is what gives the LLM its situational awareness.
    # -----------------------------------------------------------------------

    def _build_suggestion_block(self, engagement_id: int) -> str:
        """
        Build the anti-circular suggestion injection string.

        Queries the suggestions table for all non-dismissed suggestions
        and formats them for injection into the system prompt.

        The LLM sees this on every request and is instructed not to
        repeat anything in this list. This is the core mechanism that
        stops the circular suggestion problem.
        """
        suggestions = self.db.get_suggestions_for_prompt(engagement_id)

        if not suggestions:
            return ""

        lines = []
        for s in suggestions:
            status = s["status"].upper()
            text = s["canonical_text"]
            lines.append(f"  [{status}] {text}")

        return "\n".join(lines)

    def _build_artifact_block(self, engagement_id: int) -> str:
        """
        Build a summary of all ingested artifacts for the system prompt.

        We inject the summary field, not the raw content — raw EVTX
        files can be hundreds of thousands of lines. The parser
        generates a summary on ingest specifically for this purpose.

        Format: artifact type, filename, and summary per artifact.
        """
        artifacts = self.db.list_artifacts(engagement_id)

        if not artifacts:
            return "No artifacts ingested yet."

        lines = []
        for a in artifacts:
            filename = a.get("filename") or "pasted content"
            artifact_type = a.get("artifact_type", "unknown").upper()
            summary = a.get("summary") or "No summary available."
            lines.append(f"[{artifact_type}] {filename}\n  {summary}")

        return "\n\n".join(lines)

    def _build_ioc_block(self, engagement_id: int) -> str:
        """
        Build the IoC list for the system prompt.

        The LLM uses this to:
          - Reference known bad IPs/hashes in its analysis
          - Connect new evidence to known IoCs
          - Generate targeted Sigma rules
        """
        iocs = self.db.list_iocs(engagement_id)

        if not iocs:
            return "No IoCs identified yet."

        lines = []
        for ioc in iocs:
            ioc_type = ioc["ioc_type"].upper()
            value = ioc["value"]
            context = ioc.get("context", "")
            entry = f"  [{ioc_type}] {value}"
            if context:
                entry += f" — {context}"
            lines.append(entry)

        return "\n".join(lines)

    def _build_notes_block(self, engagement_id: int) -> str:
        """
        Build the analyst notes for the system prompt.

        Only notes with hits_context=True are included.
        These are the analyst's own observations and decisions —
        critical context the LLM needs but that doesn't fit
        a structured artifact format.
        """
        notes = self.db.list_context_notes(engagement_id)

        if not notes:
            return "No analyst notes."

        lines = []
        for note in notes:
            timestamp = note["created_at"]
            content = note["content"]
            lines.append(f"  [{timestamp}] {content}")

        return "\n".join(lines)

    def build_system_prompt(self, engagement_id: int) -> str:
        """
        Assemble the full system prompt for an engagement.

        Called before every LLM request. Loads fresh data from the
        database each time so the LLM always has current context.

        Components (in order):
          1. Core role and behavior instructions
          2. Anti-circular suggestion list
          3. Ingested artifact summaries
          4. Known IoCs
          5. Analyst notes
          6. Suggestion format instruction
        """
        parts = [SYSTEM_CORE]

        # Anti-circular suggestions
        suggestion_block = self._build_suggestion_block(engagement_id)
        if suggestion_block:
            parts.append(
                SYSTEM_NO_CIRCLES.format(suggestion_block=suggestion_block)
            )
        else:
            parts.append(SYSTEM_NO_SUGGESTIONS_YET)

        # Artifacts
        artifact_block = self._build_artifact_block(engagement_id)
        parts.append(
            SYSTEM_CONTEXT_ARTIFACTS.format(artifact_block=artifact_block)
        )

        # IoCs
        ioc_block = self._build_ioc_block(engagement_id)
        parts.append(
            SYSTEM_CONTEXT_IOCS.format(ioc_block=ioc_block)
        )

        # Analyst notes
        notes_block = self._build_notes_block(engagement_id)
        parts.append(
            SYSTEM_CONTEXT_NOTES.format(notes_block=notes_block)
        )

        # Suggestion format instruction — always last
        parts.append(SYSTEM_SUGGESTION_INSTRUCTION)

        return "\n".join(parts)

    # -----------------------------------------------------------------------
    # CONTEXT WINDOW MANAGEMENT
    # LLMs have a maximum token limit. If the conversation history grows
    # too long, the API call fails. We trim intelligently.
    # -----------------------------------------------------------------------

    def _estimate_tokens(self, text: str) -> int:
        """
        Rough token estimate: ~4 characters per token.

        This is an approximation. Exact tokenization requires the
        tokenizer library for each model. For our purposes, being
        within 10-15% is sufficient for window management.
        """
        return len(text) // 4

    def _trim_messages_to_fit(
        self,
        messages: list[dict],
        system_prompt: str,
        max_tokens: int = 4096,
        model: Optional[str] = None
    ) -> list[dict]:
        """
        Trim message history to fit within the model's context window.

        Strategy:
          1. Calculate tokens used by the system prompt
          2. Reserve max_tokens for the response
          3. Fill remaining space with messages, newest first
          4. Always keep at least the most recent user message

        We trim from the oldest messages first. This loses early
        context but preserves the most recent conversation thread
        which is most relevant to the current question.

        The system prompt is NOT trimmed — it contains the IoCs,
        suggestions, and artifacts that the LLM needs.
        """
        context_limit = self.groq.get_context_limit(model)
        reserved_for_response = max_tokens
        system_tokens = self._estimate_tokens(system_prompt)

        # Tokens available for message history
        available = context_limit - system_tokens - reserved_for_response

        if available <= 0:
            # System prompt alone is too large — keep only the last message
            return [messages[-1]] if messages else []

        # Walk messages from newest to oldest, keeping what fits
        kept = []
        tokens_used = 0

        for message in reversed(messages):
            msg_tokens = self._estimate_tokens(message["content"])
            if tokens_used + msg_tokens <= available:
                kept.insert(0, message)
                tokens_used += msg_tokens
            else:
                # Once we can't fit a message, stop
                # Always ensure the last user message is included
                break

        # Safety: always keep at least the most recent message
        if not kept and messages:
            kept = [messages[-1]]

        return kept

    # -----------------------------------------------------------------------
    # SUGGESTION EXTRACTION
    # After every LLM response, we scan for [SUGGEST] markers and
    # save them to the suggestions table automatically.
    # -----------------------------------------------------------------------

    def extract_suggestions(
        self,
        response_text: str,
        engagement_id: int,
        source_message_id: Optional[int] = None
    ) -> list[dict]:
        """
        Parse [SUGGEST] markers from an LLM response and persist them.

        The LLM is instructed to prefix actionable suggestions with
        [SUGGEST]. This method finds those, extracts the canonical
        text, and writes them to the suggestions table.

        Returns the list of created suggestion dicts.
        """
        # Regex: find [SUGGEST] followed by the rest of the line
        pattern = r'\[SUGGEST\]\s*(.+?)(?:\n|$)'
        matches = re.findall(pattern, response_text, re.IGNORECASE)

        created = []
        for match in matches:
            canonical_text = match.strip()

            # Skip if empty
            if not canonical_text:
                continue

            # Skip duplicates — check if this exact text already exists
            existing = self.db.get_suggestions_for_prompt(engagement_id)
            existing_texts = [s["canonical_text"].lower() for s in existing]

            if canonical_text.lower() in existing_texts:
                continue

            suggestion = self.db.create_suggestion(
                engagement_id=engagement_id,
                canonical_text=canonical_text,
                full_text=canonical_text,
                source_message_id=source_message_id
            )
            created.append(suggestion)

        return created

    # -----------------------------------------------------------------------
    # MAIN CHAT METHOD
    # Called by the chat route for every analyst message.
    # -----------------------------------------------------------------------

    def chat(
        self,
        engagement_id: int,
        user_message: str,
    ) -> dict:
        """
        Process a chat message and return the full response.

        Full flow:
          1. Build system prompt from engagement context
          2. Load message history from DB
          3. Trim history to fit context window
          4. Send to Groq
          5. Save user message and assistant response to DB
          6. Extract and save any [SUGGEST] markers
          7. Return response with metadata

        Returns dict with:
          content       — the assistant's response text
          message_id    — DB id of the saved assistant message
          suggestions   — list of new suggestions extracted
          tokens        — token usage dict
        """
        # 1. Build system prompt
        system_prompt = self.build_system_prompt(engagement_id)

        # 2. Save user message to DB first
        user_msg_record = self.db.create_message(
            engagement_id=engagement_id,
            role="user",
            content=user_message,
        )

        # 3. Load full history and trim to fit
        all_messages = self.db.list_messages(engagement_id)

        # Convert DB records to Groq message format
        history = [
            {"role": m["role"], "content": m["content"]}
            for m in all_messages
            # Exclude system messages — those go in system_prompt
            if m["role"] != "system"
        ]

        # 4. Trim history to fit context window
        trimmed = self._trim_messages_to_fit(
            messages=history,
            system_prompt=system_prompt,
        )

        # Prepend system prompt as the first message
        messages_for_llm = [
            {"role": "system", "content": system_prompt}
        ] + trimmed

        # 5. Send to Groq
        response = self.groq.chat(messages=messages_for_llm)

        # 6. Save assistant response to DB
        token_count = response.get("total_tokens")
        assistant_msg_record = self.db.create_message(
            engagement_id=engagement_id,
            role="assistant",
            content=response["content"],
            token_count=token_count,
        )

        # 7. Extract suggestions from the response
        new_suggestions = self.extract_suggestions(
            response_text=response["content"],
            engagement_id=engagement_id,
            source_message_id=assistant_msg_record["id"],
        )

        return {
            "content":     response["content"],
            "message_id":  assistant_msg_record["id"],
            "suggestions": new_suggestions,
            "tokens": {
                "input":  response["input_tokens"],
                "output": response["output_tokens"],
                "total":  response["total_tokens"],
            }
        }

    def chat_stream(
        self,
        engagement_id: int,
        user_message: str,
    ) -> Generator[str, None, None]:
        """
        Streaming version of chat().

        Yields text chunks as they arrive from Groq.
        The full response is assembled as it streams, then saved
        to the DB and suggestions are extracted after completion.

        Used by the SSE endpoint in routes/chat.py.

        Yields:
          str chunks of the response as they stream
          Final yield: JSON string with metadata (suggestions, message_id)
                       prefixed with "__META__:" so the frontend can
                       distinguish it from content chunks.
        """
        system_prompt = self.build_system_prompt(engagement_id)

        # Save user message
        self.db.create_message(
            engagement_id=engagement_id,
            role="user",
            content=user_message,
        )

        # Load and trim history
        all_messages = self.db.list_messages(engagement_id)
        history = [
            {"role": m["role"], "content": m["content"]}
            for m in all_messages
            if m["role"] != "system"
        ]
        trimmed = self._trim_messages_to_fit(
            messages=history,
            system_prompt=system_prompt,
        )

        messages_for_llm = [
            {"role": "system", "content": system_prompt}
        ] + trimmed

        # Stream and accumulate
        full_response = ""
        for chunk in self.groq.chat_stream(messages=messages_for_llm):
            full_response += chunk
            yield chunk

        # After streaming completes — save to DB and extract suggestions
        assistant_msg_record = self.db.create_message(
            engagement_id=engagement_id,
            role="assistant",
            content=full_response,
        )

        new_suggestions = self.extract_suggestions(
            response_text=full_response,
            engagement_id=engagement_id,
            source_message_id=assistant_msg_record["id"],
        )

        # Send metadata to frontend as final chunk
        meta = {
            "message_id":  assistant_msg_record["id"],
            "suggestions": new_suggestions,
        }
        yield f"__META__:{json.dumps(meta)}"

    # -----------------------------------------------------------------------
    # PLAYBOOK GENERATION
    # -----------------------------------------------------------------------

    def generate_playbook(self, engagement_id: int) -> list[dict]:
        """
        Generate a dynamic IR playbook for the engagement.

        Builds the full context system prompt, appends the playbook
        generation instruction, and requests structured JSON output.

        Parses the JSON response and saves each step to the DB.
        Returns the list of created playbook step dicts.
        """
        system_prompt = self.build_system_prompt(engagement_id)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": PLAYBOOK_PROMPT}
        ]

        response = self.groq.chat(
            messages=messages,
            temperature=0.2,    # Lower temp for structured output
            max_tokens=4096,
        )

        # Parse JSON from response
        try:
            # Strip any markdown code fences the LLM might add
            content = response["content"]
            content = re.sub(r'```json\s*', '', content)
            content = re.sub(r'```\s*', '', content)
            steps_data = json.loads(content.strip())
        except json.JSONDecodeError as e:
            raise ValueError(
                f"LLM returned invalid JSON for playbook: {e}\n"
                f"Raw response: {response['content'][:500]}"
            )

        # Save each step to DB
        created_steps = []
        for i, step in enumerate(steps_data):
            created = self.db.create_playbook_step(
                engagement_id=engagement_id,
                step_order=i + 1,
                phase=step.get("phase", "identification"),
                title=step.get("title", f"Step {i+1}"),
                description=step.get("description", ""),
            )
            created_steps.append(created)

        return created_steps

    # -----------------------------------------------------------------------
    # SIGMA RULE GENERATION
    # -----------------------------------------------------------------------

    def generate_sigma_rule(
        self,
        engagement_id: int,
        ioc_id: Optional[int] = None,
        context_hint: Optional[str] = None
    ) -> dict:
        """
        Generate a Sigma detection rule.

        If ioc_id is provided, targets the rule at that specific IoC.
        Otherwise uses broader engagement context.

        Returns the created sigma_rule dict from the DB.
        """
        system_prompt = self.build_system_prompt(engagement_id)

        # Build context for the Sigma prompt
        context_parts = []

        if ioc_id:
            iocs = self.db.list_iocs(engagement_id)
            target_ioc = next(
                (i for i in iocs if i["id"] == ioc_id), None
            )
            if target_ioc:
                context_parts.append(
                    f"Target IoC: [{target_ioc['ioc_type'].upper()}] "
                    f"{target_ioc['value']}"
                )
                if target_ioc.get("context"):
                    context_parts.append(
                        f"IoC context: {target_ioc['context']}"
                    )

        if context_hint:
            context_parts.append(f"Additional context: {context_hint}")

        if not context_parts:
            context_parts.append(
                "Generate a detection rule based on the engagement artifacts "
                "and IoCs provided in the system context."
            )

        sigma_context = "\n".join(context_parts)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": SIGMA_PROMPT.format(
                context=sigma_context
            )}
        ]

        response = self.groq.chat(
            messages=messages,
            temperature=0.1,    # Very low temp — Sigma rules need precision
            max_tokens=2048,
        )

        rule_yaml = response["content"].strip()

        # Extract title from YAML for the DB record
        title_match = re.search(r'^title:\s*(.+)$', rule_yaml, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else "Generated Rule"

        desc_match = re.search(
            r'^description:\s*(.+)$', rule_yaml, re.MULTILINE
        )
        description = desc_match.group(1).strip() if desc_match else None

        # Save to DB
        sigma_rule = self.db.create_sigma_rule(
            engagement_id=engagement_id,
            title=title,
            rule_yaml=rule_yaml,
            description=description,
            ioc_id=ioc_id,
        )

        return sigma_rule


# ---------------------------------------------------------------------------
# Module-level singleton — same pattern as groq.py
# Import this in routes and services:
#   from ai.ai import ai_controller
# ---------------------------------------------------------------------------
ai_controller = AIController()