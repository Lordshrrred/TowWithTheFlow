#!/usr/bin/env python3
"""
TWTF Live Syndication Test — towing-cost-albuquerque-new-mexico
Runs all platforms, prints FULL raw responses, no catches hidden.
"""

import os, sys, re, json, base64
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
import requests

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

DEVTO_API_KEY          = os.getenv("DEVTO_API_KEY", "")
HASHNODE_API_KEY       = os.getenv("HASHNODE_API_KEY", "")
HASHNODE_PUB_ID        = os.getenv("HASHNODE_PUBLICATION_ID", "")
TUMBLR_CONSUMER_KEY    = os.getenv("TUMBLR_CONSUMER_KEY", "")
TUMBLR_CONSUMER_SECRET = os.getenv("TUMBLR_CONSUMER_SECRET", "")
TUMBLR_TOKEN           = os.getenv("TUMBLR_TOKEN", "")
TUMBLR_TOKEN_SECRET    = os.getenv("TUMBLR_TOKEN_SECRET", "")
TUMBLR_BLOG_NAME       = os.getenv("TUMBLR_BLOG_NAME", "towwiththeflow")
BLOGGER_CLIENT_ID      = os.getenv("BLOGGER_CLIENT_ID", "")
BLOGGER_CLIENT_SECRET  = os.getenv("BLOGGER_CLIENT_SECRET", "")
BLOGGER_REFRESH_TOKEN  = os.getenv("BLOGGER_REFRESH_TOKEN", "")
BLOGGER_BLOG_ID        = os.getenv("BLOGGER_BLOG_ID", "")
GITHUB_TOKEN           = os.getenv("GITHUB_TOKEN", "")

SLUG        = "towing-cost-albuquerque-new-mexico"
BASE_URL    = "https://towwiththeflow.com"
CANONICAL   = f"{BASE_URL}/{SLUG}/"
POST_FILE   = ROOT / "content" / "posts" / f"{SLUG}.md"
LOG_FILE    = ROOT / "scripts" / "syndication_log.txt"
SYNCED_FILE = ROOT / "scripts" / "synced-posts.txt"
DIVIDER     = "=" * 70


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{ts}] {msg}\n"
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(entry)


def parse_post(path):
    txt = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)", txt, re.DOTALL)
    if not m:
        return {}, txt
    fm, body = m.group(1), m.group(2).strip()
    meta = {}
    tm = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', fm, re.MULTILINE)
    if tm:
        meta["title"] = tm.group(1).strip().strip("\"'")
    dm = re.search(r'^description:\s*["\']?(.+?)["\']?\s*$', fm, re.MULTILINE)
    if dm:
        meta["description"] = dm.group(1).strip().strip("\"'")
    tags_m = re.search(r"^tags:\s*\[(.+?)\]", fm, re.MULTILINE)
    if tags_m:
        meta["tags"] = [t.strip().strip("\"'") for t in tags_m.group(1).split(",")]
    return meta, body


def md_to_html(md_text):
    import markdown
    return markdown.markdown(md_text, extensions=["extra"])


# ── Boot ──────────────────────────────────────────────────────────────────────
print(f"\n{DIVIDER}")
print("TWTF LIVE SYNDICATION TEST")
print(f"Post: {SLUG}")
print(f"Time: {datetime.now().isoformat()}")
print(DIVIDER)

meta, body = parse_post(POST_FILE)
TITLE     = meta.get("title", SLUG)
DESC      = meta.get("description", "")
TAGS      = meta.get("tags", ["towing"])
BODY_HTML = md_to_html(body)

print(f"\nTitle  : {TITLE}")
print(f"Tags   : {TAGS}")
print(f"Canon  : {CANONICAL}")
print(f"Body   : {len(body)} chars markdown / {len(BODY_HTML)} chars HTML\n")

log(f"--- Syndicating: {SLUG} ---")
results = {}


# ─────────────────────────────────────────────────────────────────────────────
# PLATFORM 1: DEV.TO
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{'─'*70}")
print("PLATFORM 1: DEV.TO")
print(f"{'─'*70}")

