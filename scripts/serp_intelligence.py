#!/usr/bin/env python3
"""
Tow With The Flow — Weekly SERP Intelligence + AI Search Visibility Checker
For the 10 highest-priority local SEO / pain-point keywords that already have
a live post, uses Claude with web search to see who's ranking, what their
angle and content gaps are, and whether towwiththeflow.com shows up in
organic results or an AI Overview. Compiles the findings into a markdown
report under /reports.
"""

from __future__ import annotations

import os
import sys
import json
import re
from datetime import date, datetime
from pathlib import Path
from dotenv import load_dotenv
import anthropic

from claude_utils import make_client, create_message
from generate_post import load_keywords, is_local, load_post_index

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
    sys.exit(1)

LOG_FILE = Path(__file__).parent / "syndication_log.txt"
REPORTS_DIR = ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://towwiththeflow.com"
KEYWORD_LIMIT = 10
MODEL = "claude-sonnet-4-6"
MAX_CONTINUATIONS = 3  # cap on resuming a paused server-tool turn

SYSTEM_PROMPT = """You are an SEO analyst researching search visibility for towwiththeflow.com, a car breakdown and roadside emergency help site.

For the keyword given in the user message:
1. Search for that exact keyword.
2. Identify the top 3 organic results (exclude ads).
3. For each of the 3: summarize its angle/structure and approximate word count in one field, and note concrete content gaps (missing info, weak structure, thin content, no local specificity, etc.) in another field.
4. Determine whether towwiththeflow.com appears anywhere in the organic results, and if so, at what position (1-10+). Also check whether an AI Overview / AI-generated summary is shown for this query, and whether it mentions or cites towwiththeflow.com.

Return ONLY a single JSON object with exactly this shape, no markdown, no backticks, no explanation:
{"keyword": "...", "top3": [{"url": "...", "angle": "...", "gaps": "..."}, {"url": "...", "angle": "...", "gaps": "..."}, {"url": "...", "angle": "...", "gaps": "..."}], "twtf_present": true or false, "twtf_position": integer or null, "ai_overview_mentions_twtf": true or false}

If fewer than 3 organic results exist, return as many as you found. If no AI Overview is shown for the query, set ai_overview_mentions_twtf to false."""


def log(message: str):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    entry = f"[{timestamp}] SERP_INTELLIGENCE: {message}\n"
    print(entry, end='')
    with LOG_FILE.open('a', encoding='utf-8') as f:
        f.write(entry)


def _rank(done: list[tuple[str, int | None]]) -> list[tuple[str, int | None]]:
    """Highest score first; unscored keywords fill remaining slots (same
    ordering convention as generate_post.pick_keyword)."""
    scored = [(kw, score) for kw, score in done if score is not None]
    unscored = [(kw, score) for kw, score in done if score is None]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored + unscored


def load_top_keywords(limit: int = KEYWORD_LIMIT) -> list[tuple[str, int | None]]:
    """Highest-priority local SEO AND pain-point keywords that already have a
    live post (marked '# DONE' in keywords.txt). Local and pain-point
    keywords are ranked separately and split evenly so the local score scale
    (city pages are seeded much higher) doesn't crowd out pain-point topics."""
    keywords = load_keywords()  # (line_index, keyword, score_or_None, is_done)
    done = [(kw, score) for _i, kw, score, is_done in keywords if is_done]
    local_done = _rank([(kw, s) for kw, s in done if is_local(kw)])
    pain_point_done = _rank([(kw, s) for kw, s in done if not is_local(kw)])

    half = (limit + 1) // 2
    selected = local_done[:half] + pain_point_done[:limit - half]
    if len(selected) < limit:
        # One bucket was short — top off from the other's leftovers.
        leftovers = local_done[half:] + pain_point_done[limit - half:]
        selected += leftovers[:limit - len(selected)]
    return selected[:limit]


