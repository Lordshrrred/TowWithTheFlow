#!/usr/bin/env python3
"""
Syndicate a post to Blogger via the Blogger API v3.

Usage:
    python scripts/blogger_syndicate.py <slug>

Requires in .env:
    BLOGGER_CLIENT_ID
    BLOGGER_CLIENT_SECRET
    BLOGGER_REFRESH_TOKEN
    BLOGGER_BLOG_ID

Install:
    pip install google-auth google-auth-oauthlib requests markdown python-dotenv
"""

import os
import sys
import re
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

BLOGGER_CLIENT_ID     = os.getenv("BLOGGER_CLIENT_ID", "")
BLOGGER_CLIENT_SECRET = os.getenv("BLOGGER_CLIENT_SECRET", "")
BLOGGER_REFRESH_TOKEN = os.getenv("BLOGGER_REFRESH_TOKEN", "")
BLOGGER_BLOG_ID       = os.getenv("BLOGGER_BLOG_ID", "")

POSTS_DIR = ROOT / "content" / "posts"
BASE_URL  = "https://towwiththeflow.com"

TOKEN_URI = "https://oauth2.googleapis.com/token"
API_BASE  = "https://www.googleapis.com/blogger/v3/blogs"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def get_access_token() -> str:
    """Exchange the stored refresh token for a fresh access token."""
    resp = requests.post(TOKEN_URI, data={
        "client_id":     BLOGGER_CLIENT_ID,
        "client_secret": BLOGGER_CLIENT_SECRET,
        "refresh_token": BLOGGER_REFRESH_TOKEN,
        "grant_type":    "refresh_token",
    }, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(f"Token refresh failed {resp.status_code}: {resp.text}")
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# Markdown helpers
# ---------------------------------------------------------------------------

def parse_frontmatter(content: str) -> tuple[dict, str]:
    match = re.match(r'^---\n(.*?)\n---\n(.*)', content, re.DOTALL)
    if not match:
        return {}, content
    fm_text = match.group(1)
    body    = match.group(2).strip()

    meta = {}
    tm = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', fm_text, re.MULTILINE)
    if tm:
        meta['title'] = tm.group(1).strip().strip('"\'')

    tags_inline = re.search(r'^tags:\s*\[(.+?)\]', fm_text, re.MULTILINE)
    if tags_inline:
        meta['tags'] = [t.strip().strip('"\'') for t in tags_inline.group(1).split(',')]
    else:
        tags_block = re.findall(r'^\s*-\s+["\']?(.+?)["\']?\s*$', fm_text, re.MULTILINE)
        if tags_block:
            meta['tags'] = tags_block

    slug_m = re.search(r'^slug:\s*["\']?(.+?)["\']?\s*$', fm_text, re.MULTILINE)
    if slug_m:
        meta['slug'] = slug_m.group(1).strip().strip('"\'')

    return meta, body


def markdown_to_html(md_text: str) -> str:
    """Convert markdown to HTML using the markdown package."""
    try:
        import markdown
        return markdown.markdown(md_text, extensions=['tables', 'nl2br'])
    except ImportError:
        # Minimal fallback if markdown package isn't installed
        html = md_text
        # Headings
        html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$',  r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.+)$',   r'<h1>\1</h1>', html, flags=re.MULTILINE)
        # Bold / italic
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        html = re.sub(r'\*(.+?)\*',     r'<em>\1</em>',         html)
        # Blockquote
        html = re.sub(r'^> (.+)$', r'<blockquote>\1</blockquote>', html, flags=re.MULTILINE)
        # Paragraphs (double newline)
        paras = re.split(r'\n{2,}', html)
        html = '\n'.join(
            p if re.match(r'<(h[1-6]|ul|ol|li|table|blockquote)', p.strip()) else f'<p>{p.strip()}</p>'
            for p in paras if p.strip()
        )
        return html


# ---------------------------------------------------------------------------
# Rewritten body for the test post
# (same information, different phrasing and intro sentence)
# ---------------------------------------------------------------------------

