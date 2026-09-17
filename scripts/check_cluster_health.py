#!/usr/bin/env python3
"""Fail fast when a post cannot participate in the site’s cluster linking."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from clusters import CATCHALL, CLUSTERS

ROOT = Path(__file__).parent.parent
POSTS = ROOT / "content" / "posts"
HUBS = ROOT / "content" / "clusters"
SKIP = {"_index.md", "tow-content-log.md"}


def main() -> int:
    valid = {slug for slug, _, _ in CLUSTERS} | {CATCHALL[0]}
    missing: list[str] = []
    unknown: list[str] = []
    counts: Counter[str] = Counter()
    for path in sorted(POSTS.glob("*.md")):
        if path.name in SKIP:
            continue
        match = re.search(r'^clusters:\s*\[["\']?([\w-]+)', path.read_text(encoding="utf-8"), re.MULTILINE)
        if not match:
            missing.append(path.name)
            continue
        cluster = match.group(1)
        counts[cluster] += 1
        if cluster not in valid:
            unknown.append(f"{path.name}: {cluster}")

    missing_hubs = sorted(cluster for cluster in counts if not (HUBS / cluster / "_index.md").exists())
    print(f"Cluster health: {sum(counts.values())} posts across {len(counts)} clusters")
    print("Coverage:", ", ".join(f"{cluster}={count}" for cluster, count in counts.most_common()))
    if missing:
        print("Missing cluster frontmatter:", ", ".join(missing[:20]))
    if unknown:
        print("Unknown clusters:", ", ".join(unknown[:20]))
    if missing_hubs:
        print("Clusters without hubs:", ", ".join(missing_hubs))
    return 1 if missing or unknown or missing_hubs else 0


if __name__ == "__main__":
    raise SystemExit(main())
