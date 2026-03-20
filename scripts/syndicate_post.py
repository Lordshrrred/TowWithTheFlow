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
    # PAUSED: Dev.to syndication disabled until workflow is confirmed stable
    log(f"DEVTO | {slug} | SKIP: syndication paused")
    return

    if not DEVTO_API_KEY:  # noqa: unreachable
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
    """Post to Hashnode via GraphQL publishPost mutation.
    Sets canonical URL (originalArticleURL) and appends a visible backlink CTA."""
    if not HASHNODE_API_KEY or not HASHNODE_PUBLICATION_ID:
        log(f"HASHNODE | {slug} | SKIP: no API key or publication ID")
        return

    canonical_url = f"{BASE_URL}/posts/{slug}/"

    # Append a visible, clickable backlink CTA to the post body for SEO value
    title = meta.get('title', slug)
    cta = (
        f"\n\n---\n\n"
        f"**Originally published on TowWithTheFlow.com** — "
        f"[Read the full article here]({canonical_url})"
    )
    body_with_backlink = body.rstrip() + cta

    publish_mutation = """
    mutation PublishPost($input: PublishPostInput!) {
      publishPost(input: $input) {
        post {
          id
          url
        }
      }
    }
    """

    tags = [{"name": t, "slug": re.sub(r'[^a-z0-9-]', '-', t.lower())} for t in meta.get('tags', [])[:5]]

    variables = {
        "input": {
            "title": title,
            "contentMarkdown": body_with_backlink,
            "publicationId": HASHNODE_PUBLICATION_ID,
            "originalArticleURL": canonical_url,
            "tags": tags,
        }
    }

    try:
        resp = requests.post(
            "https://gql.hashnode.com",
            headers={"Authorization": HASHNODE_API_KEY, "Content-Type": "application/json"},
            json={"query": publish_mutation, "variables": variables},
            timeout=30
        )
        data = resp.json()
        post_url = data.get('data', {}).get('publishPost', {}).get('post', {}).get('url', '')
        if post_url:
            log(f"HASHNODE | {slug} | SUCCESS | url={post_url}")
        else:
            errors = data.get('errors', [])
            log(f"HASHNODE | {slug} | FAIL | {json.dumps(errors)[:300]}")

    except Exception as e:
        log(f"HASHNODE | {slug} | ERROR | {e}")


NPF_BLOCK_LIMIT = 4096  # Tumblr hard limit per NPF text block


def _split_npf_blocks(text: str, limit: int = NPF_BLOCK_LIMIT) -> list[dict]:
    """Split text into NPF text blocks, each under the per-block char limit.
    Splits at paragraph boundaries where possible to avoid mid-sentence cuts."""
    blocks = []
    while text:
        if len(text) <= limit:
            blocks.append({"type": "text", "text": text})
            break
        # Find the last double-newline within the limit
        cut = text.rfind('\n\n', 0, limit)
        if cut == -1:
            # No paragraph break found — split at last newline
            cut = text.rfind('\n', 0, limit)
        if cut == -1:
            # No newline at all — hard cut at limit
            cut = limit
        blocks.append({"type": "text", "text": text[:cut].rstrip()})
        text = text[cut:].lstrip()
    return blocks


def syndicate_tumblr(slug: str, meta: dict, body: str):
    """Post to Tumblr via OAuth1 using Neue Post Format (NPF).
    Splits long posts across multiple text blocks (Tumblr limit: 4096 chars each)."""
    if not all([TUMBLR_CONSUMER_KEY, TUMBLR_CONSUMER_SECRET, TUMBLR_TOKEN, TUMBLR_TOKEN_SECRET, TUMBLR_BLOG_NAME]):
        log(f"TUMBLR | {slug} | SKIP: missing OAuth credentials")
        return

    try:
        from requests_oauthlib import OAuth1
    except ImportError:
        log(f"TUMBLR | {slug} | ERROR: requests-oauthlib not installed")
        return

    canonical_url = f"{BASE_URL}/posts/{slug}/"
    title = meta.get('title', slug)
    tags  = meta.get('tags', [])

    # Build plain-text version of the post body (strip markdown)
    plain = body
    plain = re.sub(r'^#{1,6}\s+', '', plain, flags=re.MULTILINE)   # headings
    plain = re.sub(r'^> ', '', plain, flags=re.MULTILINE)          # blockquotes
    plain = re.sub(r'\*\*(.+?)\*\*', r'\1', plain)                 # bold
    plain = re.sub(r'\*(.+?)\*', r'\1', plain)                     # italic
    plain = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', plain)        # links
    plain = re.sub(r'^\|.+', '', plain, flags=re.MULTILINE)        # tables
    plain = re.sub(r'^[-]{3,}$', '', plain, flags=re.MULTILINE)    # hr
    plain = re.sub(r'\n{3,}', '\n\n', plain).strip()

    body_text = f"{title}\n\n{plain}"

    # CTA with inline NPF link formatting — makes the URL a real clickable hyperlink
    cta_label = "Read the full guide on TowWithTheFlow.com"
    cta_sentence = f"{cta_label}: {canonical_url}"
    link_start = len(cta_label) + 2   # after "...: "
    link_end   = len(cta_sentence)

    oauth = OAuth1(
        TUMBLR_CONSUMER_KEY, TUMBLR_CONSUMER_SECRET,
        TUMBLR_TOKEN, TUMBLR_TOKEN_SECRET
    )

    # Tumblr NPF requires tags as a comma-separated STRING, not a JSON array.
    # Passing a list causes error 8001 regardless of content.
    if isinstance(tags, list):
        tags_str = ",".join(tags)
    else:
        tags_str = str(tags)

    # Split body into <=4096-char NPF blocks, then append a dedicated link block
    body_blocks = _split_npf_blocks(body_text)
    cta_block = {
        "type": "text",
        "text": cta_sentence,
        "formatting": [{"start": link_start, "end": link_end, "type": "link", "url": canonical_url}]
    }
    content_blocks = body_blocks + [cta_block]

    log(f"TUMBLR | {slug} | {len(content_blocks)} NPF block(s), total {sum(len(b.get('text','')) for b in content_blocks)} chars")

    npf_payload = {
        "content": content_blocks,
        "tags": tags_str,
        "state": "published",
    }

    try:
        resp = requests.post(
            f"https://api.tumblr.com/v2/blog/{TUMBLR_BLOG_NAME}/posts",
            auth=oauth,
            json=npf_payload,
            timeout=30
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            post_id = (data.get('response') or {}).get('id', '')
            post_url = f"https://{TUMBLR_BLOG_NAME}.tumblr.com/post/{post_id}" if post_id else ''
            log(f"TUMBLR | {slug} | SUCCESS | status={resp.status_code} | url={post_url}")
        else:
            try:
                detail = json.dumps(resp.json())[:400]
            except Exception:
                detail = resp.text[:400]
            log(f"TUMBLR | {slug} | FAIL | status={resp.status_code} | {detail}")
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
