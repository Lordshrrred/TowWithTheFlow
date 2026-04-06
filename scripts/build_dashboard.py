#!/usr/bin/env python3
"""
Injects build-time values into dashboard templates and writes static/dashboard/

Outputs:
  static/dashboard/index.html      -- Syndication dashboard (matrix + drip queue)
  static/dashboard/analytics.html  -- GA4 analytics (amber, static JSON)

Injected placeholders:
  __PASSWORD_HASH__      -- SHA256 of DASHBOARD_PASSWORD
  __GITHUB_TOKEN__       -- Ephemeral Actions token for GitHub API reads (expires after run)
  __DASHBOARD_TOKEN__    -- Long-lived PAT for workflow dispatch (DASHBOARD_TRIGGER_TOKEN secret)
  __BLOGGER_BLOG_ID__    -- Blogger blog ID
  __BLOGGER_API_KEY__    -- Blogger API key (optional)
  __BUILD_TIMESTAMP__    -- ISO timestamp of when this build ran
  __BUILD_TOKEN_STATUS__ -- "configured" or "missing" (never the token value)
  __BUILD_COMMIT__       -- Git commit SHA (GITHUB_SHA env var, or "local")
  __TRIGGERS_ENABLED__   -- JS boolean literal true/false (separate from token value,
                            so token substitution cannot corrupt the enable/disable check)

NOTE: __GITHUB_TOKEN__ is the ephemeral Actions token — only good for read API calls during
the current workflow run. DO NOT use it for browser-side workflow dispatch.
Use __DASHBOARD_TOKEN__ (backed by DASHBOARD_TRIGGER_TOKEN secret, a real PAT with
workflow scope) for any trigger operations from the dashboard.
"""
import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent

BUILDS = [
    {
        "template": ROOT / "scripts" / "dashboard_template.html",
        "output":   ROOT / "static"  / "dashboard" / "index.html",
        "label":    "Syndication dashboard",
    },
    {
        "template": ROOT / "scripts" / "analytics_template.html",
        "output":   ROOT / "static"  / "dashboard" / "analytics.html",
        "label":    "Analytics dashboard",
    },
]


def main():
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=True)
    except ImportError:
        pass

    password = os.environ.get("DASHBOARD_PASSWORD", "")
    if not password:
        print("WARNING: DASHBOARD_PASSWORD not set -- dashboards will be inaccessible",
              file=sys.stderr)

    github_token    = os.environ.get("GITHUB_TOKEN", "")
    trigger_token   = os.environ.get("DASHBOARD_TRIGGER_TOKEN", "")
    if not trigger_token:
        print("WARNING: DASHBOARD_TRIGGER_TOKEN not set -- dashboard workflow triggers will be disabled",
              file=sys.stderr)

    blogger_id  = os.environ.get("BLOGGER_BLOG_ID", "")
    blogger_key = os.environ.get("BLOGGER_API_KEY", "")

    build_ts          = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    token_status      = "configured" if trigger_token else "missing"
    token_color       = "#22c55e" if trigger_token else "#ef4444"
    triggers_enabled  = "true" if trigger_token else "false"   # JS boolean literal
    commit_sha        = os.environ.get("GITHUB_SHA", "local")[:8]

    pw_hash = hashlib.sha256(password.encode()).hexdigest() if password else ""

    for build in BUILDS:
        tmpl = build["template"]
        out  = build["output"]
        if not tmpl.exists():
            print(f"  SKIP {build['label']}: template not found ({tmpl.name})",
                  file=sys.stderr)
            continue

        html = tmpl.read_text(encoding="utf-8")
        html = html.replace("__PASSWORD_HASH__",      pw_hash)
        html = html.replace("__GITHUB_TOKEN__",       github_token)
        html = html.replace("__DASHBOARD_TOKEN__",    trigger_token)
        html = html.replace("__BLOGGER_BLOG_ID__",    blogger_id)
        html = html.replace("__BLOGGER_API_KEY__",    blogger_key)
        html = html.replace("__BUILD_TIMESTAMP__",    build_ts)
        html = html.replace("__BUILD_TOKEN_STATUS__", token_status)
        html = html.replace("__TOKEN_COLOR__",        token_color)
        html = html.replace("__TRIGGERS_ENABLED__",   triggers_enabled)
        html = html.replace("__BUILD_COMMIT__",       commit_sha)

        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        print(f"  Built: {build['label']:30s}  ->  {out.relative_to(ROOT)}")

    if blogger_key:
        print("  Blogger: API v3 key injected")
    else:
        print("  Blogger: no API key -- syndication dashboard uses RSS fallback")


if __name__ == "__main__":
    main()
