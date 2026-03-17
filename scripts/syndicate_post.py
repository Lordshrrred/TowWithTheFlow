#!/usr/bin/env python3
"""
Tow With The Flow — Post Syndication
Syndicates a Hugo post to Dev.to, Hashnode, and Tumblr.
Called automatically by generate_post.py with the post slug.
Canonical URL always points back to towwiththeflow.com.
"""

import os
import sys
import re
import json
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

DEVTO_API_KEY = os.getenv("DEVTO_API_KEY", "")
HASHNODE_API_KEY = os.getenv("HASHNODE_API_KEY", "")
HASHNODE_PUBLICATION_ID = os.getenv("HASHNODE_PUBLICATION_ID", "")
TUMBLR_CONSUMER_KEY = os.getenv("TUMBLR_CONSUMER_KEY", "")
TUMBLR_CONSUMER_SECRET = os.getenv("TUMBLR_CONSUMER_SECRET", "")
TUMBLR_TOKEN = os.getenv("TUMBLR_TOKEN", "")
TUMBLR_TOKEN_SECRET = os.getenv("TUMBLR_TOKEN_SECRET", "")
TUMBLR_BLOG_NAME = os.getenv("TUMBLR_BLOG_NAME", "")

LOG_FILE = Path(__file__).parent / "syndication_log.txt"
POSTS_DIR = ROOT / "content" / "posts"
BASE_URL = "https://towwiththeflow.com"


