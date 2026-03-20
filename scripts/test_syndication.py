#!/usr/bin/env python3
"""
One-shot syndication test: Hashnode + Tumblr only.
Prints full API responses for debugging.
"""

import os, re, sys, json
from pathlib import Path
from dotenv import load_dotenv
import requests

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

HASHNODE_API_KEY       = os.getenv("HASHNODE_API_KEY", "")
HASHNODE_PUBLICATION_ID = os.getenv("HASHNODE_PUBLICATION_ID", "")
TUMBLR_CONSUMER_KEY    = os.getenv("TUMBLR_CONSUMER_KEY", "")
TUMBLR_CONSUMER_SECRET = os.getenv("TUMBLR_CONSUMER_SECRET", "")
TUMBLR_TOKEN           = os.getenv("TUMBLR_TOKEN", "")
TUMBLR_TOKEN_SECRET    = os.getenv("TUMBLR_TOKEN_SECRET", "")
TUMBLR_BLOG_NAME       = os.getenv("TUMBLR_BLOG_NAME", "")

SLUG        = "tow-truck-denver-co"
POSTS_DIR   = ROOT / "content" / "posts"
BASE_URL    = "https://towwiththeflow.com"
CANONICAL   = f"{BASE_URL}/posts/{SLUG}/"

SEP = "-" * 60


# ── helpers ──────────────────────────────────────────────────

def parse_frontmatter(content: str):
    m = re.match(r'^---\n(.*?)\n---\n(.*)', content, re.DOTALL)
    if not m:
        return {}, content
    fm, body = m.group(1), m.group(2).strip()
    meta = {}
    tm = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', fm, re.MULTILINE)
    if tm: meta['title'] = tm.group(1).strip().strip('"\'')
    dm = re.search(r'^description:\s*["\']?(.+?)["\']?\s*$', fm, re.MULTILINE)
    if dm: meta['description'] = dm.group(1).strip().strip('"\'')
    ti = re.search(r'^tags:\s*\[(.+?)\]', fm, re.MULTILINE)
    if ti:
        meta['tags'] = [t.strip().strip('"\'') for t in ti.group(1).split(',')]
    else:
        meta['tags'] = re.findall(r'^\s*-\s+["\']?(.+?)["\']?\s*$', fm, re.MULTILINE)
    return meta, body


