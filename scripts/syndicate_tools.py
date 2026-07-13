#!/usr/bin/env python3
"""
Tow With The Flow — Roadside Tool Syndication

Publishes platform-native Roadside Tool backlink content for completed
tools. Short-form/canonical destinations still use deterministic TEASERS.
Selected long-form backlink destinations use one-time generated companion
articles, cached permanently before publication so retries never cause
duplicate Claude spend.

Reuses the proven auth/posting primitives from syndicate_post.py
(Blogger OAuth, WordPress OAuth, Tumblr OAuth1, Dev.to API key, Feeder
GitHub Contents API) rather than re-implementing them, but never calls
that module's Claude-based per-platform content variation — tool
teasers are 100% template-driven.

Usage:
  python scripts/syndicate_tools.py --dry-run
  python scripts/syndicate_tools.py --live --max-posts 3
  python scripts/syndicate_tools.py --live --max-posts 1 --platforms tumblr,devto
  python scripts/syndicate_tools.py --verify-only
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import yaml

ROOT = Path(__file__).parent.parent
TOOLS_DIR = ROOT / "content" / "tools"
STATE_FILE = Path(__file__).parent / "tool_syndication_state.json"
LOG_FILE = Path(__file__).parent / "tool_syndication_log.txt"
COMPANION_CACHE_FILE = Path(__file__).parent / "tool_companion_cache.json"
PLATFORM_POLICY_FILE = Path(__file__).parent / "tool_syndication_platform_policy.json"
BASE_URL = "https://towwiththeflow.com"
COMPANION_FORMAT_VERSION = "tool-companion-v1"
COMPANION_MODEL = os.getenv("TOOL_COMPANION_MODEL", "claude-haiku-4-5-20251001")
DEFAULT_MAX_GENERATIONS = int(os.getenv("TOOL_COMPANION_MAX_GENERATIONS", "1"))

sys.path.insert(0, str(Path(__file__).parent))
import syndicate_post as sp  # noqa: E402  (reuse auth + HTML helpers only)
from claude_utils import make_client, create_message  # noqa: E402

PLATFORMS = ["blogger", "wordpress", "tumblr", "devto", "feeder"]

RUN_STATS = {
    "companion_generated": 0,
    "companion_reused": 0,
    "companion_generation_failed": 0,
    "companion_generation_skipped": 0,
    "deterministic_teasers": 0,
    "estimated_companion_input_tokens": 0,
    "estimated_companion_output_tokens": 0,
}


def log(msg: str) -> None:
    line = f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_platform_policy() -> dict[str, dict[str, Any]]:
    if PLATFORM_POLICY_FILE.exists():
        return json.loads(PLATFORM_POLICY_FILE.read_text(encoding="utf-8"))
    return {
        "blogger": {"format": "companion_article", "backlink_type": "followed_backlink"},
        "wordpress": {"format": "companion_article", "backlink_type": "followed_backlink"},
        "tumblr": {"format": "deterministic_teaser", "backlink_type": "nofollow_distribution"},
        "devto": {"format": "deterministic_teaser", "backlink_type": "nofollow_distribution"},
        "feeder": {"format": "canonical_source_copy", "backlink_type": "canonical_source_copy"},
    }


PLATFORM_POLICY = load_platform_policy()
PLATFORM_LINK_CLASS = {
    platform: policy.get("backlink_type", "unknown")
    for platform, policy in PLATFORM_POLICY.items()
}


def platform_format(platform: str) -> str:
    return PLATFORM_POLICY.get(platform, {}).get("format", "deterministic_teaser")


def uses_companion_article(platform: str) -> bool:
    return platform_format(platform) == "companion_article"


# ── State (idempotency) ──────────────────────────────────────────────────────

def load_state() -> dict[str, Any]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"pairs": {}}


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def pair_key(slug: str, platform: str) -> str:
    return f"{slug}::{platform}"


def pair_status(state: dict[str, Any], slug: str, platform: str) -> str:
    return state["pairs"].get(pair_key(slug, platform), {}).get("status", "pending")


def record_result(state: dict[str, Any], slug: str, platform: str, ok: bool, url_or_err: str) -> None:
    entry = {
        "status": "success" if ok else "failed",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "format": platform_format(platform),
    }
    if ok:
        entry["url"] = url_or_err
        entry["link_type"] = PLATFORM_LINK_CLASS.get(platform, "unknown")
        entry["backlink_verified"] = False
    else:
        entry["error"] = url_or_err[:400]
    state["pairs"][pair_key(slug, platform)] = entry
    save_state(state)


def annotate_pair(state: dict[str, Any], slug: str, platform: str, updates: dict[str, Any]) -> None:
    key = pair_key(slug, platform)
    state.setdefault("pairs", {}).setdefault(key, {"status": "pending"})
    state["pairs"][key].update(updates)
    save_state(state)


# ── Permanent companion cache ────────────────────────────────────────────────

def load_companion_cache() -> dict[str, Any]:
    if COMPANION_CACHE_FILE.exists():
        try:
            data = json.loads(COMPANION_CACHE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("items", {})
                return data
        except json.JSONDecodeError:
            pass
    return {"items": {}}


def save_companion_cache(cache: dict[str, Any]) -> None:
    COMPANION_CACHE_FILE.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")


def tool_source_material(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "slug": tool["slug"],
        "title": tool.get("title", ""),
        "description": tool.get("description", ""),
        "whenToUse": tool.get("whenToUse", ""),
        "problemSolved": tool.get("problemSolved", ""),
        "timeEstimate": tool.get("timeEstimate", ""),
        "relatedTopics": tool.get("relatedTopics", []),
        "canonical_url": tool.get("canonical_url", ""),
    }


def source_hash(tool: dict[str, Any]) -> str:
    payload = json.dumps(tool_source_material(tool), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def companion_cache_key(tool: dict[str, Any], platform: str) -> str:
    raw = f"{tool['slug']}::{platform}::{source_hash(tool)}::{COMPANION_FORMAT_VERSION}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def valid_companion_item(item: Any, tool: dict[str, Any], platform: str) -> bool:
    if not isinstance(item, dict):
        return False
    required = ["title", "body_markdown", "excerpt", "cta", "canonical_url", "source_hash", "format_version"]
    if any(not str(item.get(k, "")).strip() for k in required):
        return False
    if item.get("canonical_url") != tool["canonical_url"]:
        return False
    if item.get("source_hash") != source_hash(tool):
        return False
    if item.get("format_version") != COMPANION_FORMAT_VERSION:
        return False
    if tool["canonical_url"] not in item.get("body_markdown", ""):
        return False
    return item.get("platform") == platform


COMPANION_SYSTEM_PROMPT = """You write useful companion articles for Tow With The Flow, a calm roadside help site.

