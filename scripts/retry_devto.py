#!/usr/bin/env python3
"""Retry Dev.to syndication for posts 5-10 that hit rate limits."""

import os
import re
import json
import time
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path("C:/Users/Earth/OneDrive/TowWithTheFlow")
load_dotenv(ROOT / ".env")

DEVTO_API_KEY = os.getenv("DEVTO_API_KEY", "")
POSTS_DIR = ROOT / "content" / "posts"
LOG_FILE = ROOT / "scripts" / "syndication_log.txt"
BASE_URL = "https://towwiththeflow.com"

SLUGS = [
    "car-overheated-can-i-drive-it",
    "battery-dead-but-lights-turn-on",
    "engine-stalls-at-stop-sign-causes",
    "car-shakes-while-driving-slow-speeds",
    "car-makes-grinding-noise-when-driving",
    "what-happens-if-you-run-out-of-oil-while-driving",
]

DELAY = 310  # seconds between posts (Dev.to rate limit: 2 per 5 min)


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
    dm = re.search(r'^description:\s*["\']?(.+?)["\']?\s*$', fm, re.MULTILINE)
    if dm:
        meta['description'] = dm.group(1).strip().strip('"\'')
    tags_inline = re.search(r'^tags:\s*\[(.+?)\]', fm, re.MULTILINE)
    if tags_inline:
        meta['tags'] = [t.strip().strip('"\'') for t in tags_inline.group(1).split(',')]
    else:
        meta['tags'] = re.findall(r'^\s*-\s+["\']?(.+?)["\']?\s*$', fm, re.MULTILINE)
    return meta, body


def post_to_devto(slug: str) -> str:
    """Returns 'success', 'duplicate', or 'fail'."""
    post_file = POSTS_DIR / f"{slug}.md"
    if not post_file.exists():
        log(f"DEVTO | {slug} | ERROR: file not found")
        return 'fail'

    meta, body = parse_frontmatter(post_file.read_text(encoding='utf-8'))
    canonical_url = f"{BASE_URL}/{slug}/"
    tags = [re.sub(r'[^a-z0-9]', '', t.lower()) for t in meta.get('tags', [])[:4]]

    payload = {
        "article": {
            "title": meta.get('title', slug),
            "body_markdown": body,
            "published": True,
            "tags": tags,
            "canonical_url": canonical_url,
            "description": meta.get('description', ''),
        }
    }

    try:
        resp = requests.post(
            "https://dev.to/api/articles",
            headers={"api-key": DEVTO_API_KEY, "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
        if resp.status_code in (200, 201):
            log(f"DEVTO | {slug} | SUCCESS | status={resp.status_code}")
            return 'success'
        elif resp.status_code == 422:
            log(f"DEVTO | {slug} | DUPLICATE | already posted")
            return 'duplicate'
        else:
            try:
                detail = json.dumps(resp.json())[:300]
            except Exception:
                detail = resp.text[:300]
            log(f"DEVTO | {slug} | FAIL | status={resp.status_code} | {detail}")
            return 'fail'
    except Exception as e:
        log(f"DEVTO | {slug} | ERROR | {e}")
        return 'fail'


if __name__ == "__main__":
    if not DEVTO_API_KEY:
        print("ERROR: DEVTO_API_KEY missing from .env")
        raise SystemExit(1)

    print(f"Posting {len(SLUGS)} articles to Dev.to with {DELAY}s delay between each.")
    print("This will take approximately", (len(SLUGS) - 1) * DELAY // 60, "minutes.\n")

    results = {}
    for i, slug in enumerate(SLUGS):
        result = post_to_devto(slug)
        results[slug] = result
        if result == 'fail' and i < len(SLUGS) - 1:
            print(f"  Waiting {DELAY}s before next post...")
            time.sleep(DELAY)
        elif result in ('success', 'duplicate') and i < len(SLUGS) - 1:
            print(f"  Waiting {DELAY}s before next post...")
            time.sleep(DELAY)

    print("\n--- FINAL DEV.TO STATUS ---")
    for slug, status in results.items():
        print(f"  {status.upper():10}  {slug}")
    success = sum(1 for v in results.values() if v == 'success')
    dupe = sum(1 for v in results.values() if v == 'duplicate')
    print(f"\n{success} new, {dupe} already posted, {len(SLUGS)-success-dupe} failed")
