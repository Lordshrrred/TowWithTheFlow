#!/usr/bin/env python3
from __future__ import annotations

from datetime import date
from pathlib import Path

from syndicate_post import (
    POSTS_DIR,
    ensure_backlink,
    load_post,
    load_wordpress_synced,
    log,
    mark_wordpress_synced,
    parse_frontmatter,
    syndicate_wordpress,
)

SKIP_FILES = {"_index.md", "tow-content-log.md"}


def get_all_posts() -> list[tuple[date, str]]:
    posts = []
    for f in POSTS_DIR.glob("*.md"):
        if f.name in SKIP_FILES:
            continue
        try:
            meta, _ = parse_frontmatter(f.read_text(encoding="utf-8"))
            d = date.fromisoformat(str(meta.get("date", "2000-01-01"))[:10])
        except Exception:
            d = date(2000, 1, 1)
        posts.append((d, f.stem))
    return sorted(posts)


def main():
    today = date.today()
    wp_synced = load_wordpress_synced()
    backlog = [(d, slug) for d, slug in get_all_posts() if d < today and slug not in wp_synced]

    log(f"WORDPRESS_BACKLOG | total={len(get_all_posts())} wordpress_synced={len(wp_synced)} backlog={len(backlog)}")
    if not backlog:
        log("WORDPRESS_BACKLOG | no pending WordPress backlog posts")
        return

    _, slug = backlog[0]
    result = load_post(slug)
    if result is None:
        return
    meta, raw_body = result
    body = ensure_backlink(raw_body, slug)

    log(f"WORDPRESS_BACKLOG | {slug} | START")
    ok, detail = syndicate_wordpress(slug, meta, body)
    if ok:
        mark_wordpress_synced(slug)
    log(f"WORDPRESS | {slug} | {'SUCCESS' if ok else 'FAIL'} | {detail}")


if __name__ == "__main__":
    main()