devto_tags = [re.sub(r"[^a-z0-9]", "", t.lower())[:20] for t in TAGS[:4]]
devto_tags = [t for t in devto_tags if t] or ["towing"]

devto_payload = {
    "article": {
        "title": TITLE,
        "body_markdown": body,
        "published": True,
        "canonical_url": CANONICAL,
        "tags": devto_tags,
        "description": DESC,
    }
}

print(f"\nAPI CALL:")
print(f"  POST https://dev.to/api/articles")
print(f"  api-key: {DEVTO_API_KEY[:8]}...")
print(f"  Payload tags: {devto_tags}")
print(f"  body_markdown length: {len(body)} chars\n")

devto_r = requests.post(
    "https://dev.to/api/articles",
    json=devto_payload,
    headers={"api-key": DEVTO_API_KEY, "Content-Type": "application/json"},
    timeout=30,
)

print(f"HTTP STATUS: {devto_r.status_code}")
print("FULL RESPONSE:")
try:
    print(json.dumps(devto_r.json(), indent=2))
except Exception:
    print(devto_r.text)

if devto_r.status_code in (200, 201):
    url = devto_r.json().get("url", "")
    print(f"\n[RESULT] DEV.TO SUCCESS — {url}")
    log(f"DEVTO | {SLUG} | SUCCESS | status={devto_r.status_code} | url={url}")
    results["dev"] = {"ok": True, "url": url}
else:
    print(f"\n[RESULT] DEV.TO FAILED — HTTP {devto_r.status_code}")
    log(f"DEVTO | {SLUG} | FAIL | status={devto_r.status_code} | {devto_r.text[:300]}")
    results["dev"] = {"ok": False, "error": f"HTTP {devto_r.status_code}: {devto_r.text[:300]}"}


# ─────────────────────────────────────────────────────────────────────────────
# PLATFORM 2: HASHNODE
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{'─'*70}")
print("PLATFORM 2: HASHNODE")
print(f"{'─'*70}")

hn_tags = [
    {"slug": re.sub(r"[^a-z0-9-]", "-", t.lower().replace(" ", "-")).strip("-"), "name": t}
    for t in TAGS[:5]
]

hn_mutation = """
mutation PublishPost($input: PublishPostInput!) {
  publishPost(input: $input) {
    post {
      id
      title
      url
    }
  }
}
"""

hn_vars = {
    "input": {
        "title": TITLE,
        "contentMarkdown": body,
        "publicationId": HASHNODE_PUB_ID,
        "tags": hn_tags,
        "originalArticleURL": CANONICAL,
        "metaTags": {"description": DESC},
    }
}

print(f"\nAPI CALL:")
print(f"  POST https://gql.hashnode.com")
print(f"  Authorization: {HASHNODE_API_KEY[:8]}...")
print(f"  publicationId: {HASHNODE_PUB_ID}")
print(f"  tags: {hn_tags}")
print(f"  originalArticleURL: {CANONICAL}\n")

hn_r = requests.post(
    "https://gql.hashnode.com",
    json={"query": hn_mutation, "variables": hn_vars},
    headers={"Authorization": HASHNODE_API_KEY, "Content-Type": "application/json"},
    timeout=30,
)

print(f"HTTP STATUS: {hn_r.status_code}")
print("FULL RESPONSE:")
try:
    print(json.dumps(hn_r.json(), indent=2))
except Exception:
    print(hn_r.text)

hn_data = hn_r.json() if hn_r.status_code == 200 else {}
if hn_r.status_code == 200 and "errors" not in hn_data:
    post_data = hn_data.get("data", {}).get("publishPost", {}).get("post", {})
    url = post_data.get("url", "")
    print(f"\n[RESULT] HASHNODE SUCCESS — {url}")
    log(f"HASHNODE | {SLUG} | SUCCESS | url={url}")
    results["hash"] = {"ok": True, "url": url}
