#!/usr/bin/env python3
"""Build low-cost SEO strategy status for keyword runway and backlink throughput."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

from generate_post import load_keywords

ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = Path(__file__).parent
STATUS_FILE = SCRIPTS_DIR / "keyword-generation-status.json"
BACKLINK_AUDIT_FILE = SCRIPTS_DIR / "backlink_audit.json"
LOG_FILE = SCRIPTS_DIR / "syndication_log.txt"

REQUIRED_BACKLINK_PLATFORMS = ["dev", "tumblr", "blog", "wordpress", "feeder"]


def env_number(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        return default


def keyword_inventory() -> dict:
    rows = load_keywords()
    pending = sum(1 for *_rest, done in rows if not done)
    live = sum(1 for *_rest, done in rows if done)
    cadence = env_number("SEO_PUBLISHING_POSTS_PER_DAY", 4)
    pause_days = env_number("KEYWORD_RUNWAY_PAUSE_DAYS", 90)
    resume_days = env_number("KEYWORD_RUNWAY_RESUME_DAYS", 45)
    days = pending / cadence if cadence > 0 else 0
    rounded_days = round(days, 1)

    previous_status = "running"
    if STATUS_FILE.exists():
        try:
            previous_status = json.loads(STATUS_FILE.read_text(encoding="utf-8")).get("keywordGeneration", {}).get("status", "running")
        except (OSError, json.JSONDecodeError):
            previous_status = "running"

    if days >= pause_days:
        status = "paused"
        reason = f"{rounded_days} publishing days of inventory remain, above the {int(pause_days)} day pause threshold."
    elif days <= resume_days:
        status = "running"
        reason = f"{rounded_days} publishing days of inventory remain, at or below the {int(resume_days)} day resume threshold."
    else:
        status = previous_status if previous_status in {"running", "paused"} else "running"
        reason = (
            f"{rounded_days} publishing days of inventory remain between the "
            f"{int(resume_days)} day resume and {int(pause_days)} day pause thresholds; "
            f"holding previous state: {status}."
        )

    return {
        "currentInventory": pending,
        "liveKeywords": live,
        "estimatedDaysRemaining": rounded_days,
        "publishingCadencePerDay": cadence,
        "pauseThresholdDays": pause_days,
        "resumeThresholdDays": resume_days,
        "status": status,
        "reason": reason,
    }


def backlink_inventory() -> dict:
    if not BACKLINK_AUDIT_FILE.exists():
        return {
            "backlogPosts": None,
            "backlogUnits": None,
            "requiredPlatformsPerPost": len(REQUIRED_BACKLINK_PLATFORMS),
            "source": "missing backlink_audit.json",
        }

    try:
        audit = json.loads(BACKLINK_AUDIT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "backlogPosts": None,
            "backlogUnits": None,
            "requiredPlatformsPerPost": len(REQUIRED_BACKLINK_PLATFORMS),
            "source": "unreadable backlink_audit.json",
        }

    backlog_posts = 0
    backlog_units = 0
    for _slug, row in (audit.get("slugs") or {}).items():
        missing = [
            platform
            for platform in REQUIRED_BACKLINK_PLATFORMS
            if (row.get(platform) or {}).get("verified") is not True
        ]
        if missing:
            backlog_posts += 1
            backlog_units += len(missing)

    return {
        "backlogPosts": backlog_posts,
        "backlogUnits": backlog_units,
        "requiredPlatformsPerPost": len(REQUIRED_BACKLINK_PLATFORMS),
        "generatedAt": audit.get("generated_at"),
        "source": "backlink_audit.json",
    }


def recent_backlink_completions(days: int = 14) -> float:
    if not LOG_FILE.exists():
        return 0.0
    cutoff = datetime.now() - timedelta(days=days)
    rx = re.compile(
        r"^\[(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s+"
        r"(?P<platform>DEVTO|TUMBLR|BLOGGER|WORDPRESS|FEEDER)\s+\|\s+"
        r"(?P<slug>[\w-]+)\s+\|\s+SUCCESS"
    )
    seen: set[tuple[str, str]] = set()
    for line in LOG_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = rx.match(line)
        if not m:
            continue
        try:
            ts = datetime.strptime(m.group("ts"), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if ts < cutoff:
            continue
        seen.add((m.group("slug"), m.group("platform")))
    return round(len(seen) / max(days, 1), 1)


def backlink_throughput() -> dict:
    inventory = backlink_inventory()
    completed_per_day = recent_backlink_completions()
    posts_per_day = env_number("SEO_PUBLISHING_POSTS_PER_DAY", 4)
    required = inventory.get("requiredPlatformsPerPost") or len(REQUIRED_BACKLINK_PLATFORMS)
    new_units_per_day = round(posts_per_day * required, 1)
    backlog_units = inventory.get("backlogUnits")
    net_units_per_day = round(new_units_per_day - completed_per_day, 1)

    if backlog_units in (None, 0):
        estimate = "maintenance"
        reason = "Backlink backlog is clear; new posts should syndicate, verify, and complete as they publish."
    elif completed_per_day > new_units_per_day:
        days = round(backlog_units / (completed_per_day - new_units_per_day), 1)
        estimate = days
        reason = f"Backlinks are catching up by {round(completed_per_day - new_units_per_day, 1)} platform links/day."
    elif completed_per_day == new_units_per_day:
        estimate = None
        reason = "Backlinks are keeping pace, but not reducing the historical backlog."
    else:
        estimate = None
        reason = f"Backlog is growing by {abs(net_units_per_day)} platform links/day at the current rate."

    return {
        **inventory,
        "completedPerDay": completed_per_day,
        "newPostsPerDay": posts_per_day,
        "newBacklinkUnitsPerDay": new_units_per_day,
        "netBacklinkUnitsPerDay": net_units_per_day,
        "estimatedCatchUpDays": estimate,
        "reason": reason,
    }


def build_status() -> dict:
    keyword = keyword_inventory()
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "keywordGeneration": keyword,
        "backlinks": backlink_throughput(),
        "curatedExpansion": {
            "supported": True,
            "script": "scripts/import_curated_keywords.py",
            "reason": "Use curated lists for new clusters, tools, products, competitor reviews, and intentional trend discoveries instead of endless generic expansion.",
        },
    }


def write_status() -> dict:
    payload = build_status()
    STATUS_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    status = write_status()
    kw = status["keywordGeneration"]
    bl = status["backlinks"]
    print(
        f"Keyword generation: {kw['status']} | "
        f"{kw['currentInventory']} pending | {kw['estimatedDaysRemaining']} days"
    )
    print(
        f"Backlinks: backlog_posts={bl['backlogPosts']} backlog_units={bl['backlogUnits']} "
        f"completed/day={bl['completedPerDay']} new_units/day={bl['newBacklinkUnitsPerDay']} "
        f"net={bl['netBacklinkUnitsPerDay']}"
    )