def log(message: str):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    entry = f"[{timestamp}] {message}\n"
    print(entry, end='')
    with LOG_FILE.open('a', encoding='utf-8') as f:
        f.write(entry)


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse Hugo frontmatter and return (metadata dict, body markdown)"""
    match = re.match(r'^---\n(.*?)\n---\n(.*)', content, re.DOTALL)
    if not match:
        return {}, content

    fm_text = match.group(1)
    body = match.group(2).strip()

    meta = {}
    # Parse title
    tm = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', fm_text, re.MULTILINE)
    if tm:
        meta['title'] = tm.group(1).strip().strip('"\'')

    # Parse description
    dm = re.search(r'^description:\s*["\']?(.+?)["\']?\s*$', fm_text, re.MULTILINE)
    if dm:
        meta['description'] = dm.group(1).strip().strip('"\'')

    # Parse tags
    # Handle both inline array and block list styles
    tags_inline = re.search(r'^tags:\s*\[(.+?)\]', fm_text, re.MULTILINE)
    if tags_inline:
        raw = tags_inline.group(1)
        meta['tags'] = [t.strip().strip('"\'') for t in raw.split(',')]
    else:
        tags_block = re.findall(r'^\s*-\s+["\']?(.+?)["\']?\s*$', fm_text, re.MULTILINE)
        if tags_block:
            meta['tags'] = tags_block

    return meta, body


def load_post(slug: str) -> tuple[dict, str] | None:
    post_file = POSTS_DIR / f"{slug}.md"
    if not post_file.exists():
        log(f"ERROR: Post file not found: {post_file}")
        return None
    content = post_file.read_text(encoding='utf-8')
    return parse_frontmatter(content)


def syndicate_devto(slug: str, meta: dict, body: str):
    """Post to Dev.to with canonical URL"""
    if not DEVTO_API_KEY:
        log(f"DEVTO | {slug} | SKIP: no API key")
        return

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
            timeout=30
        )
        if resp.status_code in (200, 201):
            log(f"DEVTO | {slug} | SUCCESS | status={resp.status_code}")
        else:
            log(f"DEVTO | {slug} | FAIL | status={resp.status_code} | {resp.text[:200]}")
    except Exception as e:
        log(f"DEVTO | {slug} | ERROR | {e}")


def syndicate_hashnode(slug: str, meta: dict, body: str):
    """Post to Hashnode via GraphQL with canonical URL"""
    if not HASHNODE_API_KEY or not HASHNODE_PUBLICATION_ID:
        log(f"HASHNODE | {slug} | SKIP: no API key or publication ID")
        return

    canonical_url = f"{BASE_URL}/{slug}/"

    # Step 1: Create draft
    create_mutation = """
    mutation CreateDraft($input: CreateDraftInput!) {
      createDraft(input: $input) {
        draft {
          id
        }
      }
    }
    """

    tags = [{"name": t, "slug": re.sub(r'[^a-z0-9-]', '-', t.lower())} for t in meta.get('tags', [])[:5]]

    variables = {
        "input": {
            "title": meta.get('title', slug),
            "contentMarkdown": body,
            "publicationId": HASHNODE_PUBLICATION_ID,
            "canonicalUrl": canonical_url,
            "tags": tags,
        }
    }

    try:
        resp = requests.post(
            "https://gql.hashnode.com",
            headers={"Authorization": HASHNODE_API_KEY, "Content-Type": "application/json"},
            json={"query": create_mutation, "variables": variables},
            timeout=30
        )
        data = resp.json()
        draft_id = data.get('data', {}).get('createDraft', {}).get('draft', {}).get('id')

        if not draft_id:
            log(f"HASHNODE | {slug} | FAIL (create draft) | {json.dumps(data)[:300]}")
            return

        # Step 2: Publish draft
        publish_mutation = """
        mutation PublishDraft($input: PublishDraftInput!) {
          publishDraft(input: $input) {
            post {
              id
              url
            }
          }
        }
        """
        pub_resp = requests.post(
            "https://gql.hashnode.com",
            headers={"Authorization": HASHNODE_API_KEY, "Content-Type": "application/json"},
            json={"query": publish_mutation, "variables": {"input": {"draftId": draft_id}}},
            timeout=30
        )
        pub_data = pub_resp.json()
        post_url = pub_data.get('data', {}).get('publishDraft', {}).get('post', {}).get('url', '')
        if post_url:
            log(f"HASHNODE | {slug} | SUCCESS | url={post_url}")
        else:
            log(f"HASHNODE | {slug} | FAIL (publish) | {json.dumps(pub_data)[:300]}")

    except Exception as e:
        log(f"HASHNODE | {slug} | ERROR | {e}")


def syndicate_tumblr(slug: str, meta: dict, body: str):
    """Post to Tumblr via OAuth1"""
    if not all([TUMBLR_CONSUMER_KEY, TUMBLR_CONSUMER_SECRET, TUMBLR_TOKEN, TUMBLR_TOKEN_SECRET, TUMBLR_BLOG_NAME]):
        log(f"TUMBLR | {slug} | SKIP: missing OAuth credentials")
        return

    try:
        from requests_oauthlib import OAuth1
    except ImportError:
        log(f"TUMBLR | {slug} | ERROR: requests-oauthlib not installed")
        return

    canonical_url = f"{BASE_URL}/{slug}/"
    title = meta.get('title', slug)

    # Convert markdown to basic HTML (simple conversion)
    html_body = body
    # Blockquotes
    html_body = re.sub(r'^> (.+)$', r'<blockquote>\1</blockquote>', html_body, flags=re.MULTILINE)
    # Bold
    html_body = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html_body)
    # H2
    html_body = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html_body, flags=re.MULTILINE)
    # H3
    html_body = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html_body, flags=re.MULTILINE)
    # Numbered lists
    html_body = re.sub(r'^\d+\. (.+)$', r'<li>\1</li>', html_body, flags=re.MULTILINE)
    # Paragraphs (wrap consecutive non-tag lines)
    paragraphs = []
    for line in html_body.split('\n'):
        stripped = line.strip()
        if stripped and not stripped.startswith('<'):
            paragraphs.append(f'<p>{stripped}</p>')
        else:
            paragraphs.append(stripped)
    html_body = '\n'.join(paragraphs)

    full_html = (
        f"<h1>{title}</h1>\n"
        f"{html_body}\n"
        f'<p><a href="{canonical_url}">Read the full guide at towwiththeflow.com</a></p>'
    )

    oauth = OAuth1(
        TUMBLR_CONSUMER_KEY, TUMBLR_CONSUMER_SECRET,
        TUMBLR_TOKEN, TUMBLR_TOKEN_SECRET
    )

    payload = {
        "type": "html",
        "state": "published",
        "title": title,
        "body": full_html,
        "tags": ",".join(meta.get('tags', [])),
        "native_inline_images": True,
    }

    try:
        resp = requests.post(
            f"https://api.tumblr.com/v2/blog/{TUMBLR_BLOG_NAME}/posts",
            auth=oauth,
            data=payload,
            timeout=30
        )
        data = resp.json()
        if data.get('meta', {}).get('status') in (200, 201) or data.get('response', {}).get('id'):
            log(f"TUMBLR | {slug} | SUCCESS")
        else:
            log(f"TUMBLR | {slug} | FAIL | {json.dumps(data)[:300]}")
    except Exception as e:
        log(f"TUMBLR | {slug} | ERROR | {e}")


def main():
    if len(sys.argv) < 2:
        print("Usage: syndicate_post.py <slug>", file=sys.stderr)
        sys.exit(1)

    slug = sys.argv[1]
    log(f"--- Syndicating: {slug} ---")

    result = load_post(slug)
    if result is None:
        sys.exit(1)

    meta, body = result

    syndicate_devto(slug, meta, body)
    syndicate_hashnode(slug, meta, body)
    syndicate_tumblr(slug, meta, body)

    log(f"--- Done syndicating: {slug} ---")


if __name__ == "__main__":
    main()