Write a standalone article that solves a closely related problem without duplicating the interactive tool page.
Use plain English, practical safety-first advice, and short paragraphs.
Do not fabricate prices, laws, phone numbers, exact mechanical diagnoses, statistics, or guarantees.
Naturally introduce the canonical TWTF tool as the next useful step and include exactly one markdown link to it.
Use normal punctuation. Do not use em dashes.

Return strict JSON only:
{
  "title": "article title",
  "excerpt": "one sentence under 160 characters",
  "body_markdown": "markdown article body, 550-850 words, no frontmatter",
  "cta": "short call to action"
}
"""


def companion_prompt(tool: dict[str, Any], platform: str) -> str:
    topics = ", ".join(
        t.get("label", "") for t in tool.get("relatedTopics", []) if isinstance(t, dict) and t.get("label")
    )
    return (
        f"Platform: {platform}\n"
        f"Tool title: {tool['title']}\n"
        f"Tool URL: {tool['canonical_url']}\n"
        f"When to use tool: {tool.get('whenToUse', '')}\n"
        f"Problem solved: {tool.get('problemSolved', '')}\n"
        f"Tool description: {tool.get('description', '')}\n"
        f"Related topics: {topics or 'Roadside Help'}\n\n"
        "Choose a companion article angle that helps the reader before or around the moment they would use this tool. "
        "The article must stand on its own and then point to the interactive tool for a personalized Roadside Action Plan."
    )


def _extract_json_object(text: str) -> dict[str, Any] | None:
    if not text or not text.strip():
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def sanitize_companion(data: dict[str, Any], tool: dict[str, Any]) -> dict[str, str] | None:
    title = str(data.get("title", "")).strip()
    excerpt = str(data.get("excerpt", "")).strip()
    body = str(data.get("body_markdown", "")).strip()
    cta = str(data.get("cta", "")).strip() or "Open the interactive tool"
    if not title or not excerpt or not body:
        return None
    if len(body.split()) < 350:
        return None
    if tool["canonical_url"] not in body:
        # One repair attempt without another model call.
        anchor = _pick([
            "use the interactive Roadside Action Plan",
            "walk through the tool",
            "check the TWTF tool",
            "get a clearer next step",
        ], tool["slug"], "companion", "anchor")
        body = body.rstrip() + f"\n\nFor a personalized next step, [{anchor}]({tool['canonical_url']})."
    if tool["canonical_url"] not in body:
        return None
    return {"title": title[:120], "excerpt": excerpt[:180], "body_markdown": body, "cta": cta[:120]}


def estimate_tokens(text: str) -> int:
    return max(1, round(len(text) / 4))


def get_or_generate_companion(
    tool: dict[str, Any],
    platform: str,
    *,
    max_generations: int,
    refresh: bool = False,
    allow_generate: bool = True,
) -> tuple[dict[str, Any] | None, str, str]:
    """Return (item, cache_status, message), where cache_status is generated,
    reused, skipped, or failed. Publication retries reuse cached content.
    """
    cache = load_companion_cache()
    key = companion_cache_key(tool, platform)
    existing = cache["items"].get(key)
    if not refresh and valid_companion_item(existing, tool, platform):
        RUN_STATS["companion_reused"] += 1
        return existing, "reused", key

    if not allow_generate:
        RUN_STATS["companion_generation_skipped"] += 1
        return None, "skipped", f"no valid cache for {key}"
    if RUN_STATS["companion_generated"] >= max_generations:
        RUN_STATS["companion_generation_skipped"] += 1
        return None, "skipped", "per-run companion generation cap reached"
    if not sp.ANTHROPIC_API_KEY:
        RUN_STATS["companion_generation_failed"] += 1
        return None, "failed", "missing ANTHROPIC_API_KEY"

    prompt = companion_prompt(tool, platform)
    input_tokens = estimate_tokens(COMPANION_SYSTEM_PROMPT + prompt)
    try:
        log(f"COMPANION | {tool['slug']} | {platform} | generating model={COMPANION_MODEL}")
        client = make_client(sp.ANTHROPIC_API_KEY)
        msg = create_message(
            client,
            log=log,
            model=COMPANION_MODEL,
            max_tokens=1800,
            system=[{
                "type": "text",
                "text": COMPANION_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text if getattr(msg, "content", None) else ""
        parsed = _extract_json_object(raw)
        cleaned = sanitize_companion(parsed or {}, tool)
        if not cleaned:
            RUN_STATS["companion_generation_failed"] += 1
            return None, "failed", "model returned empty or malformed companion article"
        output_tokens = estimate_tokens(cleaned["body_markdown"])
        item = {
            **cleaned,
            "tool_id": tool["slug"],
            "platform": platform,
            "canonical_url": tool["canonical_url"],
            "model": getattr(msg, "model", COMPANION_MODEL),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_hash": source_hash(tool),
            "format_version": COMPANION_FORMAT_VERSION,
            "cache_key": key,
            "estimated_tokens": {
                "input": input_tokens,
                "output": output_tokens,
            },
            "estimated_cost_usd": round(((input_tokens / 1_000_000) * 0.80) + ((output_tokens / 1_000_000) * 4.00), 6),
        }
        cache["items"][key] = item
        save_companion_cache(cache)
        RUN_STATS["companion_generated"] += 1
        RUN_STATS["estimated_companion_input_tokens"] += input_tokens
        RUN_STATS["estimated_companion_output_tokens"] += output_tokens
        log(f"COMPANION | {tool['slug']} | {platform} | cached key={key} title={item['title']!r}")
        return item, "generated", key
    except Exception as e:
        RUN_STATS["companion_generation_failed"] += 1
        return None, "failed", str(e)[:300]


def companion_to_html(item: dict[str, Any]) -> str:
    return sp.md_to_html(item["body_markdown"])


# ── Tool discovery + eligibility ─────────────────────────────────────────────

def parse_tool_frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n?", text, re.DOTALL)
    if not m:
        return {}
    return yaml.safe_load(m.group(1)) or {}


def load_authority_backlog() -> dict[str, dict[str, Any]]:
    path = ROOT / "data" / "authority_backlog.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"assets": []}
    return {a["slug"]: a for a in data.get("assets", [])}


def eligible_tools() -> list[dict[str, Any]]:
    """Published, indexable, teaser-mode, backlog-confirmed-live tools only."""
    backlog = load_authority_backlog()
    tools = []
    for path in sorted(TOOLS_DIR.glob("*.md")):
        if path.stem == "_index":
            continue
        fm = parse_tool_frontmatter(path)
        slug = fm.get("slug") or path.stem
        asset_type = fm.get("assetType", "")
        if asset_type not in ("calculator", "decision-tool"):
            continue
        if fm.get("syndicationMode") != "teaser":
            continue
        robots = str(fm.get("robots", "")).lower()
        if "noindex" in robots:
            continue
        backlog_entry = backlog.get(slug)
        if not backlog_entry or backlog_entry.get("status") != "live":
            continue
        tools.append({
            "slug": slug,
            "title": fm.get("title", slug),
            "description": fm.get("description", ""),
            "whenToUse": fm.get("whenToUse", ""),
            "problemSolved": fm.get("problemSolved", ""),
            "timeEstimate": fm.get("timeEstimate", ""),
            "relatedTopics": fm.get("relatedTopics", []) or [],
            "priority": backlog_entry.get("priority", 999),
            "canonical_url": f"{BASE_URL}/tools/{slug}/",
        })
    return tools


def verify_live(url: str, timeout: int = 15) -> tuple[bool, str]:
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "TWTF-tool-syndication-check"})
        return r.status_code == 200, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)


# ── Deterministic queue ordering ─────────────────────────────────────────────

def queue_order(tools: list[dict[str, Any]], state: dict[str, Any]) -> list[dict[str, Any]]:
    """New tools (zero successful platforms yet) float to the front so their
    backlinks start shortly after publication; otherwise ordered by the
    authority backlog's own priority, then slug for stability."""
    def synced_count(slug: str) -> int:
        return sum(1 for p in PLATFORMS if pair_status(state, slug, p) == "success")

    def is_new(tool: dict[str, Any]) -> bool:
        return synced_count(tool["slug"]) == 0

    return sorted(tools, key=lambda t: (0 if is_new(t) else 1, t["priority"], t["slug"]))


