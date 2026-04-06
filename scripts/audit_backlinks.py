#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).parent.parent
LOG_FILE = ROOT / "scripts" / "syndication_log.txt"
OUT_FILE = ROOT / "scripts" / "backlink_audit.json"

FEEDER_OWNER = "Lordshrrred"
FEEDER_REPO = "TWTF_Feeder"
RAW_BASE = f"https://raw.githubusercontent.com/{FEEDER_OWNER}/{FEEDER_REPO}/main/content/posts"
TWTF_BASE = "https://towwiththeflow.com"

PLAT_KEYS = {"DEVTO": "dev", "TUMBLR": "tumblr", "BLOGGER": "blog", "FEEDER": "feeder"}


def expected_urls(slug: str) -> tuple[str, str]:
    a = f"{TWTF_BASE}/{slug}/".lower()
    b = f"{TWTF_BASE}/{slug}".lower()
    return a, b


def href_links(html: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r'href=["\'](https?://towwiththeflow\.com[^"\']*)["\']', html, re.I)]


def matches_slug(link: str, slug: str) -> bool:
    a, b = expected_urls(slug)
    l = (link or "").lower().strip()
    return l == a or l.startswith(a + "?") or l == b or l.startswith(b + "?")


def extract_url(detail: str) -> str:
    m = re.search(r"url=(https?://[^\s|]+)", detail)
    if m:
        return m.group(1)
    m = re.search(r"(https?://[^\s|]+)", detail)
    return m.group(1) if m else ""


def parse_successes(text: str) -> dict[str, dict[str, dict]]:
    """
    Return latest success entry per slug/platform:
      {slug: {dev|tumblr|blog|feeder: {timestamp, url, detail}}}
    """
    out: dict[str, dict[str, dict]] = {}
    rx = re.compile(
        r"^\[(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] "
        r"(?P<plat>DEVTO|TUMBLR|BLOGGER|FEEDER) \| "
        r"(?P<slug>[\w-]+) \| SUCCESS \| (?P<detail>.*)$"
    )
    for line in text.splitlines():
        m = rx.match(line)
        if not m:
            continue
        plat = PLAT_KEYS[m.group("plat")]
        slug = m.group("slug")
        ts = m.group("ts")
        detail = m.group("detail").strip()
        url = extract_url(detail)
        out.setdefault(slug, {})
        prev = out[slug].get(plat)
        if (prev is None) or (ts > prev["timestamp"]):
            out[slug][plat] = {"timestamp": ts, "url": url, "detail": detail}
    return out


def verify_dev(slug: str, url: str, sess: requests.Session) -> dict:
    try:
        if not url:
            return {"verified": None, "reason": "no_url", "url": ""}
        path = urlparse(url).path.strip("/")
        parts = [p for p in path.split("/") if p]
        if len(parts) < 2:
            return {"verified": None, "reason": "bad_url", "url": url}
        api = f"https://dev.to/api/articles/{parts[0]}/{parts[1]}"
        r = sess.get(api, timeout=20)
        if not r.ok:
            return {"verified": False, "reason": f"http_{r.status_code}", "url": url}
        d = r.json()
        canon = (d.get("canonical_url") or "").lower()
        body = (d.get("body_html") or "").lower()
        exp_a, exp_b = expected_urls(slug)
        ok = canon in (exp_a, exp_b) or (exp_a in body) or (exp_b in body)
        return {"verified": bool(ok), "reason": "ok" if ok else "slug_mismatch", "url": url}
    except Exception as e:
        return {"verified": None, "reason": f"error:{type(e).__name__}", "url": url}


def verify_html_slug(slug: str, url: str, sess: requests.Session) -> dict:
    try:
        if not url:
            return {"verified": None, "reason": "no_url", "url": ""}
        r = sess.get(url, timeout=25)
        if not r.ok:
            return {"verified": False, "reason": f"http_{r.status_code}", "url": url}
        links = href_links(r.text)
        ok = any(matches_slug(l, slug) for l in links)
        return {"verified": bool(ok), "reason": "ok" if ok else "slug_mismatch", "url": url}
    except Exception as e:
        return {"verified": None, "reason": f"error:{type(e).__name__}", "url": url}


