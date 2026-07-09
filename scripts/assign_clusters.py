#!/usr/bin/env python3
"""
Assigns every post in content/posts/ to a content cluster (see clusters.py)
by injecting a `cluster: "<slug>"` frontmatter field, derived from the
post's title. Idempotent — safe to re-run any time the taxonomy in
clusters.py changes; always recomputes and overwrites rather than trusting
a stale value.

Hugo turns this into taxonomy term pages at /clusters/<slug>/ (config in
hugo.toml), which become the pillar/hub pages for each topic, and the
single-post template uses the same field to auto-link related posts in the
same cluster — no API calls, no manual link curation.
"""

from __future__ import annotations

import re
import glob
from collections import Counter
from pathlib import Path

from clusters import assign_cluster

ROOT = Path(__file__).parent.parent
POSTS_DIR = ROOT / "content" / "posts"
SKIP = {"_index.md", "tow-content-log.md"}


def set_cluster_field(content: str, cluster_slug: str) -> str:
    # Hugo taxonomy frontmatter fields must match the *plural* config value
    # (config: `cluster = "clusters"` -> frontmatter field `clusters:`),
    # the same way `tags:` matches `tag = "tags"`. Drop any earlier
    # singular `cluster:` field from a previous run of this script.
    content = re.sub(r'^cluster:\s*.+\n', '', content, count=1, flags=re.MULTILINE)

    field = f'clusters: ["{cluster_slug}"]'
    if re.search(r'^clusters:\s*.+$', content, re.MULTILINE):
        return re.sub(r'^clusters:\s*.+$', field, content, count=1, flags=re.MULTILINE)
    # Insert right after the `slug:` line if present, else right after the
    # opening `---` — either way it lands inside the frontmatter block.
    if re.search(r'^slug:\s*.+$', content, re.MULTILINE):
        return re.sub(r'(^slug:\s*.+$)', f'\\1\n{field}', content, count=1, flags=re.MULTILINE)
    return re.sub(r'^(---\n)', f'\\1{field}\n', content, count=1)


def main():
    files = [p for p in sorted(glob.glob(str(POSTS_DIR / "*.md"))) if Path(p).name not in SKIP]
    counts = Counter()
    changed = 0

    for path_str in files:
        path = Path(path_str)
        text = path.read_text(encoding="utf-8")
        title_m = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', text, re.MULTILINE)
        title = title_m.group(1) if title_m else path.stem

        cluster_slug, cluster_label = assign_cluster(title)
        counts[cluster_label] += 1

        new_text = set_cluster_field(text, cluster_slug)
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
            changed += 1

    print(f"Processed {len(files)} posts, updated {changed}")
    for label, n in counts.most_common():
        print(f"  {n:4d}  {label}")


if __name__ == "__main__":
    main()