# ── Deterministic teaser generation ──────────────────────────────────────────

OPENERS = [
    "{whenToUse}? The {title} gives you a clear answer in {time_lower}.",
    "The {title} helps you {problem_lower} — {time_lower}, no signup.",
    "{description}",
    "{whenToUse} is exactly when the {title} is built for — {time_lower}, no signup.",
]

CTAS = [
    "Try it free: {url}",
    "Open the tool — no signup needed: {url}",
    "Walk through it yourself: {url}",
    "Get the full Roadside Action Plan: {url}",
    "See your answer here: {url}",
]

BODY_LINES = [
    "It walks you through the real factors — not a generic guess — and ends with a full Roadside Action Plan: a confidence level, a phone script, and what to watch out for.",
    "Every answer is computed right in your browser, with an honest confidence level and a phone script ready for when you call.",
    "No account, no app, no AI guessing — just the same questions a calm, experienced roadside expert would ask.",
]


def _pick(options: list[str], slug: str, platform: str, salt: str) -> str:
    h = hashlib.sha256(f"{slug}:{platform}:{salt}".encode()).hexdigest()
    return options[int(h, 16) % len(options)]


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text else text


def build_teaser(tool: dict[str, Any], platform: str) -> dict[str, str]:
    """Returns {title, opener, body, cta, tags} — platform templates below
    decide how these get assembled and how long the result is."""
    slug = tool["slug"]
    time_lower = _lower_first(tool.get("timeEstimate", "about a minute"))
    problem_lower = _lower_first(tool.get("problemSolved", "what to do next"))

    opener_tpl = _pick(OPENERS, slug, platform, "opener")
    opener = opener_tpl.format(
        whenToUse=tool.get("whenToUse") or "Stuck on the road",
        title=tool["title"],
        time_lower=time_lower,
        problem_lower=problem_lower,
        description=tool.get("description", ""),
    )
    body = _pick(BODY_LINES, slug, platform, "body")
    cta = _pick(CTAS, slug, platform, "cta").format(url=tool["canonical_url"])

    tags = []
    for topic in tool.get("relatedTopics", [])[:2]:
        label = topic.get("label", "") if isinstance(topic, dict) else ""
        tag = re.sub(r"[^A-Za-z0-9]", "", label)
        if tag:
            tags.append(tag)
    tags.append("RoadsideHelp")

    return {"opener": opener, "body": body, "cta": cta, "tags": tags}