else:
    err = hn_data.get("errors", hn_r.text) if hn_r.status_code == 200 else hn_r.text
    print(f"\n[RESULT] HASHNODE FAILED — HTTP {hn_r.status_code}")
    log(f"HASHNODE | {SLUG} | FAIL | status={hn_r.status_code} | {str(err)[:300]}")
    results["hash"] = {"ok": False, "error": str(err)[:300]}


# ─────────────────────────────────────────────────────────────────────────────
# PLATFORM 3: TUMBLR (OAuth1)
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{'─'*70}")
print("PLATFORM 3: TUMBLR (OAuth1)")
print(f"{'─'*70}")

from requests_oauthlib import OAuth1

tumblr_content = (
    f"<p><strong>{DESC}</strong></p>\n\n"
    + BODY_HTML
    + f'\n<p>Originally published at <a href="{CANONICAL}">{CANONICAL}</a></p>'
)

tumblr_url = f"https://api.tumblr.com/v2/blog/{TUMBLR_BLOG_NAME}.tumblr.com/post"

tumblr_payload = {
    "type": "text",
    "title": TITLE,
    "body": tumblr_content,
    "tags": ",".join(TAGS[:5]),
}

oauth = OAuth1(
    TUMBLR_CONSUMER_KEY,
    TUMBLR_CONSUMER_SECRET,
    TUMBLR_TOKEN,
    TUMBLR_TOKEN_SECRET,
)

print(f"\nAPI CALL:")
print(f"  POST {tumblr_url}")
print(f"  Auth: OAuth1 consumer_key={TUMBLR_CONSUMER_KEY[:8]}... token={TUMBLR_TOKEN[:8]}...")
print(f"  type: text")
print(f"  title: {TITLE[:60]}")
print(f"  tags: {TAGS[:5]}")
print(f"  body length: {len(tumblr_content)} chars HTML\n")

tumblr_r = requests.post(tumblr_url, data=tumblr_payload, auth=oauth, timeout=30)

print(f"HTTP STATUS: {tumblr_r.status_code}")
print("FULL RESPONSE:")
try:
    print(json.dumps(tumblr_r.json(), indent=2))
except Exception:
    print(tumblr_r.text)

if tumblr_r.status_code == 201:
    data = tumblr_r.json()
    resp = data.get("response", {})
    if isinstance(resp, dict):
        post_id = resp.get("id", "")
    elif isinstance(resp, list) and resp:
        post_id = resp[0]
    else:
        post_id = ""
    url = f"https://www.tumblr.com/blog/{TUMBLR_BLOG_NAME}/{post_id}" if post_id else f"https://{TUMBLR_BLOG_NAME}.tumblr.com"
    print(f"\n[RESULT] TUMBLR SUCCESS — {url}")
    log(f"TUMBLR | {SLUG} | SUCCESS | status=201 | url={url}")
    results["tumblr"] = {"ok": True, "url": url}
else:
    print(f"\n[RESULT] TUMBLR FAILED — HTTP {tumblr_r.status_code}")
    log(f"TUMBLR | {SLUG} | FAIL | status={tumblr_r.status_code} | {tumblr_r.text[:300]}")
    results["tumblr"] = {"ok": False, "error": f"HTTP {tumblr_r.status_code}: {tumblr_r.text[:300]}"}


# ─────────────────────────────────────────────────────────────────────────────
# PLATFORM 4: BLOGGER (OAuth2 refresh token)
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{'─'*70}")
print("PLATFORM 4: BLOGGER (OAuth2)")
print(f"{'─'*70}")

print(f"\nSTEP 1: Refresh access token")
print(f"  POST https://oauth2.googleapis.com/token")
print(f"  client_id: {BLOGGER_CLIENT_ID[:40]}...")
print(f"  grant_type: refresh_token\n")

token_r = requests.post(
    "https://oauth2.googleapis.com/token",
    data={
        "client_id":     BLOGGER_CLIENT_ID,
        "client_secret": BLOGGER_CLIENT_SECRET,
        "refresh_token": BLOGGER_REFRESH_TOKEN,
        "grant_type":    "refresh_token",
    },
    timeout=15,
)

