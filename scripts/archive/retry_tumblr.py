#!/usr/bin/env python3
"""One-time script: retry Tumblr syndication for the first 10 posts."""

import os
import re
import sys
import json
import time
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path("C:/Users/Earth/OneDrive/TowWithTheFlow")
load_dotenv(ROOT / ".env")

TUMBLR_CONSUMER_KEY    = os.getenv("TUMBLR_CONSUMER_KEY", "")
TUMBLR_CONSUMER_SECRET = os.getenv("TUMBLR_CONSUMER_SECRET", "")
TUMBLR_TOKEN           = os.getenv("TUMBLR_TOKEN", "")
TUMBLR_TOKEN_SECRET    = os.getenv("TUMBLR_TOKEN_SECRET", "")
TUMBLR_BLOG_NAME       = os.getenv("TUMBLR_BLOG_NAME", "")
POSTS_DIR              = ROOT / "content" / "posts"
LOG_FILE               = ROOT / "scripts" / "syndication_log.txt"
BASE_URL               = "https://towwiththeflow.com"

SLUGS = [
    "can-i-drive-with-a-broken-axle",
    "car-wont-start-clicking-noise-what-to-do",
    "car-died-while-driving-what-now",
    "what-to-do-if-your-car-breaks-down-at-night",
    "car-overheated-can-i-drive-it",
    "battery-dead-but-lights-turn-on",
    "engine-stalls-at-stop-sign-causes",
    "car-shakes-while-driving-slow-speeds",
    "car-makes-grinding-noise-when-driving",
    "what-happens-if-you-run-out-of-oil-while-driving",
]


def log(msg: str):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open('a', encoding='utf-8') as f:
        f.write(line + "\n")


def parse_frontmatter(content: str) -> tuple[dict, str]:
    match = re.match(r'^---\n(.*?)\n---\n(.*)', content, re.DOTALL)
    if not match:
        return {}, content
    fm, body = match.group(1), match.group(2).strip()
    meta = {}
    tm = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', fm, re.MULTILINE)
    if tm:
        meta['title'] = tm.group(1).strip().strip('"\'')
    tags_inline = re.search(r'^tags:\s*\[(.+?)\]', fm, re.MULTILINE)
    if tags_inline:
        meta['tags'] = [t.strip().strip('"\'') for t in tags_inline.group(1).split(',')]
    else:
        meta['tags'] = re.findall(r'^\s*-\s+["\']?(.+?)["\']?\s*$', fm, re.MULTILINE)
    return meta, body


def md_to_plain(body: str) -> str:
    """Strip markdown to plain text for NPF posting."""
    t = body
    t = re.sub(r'^#{1,6}\s+', '', t, flags=re.MULTILINE)
    t = re.sub(r'^> ', '', t, flags=re.MULTILINE)
    t = re.sub(r'\*\*(.+?)\*\*', r'\1', t)
    t = re.sub(r'\*(.+?)\*', r'\1', t)
    t = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', t)
    return t.strip()


def post_to_tumblr(slug: str) -> bool:
    post_file = POSTS_DIR / f"{slug}.md"
    if not post_file.exists():
        log(f"TUMBLR | {slug} | ERROR: file not found")
        return False

    meta, body = parse_frontmatter(post_file.read_text(encoding='utf-8'))
    title = meta.get('title', slug)
    tags  = meta.get('tags', [])
    canonical_url = f"{BASE_URL}/{slug}/"

    plain = md_to_plain(body)
    full_text = f"{title}\n\n{plain}\n\nRead the full guide: {canonical_url}"

    try:
        from requests_oauthlib import OAuth1
    except ImportError:
        log(f"TUMBLR | {slug} | ERROR: requests-oauthlib not installed")
        return False

    oauth = OAuth1(
        TUMBLR_CONSUMER_KEY, TUMBLR_CONSUMER_SECRET,
        TUMBLR_TOKEN, TUMBLR_TOKEN_SECRET
    )

    # Neue Post Format (NPF) - bypasses legacy type=text which returns error 8001
    npf_payload = {
        "content": [{"type": "text", "text": full_text}],
        "tags": tags if isinstance(tags, list) else [t.strip() for t in str(tags).split(',') if t.strip()],
        "state": "published",
    }

    try:
        resp = requests.post(
            f"https://api.tumblr.com/v2/blog/{TUMBLR_BLOG_NAME}/posts",
            auth=oauth,
            json=npf_payload,
            timeout=30,
        )
        if resp.status_code in (200, 201):
            log(f"TUMBLR | {slug} | SUCCESS | status={resp.status_code}")
            return True
        else:
            try:
                detail = json.dumps(resp.json())[:400]
            except Exception:
                detail = resp.text[:400]
            log(f"TUMBLR | {slug} | FAIL | status={resp.status_code} | {detail}")
            return False
    except Exception as e:
        log(f"TUMBLR | {slug} | ERROR | {e}")
        return False


if __name__ == "__main__":
    if not all([TUMBLR_CONSUMER_KEY, TUMBLR_CONSUMER_SECRET, TUMBLR_TOKEN, TUMBLR_TOKEN_SECRET, TUMBLR_BLOG_NAME]):
        print("ERROR: Tumblr credentials missing from .env")
        sys.exit(1)

    print(f"Blog: {TUMBLR_BLOG_NAME}  |  Posts: {len(SLUGS)}")
    results = {}
    for i, slug in enumerate(SLUGS):
        ok = post_to_tumblr(slug)
        results[slug] = "SUCCESS" if ok else "FAIL"
        if i < len(SLUGS) - 1:
            time.sleep(10)

    print("\n--- FINAL TUMBLR STATUS ---")
    for slug, status in results.items():
        print(f"  {status}  {slug}")
    success = sum(1 for v in results.values() if v == "SUCCESS")
    print(f"\n{success}/{len(SLUGS)} succeeded")