# ── Platform posting (teaser-scoped, no Claude, no full-article reuse) ──────

def cta_label(teaser: dict[str, str]) -> str:
    """Just the human label portion of a CTA, e.g. "Try it free" — never the
    raw URL, so anchor text doesn't visibly repeat the href."""
    return teaser["cta"].split(": ", 1)[0]


def post_blogger(tool: dict[str, Any], teaser: dict[str, Any], companion: dict[str, Any] | None = None) -> tuple[bool, str]:
    missing = [n for n, v in [
        ("BLOGGER_CLIENT_ID", sp.BLOGGER_CLIENT_ID),
        ("BLOGGER_CLIENT_SECRET", sp.BLOGGER_CLIENT_SECRET),
        ("BLOGGER_REFRESH_TOKEN", sp.BLOGGER_REFRESH_TOKEN),
        ("BLOGGER_BLOG_ID", sp.BLOGGER_BLOG_ID),
    ] if not v]
    if missing:
        return False, f"SKIP: missing Blogger credentials: {', '.join(missing)}"

    token, err = sp.get_blogger_token()
    if not token:
        return False, f"ERROR: token refresh failed — {err}"
    blog_id, blog_err = sp.resolve_blogger_blog_id(token)
    if not blog_id:
        return False, f"ERROR: could not resolve Blogger blog id — {blog_err}"

    if companion:
        html_body = companion_to_html(companion)
        title = companion["title"]
        labels = teaser["tags"][:5] + ["Roadside Tool"]
    else:
        html_body = (
            f"<p>{teaser['opener']}</p>"
            f"<p>{teaser['body']}</p>"
            f"<p><strong><a href=\"{tool['canonical_url']}\">{cta_label(teaser)}</a></strong></p>"
            f"<p><em>An interactive Roadside Tool from Tow With The Flow.</em></p>"
        )
        title = tool["title"]
        labels = teaser["tags"][:5]
    try:
        r = requests.post(
            f"https://www.googleapis.com/blogger/v3/blogs/{blog_id}/posts/",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"title": title, "content": html_body, "labels": labels},
            timeout=30,
        )
        if r.status_code in (200, 201):
            return True, r.json().get("url", "published")
        return False, f"HTTP {r.status_code}: {r.text[:300]}"
    except Exception as e:
        return False, str(e)