def find_post_url(keyword: str, post_index: list[tuple[str, str]]) -> str | None:
    """Best-effort match of a keyword to its live post slug, for report context only."""
    kw_tokens = set(re.findall(r'[a-z0-9]+', keyword.lower()))
    if not kw_tokens:
        return None
    best_slug, best_overlap = None, 0.0
    for slug, _title in post_index:
        slug_tokens = set(slug.split('-'))
        overlap = len(kw_tokens & slug_tokens) / len(kw_tokens)
        if overlap > best_overlap:
            best_overlap, best_slug = overlap, slug
    if best_slug and best_overlap >= 0.6:
        return f"{BASE_URL}/{best_slug}/"
    return None


def extract_json(content_blocks) -> dict | None:
    """Join all text blocks in a response and parse the trailing JSON object."""
    text = "".join(b.text for b in content_blocks if b.type == "text").strip()
    if not text:
        return None
    text = re.sub(r'^```\w*\n?', '', text)
    text = re.sub(r'\n?```$', '', text)
    # Model may add commentary before/after the JSON — pull out the last {...} blob.
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def check_keyword(client: anthropic.Anthropic, keyword: str) -> dict | None:
    """Run one web-search-grounded SERP check for a keyword. Returns the
    parsed result dict, or None if the call or the response was unusable."""
    messages = [{"role": "user", "content": f"Search for: \"{keyword}\""}]
    tools = [{"type": "web_search_20260209", "name": "web_search"}]
    system = [{
        "type": "text",
        "text": SYSTEM_PROMPT,
        "cache_control": {"type": "ephemeral"},
    }]

    response = create_message(
        client,
        log=log,
        model=MODEL,
        max_tokens=3000,
        system=system,
        tools=tools,
        messages=messages,
    )

    continuations = 0
    while response.stop_reason == "pause_turn" and continuations < MAX_CONTINUATIONS:
        continuations += 1
        log(f"{keyword} | server tool paused, resuming (continuation {continuations}/{MAX_CONTINUATIONS})")
        messages.append({"role": "assistant", "content": response.content})
        response = create_message(
            client,
            log=log,
            model=MODEL,
            max_tokens=3000,
            system=system,
            tools=tools,
            messages=messages,
        )

    if response.stop_reason == "refusal":
        log(f"{keyword} | SKIPPED — model refused the request")
        return None

    parsed = extract_json(response.content)
    if not parsed or "keyword" not in parsed or "top3" not in parsed:
        log(f"{keyword} | SKIPPED — malformed/unparseable response")
        return None

    return parsed


def normalize_result(raw: dict, fallback_keyword: str) -> dict:
    """Fill in defensive defaults so a partially-correct response still renders."""
    top3 = raw.get("top3") or []
    if not isinstance(top3, list):
        top3 = []
    cleaned_top3 = []
    for item in top3[:3]:
        if not isinstance(item, dict):
            continue
        cleaned_top3.append({
            "url": str(item.get("url", "")).strip() or "(no URL returned)",
            "angle": str(item.get("angle", "")).strip() or "(none given)",
            "gaps": item.get("gaps", "(none given)"),
        })

    twtf_position = raw.get("twtf_position")
    try:
        twtf_position = int(twtf_position) if twtf_position is not None else None
    except (TypeError, ValueError):
        twtf_position = None

    return {
        "keyword": str(raw.get("keyword", fallback_keyword)).strip(),
        "top3": cleaned_top3,
        "twtf_present": bool(raw.get("twtf_present", False)),
        "twtf_position": twtf_position,
        "ai_overview_mentions_twtf": bool(raw.get("ai_overview_mentions_twtf", False)),
    }


def format_gaps(gaps) -> str:
    if isinstance(gaps, list):
        return "; ".join(str(g).strip() for g in gaps if str(g).strip())
    return str(gaps).strip()


