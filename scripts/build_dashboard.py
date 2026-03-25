#!/usr/bin/env python3
"""
Injects build-time values into the dashboard template and writes
static/dashboard/index.html before hugo --minify runs.

Injected placeholders:
  __PASSWORD_HASH__   -- SHA256 of DASHBOARD_PASSWORD
  __GITHUB_TOKEN__    -- PAT for GitHub API reads + workflow triggers
  __BLOGGER_BLOG_ID__ -- Blogger blog ID (safe to expose, read-only)
  __BLOGGER_API_KEY__ -- Blogger API key (optional, restricted to reads)
"""
import hashlib
import os
import sys
from pathlib import Path

ROOT     = Path(__file__).parent.parent
TEMPLATE = ROOT / "scripts" / "dashboard_template.html"
OUTPUT   = ROOT / "static"  / "dashboard" / "index.html"


def main():
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=True)
    except ImportError:
        pass

    password = os.environ.get("DASHBOARD_PASSWORD", "")
    if not password:
        print("WARNING: DASHBOARD_PASSWORD not set -- dashboard will be inaccessible", file=sys.stderr)

    github_token = os.environ.get("GITHUB_TOKEN", "")
    if not github_token:
        print("WARNING: GITHUB_TOKEN not set -- Quick Actions will not work", file=sys.stderr)

    blogger_id  = os.environ.get("BLOGGER_BLOG_ID", "")
    blogger_key = os.environ.get("BLOGGER_API_KEY", "")

    pw_hash = hashlib.sha256(password.encode()).hexdigest() if password else ""

    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("__PASSWORD_HASH__",   pw_hash)
    html = html.replace("__GITHUB_TOKEN__",    github_token)
    html = html.replace("__BLOGGER_BLOG_ID__", blogger_id)
    html = html.replace("__BLOGGER_API_KEY__", blogger_key)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"Dashboard built -> {OUTPUT.relative_to(ROOT)}")
    if blogger_key:
        print("  Blogger: API v3 key injected")
    else:
        print("  Blogger: no API key -- will use RSS feed fallback")


if __name__ == "__main__":
    main()