def post_wordpress(tool: dict[str, Any], teaser: dict[str, Any], companion: dict[str, Any] | None = None) -> tuple[bool, str]:
    site = sp.wordpress_site_identifier()
    if not site:
        return False, "SKIP: missing WORDPRESS_BLOG or WORDPRESS_SITE_URL"
    token, err = sp.wordpress_get_access_token()
    if not token:
        return False, err

    if companion:
        html_body = companion_to_html(companion)
        title = companion["title"]
        excerpt = companion["excerpt"]
    else:
        html_body = (
            f"<p>{teaser['opener']}</p>"
            f"<p>{teaser['body']}</p>"
            f"<p><strong><a href=\"{tool['canonical_url']}\">{cta_label(teaser)}</a></strong></p>"
            f"<p><em>An interactive Roadside Tool from Tow With The Flow.</em></p>"
        )
        title = tool["title"]
        excerpt = tool.get("description", "")[:160]
    try:
        r = requests.post(
            f"{sp.WORDPRESS_REST_POSTS_NEW_BASE}/{site}/posts/new",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            data={
                "title": title,
                "content": html_body,
                "excerpt": excerpt,
                "status": "publish",
                "tags": ",".join(teaser["tags"][:5]),
            },
            timeout=30,
        )
        data = r.json()
    except Exception as e:
        return False, str(e)
    if not r.ok:
        detail = data if isinstance(data, dict) else {}
        return False, f"{detail.get('error', r.status_code)}: {detail.get('message', r.text[:300])}"
    return True, str(data.get("URL") or data.get("url") or tool["canonical_url"])