REWRITTEN_BODY = """\
**Bottom line: no.** A broken axle is not something you drive through. Once the axle fails, you lose controlled power delivery to that wheel — and the axle itself can seize, throw the wheel entirely, or tear through the wheel well while you're moving. Get off the road now and call for a tow. There is no safe version of limping this car to a shop.

## What To Do Right Now

1. **Get off the road safely.** If you hear a loud pop or feel a sudden loss of drive, signal and pull over immediately. Don't try to coax it to a parking lot half a mile away.
2. **Switch on your hazards.** Move as far from the travel lane as you can.
3. **Stop driving — even slowly.** A broken axle can drop the wheel or lock up without warning, even at 5 mph.
4. **Call a tow truck.** This car needs a flatbed or wheel-lift tow. Let the driver know a wheel may be compromised so they can position the truck correctly.
5. **Describe the symptoms to the shop.** Tell them the noise you heard — pop, grind, or clunk — and when it started. That helps the tech narrow down whether it's the CV joint, the axle shaft, or the differential.

### Warning Signs Your Axle Is Failing

- Loud clunking when you accelerate or go through a turn
- Vibration that increases under load
- Clicking from the front wheel during turns (a worn CV joint)
- The car pulling hard to one side when you give it gas
- Grease splattered inside the wheel well (a torn CV boot is the early warning)

A clicking CV joint is a warning. A grinding or clunking axle is an emergency.

## Repair Costs to Expect

| Repair | Typical Cost Range |
|---|---|
| CV axle shaft replacement (one side) | $200 – $500 parts + labor |
| CV joint replacement only | $150 – $350 |
| Both front axles | $400 – $900 |

Costs vary by make, model, and drivetrain. Front-wheel-drive vehicles are typically less expensive to repair than AWD models with complex rear axle assemblies.

Delaying the repair will cost you more. A fully failed axle can damage the transmission, differential, wheel bearing, and brake rotor in short order — turning a $300 fix into something well over $1,500.

## Keep Everyone Safe

- **Don't jack the car if you suspect a broken axle.** If the axle snaps while the car is raised, it can fall.
- **Move passengers away from the vehicle** if you're stopped on a busy road shoulder.
- **Set out road flares or reflective triangles** if you have them. A stalled car on a highway shoulder is a serious hazard, especially at night.
- **Check your roadside assistance plan** — AAA, most insurance providers, and manufacturer roadside programs typically cover a tow to the nearest shop.

Not sure if the axle is fully broken or just damaged? Either way, a broken or failing axle almost always announces itself: a sudden change in how the car pulls, an unexpected dragging sensation, or a noise that appeared out of nowhere. Trust your gut and get off the road.
"""


# ---------------------------------------------------------------------------
# Blogger post
# ---------------------------------------------------------------------------

def build_html(body_md: str, slug: str) -> str:
    canonical_url = f"{BASE_URL}/{slug}/"
    body_html = markdown_to_html(body_md)
    footer = (
        f'\n\n<p><em>Originally published at '
        f'<a href="{canonical_url}">towwiththeflow.com/{slug}/</a></em></p>'
    )
    canonical_tag = f'<link rel="canonical" href="{canonical_url}">\n'
    return canonical_tag + body_html + footer


def post_to_blogger(title: str, html: str, labels: list[str], access_token: str) -> dict:
    url = f"{API_BASE}/{BLOGGER_BLOG_ID}/posts/"
    payload = {
        "title":   title,
        "content": html,
        "labels":  labels,
    }
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type":  "application/json",
        },
        json=payload,
        timeout=30,
    )
    return resp.status_code, resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    slug = sys.argv[1] if len(sys.argv) > 1 else "can-i-drive-with-a-broken-axle"

    # Validate env
    missing = [k for k, v in {
        "BLOGGER_CLIENT_ID":     BLOGGER_CLIENT_ID,
        "BLOGGER_CLIENT_SECRET": BLOGGER_CLIENT_SECRET,
        "BLOGGER_REFRESH_TOKEN": BLOGGER_REFRESH_TOKEN,
        "BLOGGER_BLOG_ID":       BLOGGER_BLOG_ID,
    }.items() if not v]
    if missing:
        raise SystemExit(f"ERROR: Missing .env vars: {', '.join(missing)}")

    # Load frontmatter for title + tags; use rewritten body
    post_file = POSTS_DIR / f"{slug}.md"
    if not post_file.exists():
        raise SystemExit(f"ERROR: Post not found: {post_file}")

    meta, _ = parse_frontmatter(post_file.read_text(encoding="utf-8"))
    title  = meta.get("title", slug)
    labels = meta.get("tags", [])

    # Use the rewritten body if this is our test slug, else use the original
    if slug == "can-i-drive-with-a-broken-axle":
        body_md = REWRITTEN_BODY
    else:
        _, body_md = parse_frontmatter(post_file.read_text(encoding="utf-8"))

    html = build_html(body_md, slug)

    print(f"Authenticating...")
    access_token = get_access_token()

    print(f"Posting '{title}' to Blogger blog {BLOGGER_BLOG_ID}...")
    status, data = post_to_blogger(title, html, labels, access_token)

    if status in (200, 201):
        live_url = data.get("url", "(no URL in response)")
        print(f"\nSUCCESS")
        print(f"Live Blogger URL: {live_url}")
        print(f"Post ID: {data.get('id', '')}")
    else:
        print(f"\nFAIL — HTTP {status}")
        print(json.dumps(data, indent=2) if isinstance(data, dict) else data)
        sys.exit(1)


if __name__ == "__main__":
    main()
