#!/usr/bin/env python3
"""
Tow With The Flow — Post Syndication (Full 5-Platform Engine)
Called by daily-post.yml at 10:30am UTC — 30 minutes after post generation.
Also called directly: python scripts/syndicate_post.py <slug>

Rules enforced:
  - Backlink check: every post MUST contain towwiththeflow.com before syndication
  - Hashnode warmup: first 7 posts skip Hashnode every other day
  - 60-second wait between each platform
  - Platform failures are logged and do NOT stop other platforms
  - Email alert if 2+ platforms fail on same day
  - Content variation per platform via Claude API
"""

import os
import sys
import re
import json
import time
import smtplib
from datetime import datetime, date
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import requests

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

DEVTO_API_KEY         = os.getenv("DEVTO_API_KEY", "")
HASHNODE_API_KEY      = os.getenv("HASHNODE_API_KEY", "")
HASHNODE_PUB_ID       = os.getenv("HASHNODE_PUBLICATION_ID", "")
HASHNODE_HOST         = os.getenv("HASHNODE_BLOG_URL", "https://towwiththeflowyo.hashnode.dev").replace("https://", "")
TUMBLR_CONSUMER_KEY   = os.getenv("TUMBLR_CONSUMER_KEY", "")
TUMBLR_CONSUMER_SECRET= os.getenv("TUMBLR_CONSUMER_SECRET", "")
TUMBLR_TOKEN          = os.getenv("TUMBLR_TOKEN", "")
TUMBLR_TOKEN_SECRET   = os.getenv("TUMBLR_TOKEN_SECRET", "")
TUMBLR_BLOG           = os.getenv("TUMBLR_BLOG_NAME", "")
BLOGGER_CLIENT_ID     = os.getenv("BLOGGER_CLIENT_ID", "")
BLOGGER_CLIENT_SECRET = os.getenv("BLOGGER_CLIENT_SECRET", "")
BLOGGER_REFRESH_TOKEN = os.getenv("BLOGGER_REFRESH_TOKEN", "")
BLOGGER_BLOG_ID       = os.getenv("BLOGGER_BLOG_ID", "")
GITHUB_TOKEN          = os.getenv("GITHUB_TOKEN", "")
ANTHROPIC_API_KEY     = os.getenv("ANTHROPIC_API_KEY", "")
GMAIL_ADDRESS         = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD    = os.getenv("GMAIL_APP_PASSWORD", "")

BASE_URL       = "https://towwiththeflow.com"
POSTS_DIR      = ROOT / "content" / "posts"
LOG_FILE       = Path(__file__).parent / "syndication_log.txt"
SYNCED_FILE    = Path(__file__).parent / "synced-posts.txt"
WARMUP_FILE    = Path(__file__).parent / "hashnode_warmup.txt"
FEEDER_OWNER   = "Lordshrrred"
FEEDER_REPO    = "TTWF_GithubPages"

# Backlink block injected when missing
BACKLINK_TMPL = (
    "\n\n---\n\n"
    "*Need more roadside help? Visit "
    "[Tow With The Flow]({url}) "
    "for complete guides on car breakdowns and towing.*"
)


# ── Logging ────────────────────────────────────────────────────────────────────
def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    print(line, end="", flush=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line)


# ── Frontmatter parser ─────────────────────────────────────────────────────────
def parse_frontmatter(text: str) -> tuple[dict, str]:
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
    tags_m = re.search(r'^tags:\s*\[(.+?)\]', fm, re.MULTILINE)
    if tags_m:
        meta["tags"] = [t.strip().strip("\"'") for t in tags_m.group(1).split(",")]
    else:
        block_tags = re.findall(r'^\s*-\s+["\']?(.+?)["\']?\s*$', fm, re.MULTILINE)
        if block_tags:
            meta["tags"] = block_tags
    return meta, body


def load_post(slug: str) -> tuple[dict, str] | None:
    post_file = POSTS_DIR / f"{slug}.md"
    if not post_file.exists():
        log(f"ERROR: Post file not found: {post_file}")
        return None
    return parse_frontmatter(post_file.read_text(encoding="utf-8"))


