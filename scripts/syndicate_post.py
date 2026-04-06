#!/usr/bin/env python3
"""
Tow With The Flow — Post Syndication (4-Platform Engine)
Called by daily-post.yml at 10:30am UTC — 30 minutes after post generation.
Also called directly: python scripts/syndicate_post.py <slug>

Rules enforced:
  - Backlink check: every post MUST contain towwiththeflow.com before syndication
  - 60-second wait between each attempted platform (skipped platforms don't count)
  - Platform failures are logged and do NOT stop other platforms
  - Email alert if 2+ platforms fail on same day
  - Content variation per platform via Claude API
"""

from __future__ import annotations

import os
import sys
import re
import json
import time
import hashlib
import smtplib
from datetime import datetime, date
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import requests

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

def env_clean(key: str, default: str = "") -> str:
    """Read env var and normalize accidental quoting/whitespace from pasted secrets."""
    val = os.getenv(key, default)
    if not isinstance(val, str):
        return default
    val = val.strip()
    if len(val) >= 2 and (
        (val[0] == '"' and val[-1] == '"') or
        (val[0] == "'" and val[-1] == "'")
    ):
        val = val[1:-1].strip()
    return val


DEVTO_API_KEY         = env_clean("DEVTO_API_KEY")
TUMBLR_CONSUMER_KEY   = env_clean("TUMBLR_CONSUMER_KEY")
TUMBLR_CONSUMER_SECRET= env_clean("TUMBLR_CONSUMER_SECRET")
TUMBLR_TOKEN          = env_clean("TUMBLR_TOKEN")
TUMBLR_TOKEN_SECRET   = env_clean("TUMBLR_TOKEN_SECRET")
TUMBLR_BLOG           = env_clean("TUMBLR_BLOG_NAME")
BLOGGER_CLIENT_ID     = env_clean("BLOGGER_CLIENT_ID")
BLOGGER_CLIENT_SECRET = env_clean("BLOGGER_CLIENT_SECRET")
BLOGGER_REFRESH_TOKEN = env_clean("BLOGGER_REFRESH_TOKEN")
BLOGGER_BLOG_ID       = env_clean("BLOGGER_BLOG_ID")
GITHUB_TOKEN          = env_clean("GITHUB_TOKEN")

# FEEDER token precedence:
# 1) FEEDER_TRIGGER_TOKEN (preferred)
# 2) FEEDER_GITHUB_TOKEN / FEEDER_PAT (legacy aliases)
# 3) GITHUB_TOKEN fallback (may fail for cross-repo writes in Actions)
FEEDER_TOKEN_SOURCE   = ""
for _k in ("FEEDER_TRIGGER_TOKEN", "FEEDER_GITHUB_TOKEN", "FEEDER_PAT", "GITHUB_TOKEN"):
    _v = env_clean(_k)
    if _v:
        FEEDER_TRIGGER_TOKEN = _v
        FEEDER_TOKEN_SOURCE = _k
        break
else:
    FEEDER_TRIGGER_TOKEN = ""

