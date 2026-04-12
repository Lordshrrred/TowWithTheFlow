#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time
from datetime import date
from pathlib import Path

from syndicate_post import (
    POSTS_DIR,
    ensure_backlink,
    load_blogger_synced,
    load_post,
    log,
    mark_blogger_synced,
    parse_frontmatter,
    syndicate_blogger,
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
    parser = argparse.ArgumentParser(description="Backfill Blogger posts to the new Blogger site.")
    parser.add_argument("--limit", type=int, default=3, help="Maximum posts to publish in one run")
    parser.add_argument("--order", choices=["oldest", "newest"], default="oldest", help="Backlog selection order")
    args = parser.parse_args()

    today = date.today()
    blogger_synced = load_blogger_synced()
    backlog = [(d, slug) for d, slug in get_all_posts() if d < today and slug not in blogger_synced]
    if args.order == "newest":
        backlog = list(reversed(backlog))

    log(
        f"BLOGGER_BACKLOG | total={len(get_all_posts())} "
        f"blogger_synced={len(blogger_synced)} backlog={len(backlog)} "
        f"limit={args.limit} order={args.order}"
    )
    if not backlog:
        log("BLOGGER_BACKLOG | no pending Blogger backlog posts")
        return

    to_run = backlog[: max(args.limit, 0)]
    for idx, (_, slug) in enumerate(to_run):
        if idx > 0:
            wait_seconds = 65
            log(f"BLOGGER_BACKLOG | waiting {wait_seconds}s before next Blogger post")
            time.sleep(wait_seconds)

        result = load_post(slug)
        if result is None:
            continue
        meta, raw_body = result
        body = ensure_backlink(raw_body, slug)

        log(f"BLOGGER_BACKLOG | {slug} | START")
        ok, detail = syndicate_blogger(slug, meta, body)
        if ok:
            mark_blogger_synced(slug)
        log(f"BLOGGER | {slug} | {'SUCCESS' if ok else 'FAIL'} | {detail}")


if __name__ == "__main__":
    main()