print(f"HTTP STATUS: {token_r.status_code}")
try:
    td = token_r.json()
    masked = {k: (v[:20] + "..." if k == "access_token" and isinstance(v, str) else v) for k, v in td.items()}
    print(f"FULL RESPONSE: {json.dumps(masked, indent=2)}")
except Exception:
    print(f"FULL RESPONSE: {token_r.text}")

if token_r.status_code != 200:
    print(f"\n[RESULT] BLOGGER FAILED (token refresh) — HTTP {token_r.status_code}")
    log(f"BLOGGER | {SLUG} | FAIL (token refresh) | {token_r.text[:200]}")
    results["blog"] = {"ok": False, "error": f"Token refresh HTTP {token_r.status_code}: {token_r.text[:200]}"}
else:
    access_token = token_r.json().get("access_token", "")

    blogger_post = {
        "title": TITLE,
        "content": (
            BODY_HTML
            + f'\n<p>Originally published at <a href="{CANONICAL}">{CANONICAL}</a></p>'
        ),
        "labels": TAGS[:5],
    }

    blogger_api_url = f"https://www.googleapis.com/blogger/v3/blogs/{BLOGGER_BLOG_ID}/posts/"

    print(f"\nSTEP 2: Create blog post")
    print(f"  POST {blogger_api_url}")
    print(f"  Authorization: Bearer {access_token[:20]}...")
    print(f"  title: {TITLE[:60]}")
    print(f"  labels: {TAGS[:5]}\n")

    blog_r = requests.post(
        blogger_api_url,
        json=blogger_post,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )

    print(f"HTTP STATUS: {blog_r.status_code}")
    print("FULL RESPONSE:")
    try:
        print(json.dumps(blog_r.json(), indent=2))
    except Exception:
        print(blog_r.text)

    if blog_r.status_code in (200, 201):
        url = blog_r.json().get("url", "")
        print(f"\n[RESULT] BLOGGER SUCCESS — {url}")
        log(f"BLOGGER | {SLUG} | SUCCESS | status={blog_r.status_code} | url={url}")
        results["blog"] = {"ok": True, "url": url}
    else:
        print(f"\n[RESULT] BLOGGER FAILED — HTTP {blog_r.status_code}")
        log(f"BLOGGER | {SLUG} | FAIL | status={blog_r.status_code} | {blog_r.text[:300]}")
        results["blog"] = {"ok": False, "error": f"HTTP {blog_r.status_code}: {blog_r.text[:300]}"}


# ─────────────────────────────────────────────────────────────────────────────
# PLATFORM 5: FEEDER (TTWF_GithubPages via GitHub Contents API)
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{'─'*70}")
print("PLATFORM 5: FEEDER (TTWF_GithubPages — GitHub Contents API)")
print(f"{'─'*70}")

feeder_path = f"content/posts/{SLUG}.md"
feeder_body_md = f"""---
title: "{TITLE}"
date: "{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}"
description: "{DESC}"
canonical: "{CANONICAL}"
tags: {json.dumps(TAGS[:5])}
---

{DESC}

{body[:800]}

...

Read the complete guide at [{BASE_URL}]({CANONICAL})
"""

feeder_encoded = base64.b64encode(feeder_body_md.encode("utf-8")).decode("utf-8")
check_url = f"https://api.github.com/repos/Lordshrrred/TTWF_GithubPages/contents/{feeder_path}"

print(f"\nSTEP 1: Check if file exists in TTWF_GithubPages")
print(f"  GET {check_url}")
print(f"  Authorization: token {GITHUB_TOKEN[:10]}...\n")

check_r = requests.get(
    check_url,
    headers={"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"},
    timeout=15,
)

print(f"HTTP STATUS: {check_r.status_code}")
try:
    cd = check_r.json()
    condensed = {k: (v if k != "content" else "[base64 omitted]") for k, v in cd.items()}
    print(f"FULL RESPONSE: {json.dumps(condensed, indent=2)[:600]}")
except Exception:
    print(f"FULL RESPONSE: {check_r.text[:400]}")

