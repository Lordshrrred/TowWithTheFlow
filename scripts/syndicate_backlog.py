#!/usr/bin/env python3
"""
Tow With The Flow — Backlog Syndication
Reads all posts from content/posts/, finds the oldest one not yet in
synced-posts.txt, and syndicates it to Dev.to, Hashnode, and Tumblr.
Runs once per day via daily-post.yml — one post per execution.
When all posts are synced, sends a completion email and exits cleanly.
"""

import os
import re
import json
import sys
import smtplib
from datetime import datetime, date
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from dotenv import load_dotenv
import requests
from requests_oauthlib import OAuth1

# ── Setup ──────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

DEVTO_API_KEY       = os.getenv("DEVTO_API_KEY", "")
HASHNODE_API_KEY    = os.getenv("HASHNODE_API_KEY", "")
HASHNODE_PUB_ID     = os.getenv("HASHNODE_PUBLICATION_ID", "")
TUMBLR_CONSUMER_KEY = os.getenv("TUMBLR_CONSUMER_KEY", "")
TUMBLR_CONSUMER_SEC = os.getenv("TUMBLR_CONSUMER_SECRET", "")
TUMBLR_TOKEN        = os.getenv("TUMBLR_TOKEN", "")
TUMBLR_TOKEN_SEC    = os.getenv("TUMBLR_TOKEN_SECRET", "")
TUMBLR_BLOG         = os.getenv("TUMBLR_BLOG_NAME", "")
GMAIL_ADDRESS       = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD  = os.getenv("GMAIL_APP_PASSWORD", "")

BASE_URL    = "https://towwiththeflow.com"
POSTS_DIR   = ROOT / "content" / "posts"
SYNCED_FILE = Path(__file__).parent / "synced-posts.txt"
LOG_FILE    = Path(__file__).parent / "syndication_log.txt"

# Files in content/posts/ that are NOT real blog posts
SKIP_FILES = {"_index.md", "tow-content-log.md"}


# ── Logging ────────────────────────────────────────────────────────────────────
def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] BACKLOG: {msg}\n"
    print(line, end="", flush=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line)