# ── Backlink guard ─────────────────────────────────────────────────────────────
def ensure_backlink(body: str, slug: str) -> str:
    """Return body with backlink block appended if not already present."""
    if BASE_URL in body:
        return body
    log(f"BACKLINK | {slug} | missing — injecting before syndication")
    canonical = f"{BASE_URL}/{slug}/"
    return body.rstrip() + BACKLINK_TMPL.format(url=canonical)


# ── Hashnode warmup ────────────────────────────────────────────────────────────
def read_warmup() -> tuple[int, bool]:
    """Returns (posts_published, warmup_complete)."""
    if not WARMUP_FILE.exists():
        return 0, False
    text = WARMUP_FILE.read_text(encoding="utf-8")
    m_pub = re.search(r'posts_published:\s*(\d+)', text)
    m_done = re.search(r'warmup_complete:\s*(true|false)', text, re.IGNORECASE)
    published = int(m_pub.group(1)) if m_pub else 0
    complete = m_done.group(1).lower() == "true" if m_done else False
    return published, complete


def update_warmup(posts_published: int):
    """Increment posts_published; set warmup_complete when >= 7."""
    complete = posts_published >= 7
    WARMUP_FILE.write_text(
        f"posts_published: {posts_published}\n"
        f"warmup_complete: {'true' if complete else 'false'}\n"
        f"started: 2026-03-26\n"
        f"notes: Hashnode new account warmup — target 1 post every 2 days for 7 days before daily cadence\n",
        encoding="utf-8"
    )
    return complete


def should_syndicate_hashnode(slug: str) -> bool:
    """During warmup (first 7 posts), skip Hashnode every other day."""
    published, complete = read_warmup()
    if complete:
        log(f"HASHNODE | {slug} | warmup complete — syndicating daily")
        return True
    # Skip every other day during warmup: skip if posts_published is odd
    # Day 1: publish (0 published → publish → becomes 1)
    # Day 2: skip
    # Day 3: publish (2 published → publish → becomes 3) etc.
    if published % 2 == 1:
        log(f"HASHNODE | {slug} | warmup day skip (posts_published={published} — every-other-day rule)")
        return False
    log(f"HASHNODE | {slug} | warmup active (posts_published={published}) — syndicating")
    return True


# ── Content variation via Claude ───────────────────────────────────────────────
VARIATION_SYSTEM = """You are rewriting a car breakdown/roadside help article for a specific syndication platform.
Keep all the same facts and structure. Change the phrasing, opening sentence, and wording throughout.
Do NOT change the canonical URL or backlink block at the end — preserve it exactly.
Do NOT use em dashes (—). Return ONLY the rewritten markdown body (no frontmatter).
Keep it between 400-600 words total."""

def get_variation(body: str, platform: str) -> str:
    """Get a lightly rephrased version of the body for a specific platform.
    Falls back to original body if Claude API is unavailable."""
    if not ANTHROPIC_API_KEY:
        return body
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-20250514",
            max_tokens=1200,
            system=VARIATION_SYSTEM,
            messages=[{
                "role": "user",
                "content": f"Platform: {platform}\n\nRewrite this article body:\n\n{body}"
            }]
        )
        result = msg.content[0].text.strip()
        # Ensure backlink survived
        if BASE_URL not in result:
            result = result.rstrip() + "\n\n" + body[body.rfind("---"):]  # restore original backlink section
        return result
    except Exception as e:
        log(f"VARIATION | {platform} | Claude error: {e} — using original body")
        return body


# ── Platform: Dev.to ──────────────────────────────────────────────────────────
def syndicate_devto(slug: str, meta: dict, body: str) -> tuple[bool, str]:
    if not DEVTO_API_KEY:
        return False, "SKIP: no DEVTO_API_KEY"

    canonical = f"{BASE_URL}/{slug}/"
    tags = [re.sub(r'[^a-z0-9]', '', t.lower()) for t in meta.get("tags", [])[:4]]
    varied_body = get_variation(body, "Dev.to")

    try:
        r = requests.post(
            "https://dev.to/api/articles",
            headers={"api-key": DEVTO_API_KEY, "Content-Type": "application/json"},
            json={"article": {
                "title":         meta.get("title", slug),
                "body_markdown": varied_body,
                "published":     True,
                "tags":          tags,
                "canonical_url": canonical,
                "description":   meta.get("description", ""),
            }},
            timeout=30
        )
        if r.status_code in (200, 201):
            return True, r.json().get("url", canonical)
        return False, f"HTTP {r.status_code}: {r.text[:300]}"
    except Exception as e:
        return False, str(e)


