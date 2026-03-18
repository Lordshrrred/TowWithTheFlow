#!/usr/bin/env python3
"""
Tow With The Flow — Weekly Keyword Research
Discovers 20 new long-tail keyword opportunities via Claude API,
scores each one 1-10, and appends unique ones to keywords.txt
sorted by score descending.
"""

import os
import sys
import json
import re
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import anthropic

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
    sys.exit(1)

KEYWORDS_FILE = Path(__file__).parent / "keywords.txt"
LOG_FILE = Path(__file__).parent / "syndication_log.txt"

SYSTEM_PROMPT = """You are an SEO keyword researcher for towwiththeflow.com, a car breakdown and roadside emergency help site. Generate 20 new long-tail keywords and score each one across three dimensions:

1. Search intent strength (1-10): Is someone actively desperate for this answer right now? High = emergency, urgent, needs action immediately.
2. Low competition likelihood (1-10): Is this specific enough that a small site can rank? High = very niche, location-specific, or precise scenario.
3. Monetization potential (1-10): Does the query imply willingness to pay? High = towing cost questions, insurance questions, product questions.

Average the three scores and round to the nearest integer for the final score.

Phrase keywords exactly how someone types into Google during a stressful roadside moment. Cover: specific car problems, towing costs by city, seasonal issues, insurance questions, roadside safety, specific breakdown scenarios.

Return ONLY a JSON array of 20 objects. Each object must have exactly two keys: "score" (integer 1-10) and "keyword" (string). No markdown, no backticks, no explanation. Example format:
[{"score": 9, "keyword": "tow truck cost no insurance"}, {"score": 6, "keyword": "car making noise when turning"}, ...]

NEVER use em dashes (—) or double hyphens (--) in keyword strings."""


def strip_score_prefix(text: str) -> str:
    """Strip [N] score prefix from a keyword line, returning just the keyword."""
    return re.sub(r'^\[\d+\]\s*', '', text).strip()


def load_existing_keywords() -> set[str]:
    if not KEYWORDS_FILE.exists():
        return set()
    lines = KEYWORDS_FILE.read_text(encoding='utf-8').splitlines()
    keywords = set()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('# DONE'):
            stripped = stripped.replace('# DONE', '').strip()
        # Strip score prefix [N] if present
        stripped = strip_score_prefix(stripped)
        if stripped:
            keywords.add(stripped.lower())
    return keywords


def log(message: str):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    entry = f"[{timestamp}] KEYWORD_RESEARCH: {message}\n"
    print(entry, end='')
    with LOG_FILE.open('a', encoding='utf-8') as f:
        f.write(entry)


def main():
    existing = load_existing_keywords()
    log(f"Loaded {len(existing)} existing keywords")

    existing_sample = '\n'.join(list(existing)[:30])
    user_message = (
        f"Here are some existing keywords on the site (avoid duplicating these topics):\n"
        f"{existing_sample}\n\n"
        f"Now generate 20 new keyword opportunities with scores."
    )

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}]
    )

    response_text = message.content[0].text.strip()

    # Strip markdown code fences if present
    response_text = re.sub(r'^```\w*\n?', '', response_text)
    response_text = re.sub(r'\n?```$', '', response_text)

    try:
        raw_keywords = json.loads(response_text)
        if not isinstance(raw_keywords, list):
            raise ValueError("Response is not a list")
    except (json.JSONDecodeError, ValueError) as e:
        log(f"ERROR parsing JSON response: {e}")
        log(f"Raw response: {response_text[:200]}")
        sys.exit(1)

    # Normalise: each item must be {"score": int, "keyword": str}
    scored = []
    for item in raw_keywords:
        if isinstance(item, dict) and "keyword" in item:
            kw = str(item["keyword"]).strip()
            try:
                score = max(1, min(10, int(item.get("score", 5))))
            except (TypeError, ValueError):
                score = 5
            scored.append((score, kw))
        elif isinstance(item, str):
            # Fallback: plain string with no score
            scored.append((5, item.strip()))

    # Filter duplicates (compare lowercased bare keyword)
    unique = [(s, kw) for s, kw in scored if kw.lower() not in existing]
    log(f"Claude returned {len(scored)} keywords, {len(unique)} are new")

    if not unique:
        log("No new unique keywords found")
        return

    # Sort by score descending so best opportunities appear first in the file
    unique.sort(key=lambda x: x[0], reverse=True)

    with KEYWORDS_FILE.open('a', encoding='utf-8') as f:
        for score, kw in unique:
            f.write(f"[{score}] {kw}\n")

    log(f"Appended {len(unique)} new keywords to keywords.txt (sorted by score)")
    for score, kw in unique:
        log(f"  [{score}] {kw}")


if __name__ == "__main__":
    main()
