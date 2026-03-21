"""
groq.py — Groq API wrapper for Ariadne.

This module has one job: talk to the Groq API.
It knows nothing about engagements, artifacts, or the database.
It only knows how to send messages and get responses back.

ai.py imports from here. Nothing else should import groq.py directly.

Why isolate Groq here?
  If we swap to OpenAI, Anthropic, or a local Ollama model later,
  we only change this file. ai.py and everything above it stays
  identical.
"""

import os
from groq import Groq
from dotenv import load_dotenv
from typing import Optional, Generator

# Load .env file so GROQ_API_KEY is available
# This is safe to call multiple times — it won't overwrite
# values already set in the environment
load_dotenv()

# ---------------------------------------------------------------------------
# Available models on Groq
# We define these as constants so there's one place to update them
# when Groq releases new models or deprecates old ones.
# ---------------------------------------------------------------------------

# Primary model — best reasoning, use for IR analysis
MODEL_PRIMARY = "llama-3.3-70b-versatile"

# Fast model — lower latency, use for quick extractions
# e.g. pulling IoCs from a blob of text
MODEL_FAST = "llama-3.1-8b-instant"

# Default to primary
DEFAULT_MODEL = MODEL_PRIMARY

# Token limits per model
# We stay under these to avoid API errors
# Groq's actual limits are higher but we reserve headroom
MODEL_CONTEXT_LIMITS = {
    MODEL_PRIMARY: 28000,
    MODEL_FAST:    14000,
}


class GroqClient:
    """
    Thin wrapper around the Groq Python SDK.

    Handles:
      - Client initialization from environment variable
      - Synchronous chat completion
      - Streaming chat completion
      - Token usage tracking
      - Error handling and retry logic
    """

    def __init__(self):
        """
        Initialize the Groq client.

        Reads GROQ_API_KEY from environment/.env file.
        Raises a clear error if the key isn't set rather than
        letting it fail silently inside the SDK.
        """
        api_key = os.getenv("GROQ_API_KEY")

        if not api_key:
            raise ValueError(
                "GROQ_API_KEY not found. "
                "Check that your .env file exists and contains: "
                "GROQ_API_KEY=your_key_here"
            )

        self.client = Groq(api_key=api_key)
        self.default_model = DEFAULT_MODEL
        print(f"[groq] Client initialized. Default model: {self.default_model}")

    def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> dict:
        """
        Send a list of messages and return the full response.

        This is the non-streaming version. The entire response is
        generated before returning. Use this for:
          - Artifact parsing / extraction tasks
          - Playbook generation
          - Sigma rule generation
          - Any task where you need the complete response at once

        Args:
            messages:    List of dicts with 'role' and 'content' keys.
                         e.g. [{"role": "user", "content": "Analyze this"}]
                         This is the standard OpenAI/Groq message format.

            model:       Which Groq model to use. Defaults to primary.

            temperature: Controls randomness. 0.0 = deterministic,
                         1.0 = creative. For IR analysis we want low
                         temperature — consistent, factual responses.
                         0.3 is a good default.

            max_tokens:  Maximum tokens in the response. 4096 is enough
                         for most responses. Increase for long playbooks.

        Returns:
            dict with keys:
              content      — the response text
              model        — which model was used
              input_tokens — tokens consumed by the prompt
              output_tokens — tokens in the response
              total_tokens  — sum of above
        """
        model = model or self.default_model

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            # Extract the response content
            content = response.choices[0].message.content

            # Extract token usage for tracking
            usage = response.usage

            return {
                "content":       content,
                "model":         model,
                "input_tokens":  usage.prompt_tokens,
                "output_tokens": usage.completion_tokens,
                "total_tokens":  usage.total_tokens,
            }

        except Exception as e:
            # Re-raise with context so ai.py can handle it appropriately
            raise RuntimeError(f"[groq] Chat completion failed: {e}") from e

    def chat_stream(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> Generator[str, None, None]:
        """
        Send messages and stream the response token by token.

        Use this for the chat interface so the analyst sees the
        response appearing in real time rather than waiting for
        the full response.

        This is a generator function — it yields text chunks as
        they arrive from the Groq API.

        Usage in ai.py:
            for chunk in groq_client.chat_stream(messages):
                yield chunk   # forward to SSE stream

        Args:
            Same as chat() above.

        Yields:
            str — text chunks as they stream from the API.
                  Each chunk is a small piece of the response.
                  The caller assembles them into the full response.
        """
        model = model or self.default_model

        try:
            stream = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,   # This enables streaming
            )

            # Iterate over stream chunks as they arrive
            for chunk in stream:
                # Each chunk has choices[0].delta.content
                # delta.content can be None for the final chunk
                delta = chunk.choices[0].delta
                if delta.content is not None:
                    yield delta.content

        except Exception as e:
            raise RuntimeError(f"[groq] Streaming failed: {e}") from e

    def get_context_limit(self, model: Optional[str] = None) -> int:
        """
        Return the token context limit for the given model.
        Used by ai.py when trimming message history to fit the window.
        """
        model = model or self.default_model
        return MODEL_CONTEXT_LIMITS.get(model, 14000)

    def health_check(self) -> dict:
        """
        Verify the Groq connection is working.
        Called by the /health endpoint in main.py.

        Sends a minimal message to confirm the API key is valid
        and the service is reachable.
        """
        try:
            response = self.chat(
                messages=[{
                    "role": "user",
                    "content": "Reply with only the word: online"
                }],
                max_tokens=10,
                temperature=0.0,
            )
            return {
                "status":  "connected",
                "model":   response["model"],
                "response": response["content"].strip(),
            }
        except Exception as e:
            return {
                "status":  "error",
                "message": str(e),
            }


# ---------------------------------------------------------------------------
# Module-level singleton
# We create one instance and import it everywhere that needs it.
# This avoids re-reading the .env file and re-initializing the SDK
# on every request.
#
# Usage in ai.py:
#   from ai.groq import groq_client
# ---------------------------------------------------------------------------
groq_client = GroqClient()