# ── Platform: Hashnode ────────────────────────────────────────────────────────
def syndicate_hashnode(slug: str, meta: dict, body: str) -> tuple[bool, str]:
    if not HASHNODE_API_KEY or not HASHNODE_PUB_ID:
        return False, "SKIP: no HASHNODE_API_KEY or HASHNODE_PUBLICATION_ID"
    if not should_syndicate_hashnode(slug):
        return False, "SKIP: Hashnode warmup — every-other-day rule"

    canonical = f"{BASE_URL}/{slug}/"
    varied_body = get_variation(body, "Hashnode")
    tags = [
        {"name": t, "slug": re.sub(r'[^a-z0-9-]', '-', t.lower())}
        for t in meta.get("tags", [])[:5]
    ]

    # Try publishPost directly
    publish_mutation = """
    mutation PublishPost($input: PublishPostInput!) {
      publishPost(input: $input) {
        post { id url }
      }
    }"""
    try:
        r = requests.post(
            "https://gql.hashnode.com",
            headers={"Authorization": HASHNODE_API_KEY, "Content-Type": "application/json"},
            json={"query": publish_mutation, "variables": {"input": {
                "title":              meta.get("title", slug),
                "contentMarkdown":    varied_body,
                "publicationId":      HASHNODE_PUB_ID,
                "originalArticleURL": canonical,
                "tags":               tags,
            }}},
            timeout=30
        )
        data = r.json()
        post = (data.get("data") or {}).get("publishPost", {}).get("post", {})
        if post.get("url"):
            # Update warmup counter
            published, _ = read_warmup()
            new_count = published + 1
            complete = update_warmup(new_count)
            if complete:
                log(f"HASHNODE | {slug} | warmup COMPLETE ({new_count}/7 posts)")
            return True, post["url"]
        errors = data.get("errors", [])
        return False, f"publishPost failed: {json.dumps(errors)[:200]}"
    except Exception as e:
        return False, str(e)


# ── Platform: Tumblr ──────────────────────────────────────────────────────────
def strip_markdown(text: str) -> str:
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^>\s?', '', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = re.sub(r'^\|.+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[-]{3,}$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def split_npf_blocks(text: str, limit: int = 4096) -> list[dict]:
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


def syndicate_tumblr(slug: str, meta: dict, body: str) -> tuple[bool, str]:
    if not all([TUMBLR_CONSUMER_KEY, TUMBLR_CONSUMER_SECRET, TUMBLR_TOKEN, TUMBLR_TOKEN_SECRET, TUMBLR_BLOG]):
        return False, "SKIP: missing Tumblr OAuth credentials"

    try:
        from requests_oauthlib import OAuth1
    except ImportError:
        return False, "ERROR: requests-oauthlib not installed"

    canonical = f"{BASE_URL}/{slug}/"
    varied_body = get_variation(body, "Tumblr")
    plain = strip_markdown(varied_body)
    body_text = f"{meta.get('title', slug)}\n\n{plain}"

    cta_label    = "Read the full guide on TowWithTheFlow.com"
    cta_sentence = f"{cta_label}: {canonical}"
    link_start   = len(cta_label) + 2
    link_end     = len(cta_sentence)

    tags_raw = meta.get("tags", [])
    tags_str = ",".join(tags_raw) if isinstance(tags_raw, list) else str(tags_raw)

    body_blocks  = split_npf_blocks(body_text)
    cta_block    = {
        "type": "text",
        "text": cta_sentence,
        "formatting": [{"start": link_start, "end": link_end, "type": "link", "url": canonical}]
    }
    content_blocks = body_blocks + [cta_block]

    oauth = OAuth1(TUMBLR_CONSUMER_KEY, TUMBLR_CONSUMER_SECRET, TUMBLR_TOKEN, TUMBLR_TOKEN_SECRET)
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


