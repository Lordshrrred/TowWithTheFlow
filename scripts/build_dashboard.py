#!/usr/bin/env python3
"""
Injects SHA256-hashed password and GitHub token into the dashboard template.
Run before `hugo --minify`. Called by hugo.yml workflow.
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
        print("WARNING: DASHBOARD_PASSWORD not set — dashboard will be inaccessible", file=sys.stderr)

    github_token = os.environ.get("GITHUB_TOKEN", "")
    if not github_token:
        print("WARNING: GITHUB_TOKEN not set — Quick Actions will not work", file=sys.stderr)

    pw_hash = hashlib.sha256(password.encode()).hexdigest() if password else ""

    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("__PASSWORD_HASH__", pw_hash)
    html = html.replace("__GITHUB_TOKEN__",  github_token)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"Dashboard built -> {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
