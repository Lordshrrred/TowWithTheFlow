#!/usr/bin/env python3
"""Select and summarize TWTF authority assets.

This is intentionally data-only: it never publishes, commits, or calls APIs.
The daily authority workflow can use it to pick the next asset, while humans
can use it to audit priorities and prerequisites.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
BACKLOG_FILE = ROOT / "data" / "authority_backlog.json"

UNFINISHED = {"planned", "draft", "needs-research", "needs-review", "in-progress"}


def load_backlog() -> dict:
    return json.loads(BACKLOG_FILE.read_text(encoding="utf-8"))


def sorted_assets(backlog: dict) -> list[dict]:
    return sorted(backlog.get("assets", []), key=lambda a: (int(a.get("priority", 9999)), a.get("slug", "")))


def next_asset(backlog: dict) -> dict | None:
    for asset in sorted_assets(backlog):
        if str(asset.get("status", "")).lower() in UNFINISHED:
            return asset
    return None


def print_asset(asset: dict) -> None:
    print(f"{asset['priority']:>2}. {asset['title']} ({asset['assetType']}, {asset['complexity']})")
    print(f"    slug: /{asset['section']}/{asset['slug']}/")
    print(f"    status: {asset['status']} | hub: {asset['hub']} | syndication: {asset['syndicationMode']}")
    print(f"    intent: {asset['intent']}")
    prereqs = asset.get("prerequisites", [])
    if prereqs:
        print(f"    prerequisites: {', '.join(prereqs)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--next", action="store_true", help="Print only the next unfinished authority asset")
    args = parser.parse_args()

    backlog = load_backlog()
    if args.next:
        asset = next_asset(backlog)
        if not asset:
            print("No unfinished authority assets found.")
            return
        print_asset(asset)
        return

    print(backlog.get("selectionPolicy", ""))
    print()
    for asset in sorted_assets(backlog):
        print_asset(asset)


if __name__ == "__main__":
    main()
