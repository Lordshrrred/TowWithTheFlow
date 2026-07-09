#!/usr/bin/env python3
"""
Tow With The Flow — SEO Dashboard Data Builder
Aggregates data that's already being collected by other scripts (keywords.txt,
the weekly SERP intelligence report, the backlink audit) into a single JSON
file the SEO dashboard tab reads. Makes no API calls of its own.

Output: static/data/seo.json
"""

from __future__ import annotations

import json
from pathlib import Path

from generate_post import load_keywords, is_local

ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = Path(__file__).parent
REPORTS_DIR = ROOT / "reports"
OUTPUT_FILE = ROOT / "static" / "data" / "seo.json"

NEXT_TARGETS_LIMIT = 10


def keyword_clusters() -> tuple[dict, list[dict]]:
    """Live/pending counts split by local vs. pain-point, plus the highest
    -scored pending keywords (what we're trying to rank for next)."""
    keywords = load_keywords()  # (line_index, keyword, score_or_None, is_done)

    def bucket(rows):
        return {
            "live": sum(1 for _kw, _s, done in rows if done),
            "pending": sum(1 for _kw, _s, done in rows if not done),
        }

    rows = [(kw, score, done) for _i, kw, score, done in keywords]
    local_rows = [(kw, s, d) for kw, s, d in rows if is_local(kw)]
    pain_point_rows = [(kw, s, d) for kw, s, d in rows if not is_local(kw)]

    summary = {
        "total": len(rows),
        "live": sum(1 for _kw, _s, done in rows if done),
        "pending": sum(1 for _kw, _s, done in rows if not done),
        "local": bucket(local_rows),
        "pain_point": bucket(pain_point_rows),
    }

    pending_scored = [
        {"keyword": kw, "score": score, "type": "local" if is_local(kw) else "pain_point"}
        for kw, score, done in rows
        if not done and score is not None
    ]
    pending_scored.sort(key=lambda x: x["score"], reverse=True)
    next_targets = pending_scored[:NEXT_TARGETS_LIMIT]

    return summary, next_targets


def latest_serp_data() -> dict:
    """Structured sidecar written by serp_intelligence.py, if a check has run yet."""
    path = REPORTS_DIR / "serp-intelligence-latest.json"
    if not path.exists():
        return {
            "report_date": None,
            "checked": 0,
            "skipped": 0,
            "present_count": 0,
            "ai_overview_count": 0,
            "results": [],
        }

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {
            "report_date": None,
            "checked": 0,
            "skipped": 0,
            "present_count": 0,
            "ai_overview_count": 0,
            "results": [],
        }

    results = data.get("results", [])
    return {
        "report_date": data.get("report_date"),
        "checked": len(results),
        "skipped": len(data.get("skipped", [])),
        "present_count": sum(1 for r in results if r.get("twtf_present")),
        "ai_overview_count": sum(1 for r in results if r.get("ai_overview_mentions_twtf")),
        "results": results,
    }


def backlink_health() -> dict:
    """Per-platform verified/checked counts from the most recent backlink audit."""
    path = SCRIPTS_DIR / "backlink_audit.json"
    if not path.exists():
        return {"generated_at": None, "platforms": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"generated_at": None, "platforms": {}}
    return {
        "generated_at": data.get("generated_at"),
        "platforms": data.get("summary", {}),
    }


def main():
    from datetime import datetime, timezone

    keywords_summary, next_targets = keyword_clusters()
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "keywords": keywords_summary,
        "next_targets": next_targets,
        "serp": latest_serp_data(),
        "backlinks": backlink_health(),
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT_FILE.relative_to(ROOT)}")
    print(
        f"  keywords: {keywords_summary['live']} live / {keywords_summary['pending']} pending "
        f"({keywords_summary['local']['live']} local live, {keywords_summary['pain_point']['live']} pain-point live)"
    )
    print(f"  next targets: {len(next_targets)}")
    print(f"  serp check: {payload['serp']['checked']} keywords, report_date={payload['serp']['report_date']}")


if __name__ == "__main__":
    main()