def build_report(report_date: str, results: list[dict], skipped: list[str]) -> str:
    lines = [f"# SERP Intelligence + AI Search Visibility Report — {report_date}", ""]

    present_count = sum(1 for r in results if r["twtf_present"])
    ai_mention_count = sum(1 for r in results if r["ai_overview_mentions_twtf"])
    lines.append(
        f"Checked {len(results)} keyword(s) "
        f"({len(skipped)} skipped). "
        f"towwiththeflow.com appears in organic results for {present_count}/{len(results)}. "
        f"Mentioned in an AI Overview for {ai_mention_count}/{len(results)}."
    )
    lines.append("")

    for r in results:
        kw = r["keyword"]
        lines.append(f"## {kw}")
        post_url = r.get("our_post_url")
        if post_url:
            lines.append(f"- **Our post:** {post_url}")
        if r["twtf_present"]:
            pos = r["twtf_position"]
            pos_label = f"position {pos}" if pos is not None else "position unknown"
            lines.append(f"- **Visibility:** ✅ Present in organic results ({pos_label})")
        else:
            lines.append("- **Visibility:** ❌ Not found in organic results")
        lines.append(
            f"- **AI Overview mentions us:** {'✅ Yes' if r['ai_overview_mentions_twtf'] else '❌ No'}"
        )
        lines.append("")
        lines.append("**Top 3 organic results:**")
        lines.append("")
        if not r["top3"]:
            lines.append("- (no results returned)")
        for i, item in enumerate(r["top3"], start=1):
            lines.append(f"{i}. [{item['url']}]({item['url']})")
            lines.append(f"   - Angle/structure: {item['angle']}")
            lines.append(f"   - Content gaps: {format_gaps(item['gaps'])}")
        lines.append("")

    if skipped:
        lines.append("## Skipped keywords")
        lines.append("")
        lines.append("These returned a refusal or a response that couldn't be parsed — see syndication_log.txt for details.")
        lines.append("")
        for kw in skipped:
            lines.append(f"- {kw}")
        lines.append("")

    return "\n".join(lines)


def main():
    top_keywords = load_top_keywords()
    if not top_keywords:
        log("No keywords with live posts found in keywords.txt — nothing to check")
        return

    local_count = sum(1 for kw, _ in top_keywords if is_local(kw))
    log(f"Checking {len(top_keywords)} keywords ({local_count} local, {len(top_keywords) - local_count} pain-point)")

    post_index = load_post_index()
    client = make_client(ANTHROPIC_API_KEY)

    results = []
    skipped = []
    for keyword, score in top_keywords:
        label = f"[{score}] {keyword}" if score is not None else keyword
        log(f"Checking: {label}")
        try:
            raw = check_keyword(client, keyword)
        except Exception as e:
            log(f"{keyword} | SKIPPED — API error: {e}")
            skipped.append(keyword)
            continue

        if raw is None:
            skipped.append(keyword)
            continue

        result = normalize_result(raw, keyword)
        result["our_post_url"] = find_post_url(keyword, post_index)
        results.append(result)
        status = "present" if result["twtf_present"] else "not found"
        log(f"{keyword} | done — twtf {status}")

    report_date = date.today().isoformat()
    report_md = build_report(report_date, results, skipped)
    report_path = REPORTS_DIR / f"serp-intelligence-{report_date}.md"
    report_path.write_text(report_md, encoding="utf-8")

    # Structured sidecar for the SEO dashboard (avoids re-parsing markdown).
    # "-latest.json" is a stable filename so the dashboard build step always
    # knows where to look regardless of what today's date is.
    payload = {
        "report_date": report_date,
        "results": results,
        "skipped": skipped,
    }
    payload_json = json.dumps(payload, indent=2)
    (REPORTS_DIR / f"serp-intelligence-{report_date}.json").write_text(payload_json, encoding="utf-8")
    (REPORTS_DIR / "serp-intelligence-latest.json").write_text(payload_json, encoding="utf-8")

    log(
        f"Report saved: reports/{report_path.name} | "
        f"{len(results)}/{len(top_keywords)} keywords analyzed | "
        f"{sum(1 for r in results if r['twtf_present'])} show TWTF | "
        f"{len(skipped)} skipped"
    )


if __name__ == "__main__":
    main()