def post_tumblr(tool: dict[str, Any], teaser: dict[str, Any]) -> tuple[bool, str]:
    if not all([sp.TUMBLR_CONSUMER_KEY, sp.TUMBLR_CONSUMER_SECRET, sp.TUMBLR_TOKEN, sp.TUMBLR_TOKEN_SECRET, sp.TUMBLR_BLOG]):
        return False, "SKIP: missing Tumblr OAuth credentials"
    try:
        from requests_oauthlib import OAuth1
    except ImportError:
        return False, "ERROR: requests-oauthlib not installed"

    label = cta_label(teaser)
    url = tool["canonical_url"]
    text = f"{tool['title']}\n\n{teaser['opener']}\n\n{teaser['body']}\n\n{label}"
    link_start = len(text) - len(label)
    formatting = [{"start": link_start, "end": len(text), "type": "link", "url": url}]

    oauth = OAuth1(sp.TUMBLR_CONSUMER_KEY, sp.TUMBLR_CONSUMER_SECRET, sp.TUMBLR_TOKEN, sp.TUMBLR_TOKEN_SECRET)
    try:
        r = requests.post(
            f"https://api.tumblr.com/v2/blog/{sp.TUMBLR_BLOG}/posts",
            auth=oauth,
            json={
                "content": [{"type": "text", "text": text, "formatting": formatting}],
                "tags": ",".join(teaser["tags"][:5]),
                "state": "published",
            },
            timeout=30,
        )
        if r.status_code in (200, 201):
            post_id = r.json().get("response", {}).get("id", "")
            return True, f"https://{sp.TUMBLR_BLOG}.tumblr.com/post/{post_id}"
        return False, f"HTTP {r.status_code}: {json.dumps(r.json())[:300]}"
    except Exception as e:
        return False, str(e)


def post_devto(tool: dict[str, Any], teaser: dict[str, Any]) -> tuple[bool, str]:
    if not sp.DEVTO_ENABLED:
        return False, "SKIP: Dev.to disabled (DEVTO_ENABLED=false)"
    if not sp.DEVTO_API_KEY:
        return False, "SKIP: no Dev.to API key in environment"

    body_md = (
        f"{teaser['opener']}\n\n"
        f"{teaser['body']}\n\n"
        f"**[{cta_label(teaser)}]({tool['canonical_url']})**\n\n"
        f"*An interactive Roadside Tool from Tow With The Flow.*"
    )
    devto_tags = [re.sub(r"[^a-z0-9]", "", t.lower()) for t in teaser["tags"]][:4]
    devto_tags = [t for t in devto_tags if t] or ["roadside"]
    try:
        r = requests.post(
            "https://dev.to/api/articles",
            headers={"api-key": sp.DEVTO_API_KEY, "Content-Type": "application/json"},
            json={"article": {
                "title": tool["title"],
                "body_markdown": body_md,
                "published": True,
                "tags": devto_tags,
                "canonical_url": tool["canonical_url"],
                "description": tool.get("description", ""),
            }},
            timeout=30,
        )
        if r.status_code in (200, 201):
            return True, r.json().get("url", tool["canonical_url"])
        return False, f"HTTP {r.status_code}: {r.text[:300]}"
    except Exception as e:
        return False, str(e)