# ── Platform: Blogger ─────────────────────────────────────────────────────────
def get_blogger_token() -> str:
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id":     BLOGGER_CLIENT_ID,
        "client_secret": BLOGGER_CLIENT_SECRET,
        "refresh_token": BLOGGER_REFRESH_TOKEN,
        "grant_type":    "refresh_token",
    }, timeout=20)
    return r.json().get("access_token", "")


def md_to_html(text: str) -> str:
    """Minimal markdown-to-HTML for Blogger."""
    lines = text.split('\n')
    out = []
    for line in lines:
        line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
        line = re.sub(r'\*(.+?)\*', r'<em>\1</em>', line)
        line = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'<a href="\2">\1</a>', line)
        m = re.match(r'^#{1,6}\s+(.+)', line)
        if m:
            n = len(re.match(r'^(#+)', line).group(1))
            line = f"<h{n}>{m.group(1)}</h{n}>"
        elif line.startswith('> '):
            line = f"<blockquote>{line[2:]}</blockquote>"
        elif re.match(r'^\d+\.\s+', line):
            line = re.sub(r'^\d+\.\s+', '', line)
            line = f"<p>{line}</p>"
        elif line.startswith('- ') or line.startswith('• '):
            line = f"<p>{line}</p>"
        elif line.strip() == '' or line.strip() == '---':
            line = '<br>'
        else:
            line = f"<p>{line}</p>" if line.strip() else ''
        out.append(line)
    return '\n'.join(filter(None, out))


def syndicate_blogger(slug: str, meta: dict, body: str) -> tuple[bool, str]:
    if not all([BLOGGER_CLIENT_ID, BLOGGER_CLIENT_SECRET, BLOGGER_REFRESH_TOKEN, BLOGGER_BLOG_ID]):
        return False, "SKIP: missing Blogger credentials"

    canonical = f"{BASE_URL}/{slug}/"
    varied_body = get_variation(body, "Blogger")
    html_content = md_to_html(varied_body)
    access_token = get_blogger_token()
    if not access_token:
        return False, "ERROR: could not refresh Blogger token"

    try:
        r = requests.post(
            f"https://www.googleapis.com/blogger/v3/blogs/{BLOGGER_BLOG_ID}/posts/",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json={
                "title":   meta.get("title", slug),
                "content": html_content,
                "labels":  meta.get("tags", [])[:5],
            },
            timeout=30
        )
        if r.status_code in (200, 201):
            return True, r.json().get("url", "published")
        return False, f"HTTP {r.status_code}: {r.text[:300]}"
    except Exception as e:
        return False, str(e)


# ── Platform: Feeder (TTWF_GithubPages) ───────────────────────────────────────
def syndicate_feeder(slug: str, meta: dict, body: str) -> tuple[bool, str]:
    if not GITHUB_TOKEN:
        return False, "SKIP: no GITHUB_TOKEN"

    canonical = f"{BASE_URL}/{slug}/"
    varied_body = get_variation(body, "Feeder")

    # Build a feeder slug (add -guide suffix if not already varied)
    feeder_slug = f"{slug}-guide" if not slug.endswith("-guide") else slug
    feeder_url  = f"https://lordshrrred.github.io/TTWF_GithubPages/{feeder_slug}/"

    today = date.today().isoformat()
    fm = (
        f"---\n"
        f'title: "{meta.get("title", slug)}"\n'
        f"date: {today}\n"
        f'description: "{meta.get("description", "")}"\n'
        f"tags: {json.dumps(meta.get('tags', []))}\n"
        f'slug: "{feeder_slug}"\n'
        f'canonical: "{canonical}"\n'
        f"---\n\n"
    )
    file_content = fm + varied_body
    import base64
    encoded = base64.b64encode(file_content.encode("utf-8")).decode("ascii")

    api_url = f"https://api.github.com/repos/{FEEDER_OWNER}/{FEEDER_REPO}/contents/content/posts/{feeder_slug}.md"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Content-Type":  "application/json",
    }

    # Check if file exists (to get SHA for update)
    existing = requests.get(api_url, headers=headers, timeout=20)
    sha = existing.json().get("sha") if existing.status_code == 200 else None

    payload = {
        "message": f"Feeder: auto-syndicate {feeder_slug}",
        "content": encoded,
    }
    if sha:
        payload["sha"] = sha

    try:
        r = requests.put(api_url, headers=headers, json=payload, timeout=30)
        if r.status_code in (200, 201):
            return True, feeder_url
        return False, f"HTTP {r.status_code}: {r.text[:300]}"
    except Exception as e:
        return False, str(e)


