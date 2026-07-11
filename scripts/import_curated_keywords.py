#!/usr/bin/env python3
"""Append a curated keyword list to scripts/keywords.txt without using Claude."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

from keyword_research import load_existing_keywords, strip_score_prefix

KEYWORDS_FILE = Path(__file__).parent / "keywords.txt"


def normalize_keyword(text: str) -> str:
    return re.sub(r"\s+", " ", strip_score_prefix(text).strip()).strip(" -")


def load_rows(path: Path, default_score: int) -> list[tuple[int, str]]:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else data.get("keywords", [])
        out = []
        for item in rows:
            if isinstance(item, str):
                out.append((default_score, normalize_keyword(item)))
            elif isinstance(item, dict):
                out.append((int(item.get("score", default_score)), normalize_keyword(str(item.get("keyword", "")))))
        return out

    if path.suffix.lower() == ".csv":
        out = []
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                out.append((int(row.get("score") or default_score), normalize_keyword(row.get("keyword") or row.get("query") or "")))
        return out

    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = re.match(r"^\[(\d+)\]\s+(.+)$", stripped)
        if m:
            out.append((int(m.group(1)), normalize_keyword(m.group(2))))
        else:
            out.append((default_score, normalize_keyword(stripped)))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Import curated TWTF keyword expansions.")
    parser.add_argument("--file", required=True, help="TXT, CSV, or JSON file containing curated keywords.")
    parser.add_argument("--score", type=int, default=8, help="Default score for rows without a score.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    source = Path(args.file)
    existing = load_existing_keywords()
    rows = [(max(1, min(10, score)), kw) for score, kw in load_rows(source, args.score) if kw]
    unique = [(score, kw) for score, kw in rows if kw.lower() not in existing]

    print(f"Curated keywords read: {len(rows)}")
    print(f"New unique keywords: {len(unique)}")
    if args.dry_run:
        for score, kw in unique[:25]:
            print(f"[{score}] {kw}")
        return

    with KEYWORDS_FILE.open("a", encoding="utf-8") as f:
        f.write(f"\n# Curated expansion import from {source.name}\n")
        for score, kw in unique:
            f.write(f"[{score}] {kw}\n")
    print(f"Appended {len(unique)} curated keywords to {KEYWORDS_FILE}")


if __name__ == "__main__":
    main()
