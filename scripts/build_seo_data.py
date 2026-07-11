#!/usr/bin/env python3
"""
Tow With The Flow — SEO Dashboard Data Builder
Aggregates data that's already being collected by other scripts (keywords.txt,
optional manual competitive research, the backlink audit, and the
Search Console/GA4 intelligence summary) into a single JSON file the SEO
dashboard tab reads. Makes no API calls of its own.

Output: static/data/seo.json
"""

from __future__ import annotations

import glob
import json
import re
from pathlib import Path

from generate_post import load_keywords, is_local
from clusters import cluster_label
from seo_strategy_status import build_status

ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = Path(__file__).parent
POSTS_DIR = ROOT / "content" / "posts"
REPORTS_DIR = ROOT / "reports"
OUTPUT_FILE = ROOT / "static" / "data" / "seo.json"

NEXT_TARGETS_LIMIT = 10


def content_clusters() -> list[dict]:
    """How many live posts fall into each content cluster (see clusters.py),
    for the SEO dashboard's cluster breakdown and hub-page links."""
    files = [p for p in glob.glob(str(POSTS_DIR / "*.md")) if Path(p).name not in {"_index.md", "tow-content-log.md"}]
    counts: dict[str, int] = {}
    for path_str in files:
        text = Path(path_str).read_text(encoding="utf-8")
        m = re.search(r'^clusters:\s*\[["\']?([\w-]+)', text, re.MULTILINE)
        slug = m.group(1) if m else "roadside-help"
        counts[slug] = counts.get(slug, 0) + 1

    return sorted(
        [{"slug": slug, "label": cluster_label(slug), "count": count} for slug, count in counts.items()],
        key=lambda c: c["count"],
        reverse=True,
    )


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


def latest_competitive_research_data() -> dict:
    """Structured manual competitive-research sidecar, if one has run yet."""
    path = REPORTS_DIR / "competitive-research-latest.json"
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


def seo_intelligence_summary() -> dict:
    """Compact public-safe summary written by seo_intelligence.py.
    Raw GSC/GA4 cache stays under .cache/ and is never copied to static/."""
    path = REPORTS_DIR / "seo-intelligence-latest.json"
    if not path.exists():
        return {
            "generated_at": None,
            "statuses": [],
            "request_counts": {"gsc": 0, "ga4": 0},
            "top_actions": [],
            "near_page_one_count": 0,
            "ctr_opportunity_count": 0,
            "cannibalization_count": 0,
            "report_path": "reports/seo-intelligence-latest.md",
        }

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {
            "generated_at": None,
            "statuses": [{"source": "seo_intelligence", "status": "error", "message": "Could not parse latest SEO intelligence report."}],
            "request_counts": {"gsc": 0, "ga4": 0},
            "top_actions": [],
            "near_page_one_count": 0,
            "ctr_opportunity_count": 0,
            "cannibalization_count": 0,
            "report_path": "reports/seo-intelligence-latest.md",
        }

    return data.get("summary") or {
        "generated_at": data.get("generated_at"),
        "statuses": data.get("statuses", []),
        "request_counts": data.get("request_counts", {"gsc": 0, "ga4": 0}),
        "top_actions": data.get("top_actions", [])[:3],
        "near_page_one_count": len((data.get("classifications") or {}).get("near_page_one", [])),
        "ctr_opportunity_count": len((data.get("classifications") or {}).get("ctr_opportunities", [])),
        "cannibalization_count": len(data.get("cannibalization", [])),
        "report_path": "reports/seo-intelligence-latest.md",
    }


def main():
    from datetime import datetime, timezone

    keywords_summary, next_targets = keyword_clusters()
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "keywords": keywords_summary,
        "next_targets": next_targets,
        "content_clusters": content_clusters(),
        "competitive_research": latest_competitive_research_data(),
        "backlinks": backlink_health(),
        "intelligence": seo_intelligence_summary(),
        "strategy": build_status(),
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT_FILE.relative_to(ROOT)}")
    print(
        f"  keywords: {keywords_summary['live']} live / {keywords_summary['pending']} pending "
        f"({keywords_summary['local']['live']} local live, {keywords_summary['pain_point']['live']} pain-point live)"
    )
    print(f"  next targets: {len(next_targets)}")
    print(f"  content clusters: {len(payload['content_clusters'])}")
    print(f"  manual competitive research: {payload['competitive_research']['checked']} keywords, report_date={payload['competitive_research']['report_date']}")
    print(f"  seo intelligence: {len(payload['intelligence']['top_actions'])} top actions")
    print(
        f"  strategy: keyword generation {payload['strategy']['keywordGeneration']['status']}, "
        f"{payload['strategy']['keywordGeneration']['estimatedDaysRemaining']} days runway"
    )


if __name__ == "__main__":
    main()