# ── Email alert ────────────────────────────────────────────────────────────────
def send_failure_alert(slug: str, failures: list[str]):
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        return
    body = (
        f"Hey Matt,\n\n"
        f"Syndication for '{slug}' had {len(failures)} platform failures:\n\n"
        + "\n".join(f"  - {f}" for f in failures)
        + "\n\nCheck syndication_log.txt for details.\n\n- TWTF Bot"
    )
    msg = MIMEMultipart()
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = "earthlingoflight@gmail.com"
    msg["Subject"] = f"TWTF Syndication Alert: {len(failures)} failures for {slug}"
    msg.attach(MIMEText(body, "plain"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, "earthlingoflight@gmail.com", msg.as_string())
        log(f"EMAIL | alert sent for {len(failures)} failures on {slug}")
    except Exception as e:
        log(f"EMAIL | FAILED to send alert: {e}")


# ── Synced-posts tracker ───────────────────────────────────────────────────────
def load_synced() -> set[str]:
    if not SYNCED_FILE.exists():
        SYNCED_FILE.write_text("", encoding="utf-8")
        return set()
    return {l.strip() for l in SYNCED_FILE.read_text(encoding="utf-8").splitlines() if l.strip()}


def mark_synced(slug: str):
    with SYNCED_FILE.open("a", encoding="utf-8") as f:
        f.write(slug + "\n")


# ── Main orchestrator ──────────────────────────────────────────────────────────
def run_syndication(slug: str):
    log(f"=== SYNDICATE START: {slug} ===")

    result = load_post(slug)
    if result is None:
        sys.exit(1)
    meta, raw_body = result

    # Guarantee backlink before anything touches the content
    body = ensure_backlink(raw_body, slug)

    platforms = [
        ("DEVTO",   lambda: syndicate_devto(slug, meta, body)),
        ("HASHNODE",lambda: syndicate_hashnode(slug, meta, body)),
        ("TUMBLR",  lambda: syndicate_tumblr(slug, meta, body)),
        ("BLOGGER", lambda: syndicate_blogger(slug, meta, body)),
        ("FEEDER",  lambda: syndicate_feeder(slug, meta, body)),
    ]

    failures = []
    successes = 0

    for i, (platform, fn) in enumerate(platforms):
        if i > 0:
            log(f"--- waiting 60s before next platform ---")
            time.sleep(60)

        log(f"{platform} | {slug} | syndicating...")
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"unhandled exception: {e}"

        status = "SUCCESS" if ok else "FAIL"
        log(f"{platform} | {slug} | {status} | {detail}")

        if ok:
            successes += 1
        else:
            failures.append(f"{platform}: {detail[:100]}")

    log(f"=== SYNDICATE DONE: {slug} | {successes}/5 succeeded ===")

    # Mark synced if at least 1 platform succeeded
    if successes >= 1:
        synced = load_synced()
        if slug not in synced:
            mark_synced(slug)
            log(f"SYNCED | {slug} marked in synced-posts.txt")

    # Alert if 2+ failures
    if len(failures) >= 2:
        send_failure_alert(slug, failures)

    return successes, failures


def main():
    if len(sys.argv) < 2:
        print("Usage: syndicate_post.py <slug>", file=sys.stderr)
        sys.exit(1)

    slug = sys.argv[1]
    successes, failures = run_syndication(slug)
    sys.exit(0 if successes >= 1 else 1)


if __name__ == "__main__":
    main()