def post_feeder(tool: dict[str, Any], teaser: dict[str, Any]) -> tuple[bool, str]:
    token = sp.FEEDER_TRIGGER_TOKEN
    if not token:
        return False, "SKIP: no feeder token set (FEEDER_TRIGGER_TOKEN)"

    slug = tool["slug"]
    feeder_slug = f"{slug}-tool"
    feeder_url = f"https://lordshrrred.github.io/TWTF_Feeder/{feeder_slug}/"
    today = datetime.now(timezone.utc).date().isoformat()

    body_md = f"{teaser['opener']}\n\n{teaser['body']}\n\n**[{cta_label(teaser)}]({tool['canonical_url']})**\n"
    fm = (
        "---\n"
        f'title: "{tool["title"]}"\n'
        f"date: {today}\n"
        f'description: "{tool.get("description", "")}"\n'
        f'slug: "{feeder_slug}"\n'
        f'canonical: "{tool["canonical_url"]}"\n'
        "---\n\n"
    )
    encoded = base64.b64encode((fm + body_md).encode("utf-8")).decode("ascii")
    api_url = f"https://api.github.com/repos/{sp.FEEDER_OWNER}/{sp.FEEDER_REPO}/contents/content/posts/{feeder_slug}.md"
    headers = {"Authorization": f"token {token}", "Content-Type": "application/json"}

    existing = requests.get(api_url, headers=headers, timeout=20)
    sha = existing.json().get("sha") if existing.status_code == 200 else None
    payload = {"message": f"Feeder: syndicate tool teaser {feeder_slug}", "content": encoded}
    if sha:
        payload["sha"] = sha

    try:
        r = requests.put(api_url, headers=headers, json=payload, timeout=30)
        if r.status_code in (200, 201):
            return True, feeder_url
        return False, f"HTTP {r.status_code}: {r.text[:300]}"
    except Exception as e:
        return False, str(e)


POSTERS = {
    "blogger": post_blogger,
    "wordpress": post_wordpress,
    "tumblr": post_tumblr,
    "devto": post_devto,
    "feeder": post_feeder,
}


# ── Backlink verification (live, not assumed) ────────────────────────────────

def verify_backlink(url: str, canonical: str) -> dict[str, Any]:
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "TWTF-backlink-check"})
    except Exception as e:
        return {"exists": False, "error": str(e)}
    if not r.ok:
        return {"exists": False, "error": f"HTTP {r.status_code}"}
    html = r.text
    escaped = re.escape(canonical)
    m = re.search(rf'<a\b[^>]*href=["\']?{escaped}["\']?[^>]*>', html, re.IGNORECASE)
    if not m:
        return {"exists": True, "contextual_link_found": False}
    tag = m.group(0)
    nofollow = "nofollow" in tag.lower()
    return {"exists": True, "contextual_link_found": True, "nofollow_attr": nofollow}


# ── Main run ──────────────────────────────────────────────────────────────────

def state_summary(state: dict[str, Any], *, preserve_run_stats: bool = False) -> dict[str, Any]:
    cache = load_companion_cache()
    pairs = state.get("pairs", {})
    run_stats = dict(RUN_STATS)
    if preserve_run_stats:
        run_stats = state.get("summary", {}).get("run_stats", run_stats)
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "companion_articles_cached": len(cache.get("items", {})),
        "companion_articles_published": sum(
            1 for v in pairs.values()
            if v.get("status") == "success" and v.get("format") == "companion_article"
        ),
        "deterministic_teasers_prepared": sum(
            1 for v in pairs.values()
            if v.get("status") == "success" and v.get("format") in ("deterministic_teaser", "canonical_source_copy")
        ),
        "run_stats": run_stats,
    }


def save_state_with_summary(state: dict[str, Any], *, preserve_run_stats: bool = False) -> None:
    state["summary"] = state_summary(state, preserve_run_stats=preserve_run_stats)
    save_state(state)


