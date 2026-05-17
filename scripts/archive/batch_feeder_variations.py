#!/usr/bin/env python3
"""
Generate feeder variations on TTWF_GithubPages for all TWTF posts
that don't already have a corresponding feeder post.

Run: python scripts/batch_feeder_variations.py
"""

import os, re, sys, time
from datetime import date, timedelta
from pathlib import Path
from dotenv import load_dotenv
import anthropic

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env", override=True)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    sys.exit("ERROR: ANTHROPIC_API_KEY not set")

TWTF_DIR   = ROOT / "content" / "posts"
FEEDER_DIR = Path("C:/Users/Earth/OneDrive/Github/TTWF_GithubPages/content/posts")
TWTF_BASE  = "https://towwiththeflow.com"
TODAY      = date.today()

# Rotate suffixes so posts vary
SUFFIXES = ["-tips", "-advice", "-help", "-guide"]

SKIP_SLUGS = {"_index", "tow-content-log"}

CITY_PREFIX = "towing-cost-"
def city_to_feeder(slug):
    return f"{slug[len(CITY_PREFIX):]}-towing-prices"

SUFFIX_ENDINGS = ("-tips", "-advice", "-help", "-guide", "-prices")
def base_slug(slug):
    for s in SUFFIX_ENDINGS:
        if slug.endswith(s):
            return slug[:-len(s)]
    return slug


def build_missing_list():
    twtf_slugs   = sorted(f.stem for f in TWTF_DIR.glob("*.md"))
    feeder_slugs = set(f.stem for f in FEEDER_DIR.glob("*.md"))

    feeder_base_map = {}
    for fs in feeder_slugs:
        feeder_base_map[base_slug(fs)] = fs
        feeder_base_map[fs] = fs

    missing = []
    for slug in twtf_slugs:
        if slug in SKIP_SLUGS:
            continue
        if slug in feeder_base_map:
            continue
        if slug.startswith(CITY_PREFIX):
            equiv = city_to_feeder(slug)
            if equiv in feeder_slugs:
                continue
        missing.append(slug)
    return missing


def read_twtf_post(slug):
    p = TWTF_DIR / f"{slug}.md"
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8")


def make_system_prompt(original_slug):
    backlink = (
        f"For the complete guide on this topic, visit "
        f"[Tow With The Flow](https://towwiththeflow.com/{original_slug}/) "
        f"\u2014 real answers when your car breaks down."
    )
    return (
        "Rewrite this car breakdown/roadside help article as a unique variation "
        "for a feeder blog. Use the same information but completely different phrasing, "
        "different opening paragraph, different structure. Must not read as duplicate "
        "content. Never use em dashes in the body text. "
        "TARGET LENGTH: 400-600 words total (body only). Be direct and concise. No filler. "
        f"End every post with EXACTLY this backlink block as the very last lines:\n\n"
        f"---\n\n{backlink}\n\n"
        "This backlink block is non-negotiable and must never be omitted. "
        "Return only valid Hugo markdown with frontmatter. "
        "Frontmatter fields: title (slightly varied from original), "
        "date (today), description (under 155 chars), tags (same or similar), "
        "slug (I will provide the target slug — use it exactly as given)."
    )


def generate_variation(original_content, original_slug, target_slug, suffix_idx):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    system = make_system_prompt(original_slug)

    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1800,
        system=system,
        messages=[{
            "role": "user",
            "content": (
                f"Target feeder slug: {target_slug}\n\n"
                f"Original article to rewrite:\n\n{original_content}"
            ),
        }],
    )
    result = msg.content[0].text.strip()
    result = re.sub(r'^```\w*\n?', '', result)
    result = re.sub(r'\n?```$', '', result)

    # Guarantee the specific backlink is present
    backlink = (
        f"For the complete guide on this topic, visit "
        f"[Tow With The Flow](https://towwiththeflow.com/{original_slug}/) "
        f"\u2014 real answers when your car breaks down."
    )
    if f"towwiththeflow.com/{original_slug}/" not in result:
        result = result.rstrip() + f"\n\n{backlink}\n"

    # Ensure slug in frontmatter matches target
    result = re.sub(
        r'^(slug:\s*)["\']?[^"\'\n]+["\']?\s*$',
        f'\\g<1>"{target_slug}"',
        result, count=1, flags=re.MULTILINE
    )
    return result


def main():
    missing = build_missing_list()
    total   = len(missing)
    print(f"Found {total} TWTF posts needing feeder variations\n")

    generated = []

    for i, slug in enumerate(missing):
        suffix   = SUFFIXES[i % len(SUFFIXES)]
        new_slug = f"{slug}{suffix}"
        out_path = FEEDER_DIR / f"{new_slug}.md"

        if out_path.exists():
            print(f"[{i+1:02d}/{total}] SKIP (exists): {new_slug}")
            generated.append(new_slug)
            continue

        original = read_twtf_post(slug)
        if not original:
            print(f"[{i+1:02d}/{total}] MISSING source: {slug}")
            continue

        print(f"[{i+1:02d}/{total}] {slug}  ->  {new_slug}")
        content = generate_variation(original, slug, new_slug, i)
        out_path.write_text(content, encoding="utf-8")
        generated.append(new_slug)
        print(f"       Saved: {out_path.name}")

        if i < total - 1:
            time.sleep(1)

    print(f"\n=== Done: {len(generated)}/{total} variations saved ===")

    # Write the slug list so the backdating step can read it
    slug_list_path = Path(__file__).parent / "feeder_variation_slugs.txt"
    slug_list_path.write_text("\n".join(generated) + "\n", encoding="utf-8")
    print(f"Slug list written to: {slug_list_path}")


if __name__ == "__main__":
    main()