def verify_feeder(slug: str, url: str, sess: requests.Session) -> dict:
    try:
        candidates: list[str] = []
        if url:
            p = urlparse(url).path.strip("/")
            if p:
                candidates.append(p.split("/")[0])
        candidates.extend([slug, f"{slug}-guide"])
        seen = set()
        unique = []
        for c in candidates:
            if c and c not in seen:
                seen.add(c)
                unique.append(c)
        exp_a, exp_b = expected_urls(slug)
        for cand in unique:
            raw = f"{RAW_BASE}/{cand}.md"
            r = sess.get(raw, timeout=20)
            if not r.ok:
                continue
            txt = r.text.lower()
            ok = (exp_a in txt) or (exp_b in txt)
            if ok:
                return {
                    "verified": True,
                    "reason": "ok",
                    "url": f"https://lordshrrred.github.io/TWTF_Feeder/{cand}/",
                }
        return {"verified": False, "reason": "slug_mismatch", "url": url}
    except Exception as e:
        return {"verified": None, "reason": f"error:{type(e).__name__}", "url": url}


def recover_blogger(slug: str, sess: requests.Session) -> dict | None:
    """If log doesn't show Blogger success URL, discover likely live post and verify exact slug backlink."""
    try:
        r = sess.get("https://denverroadsideguide.blogspot.com/sitemap.xml", timeout=20)
        if not r.ok:
            return None
        locs = [m.group(1) for m in re.finditer(r"<loc>(https?://[^<]+)</loc>", r.text)]
        core = [w for w in slug.split("-") if w not in {"what", "to", "do", "the", "a", "an", "in", "for", "and", "or", "with"}]
        scored: list[tuple[int, str]] = []
        for u in locs:
            low = u.lower()
            if "denverroadsideguide.blogspot.com/20" not in low:
                continue
            score = 0
            if slug in low:
                score += 8
            for w in core[:8]:
                if w in low:
                    score += 1
            if score > 0:
                scored.append((score, u))
        for _, cand in sorted(scored, reverse=True)[:8]:
            chk = verify_html_slug(slug, cand, sess)
            if chk.get("verified") is True:
                chk["recovered_live"] = True
                return chk
    except Exception:
        return None
    return None


def main() -> None:
    text = LOG_FILE.read_text(encoding="utf-8", errors="ignore") if LOG_FILE.exists() else ""
    successes = parse_successes(text)
    sess = requests.Session()
    sess.headers.update({"User-Agent": "TWTF-Backlink-Audit/1.0"})

    slugs_out: dict[str, dict] = {}
    for slug, plats in successes.items():
        row: dict[str, dict] = {}
        # Existing success entries
        if "dev" in plats:
            row["dev"] = verify_dev(slug, plats["dev"]["url"], sess)
        if "tumblr" in plats:
            row["tumblr"] = verify_html_slug(slug, plats["tumblr"]["url"], sess)
        if "blog" in plats:
            row["blog"] = verify_html_slug(slug, plats["blog"]["url"], sess)
        if "feeder" in plats:
            row["feeder"] = verify_feeder(slug, plats["feeder"]["url"], sess)

        # Recovery for blogger when no success URL logged
        if "blog" not in row:
            rec = recover_blogger(slug, sess)
            if rec:
                row["blog"] = rec

        slugs_out[slug] = row

    summary = {p: {"verified": 0, "checked": 0} for p in ["dev", "tumblr", "blog", "feeder"]}
    for _, row in slugs_out.items():
        for p, d in row.items():
            if d.get("verified") is None:
                continue
            summary[p]["checked"] += 1
            if d.get("verified") is True:
                summary[p]["verified"] += 1

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "github-actions-audit",
        "slugs": slugs_out,
        "summary": summary,
    }
    OUT_FILE.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUT_FILE} (slugs={len(slugs_out)})")


if __name__ == "__main__":
    main()