def run(
    dry_run: bool,
    max_posts: int,
    platforms: list[str],
    verify_only: bool,
    *,
    max_generations: int,
    refresh_companion: bool = False,
) -> None:
    state = load_state()
    tools = eligible_tools()
    log(f"Eligible tools: {len(tools)}")

    if verify_only:
        for key, entry in list(state["pairs"].items()):
            if entry.get("status") != "success" or entry.get("backlink_verified"):
                continue
            slug, platform = key.split("::")
            tool = next((t for t in tools if t["slug"] == slug), None)
            if not tool or "url" not in entry:
                continue
            result = verify_backlink(entry["url"], tool["canonical_url"])
            entry["backlink_verification"] = result
            # Only lock verification in once the destination page itself was
            # reachable — a transient 404 (e.g. Feeder's own site still
            # rebuilding) should retry on the next verify-only run instead of
            # being permanently marked as checked.
            entry["backlink_verified"] = bool(result.get("exists"))
            log(f"VERIFY | {slug} | {platform} | {result}")
        save_state_with_summary(state, preserve_run_stats=True)
        return

    ordered = queue_order(tools, state)
    active_platforms = [p for p in PLATFORMS if p in platforms]
    posted = 0

    for tool in ordered:
        if posted >= max_posts:
            break
        slug = tool["slug"]
        live_ok, live_detail = verify_live(tool["canonical_url"])
        if not live_ok:
            log(f"SKIP tool | {slug} | canonical URL not live: {live_detail}")
            continue

        for platform in active_platforms:
            if posted >= max_posts:
                break
            if pair_status(state, slug, platform) == "success":
                continue

            teaser = build_teaser(tool, platform)
            companion = None
            companion_status = "not_applicable"
            companion_key = ""
            fmt = platform_format(platform)
            if dry_run:
                if uses_companion_article(platform):
                    companion, companion_status, companion_key = get_or_generate_companion(
                        tool,
                        platform,
                        max_generations=max_generations,
                        refresh=refresh_companion,
                        allow_generate=False,
                    )
                    log(f"DRY RUN | {slug} | {platform} | format={fmt} cache={companion_status} key={companion_key}")
                else:
                    RUN_STATS["deterministic_teasers"] += 1
                    log(f"DRY RUN | {slug} | {platform} | format={fmt} opener={teaser['opener']!r} cta={teaser['cta']!r}")
                posted += 1
                continue

            if uses_companion_article(platform):
                companion, companion_status, companion_key = get_or_generate_companion(
                    tool,
                    platform,
                    max_generations=max_generations,
                    refresh=refresh_companion,
                    allow_generate=True,
                )
                if not companion:
                    record_result(state, slug, platform, False, f"COMPANION {companion_status}: {companion_key}")
                    annotate_pair(state, slug, platform, {
                        "format": fmt,
                        "companion_status": companion_status,
                        "companion_cache_key": companion_key if len(companion_key) <= 120 else "",
                    })
                    log(f"FAIL | {slug} | {platform} | companion {companion_status}: {companion_key}")
                    posted += 1
                    continue
            else:
                RUN_STATS["deterministic_teasers"] += 1

            ok, detail = POSTERS[platform](tool, teaser, companion) if uses_companion_article(platform) else POSTERS[platform](tool, teaser)
            record_result(state, slug, platform, ok, detail)
            annotate_pair(state, slug, platform, {
                "format": fmt,
                "companion_status": companion_status,
                "companion_cache_key": companion.get("cache_key", companion_key) if companion else "",
                "companion_title": companion.get("title", "") if companion else "",
                "companion_model": companion.get("model", "") if companion else "",
            })
            log(f"{'OK' if ok else 'FAIL'} | {slug} | {platform} | {detail}")
            posted += 1
            if posted < max_posts:
                time.sleep(20)

    if not dry_run:
        save_state_with_summary(state)
    log(
        "RUN SUMMARY | "
        f"generated={RUN_STATS['companion_generated']} "
        f"reused={RUN_STATS['companion_reused']} "
        f"deterministic={RUN_STATS['deterministic_teasers']} "
        f"generation_failed={RUN_STATS['companion_generation_failed']} "
        f"generation_skipped={RUN_STATS['companion_generation_skipped']}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic Roadside Tool syndication.")
    parser.add_argument("--dry-run", action="store_true", help="Generate teasers without posting.")
    parser.add_argument("--live", action="store_true", help="Actually post to platforms.")
    parser.add_argument("--verify-only", action="store_true", help="Run backlink verification on prior successes only.")
    parser.add_argument("--max-posts", type=int, default=3, help="Bounded number of (tool, platform) posts this run.")
    parser.add_argument("--platforms", type=str, default=",".join(PLATFORMS), help="Comma-separated platform allowlist.")
    parser.add_argument("--max-generations", type=int, default=DEFAULT_MAX_GENERATIONS, help="Max first-time companion articles to generate this run.")
    parser.add_argument("--refresh-companion", action="store_true", help="Force companion regeneration for matching source/version keys.")
    args = parser.parse_args()

    if not (args.dry_run or args.live or args.verify_only):
        parser.error("Pass --dry-run, --live, or --verify-only")

    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]
    run(
        dry_run=args.dry_run and not args.live,
        max_posts=args.max_posts,
        platforms=platforms,
        verify_only=args.verify_only,
        max_generations=args.max_generations,
        refresh_companion=args.refresh_companion,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