existing_sha = None
if check_r.status_code == 200:
    existing_sha = check_r.json().get("sha", "")
    print(f"\n  File already exists. SHA: {existing_sha[:16]}... Will UPDATE.")
else:
    print(f"\n  File not found. Will CREATE.")

commit_payload = {
    "message": f"feat: add feeder post {SLUG}",
    "content": feeder_encoded,
    "branch": "main",
}
if existing_sha:
    commit_payload["sha"] = existing_sha

print(f"\nSTEP 2: {'Update' if existing_sha else 'Create'} file via Contents API")
print(f"  PUT {check_url}")
print(f"  message: {commit_payload['message']}")
print(f"  content: [base64 encoded, {len(feeder_encoded)} chars]")
if existing_sha:
    print(f"  sha: {existing_sha[:16]}...")
print()

feeder_r = requests.put(
    check_url,
    json=commit_payload,
    headers={
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    },
    timeout=30,
)

print(f"HTTP STATUS: {feeder_r.status_code}")
print("FULL RESPONSE:")
try:
    fd = feeder_r.json()
    if "content" in fd and isinstance(fd["content"], dict):
        fd["content"]["content"] = "[base64 omitted]"
    print(json.dumps(fd, indent=2)[:1500])
except Exception:
    print(feeder_r.text[:800])

if feeder_r.status_code in (200, 201):
    commit_url = feeder_r.json().get("commit", {}).get("html_url", "")
    live_url = f"https://lordshrrred.github.io/TTWF_GithubPages/{SLUG}/"
    print(f"\n[RESULT] FEEDER SUCCESS — {live_url}")
    print(f"  Commit: {commit_url}")
    log(f"FEEDER | {SLUG} | SUCCESS | url={live_url} | commit={commit_url}")
    results["feeder"] = {"ok": True, "url": live_url}
else:
    print(f"\n[RESULT] FEEDER FAILED — HTTP {feeder_r.status_code}")
    log(f"FEEDER | {SLUG} | FAIL | status={feeder_r.status_code} | {feeder_r.text[:300]}")
    results["feeder"] = {"ok": False, "error": f"HTTP {feeder_r.status_code}: {feeder_r.text[:300]}"}


# ─────────────────────────────────────────────────────────────────────────────
# FINAL REPORT
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{DIVIDER}")
print("FINAL REPORT")
print(DIVIDER)

succeeded = [(p.upper(), r.get("url", "")) for p, r in results.items() if r["ok"]]
failed    = [(p.upper(), r.get("error", "")) for p, r in results.items() if not r["ok"]]

print(f"\nSUCCEEDED ({len(succeeded)}/5):")
for p, u in succeeded:
    print(f"  {p}: {u}")

print(f"\nFAILED ({len(failed)}/5):")
for p, e in failed:
    print(f"  {p}: {e}")

print("\nWHAT NEEDS FIXING:")
for p, e in failed:
    if "429" in e or "Rate limit" in e.lower():
        print(f"  {p}: Rate limited — wait and retry")
    elif "401" in e or "403" in e:
        print(f"  {p}: Auth failure — check API key/token")
    elif "token refresh" in e.lower():
        print(f"  {p}: OAuth refresh token expired — re-authorize")
    elif "400" in e:
        print(f"  {p}: Bad request — check payload format")
    else:
        print(f"  {p}: {e[:150]}")

if len(succeeded) >= 2:
    synced_txt = SYNCED_FILE.read_text(encoding="utf-8").strip()
    synced_set = set(synced_txt.splitlines()) if synced_txt else set()
    synced_set.add(SLUG)
    SYNCED_FILE.write_text("\n".join(sorted(synced_set)) + "\n", encoding="utf-8")
    print(f"\n[UPDATE] synced-posts.txt updated — added {SLUG}")
else:
    print(f"\n[SKIP] synced-posts.txt NOT updated (only {len(succeeded)}/5 succeeded)")

log(f"--- Done syndicating: {SLUG} | {len(succeeded)}/{len(results)} succeeded ---")
print(f"\nLog updated: scripts/syndication_log.txt\n")