# ── Frontmatter parser ─────────────────────────────────────────────────────────
def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Returns (meta dict, body markdown)."""
    m = re.match(r"^---\n(.*?)\n---\n?(.*)", text, re.DOTALL)
    if not m:
        return {}, text
    fm, body = m.group(1), m.group(2).strip()

    meta: dict = {}
    for field, pattern in [
        ("title",       r'^title:\s*["\']?(.+?)["\']?\s*$'),
        ("description", r'^description:\s*["\']?(.+?)["\']?\s*$'),
        ("date",        r'^date:\s*(.+?)\s*$'),
    ]:
        hit = re.search(pattern, fm, re.MULTILINE)
        if hit:
            meta[field] = hit.group(1).strip().strip("\"'")

    # Tags — inline array style only
    tags_m = re.search(r'^tags:\s*\[(.+?)\]', fm, re.MULTILINE)
    if tags_m:
        meta["tags"] = [t.strip().strip("\"'") for t in tags_m.group(1).split(",")]
    else:
        # Block list style
        block_tags = re.findall(r'^\s*-\s+["\']?(.+?)["\']?\s*$', fm, re.MULTILINE)
        if block_tags:
            meta["tags"] = block_tags

    return meta, body


# ── Post discovery ─────────────────────────────────────────────────────────────
def get_all_posts() -> list[tuple[date, str]]:
    """Return (post_date, slug) sorted oldest-first, skipping non-post files."""
    posts = []
    for f in POSTS_DIR.glob("*.md"):
        if f.name in SKIP_FILES:
            continue
        slug = f.stem
        try:
            text = f.read_text(encoding="utf-8")
            meta, _ = parse_frontmatter(text)
            d = date.fromisoformat(str(meta.get("date", "2000-01-01"))[:10])
        except Exception:
            d = date(2000, 1, 1)
        posts.append((d, slug))
    return sorted(posts)  # oldest first


# ── Synced-posts tracker ───────────────────────────────────────────────────────
def load_synced() -> set[str]:
    if not SYNCED_FILE.exists():
        SYNCED_FILE.write_text("", encoding="utf-8")
        return set()
    lines = SYNCED_FILE.read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip()}


def mark_synced(slug: str):
    with SYNCED_FILE.open("a", encoding="utf-8") as f:
        f.write(slug + "\n")


# ── Markdown helpers ───────────────────────────────────────────────────────────
def strip_markdown(text: str) -> str:
    """Produce readable plain text from markdown for Tumblr NPF."""
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)   # headings
    text = re.sub(r'^>\s?', '', text, flags=re.MULTILINE)         # blockquotes
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)                  # bold
    text = re.sub(r'\*(.+?)\*', r'\1', text)                      # italic
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)         # links
    text = re.sub(r'^\|.+', '', text, flags=re.MULTILINE)         # tables
    text = re.sub(r'^[-]{3,}$', '', text, flags=re.MULTILINE)     # hr
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def split_npf_blocks(text: str, limit: int = 4096) -> list[dict]:
    """Split long text into NPF-compliant blocks (max limit chars each)."""
    blocks = []
    while text:
        if len(text) <= limit:
            blocks.append({"type": "text", "text": text})
            break
        cut = text.rfind('\n\n', 0, limit)
        if cut == -1:
            cut = text.rfind('\n', 0, limit)
        if cut == -1:
            cut = limit
        blocks.append({"type": "text", "text": text[:cut].rstrip()})
        text = text[cut:].lstrip()
    return blocks


# ── Dev.to ─────────────────────────────────────────────────────────────────────
def syndicate_devto(slug: str, meta: dict, body: str) -> tuple[bool, str]:
    if not DEVTO_API_KEY:
        return False, "SKIP: no DEVTO_API_KEY"

    canonical = f"{BASE_URL}/{slug}/"
    tags = [re.sub(r'[^a-z0-9]', '', t.lower()) for t in meta.get("tags", [])[:4]]

    try:
        r = requests.post(
            "https://dev.to/api/articles",
            headers={"api-key": DEVTO_API_KEY, "Content-Type": "application/json"},
            json={"article": {
                "title":         meta.get("title", slug),
                "body_markdown": body,
                "published":     True,
                "tags":          tags,
                "canonical_url": canonical,
                "description":   meta.get("description", ""),
            }},
            timeout=30
        )
        if r.status_code in (200, 201):
            return True, r.json().get("url", "published")
        return False, f"HTTP {r.status_code}: {r.text[:300]}"
    except Exception as e:
        return False, str(e)


# ── Hashnode ───────────────────────────────────────────────────────────────────
def syndicate_hashnode(slug: str, meta: dict, body: str) -> tuple[bool, str]:
    if not HASHNODE_API_KEY or not HASHNODE_PUB_ID:
        return False, "SKIP: no HASHNODE_API_KEY or HASHNODE_PUBLICATION_ID"

    canonical = f"{BASE_URL}/{slug}/"
    cta = (
        "\n\n---\n\n"
        "**Originally published on TowWithTheFlow.com** — "
        f"[Read the full article here]({canonical})"
    )
    body_with_cta = body.rstrip() + cta
    tags = [
        {"name": t, "slug": re.sub(r'[^a-z0-9-]', '-', t.lower())}
        for t in meta.get("tags", [])[:5]
    ]

    # Step 1: createDraft
    create_mutation = """
    mutation CreateDraft($input: CreateDraftInput!) {
      createDraft(input: $input) {
        draft { id }
      }
    }"""
    try:
        r = requests.post(
            "https://gql.hashnode.com",
            headers={"Authorization": HASHNODE_API_KEY, "Content-Type": "application/json"},
            json={"query": create_mutation, "variables": {"input": {
                "title":              meta.get("title", slug),
                "contentMarkdown":    body_with_cta,
                "publicationId":      HASHNODE_PUB_ID,
                "originalArticleURL": canonical,
                "tags":               tags,
            }}},
            timeout=30
        )
        data = r.json()
        draft_id = (data.get("data") or {}).get("createDraft", {}).get("draft", {}).get("id")

        if not draft_id:
            # createDraft not available — fall back to direct publishPost
            raise ValueError(f"createDraft returned no id: {json.dumps(data.get('errors',''))[:200]}")

    except Exception as create_err:
        # Fall back to publishPost (works on all Hashnode plan tiers)
        publish_mutation = """
        mutation PublishPost($input: PublishPostInput!) {
          publishPost(input: $input) {
            post { id url }
          }
        }"""
        try:
            r2 = requests.post(
                "https://gql.hashnode.com",
                headers={"Authorization": HASHNODE_API_KEY, "Content-Type": "application/json"},
                json={"query": publish_mutation, "variables": {"input": {
                    "title":              meta.get("title", slug),
                    "contentMarkdown":    body_with_cta,
                    "publicationId":      HASHNODE_PUB_ID,
                    "originalArticleURL": canonical,
                    "tags":               tags,
                }}},
                timeout=30
            )
            data2 = r2.json()
            post = (data2.get("data") or {}).get("publishPost", {}).get("post", {})
            if post.get("url"):
                return True, post["url"]
            errors = data2.get("errors", [])
            return False, f"publishPost fallback failed: {json.dumps(errors)[:200]}"
        except Exception as e2:
            return False, f"createDraft err: {create_err} | publishPost err: {e2}"

    # Step 2: publishDraft
    publish_draft_mutation = """
    mutation PublishDraft($input: PublishDraftInput!) {
      publishDraft(input: $input) {
        post { id url }
      }
    }"""
    try:
        r3 = requests.post(
            "https://gql.hashnode.com",
            headers={"Authorization": HASHNODE_API_KEY, "Content-Type": "application/json"},
            json={"query": publish_draft_mutation, "variables": {"input": {"draftId": draft_id}}},
            timeout=30
        )
        data3 = r3.json()
        post = (data3.get("data") or {}).get("publishDraft", {}).get("post", {})
        if post.get("url"):
            return True, post["url"]
        errors = data3.get("errors", [])
        return False, f"publishDraft failed: {json.dumps(errors)[:200]}"
    except Exception as e3:
        return False, f"publishDraft exception: {e3}"


# ── Tumblr ─────────────────────────────────────────────────────────────────────
def syndicate_tumblr(slug: str, meta: dict, body: str) -> tuple[bool, str]:
    if not all([TUMBLR_CONSUMER_KEY, TUMBLR_CONSUMER_SEC, TUMBLR_TOKEN, TUMBLR_TOKEN_SEC, TUMBLR_BLOG]):
        return False, "SKIP: missing Tumblr OAuth credentials"

    canonical = f"{BASE_URL}/{slug}/"
    plain = strip_markdown(body)
    body_text = f"{meta.get('title', slug)}\n\n{plain}"

    cta_label    = "Read the full guide on TowWithTheFlow.com"
    cta_sentence = f"{cta_label}: {canonical}"
    link_start   = len(cta_label) + 2   # after ": "
    link_end     = len(cta_sentence)

    tags_raw = meta.get("tags", [])
    tags_str = ",".join(tags_raw) if isinstance(tags_raw, list) else str(tags_raw)

    body_blocks = split_npf_blocks(body_text)
    cta_block = {
        "type": "text",
        "text": cta_sentence,
        "formatting": [{"start": link_start, "end": link_end, "type": "link", "url": canonical}]
    }
    content_blocks = body_blocks + [cta_block]

    oauth = OAuth1(TUMBLR_CONSUMER_KEY, TUMBLR_CONSUMER_SEC, TUMBLR_TOKEN, TUMBLR_TOKEN_SEC)

    try:
        r = requests.post(
            f"https://api.tumblr.com/v2/blog/{TUMBLR_BLOG}/posts",
            auth=oauth,
            json={"content": content_blocks, "tags": tags_str, "state": "published"},
            timeout=30
        )
        if r.status_code in (200, 201):
            post_id = r.json().get("response", {}).get("id", "")
            return True, f"https://{TUMBLR_BLOG}.tumblr.com/post/{post_id}"
        return False, f"HTTP {r.status_code}: {json.dumps(r.json())[:300]}"
    except Exception as e:
        return False, str(e)


# ── Completion email ───────────────────────────────────────────────────────────
def send_completion_email(total: int):
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        log("EMAIL: skipped — GMAIL_ADDRESS or GMAIL_APP_PASSWORD not set")
        return

    body = (
        "Hey Matt,\n\n"
        "All posts on Tow With The Flow have been fully syndicated\n"
        "across Dev.to, Hashnode, and Tumblr.\n\n"
        f"Total posts synced: {total}\n\n"
        "The daily automation is now running on its own.\n"
        "New posts will continue to syndicate automatically.\n\n"
        "- Your TWTF Bot"
    )
    msg = MIMEMultipart()
    msg["From"]    = "towwiththeflowllc@gmail.com"
    msg["To"]      = "earthlingoflight@gmail.com"
    msg["Subject"] = "Backlog Syndication Complete!"
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(msg["From"], msg["To"], msg.as_string())
        log("EMAIL: completion email sent to earthlingoflight@gmail.com")
    except Exception as e:
        log(f"EMAIL: FAILED — {e}")


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    all_posts = get_all_posts()
    synced    = load_synced()
    unsynced  = [(d, slug) for d, slug in all_posts if slug not in synced]

    log(f"Posts total={len(all_posts)}  synced={len(synced)}  unsynced={len(unsynced)}")

    if not unsynced:
        log("All posts synced — sending completion email")
        send_completion_email(len(all_posts))
        sys.exit(0)

    # Pick oldest unsynced
    post_date, slug = unsynced[0]
    log(f"Syndicating: {slug}  (date={post_date})")

    post_file = POSTS_DIR / f"{slug}.md"
    text      = post_file.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(text)

    # ── Dev.to ────────────────────────────────────────────────
    ok, detail = syndicate_devto(slug, meta, body)
    log(f"DEVTO    | {slug} | {'SUCCESS' if ok else 'FAIL'} | {detail}")

    # ── Hashnode ──────────────────────────────────────────────
    ok, detail = syndicate_hashnode(slug, meta, body)
    log(f"HASHNODE | {slug} | {'SUCCESS' if ok else 'FAIL'} | {detail}")

    # ── Tumblr ────────────────────────────────────────────────
    ok, detail = syndicate_tumblr(slug, meta, body)
    log(f"TUMBLR   | {slug} | {'SUCCESS' if ok else 'FAIL'} | {detail}")

    # Mark synced to keep the backlog moving (failures are logged above)
    mark_synced(slug)
    log(f"Marked synced: {slug}  ({len(synced) + 1}/{len(all_posts)} total)")


if __name__ == "__main__":
    main()
