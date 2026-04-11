#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
OUT_FILE = ROOT / "scripts" / "wordpress_backlink_audit.json"
WORDPRESS_BASE = "https://towwiththeflowyo.wordpress.com"
TWTF_BASE = "https://towwiththeflow.com"


def expected_urls(slug: str) -> tuple[str, str]:
    return f"{TWTF_BASE}/{slug}/".lower(), f"{TWTF_BASE}/{slug}".lower()


def href_links(html: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r'href=["\'](https?://towwiththeflow\.com[^"\']*)["\']', html, re.I)]


def matches_slug(link: str, slug: str) -> bool:
    a, b = expected_urls(slug)
    link = (link or "").lower().strip()
    return link == a or link.startswith(a + "?") or link == b or link.startswith(b + "?")


def discover_wordpress_posts(sess: requests.Session) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()

    # Prefer sitemap because it gives canonical public URLs.
    sitemap = sess.get(f"{WORDPRESS_BASE}/sitemap.xml", timeout=20)
    if sitemap.ok:
        for url in re.findall(r"<loc>(https?://[^<]+)</loc>", sitemap.text):
            if "/20" not in url:
                continue
            if url in seen:
                continue
            seen.add(url)
            urls.append(url)

    # Feed as a fallback in case WordPress lags on sitemap updates.
    feed = sess.get(f"{WORDPRESS_BASE}/feed/", timeout=20)
    if feed.ok:
        for url in re.findall(r"<link>(https?://[^<]+)</link>", feed.text):
            if "/20" not in url:
                continue
            if url in seen:
                continue
            seen.add(url)
            urls.append(url)

    return urls


def slug_from_wordpress_url(url: str) -> str:
    path = url.removeprefix(WORDPRESS_BASE).strip("/")
    parts = [p for p in path.split("/") if p]
    return parts[-1] if len(parts) >= 4 else ""


def verify_post(slug: str, url: str, sess: requests.Session) -> dict:
    try:
        r = sess.get(url, timeout=20)
        if not r.ok:
            return {"verified": False, "reason": f"http_{r.status_code}", "url": url}
        links = href_links(r.text)
        matched = next((link for link in links if matches_slug(link, slug)), "")
        return {
            "verified": bool(matched),
            "reason": "ok" if matched else "slug_mismatch",
            "url": url,
            "matched": matched,
            "recovered_live": True,
        }
    except Exception as e:
        return {"verified": None, "reason": f"error:{type(e).__name__}", "url": url}


def main() -> None:
    sess = requests.Session()
    sess.headers.update({"User-Agent": "TWTF-WordPress-Backlink-Audit/1.0"})

    slugs_out: dict[str, dict] = {}
    scanned_urls = discover_wordpress_posts(sess)
    for url in scanned_urls:
        slug = slug_from_wordpress_url(url)
        if not slug:
            continue
        slugs_out[slug] = {"wordpress": verify_post(slug, url, sess)}

    checked = 0
    verified = 0
    for row in slugs_out.values():
        wp = row.get("wordpress", {})
        if wp.get("verified") is None:
            continue
        checked += 1
        if wp.get("verified") is True:
            verified += 1

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "wordpress-sitemap-scan",
        "site": WORDPRESS_BASE,
        "scanned_urls": scanned_urls,
        "slugs": slugs_out,
        "summary": {"wordpress": {"verified": verified, "checked": checked}},
    }
    OUT_FILE.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUT_FILE} (wordpress_slugs={len(slugs_out)})")


if __name__ == "__main__":
    main()