ANTHROPIC_API_KEY     = env_clean("ANTHROPIC_API_KEY")
GMAIL_ADDRESS         = env_clean("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD    = env_clean("GMAIL_APP_PASSWORD")

BASE_URL       = "https://towwiththeflow.com"
POSTS_DIR      = ROOT / "content" / "posts"
LOG_FILE       = Path(__file__).parent / "syndication_log.txt"
SYNCED_FILE    = Path(__file__).parent / "synced-posts.txt"
FEEDER_OWNER   = "Lordshrrred"
FEEDER_REPO    = "TWTF_Feeder"

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


# ── Content variation via Claude ───────────────────────────────────────────────
def variation_length_profile(slug: str, platform: str) -> tuple[str, int]:
    """Choose a deterministic mixed length target by slug+platform.
    Distribution:
      - ~70% medium (500-900)
      - ~20% long (900-1200)
      - ~10% short (420-650)
    Tumblr gets a slightly shorter cap for readability."""
    seed = int(hashlib.sha1(f"{slug}:{platform}".encode("utf-8")).hexdigest()[:8], 16) % 10
    if seed < 7:
        rng = "500-900"
        max_tokens = 1800
    elif seed < 9:
        rng = "900-1200"
        max_tokens = 2200
    else:
        rng = "420-650"
        max_tokens = 1400
    if platform.lower() == "tumblr" and rng == "900-1200":
        rng = "500-850"
        max_tokens = 1700
    return rng, max_tokens


def build_variation_system(length_range: str) -> str:
    return f"""You are rewriting a car breakdown/roadside help article for syndication.
Keep all core facts accurate, but make this a genuinely distinct version.

SEO + uniqueness requirements:
- Use a different headline style and opening hook than the original.
- Reorder sections when natural; do not mirror the exact paragraph order.
- Add one concrete practical element (mini checklist, cost example, or caution scenario).
- Keep the same intent, safety guidance, and canonical destination.

Hard constraints:
- Keep total body length between {length_range} words.
- Do NOT change the canonical URL or final backlink block; preserve it exactly.
- Do NOT use em dashes (—).
- Return ONLY rewritten markdown body (no frontmatter)."""


def get_variation(body: str, platform: str, slug: str) -> str:
    """Get a lightly rephrased version of the body for a specific platform.
    Falls back to original body if Claude API is unavailable."""
    if not ANTHROPIC_API_KEY:
        return body
    try:
        length_range, max_tokens = variation_length_profile(slug, platform)
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-20250514",
            max_tokens=max_tokens,
            system=build_variation_system(length_range),
            messages=[{
                "role": "user",
                "content": (
                    f"Platform: {platform}\n"
                    f"Slug: {slug}\n"
                    f"Target length: {length_range} words\n\n"
                    f"Rewrite this article body:\n\n{body}"
                )
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
    varied_body = get_variation(body, "Dev.to", slug)

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
    varied_body = get_variation(body, "Tumblr", slug)
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
def get_blogger_token() -> tuple[str, str]:
    """Exchange refresh token for an access token.
    Returns (access_token, error_msg). On success error_msg is empty.
    Common Google error codes:
      invalid_grant  — refresh token expired/revoked (needs new OAuth consent)
      invalid_client — client_id or client_secret is wrong
      invalid_request — refresh_token value is malformed
    """
    try:
        r = requests.post("https://oauth2.googleapis.com/token", data={
            "client_id":     BLOGGER_CLIENT_ID,
            "client_secret": BLOGGER_CLIENT_SECRET,
            "refresh_token": BLOGGER_REFRESH_TOKEN,
            "grant_type":    "refresh_token",
        }, timeout=20)
        data = r.json()
    except Exception as e:
        return "", f"network error: {e}"

    token = data.get("access_token", "")
    if token:
        return token, ""

    err  = data.get("error", "unknown_error")
    desc = data.get("error_description", "no description from Google")
    hint = ""
    if err == "invalid_grant":
        hint = " [refresh token is expired or revoked — needs new OAuth consent flow]"
    elif err == "invalid_client":
        hint = " [client_id or client_secret is wrong]"
    elif err == "invalid_request":
        hint = " [refresh_token value is malformed or empty]"
    return "", f"{err}: {desc}{hint}"


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
    # Step 1/3 — preflight: check which credentials are missing (no values exposed)
    missing = [name for name, val in [
        ("BLOGGER_CLIENT_ID",     BLOGGER_CLIENT_ID),
        ("BLOGGER_CLIENT_SECRET", BLOGGER_CLIENT_SECRET),
        ("BLOGGER_REFRESH_TOKEN", BLOGGER_REFRESH_TOKEN),
        ("BLOGGER_BLOG_ID",       BLOGGER_BLOG_ID),
    ] if not val]
    if missing:
        return False, f"SKIP: missing Blogger credentials: {', '.join(missing)}"

    log(f"BLOGGER | {slug} | step 1/3: refreshing access token")
    access_token, token_err = get_blogger_token()
    if not access_token:
        log(f"BLOGGER | {slug} | token refresh failed: {token_err}")
        return False, f"ERROR: token refresh failed — {token_err}"

    log(f"BLOGGER | {slug} | step 2/3: converting markdown to HTML")
    canonical = f"{BASE_URL}/{slug}/"
    varied_body = get_variation(body, "Blogger", slug)
    html_content = md_to_html(varied_body)

    log(f"BLOGGER | {slug} | step 3/3: posting to blog {BLOGGER_BLOG_ID}")
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


# ── Platform: Feeder (TWTF_Feeder) ────────────────────────────────────────────
def syndicate_feeder(slug: str, meta: dict, body: str) -> tuple[bool, str]:
    token = FEEDER_TRIGGER_TOKEN
    if not token:
        return False, "SKIP: no feeder token set (FEEDER_TRIGGER_TOKEN preferred)"

    canonical = f"{BASE_URL}/{slug}/"
    varied_body = get_variation(body, "Feeder", slug)

    # Build a feeder slug (add -guide suffix if not already varied)
    feeder_slug = f"{slug}-guide" if not slug.endswith("-guide") else slug
    feeder_url  = f"https://lordshrrred.github.io/TWTF_Feeder/{feeder_slug}/"

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
        "Authorization": f"token {token}",
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
        if r.status_code == 401:
            return False, (
                "HTTP 401: feeder token rejected (bad/expired token). "
                "Set FEEDER_TRIGGER_TOKEN to a valid PAT with contents:write on "
                f"{FEEDER_OWNER}/{FEEDER_REPO}."
            )
        if r.status_code == 403:
            return False, (
                "HTTP 403: token lacks permission for feeder repo. "
                "Use FEEDER_TRIGGER_TOKEN PAT with contents:write on "
                f"{FEEDER_OWNER}/{FEEDER_REPO}."
            )
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
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    result = load_post(slug)
    if result is None:
        sys.exit(1)
    meta, raw_body = result

    title     = meta.get("title", slug)
    post_date = meta.get("date", "unknown")

    log(f"=== SYNDICATE START: {slug} ===")
    log(f"PREFLIGHT | title: {title}")
    log(f"PREFLIGHT | date: {post_date}")
    log(f"PREFLIGHT | timestamp: {ts}")
    log(f"PREFLIGHT | DEVTO:   {'configured' if DEVTO_API_KEY else 'MISSING — will SKIP'}")
    tumblr_ok = all([TUMBLR_CONSUMER_KEY, TUMBLR_CONSUMER_SECRET, TUMBLR_TOKEN, TUMBLR_TOKEN_SECRET, TUMBLR_BLOG])
    log(f"PREFLIGHT | TUMBLR:  {'configured' if tumblr_ok else 'MISSING — will SKIP'}")
    blogger_ok = all([BLOGGER_CLIENT_ID, BLOGGER_CLIENT_SECRET, BLOGGER_REFRESH_TOKEN, BLOGGER_BLOG_ID])
    log(f"PREFLIGHT | BLOGGER: {'configured' if blogger_ok else 'MISSING — will SKIP'}")
    if FEEDER_TRIGGER_TOKEN and FEEDER_TOKEN_SOURCE != "GITHUB_TOKEN":
        log(f"PREFLIGHT | FEEDER:  configured (source={FEEDER_TOKEN_SOURCE}, dedicated token)")
    elif FEEDER_TRIGGER_TOKEN:
        log(f"PREFLIGHT | FEEDER:  configured (source=GITHUB_TOKEN — may lack cross-repo write)")
    else:
        log(f"PREFLIGHT | FEEDER:  MISSING — will SKIP")

    # Guarantee backlink before anything touches the content
    body = ensure_backlink(raw_body, slug)

    platforms = [
        ("DEVTO",   lambda: syndicate_devto(slug, meta, body)),
        ("TUMBLR",  lambda: syndicate_tumblr(slug, meta, body)),
        ("BLOGGER", lambda: syndicate_blogger(slug, meta, body)),
        ("FEEDER",  lambda: syndicate_feeder(slug, meta, body)),
    ]

    failures  = []
    successes = 0
    attempted = 0

    for platform, fn in platforms:
        if attempted > 0:
            log(f"--- waiting 60s before next platform ---")
            time.sleep(60)

        log(f"{platform} | {slug} | START")
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"unhandled exception: {e}"

        is_skip = detail.startswith("SKIP:")
        if not is_skip:
            attempted += 1

        status = "SUCCESS" if ok else ("SKIP" if is_skip else "FAIL")
        log(f"{platform} | {slug} | {status} | {detail}")

        if ok:
            successes += 1
        elif not is_skip:
            failures.append(f"{platform}: {detail[:100]}")

    log(f"=== SYNDICATE DONE: {slug} | {successes}/4 succeeded | {attempted} attempted | {len(failures)} failed ===")

    if successes >= 1:
        synced = load_synced()
        if slug not in synced:
            mark_synced(slug)
            log(f"SYNCED | {slug} marked in synced-posts.txt")
    else:
        log(f"NOT SYNCED | {slug} — 0 platforms succeeded, not marking as synced")

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