def strip_markdown(text: str) -> str:
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^> \*\*Quick Answer:\*\*\s*', 'Quick Answer: ', text, flags=re.MULTILINE)
    text = re.sub(r'^> ', '', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = re.sub(r'^[-–]{3,}$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\|.+', '', text, flags=re.MULTILINE)   # strip tables
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ── load post ────────────────────────────────────────────────

post_file = POSTS_DIR / f"{SLUG}.md"
if not post_file.exists():
    print(f"ERROR: {post_file} not found"); sys.exit(1)

meta, body = parse_frontmatter(post_file.read_text(encoding='utf-8'))
title  = meta.get('title', SLUG)
tags   = meta.get('tags', [])

print(f"\n{SEP}")
print(f"POST:  {title}")
print(f"SLUG:  {SLUG}")
print(f"TAGS:  {tags}")
print(f"CANONICAL: {CANONICAL}")
print(SEP)


# ══════════════════════════════════════════════════════════════
# HASHNODE
# ══════════════════════════════════════════════════════════════

print(f"\n{'='*60}")
print("HASHNODE TEST")
print('='*60)

if not HASHNODE_API_KEY or not HASHNODE_PUBLICATION_ID:
    print("SKIP: HASHNODE_API_KEY or HASHNODE_PUBLICATION_ID missing")
else:
    mutation = """
    mutation PublishPost($input: PublishPostInput!) {
      publishPost(input: $input) {
        post {
          id
          url
          slug
          title
        }
      }
    }
    """

    hn_tags = [
        {"name": t, "slug": re.sub(r'[^a-z0-9-]', '-', t.lower().replace(' ', '-'))}
        for t in tags[:5]
    ]

    variables = {
        "input": {
            "title": title,
            "contentMarkdown": body,
            "publicationId": HASHNODE_PUBLICATION_ID,
            "originalArticleURL": CANONICAL,
            "tags": hn_tags,
        }
    }

    print(f"Publication ID: {HASHNODE_PUBLICATION_ID}")
    print(f"Tags payload:   {hn_tags}")
    print(f"Sending to:     https://gql.hashnode.com ...")

    try:
        resp = requests.post(
            "https://gql.hashnode.com",
            headers={
                "Authorization": HASHNODE_API_KEY,
                "Content-Type": "application/json",
            },
            json={"query": mutation, "variables": variables},
            timeout=30
        )
        print(f"\nHTTP Status: {resp.status_code}")
        print("Full response body:")
        try:
            data = resp.json()
            print(json.dumps(data, indent=2))
        except Exception:
            print(resp.text)

        # Parse result
        post_url = (data.get('data') or {}).get('publishPost', {}).get('post', {}).get('url', '')
        errors   = data.get('errors', [])
        if post_url:
            print(f"\n✓ HASHNODE SUCCESS")
            print(f"  Live URL: {post_url}")
        elif errors:
            print(f"\n✗ HASHNODE FAILED")
            for e in errors:
                print(f"  Error: {e}")
        else:
            print(f"\n? HASHNODE: No URL and no errors — check response above")

    except Exception as e:
        print(f"\n✗ HASHNODE EXCEPTION: {e}")


# ══════════════════════════════════════════════════════════════
# TUMBLR
# ══════════════════════════════════════════════════════════════

print(f"\n{'='*60}")
print("TUMBLR TEST")
print('='*60)

creds_ok = all([TUMBLR_CONSUMER_KEY, TUMBLR_CONSUMER_SECRET,
                TUMBLR_TOKEN, TUMBLR_TOKEN_SECRET, TUMBLR_BLOG_NAME])
if not creds_ok:
    print("SKIP: one or more Tumblr OAuth credentials missing")
else:
    try:
        from requests_oauthlib import OAuth1
    except ImportError:
        print("ERROR: requests-oauthlib not installed. Run: pip install requests-oauthlib")
        sys.exit(1)

    plain = strip_markdown(body)
    full_text = f"{title}\n\n{plain}\n\nRead the full guide: {CANONICAL}"

    oauth = OAuth1(TUMBLR_CONSUMER_KEY, TUMBLR_CONSUMER_SECRET,
                   TUMBLR_TOKEN, TUMBLR_TOKEN_SECRET)

    npf_payload = {
        "content": [{"type": "text", "text": full_text}],
        "tags": tags,
        "state": "published",
    }

    print(f"Blog:       {TUMBLR_BLOG_NAME}")
    print(f"Endpoint:   https://api.tumblr.com/v2/blog/{TUMBLR_BLOG_NAME}/posts")
    print(f"Tags:       {tags}")
    print(f"Body chars: {len(full_text)}")
    print(f"Sending ...")

    try:
        resp = requests.post(
            f"https://api.tumblr.com/v2/blog/{TUMBLR_BLOG_NAME}/posts",
            auth=oauth,
            json=npf_payload,
            timeout=30
        )
        print(f"\nHTTP Status: {resp.status_code}")
        print("Full response body:")
        try:
            data = resp.json()
            print(json.dumps(data, indent=2))
        except Exception:
            print(resp.text)

        if resp.status_code in (200, 201):
            post_id  = (data.get('response') or {}).get('id', '')
            post_url = (data.get('response') or {}).get('url', '') or \
                       f"https://{TUMBLR_BLOG_NAME}.tumblr.com/post/{post_id}" if post_id else ''
            print(f"\n✓ TUMBLR SUCCESS")
            if post_url:
                print(f"  Post URL: {post_url}")
            elif post_id:
                print(f"  Post ID:  {post_id}")
                print(f"  URL:      https://{TUMBLR_BLOG_NAME}.tumblr.com/post/{post_id}")
        else:
            print(f"\n✗ TUMBLR FAILED (HTTP {resp.status_code})")

    except Exception as e:
        print(f"\n✗ TUMBLR EXCEPTION: {e}")

print(f"\n{SEP}\nDone.\n")
