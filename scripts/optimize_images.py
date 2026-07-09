#!/usr/bin/env python3
"""
One-time (and re-runnable) pass to shrink every image already in
static/images/ — most are raw Pexels 'large2x' downloads (2000px+, several
MB each) far larger than anything this site displays. Uses the same
resize_and_compress_image() that new downloads now go through in
generate_post.py, so old and new images end up consistent.
"""

from __future__ import annotations

from pathlib import Path

from generate_post import resize_and_compress_image

ROOT = Path(__file__).parent.parent
IMAGES_DIR = ROOT / "static" / "images"


def main():
    files = sorted(IMAGES_DIR.rglob("*.jpg")) + sorted(IMAGES_DIR.rglob("*.jpeg")) + sorted(IMAGES_DIR.rglob("*.png"))
    if not files:
        print("No images found under static/images/")
        return

    total_before = sum(f.stat().st_size for f in files)
    changed = 0
    for f in files:
        before = f.stat().st_size
        resize_and_compress_image(f)
        after = f.stat().st_size
        if after != before:
            changed += 1

    total_after = sum(f.stat().st_size for f in files)
    saved = total_before - total_after
    pct = (saved / total_before * 100) if total_before else 0
    print(f"Processed {len(files)} images ({changed} changed)")
    print(f"Before: {total_before / 1_000_000:.1f} MB")
    print(f"After:  {total_after / 1_000_000:.1f} MB")
    print(f"Saved:  {saved / 1_000_000:.1f} MB ({pct:.0f}%)")


if __name__ == "__main__":
    main()
