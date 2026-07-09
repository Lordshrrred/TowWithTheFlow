#!/usr/bin/env python3
"""
One-time backfill pass over existing posts to bring them up to the current
quality bar established by the 2026-05-17 content update and the new FAQ
schema requirement:

  - Mode "expand": posts under 500 words get expanded (existing structure,
    facts, and internal links preserved — new detail added, not rewritten)
    and get a Common Questions section added.
  - Mode "faq-only": posts already at/above 500 words just get a Common
    Questions section appended; body is left untouched.

Both modes assign/refresh the `clusters:` frontmatter field too.

Idempotent by construction: a post that already has 500+ words and a
`faq:` field is skipped, so an interrupted run can just be re-run.
"""

from __future__ import annotations

import re
import sys
import glob
from datetime import datetime
from pathlib import Path

from claude_utils import make_client, create_message
from clusters import assign_cluster
from assign_clusters import set_cluster_field
from generate_post import extract_faq_pairs, build_faq_yaml, insert_faq_frontmatter, count_body_words

ROOT = Path(__file__).parent.parent
POSTS_DIR = ROOT / "content" / "posts"
LOG_FILE = Path(__file__).parent / "syndication_log.txt"
SKIP = {"_index.md", "tow-content-log.md"}

MODEL = "claude-sonnet-4-6"
MIN_WORDS = 500

EXPAND_SYSTEM_PROMPT = """You are expanding an existing published page for towwiththeflow.com, a car breakdown and roadside emergency help site, in the voice of a knowledgeable direct mechanic who wastes no words.

You will be given the existing body of a post (markdown, no frontmatter, no closing backlink line). Rewrite it as a fuller, more useful version:

- Keep every fact, structure, and internal link exactly as-is. Add detail, don't remove or contradict what's already there.
- Expand thin sections with genuinely specific, useful detail (concrete numbers, scenarios, edge cases) until the total body is 550-950 words.
- Add a new "## Common Questions" section near the end (before any closing safety/cost list), with exactly 2-3 Q&A pairs, formatted EXACTLY like this:

## Common Questions

**Q: [question in the reader's own words]?**
A: [direct answer, 1-3 sentences]

Pick questions a reader would plausibly search right after reading this page. Answers must be useful on their own, not a teaser.

Rules:
- NEVER use em dashes (—) or double hyphens (--).
- Return ONLY the revised markdown body. No frontmatter, no explanation, no code fences."""

FAQ_ONLY_SYSTEM_PROMPT = """You are adding a short FAQ section to an existing published page for towwiththeflow.com, a car breakdown and roadside emergency help site.

You will be given the existing body of a post. Do not change or shorten any of it. Return ONLY a new section to append, formatted EXACTLY like this, with exactly 2-3 Q&A pairs:

## Common Questions

**Q: [question in the reader's own words]?**
A: [direct answer, 1-3 sentences]

Pick questions a reader would plausibly search right after reading this page. Answers must be useful on their own, not a teaser back into the article.

Rules:
- NEVER use em dashes (—) or double hyphens (--).
- Return ONLY the new section (starting with "## Common Questions"). No frontmatter, no explanation, no code fences, no repetition of the existing body."""


def log(message: str):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    entry = f"[{timestamp}] BACKFILL: {message}\n"
    print(entry, end='')
    with LOG_FILE.open('a', encoding='utf-8') as f:
        f.write(entry)


def split_frontmatter(text: str) -> tuple[str, str]:
    m = re.match(r'^---\n(.*?)\n---\n?(.*)', text, re.DOTALL)
    if not m:
        return "", text
    return m.group(1), m.group(2)


def split_backlink(body: str) -> tuple[str, str]:
    """Return (body_without_backlink, backlink_block) so the backlink can be
    reattached byte-exact after the LLM call, never regenerated."""
    idx = body.rfind("---\n\n*Need roadside help?")
    if idx == -1:
        idx = body.rfind("*Need roadside help?")
    if idx == -1:
        return body, ""
    return body[:idx].rstrip(), body[idx:]


def strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r'^```\w*\n?', '', text)
        text = re.sub(r'\n?```$', '', text)
    return text.strip()


def needs_backfill(fm: str, word_count: int) -> str | None:
    has_faq = bool(re.search(r'^faq:\s*$', fm, re.MULTILINE))
    if word_count < MIN_WORDS:
        return "expand"
    if not has_faq:
        return "faq-only"
    return None


def process_post(client, path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    fm, body = split_frontmatter(text)
    if not fm:
        return "skip: no frontmatter"

    word_count = count_body_words(text)
    mode = needs_backfill(fm, word_count)
    if mode is None:
        return "skip: already up to standard"

    body_wo_backlink, backlink = split_backlink(body)

    if mode == "expand":
        system_prompt = EXPAND_SYSTEM_PROMPT
        user_message = f"Existing body ({word_count} words):\n\n{body_wo_backlink}"
    else:
        system_prompt = FAQ_ONLY_SYSTEM_PROMPT
        user_message = f"Existing body:\n\n{body_wo_backlink}"

    response = create_message(
        client,
        log=log,
        model=MODEL,
        max_tokens=2200,
        system=[{
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": user_message}],
    )
    result = strip_code_fences(response.content[0].text)

    if mode == "expand":
        new_body = result
    else:
        new_body = body_wo_backlink.rstrip() + "\n\n" + result.strip() + "\n"

    new_body = new_body.rstrip() + "\n\n" + backlink if backlink else new_body

    faq_pairs = extract_faq_pairs(new_body)
    if not faq_pairs:
        return f"warn: {mode} produced no parseable FAQ section"

    title_m = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', fm, re.MULTILINE)
    cluster_slug, _label = assign_cluster(title_m.group(1) if title_m else path.stem)

    new_text = f"---\n{fm}\n---\n{new_body}"
    new_text = set_cluster_field(new_text, cluster_slug)
    new_text = insert_faq_frontmatter(new_text, build_faq_yaml(faq_pairs))

    new_word_count = count_body_words(new_text)
    path.write_text(new_text, encoding="utf-8")
    return f"ok: {mode}, {word_count}->{new_word_count} words, {len(faq_pairs)} faq pairs"


def main():
    limit = None
    if len(sys.argv) > 1:
        limit = int(sys.argv[1])

    files = [Path(p) for p in sorted(glob.glob(str(POSTS_DIR / "*.md"))) if Path(p).name not in SKIP]
    client = make_client_or_exit()

    processed = 0
    skipped = 0
    failed = 0
    for path in files:
        if limit is not None and processed >= limit:
            break
        try:
            result = process_post(client, path)
        except Exception as e:
            log(f"{path.name} | ERROR: {e}")
            failed += 1
            continue

        if result.startswith("skip"):
            skipped += 1
            continue
        if result.startswith("warn"):
            log(f"{path.name} | {result}")
            failed += 1
            continue

        processed += 1
        log(f"{path.name} | {result}")

    log(f"Done: {processed} updated, {skipped} already fine, {failed} failed, {len(files)} total")


def make_client_or_exit():
    import os
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    return make_client(api_key)


if __name__ == "__main__":
    main()
