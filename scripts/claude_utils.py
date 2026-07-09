"""Shared helpers for calling the Claude API from the syndication/generation scripts.

Centralizes the retry/backoff policy so every call site behaves the same way
under rate limits or transient API errors, and logs when it's retrying so a
runaway loop is visible instead of silently burning API spend.
"""

from __future__ import annotations

import time

import anthropic

MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 2


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
        return client.messages.create(**kwargs)
    except (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.InternalServerError) as e:
        log(f"CLAUDE_API | giving up after {MAX_RETRIES} retries: {e}")
        raise
    except anthropic.APIStatusError as e:
        log(f"CLAUDE_API | request failed: {e.status_code} {e.message}")
        raise
