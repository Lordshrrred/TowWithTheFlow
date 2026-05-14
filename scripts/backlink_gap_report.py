#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
AUDIT_FILE = ROOT / "scripts" / "backlink_audit.json"
HEALTH_FILE = ROOT / "scripts" / "platform_health.json"
PLATFORMS = ["dev", "tumblr", "blog", "wordpress", "feeder"]


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> int:
    audit = load_json(AUDIT_FILE)
    health = load_json(HEALTH_FILE)
    slugs = audit.get("slugs", {})

    print(f"Audit generated: {audit.get('generated_at', 'unknown')}")
    print("Platform health:")
    for name, row in sorted((health.get("checks") or {}).items()):
        detail = row.get("detail", "")
        suffix = f" - {detail}" if detail else ""
        print(f"  {name}: {row.get('status', 'unknown')}{suffix}")

    print("\nBacklink coverage:")
    for platform in PLATFORMS:
        bad = []
        unknown = []
        verified = 0
        checked = 0
        for slug, row in sorted(slugs.items()):
            result = row.get(platform)
            if not result:
                unknown.append(slug)
                continue
            if result.get("verified") is None:
                unknown.append(slug)
                continue
            checked += 1
            if result.get("verified") is True:
                verified += 1
            else:
                bad.append(slug)

        print(f"  {platform}: {verified}/{checked} verified, {len(bad)} bad, {len(unknown)} unknown/missing")
        if bad:
            print("    bad: " + ", ".join(bad))
        if unknown:
            print("    unknown/missing: " + ", ".join(unknown))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
