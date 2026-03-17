#!/usr/bin/env python3
"""
Tow With The Flow — Weekly Keyword Research
Discovers 20 new long-tail keyword opportunities via Claude API
and appends unique ones to keywords.txt.
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

SYSTEM_PROMPT = """You are an SEO keyword researcher for towwiththeflow.com, a car breakdown and roadside emergency help site. Generate 20 new long-tail keywords that have clear search intent from a stressed driver actively looking for help. Cover specific car problems, towing costs by city, seasonal issues, insurance questions, roadside safety, and specific breakdown scenarios. Phrase them exactly how someone would type into Google in a stressful moment. Return ONLY a JSON array of 20 keyword strings, nothing else, no markdown backticks."""


def load_existing_keywords() -> set[str]:
    if not KEYWORDS_FILE.exists():
        return set()
    lines = KEYWORDS_FILE.read_text(encoding='utf-8').splitlines()
    keywords = set()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('# DONE'):
            stripped = stripped.replace('# DONE', '').strip()
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
    user_message = f"Here are some existing keywords on the site (avoid duplicating these topics):\n{existing_sample}\n\nNow generate 20 new keyword opportunities."

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}]
    )

    response_text = message.content[0].text.strip()

    # Strip markdown code fences if present
    response_text = re.sub(r'^```\w*\n?', '', response_text)
    response_text = re.sub(r'\n?```$', '', response_text)

    try:
        new_keywords = json.loads(response_text)
        if not isinstance(new_keywords, list):
            raise ValueError("Response is not a list")
    except (json.JSONDecodeError, ValueError) as e:
        log(f"ERROR parsing JSON response: {e}")
        log(f"Raw response: {response_text[:200]}")
        sys.exit(1)

    # Filter duplicates
    unique_new = [kw for kw in new_keywords if kw.lower() not in existing]
    log(f"Claude returned {len(new_keywords)} keywords, {len(unique_new)} are new")

    if not unique_new:
        log("No new unique keywords found")
        return

    with KEYWORDS_FILE.open('a', encoding='utf-8') as f:
        for kw in unique_new:
            f.write(kw + '\n')

    log(f"Appended {len(unique_new)} new keywords to keywords.txt")


if __name__ == "__main__":
    main()
