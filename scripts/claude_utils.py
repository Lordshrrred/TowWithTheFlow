"""Shared helpers for calling the Claude API from the syndication/generation scripts.

Centralizes the retry/backoff policy so every call site behaves the same way
under rate limits or transient API errors, and logs when it's retrying so a
runaway loop is visible instead of silently burning API spend.
"""

from __future__ import annotations

import time
import json

import anthropic

MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 2


def prepare_message(kwargs):
    kwargs = dict(kwargs)
    model = kwargs.get("model", "")
    if model in {"claude-haiku-5-5", "claude-sonnet-5-5"}:
        for name in ("temperature", "top_p", "top_k"):
            kwargs.pop(name, None)
        extra = dict(kwargs.get("extra_body") or {})
        tools = bool(kwargs.get("tools"))
        extra.setdefault("thinking", {"type": "adaptive" if tools else "between_tools" if "sonnet" in model else "disabled"})
        extra.setdefault("output_config", {"effort": "low" if tools else "medium"})
        kwargs["extra_body"] = extra
    return kwargs


def message_text(message):
    if getattr(message, "stop_reason", None) in {"max_tokens", "refusal", "model_context_window_exceeded"}:
        raise ValueError("Incomplete Claude response: " + message.stop_reason)
    return "\n".join(block.text for block in message.content if getattr(block, "type", "text") == "text").strip()


def make_client(api_key: str) -> anthropic.Anthropic:
    """Anthropic client with the SDK's built-in retry/backoff capped at 3 attempts."""
    return anthropic.Anthropic(api_key=api_key, max_retries=MAX_RETRIES)


def create_message(client: anthropic.Anthropic, *, log=print, **kwargs):
    """client.messages.create with logging around transient failures.

    The SDK already retries 429/5xx/connection errors internally (max_retries
    set via make_client). This wrapper just makes final failures visible in
    our own logs instead of surfacing only as a bare stack trace.
    """
    try:
        message = client.messages.create(**prepare_message(kwargs))
        usage = message.usage.model_dump() if getattr(message, "usage", None) else {}
        log("CLAUDE_USAGE " + json.dumps({"model": message.model, "usage": usage, "stop_reason": message.stop_reason}))
        return message
    except (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.InternalServerError) as e:
        log(f"CLAUDE_API | giving up after {MAX_RETRIES} retries: {e}")
        raise
    except anthropic.APIStatusError as e:
        log(f"CLAUDE_API | request failed: {e.status_code} {e.message}")
        raise
