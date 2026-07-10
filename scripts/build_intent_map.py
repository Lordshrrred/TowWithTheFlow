#!/usr/bin/env python3
"""Build a search-intent map for cannibalization review.

The report is heuristic by design. It highlights likely overlaps and pages
that need human review, but it does not merge, canonicalize, or redirect
anything automatically.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from clusters import assign_cluster

ROOT = Path(__file__).parent.parent
POSTS_DIR = ROOT / "content" / "posts"
REPORTS_DIR = ROOT / "reports"
JSON_OUT = REPORTS_DIR / "intent-map.json"
MD_OUT = REPORTS_DIR / "intent-map.md"
SKIP = {"_index.md", "tow-content-log.md"}

STOPWORDS = {
    "a", "an", "and", "are", "at", "but", "by", "can", "do", "does", "for",
    "from", "how", "i", "if", "in", "is", "it", "me", "my", "near", "of",
    "on", "or", "should", "the", "to", "truck", "tow", "towing", "what",
    "when", "who", "why", "with", "you", "your",
}

CITY_TERMS = {
    "albuquerque", "atlanta", "austin", "baltimore", "boston", "charlotte",
    "chicago", "columbus", "dallas", "denver", "detroit", "el paso",
    "fort worth", "houston", "indianapolis", "jacksonville", "las vegas",
    "los angeles", "memphis", "miami", "minneapolis", "nashville",
    "new york", "oklahoma city", "phoenix", "portland", "san antonio",
    "san diego", "seattle", "tucson",
}


def frontmatter(text: str) -> dict:
    match = re.match(r"^---\n(.*?)\n---\n?", text, re.DOTALL)
    if not match:
        return {}
    fm = match.group(1)
    data: dict[str, str] = {}
    for field in ("title", "description", "date", "slug"):
        hit = re.search(rf'^{field}:\s*["\']?(.+?)["\']?\s*$', fm, re.MULTILINE)
        if hit:
            data[field] = hit.group(1).strip().strip("\"'")
    clusters = re.search(r'^clusters:\s*\[["\']?([\w-]+)', fm, re.MULTILINE)
    if clusters:
        data["cluster"] = clusters.group(1)
    service_area = re.search(r'^serviceArea:\s*["\']?(.+?)["\']?\s*$', fm, re.MULTILINE)
    if service_area:
        data["serviceArea"] = service_area.group(1).strip().strip("\"'")
    return data


def normalize_title(title: str) -> str:
    s = title.lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9\s-]", " ", s)
    s = re.sub(r"\b(no|not)\s+insurance\b", "without insurance", s)
    s = re.sub(r"\bwon t\b|\bwont\b", "wont", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def intent_key(title: str) -> str:
    s = normalize_title(title)
    for city in CITY_TERMS:
        s = s.replace(city, " ")
    tokens = [t for t in re.split(r"\s+", s) if t and t not in STOPWORDS and len(t) > 2]
    return " ".join(tokens[:8])


def intent_type(title: str, description: str) -> str:
    text = f"{title} {description}".lower()
    if any(term in text for term in ("cost", "price", "rate", "how much", "per mile")):
        return "cost"
    if any(term in text for term in ("insurance", "coverage", "deductible", "reimbursement", "aaa", "geico", "state farm")):
        return "coverage"
    if any(term in text for term in ("what to do", "emergency", "safe", "drive", "highway", "freeway")):
        return "emergency-decision"
    if any(term in text for term in ("law", "illegal", "impound", "private property", "rights")):
        return "legal-reference"
    return "informational"


def recommendation(group: list[dict]) -> str:
    if len(group) <= 1:
        return "keep"
    locations = {p.get("serviceArea", "") for p in group if p.get("serviceArea")}
    titles = " ".join(p["title"].lower() for p in group)
    if len(locations) > 1:
        return "keep separate if each page has distinct local pricing, law, or traffic context"
    if any(term in titles for term in ("winter", "night", "after hours", "accident", "freeway", "highway")):
        return "differentiate with scenario-specific sections and cross-links"
    return "review for consolidation, canonicalization, or redirect"


def load_posts() -> list[dict]:
    rows: list[dict] = []
    for path in sorted(POSTS_DIR.glob("*.md")):
        if path.name in SKIP:
            continue
        text = path.read_text(encoding="utf-8")
        meta = frontmatter(text)
        title = meta.get("title") or path.stem.replace("-", " ")
        slug = meta.get("slug") or path.stem
        cluster = meta.get("cluster") or assign_cluster(title)[0]
        description = meta.get("description", "")
        rows.append({
            "slug": slug,
            "path": str(path.relative_to(ROOT)),
            "title": title,
            "description": description,
            "date": meta.get("date", ""),
            "cluster": cluster,
            "serviceArea": meta.get("serviceArea", ""),
            "intentType": intent_type(title, description),
            "intentKey": intent_key(title),
            "descriptionLength": len(description),
            "titleLength": len(title),
        })
    return rows


def main() -> None:
    posts = load_posts()
    groups: dict[str, list[dict]] = defaultdict(list)
    for post in posts:
        groups[f"{post['cluster']}::{post['intentType']}::{post['intentKey']}"].append(post)

    overlaps = []
    for key, pages in groups.items():
        if len(pages) < 2:
            continue
        overlaps.append({
            "key": key,
            "count": len(pages),
            "recommendation": recommendation(pages),
            "pages": pages,
        })
    overlaps.sort(key=lambda g: (-g["count"], g["key"]))

    metadata_flags = [
        {
            "slug": p["slug"],
            "path": p["path"],
            "title": p["title"],
            "titleLength": p["titleLength"],
            "descriptionLength": p["descriptionLength"],
            "issues": [
                issue
                for issue, yes in [
                    ("title too short", p["titleLength"] < 30),
                    ("title too long", p["titleLength"] > 65),
                    ("missing description", p["descriptionLength"] == 0),
                    ("description too short", 0 < p["descriptionLength"] < 90),
                    ("description too long", p["descriptionLength"] > 160),
                ]
                if yes
            ],
        }
        for p in posts
    ]
    metadata_flags = [p for p in metadata_flags if p["issues"]]

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "postCount": len(posts),
        "overlapGroupCount": len(overlaps),
        "metadataFlagCount": len(metadata_flags),
        "overlaps": overlaps,
        "metadataFlags": metadata_flags,
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "# TWTF Search Intent Map",
        "",
        f"Generated: {payload['generatedAt']}",
        f"Posts reviewed: {payload['postCount']}",
        f"Potential overlap groups: {payload['overlapGroupCount']}",
        f"Metadata flags: {payload['metadataFlagCount']}",
        "",
        "## Highest-Priority Cannibalization Reviews",
        "",
    ]
    for group in overlaps[:40]:
        lines.append(f"### {group['key']} ({group['count']} pages)")
        lines.append(f"Recommendation: {group['recommendation']}")
        for page in group["pages"]:
            lines.append(f"- `{page['slug']}`: {page['title']} ({page['path']})")
        lines.append("")
    lines.extend(["## Metadata Flags", ""])
    for page in metadata_flags[:80]:
        lines.append(f"- `{page['slug']}`: {', '.join(page['issues'])}")
    MD_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Wrote {JSON_OUT.relative_to(ROOT)}")
    print(f"Wrote {MD_OUT.relative_to(ROOT)}")
    print(f"Potential overlap groups: {len(overlaps)}")
    print(f"Metadata flags: {len(metadata_flags)}")


if __name__ == "__main__":
    main()
