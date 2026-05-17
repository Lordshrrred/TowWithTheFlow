#!/usr/bin/env python3
"""
One-off script: renames all 30 TTWF_GithubPages city posts to a new slug
format and rewrites each with Claude for meaningful content variation.

New slug format: {city}-{state}-towing-prices
  e.g. towing-cost-denver-colorado -> denver-colorado-towing-prices

Preserved at bottom of each post: the specific city backlink to TWTF.
Run from TowWithTheFlow root: python scripts/rewrite_feeder_posts.py
"""

import os, re, sys, time
from pathlib import Path
from dotenv import load_dotenv
import anthropic

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env", override=True)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    sys.exit("ERROR: ANTHROPIC_API_KEY not set")

FEEDER_DIR = Path("C:/Users/Earth/OneDrive/Github/TTWF_GithubPages/content/posts")

# ── Slug mapping: old -> new ───────────────────────────────────────────────────
SLUG_MAP = {
    "towing-cost-denver-colorado":          "denver-colorado-towing-prices",
    "towing-cost-houston-texas":            "houston-texas-towing-prices",
    "towing-cost-phoenix-arizona":          "phoenix-arizona-towing-prices",
    "towing-cost-atlanta-georgia":          "atlanta-georgia-towing-prices",
    "towing-cost-chicago-illinois":         "chicago-illinois-towing-prices",
    "towing-cost-seattle-washington":       "seattle-washington-towing-prices",
    "towing-cost-dallas-texas":             "dallas-texas-towing-prices",
    "towing-cost-miami-florida":            "miami-florida-towing-prices",
    "towing-cost-los-angeles-california":   "los-angeles-california-towing-prices",
    "towing-cost-new-york-city":            "new-york-city-towing-prices",
    "towing-cost-las-vegas-nevada":         "las-vegas-nevada-towing-prices",
    "towing-cost-san-antonio-texas":        "san-antonio-texas-towing-prices",
    "towing-cost-austin-texas":             "austin-texas-towing-prices",
    "towing-cost-nashville-tennessee":      "nashville-tennessee-towing-prices",
    "towing-cost-portland-oregon":          "portland-oregon-towing-prices",
    "towing-cost-minneapolis-minnesota":    "minneapolis-minnesota-towing-prices",
    "towing-cost-detroit-michigan":         "detroit-michigan-towing-prices",
    "towing-cost-charlotte-north-carolina": "charlotte-north-carolina-towing-prices",
    "towing-cost-indianapolis-indiana":     "indianapolis-indiana-towing-prices",
    "towing-cost-columbus-ohio":            "columbus-ohio-towing-prices",
    "towing-cost-san-diego-california":     "san-diego-california-towing-prices",
    "towing-cost-jacksonville-florida":     "jacksonville-florida-towing-prices",
    "towing-cost-memphis-tennessee":        "memphis-tennessee-towing-prices",
    "towing-cost-baltimore-maryland":       "baltimore-maryland-towing-prices",
    "towing-cost-boston-massachusetts":     "boston-massachusetts-towing-prices",
    "towing-cost-fort-worth-texas":         "fort-worth-texas-towing-prices",
    "towing-cost-el-paso-texas":            "el-paso-texas-towing-prices",
    "towing-cost-oklahoma-city-oklahoma":   "oklahoma-city-oklahoma-towing-prices",
    "towing-cost-tucson-arizona":           "tucson-arizona-towing-prices",
    "towing-cost-albuquerque-new-mexico":   "albuquerque-new-mexico-towing-prices",
}

SYSTEM_PROMPT = (
    "Rewrite this towing cost article with meaningful variation. "
    "Same information, different phrasing, different structure, different opening. "
    "Must not be duplicate content. Never use em dashes. "
    "Do not include frontmatter — return only the markdown body content. "
    "Do not include a backlink or footer — that will be added separately. "
    "Use a different section structure than the original: vary the headings, "
    "reorder the information, and open with a different angle or observation."
)


def split_content(text: str):
    """
    Split file into (frontmatter_block, body, footer).
    Footer is the final --- separator + backlink line.
    """
    # Extract frontmatter (between first and second ---)
    fm_match = re.match(r'^(---\n.*?\n---\n)(.*)', text, re.DOTALL)
    if not fm_match:
        return "", text, ""
    frontmatter = fm_match.group(1)
    rest = fm_match.group(2)

    # Isolate footer: everything from the last standalone "---\n" onward
    # A standalone --- is a line that is exactly "---" with newlines around it
    footer_match = re.search(r'\n---\n\n[^\-]', rest)
    if footer_match:
        cut = footer_match.start()
        body   = rest[:cut].strip()
        footer = rest[cut:].strip()  # e.g. "---\n\nFor towing costs in..."
    else:
        # No horizontal rule footer found -- whole rest is body
        body   = rest.strip()
        footer = ""

    return frontmatter, body, footer


def update_slug_in_frontmatter(frontmatter: str, new_slug: str) -> str:
    return re.sub(
        r'^(slug:\s*)["\']?[^"\'\n]+["\']?',
        f'\\g<1>"{new_slug}"',
        frontmatter,
        count=1,
        flags=re.MULTILINE
    )


def rewrite_body(body: str, city_label: str) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1800,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                f"City: {city_label}\n\n"
                f"Original article to rewrite:\n\n{body}"
            ),
        }],
    )
    result = msg.content[0].text.strip()
    # Strip any code fences the model might have added
    result = re.sub(r'^```\w*\n?', '', result)
    result = re.sub(r'\n?```$', '', result)
    return result


def city_label_from_old_slug(slug: str) -> str:
    """towing-cost-denver-colorado -> Denver, Colorado"""
    inner = slug.replace("towing-cost-", "")
    words = inner.replace("-", " ").title()
    # Fix multi-word city: New York City has no comma, others get City, State
    parts = inner.split("-")
    # Heuristic: last token is state unless it's "city" (New York City, Oklahoma City)
    if parts[-1] in ("city",):
        return words  # e.g. "New York City"
    # Split state vs city: state is last word
    state = parts[-1].title()
    city  = " ".join(p.title() for p in parts[:-1])
    return f"{city}, {state}"


def main():
    client_check = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    print(f"Processing {len(SLUG_MAP)} feeder posts...\n")

    for i, (old_slug, new_slug) in enumerate(SLUG_MAP.items(), 1):
        old_path = FEEDER_DIR / f"{old_slug}.md"
        new_path = FEEDER_DIR / f"{new_slug}.md"

        if not old_path.exists():
            if new_path.exists():
                print(f"[{i:02d}] ALREADY RENAMED: {new_slug} -- skipping rewrite")
                continue
            print(f"[{i:02d}] MISSING: {old_slug}")
            continue

        city_label = city_label_from_old_slug(old_slug)
        print(f"[{i:02d}] {old_slug}")
        print(f"      -> {new_slug}  ({city_label})")

        text = old_path.read_text(encoding="utf-8")
        frontmatter, body, footer = split_content(text)

        if not body:
            print(f"      WARNING: could not parse body, skipping")
            continue

        # Update slug in frontmatter
        new_fm = update_slug_in_frontmatter(frontmatter, new_slug)

        # Rewrite body with Claude
        new_body = rewrite_body(body, city_label)

        # Reassemble: frontmatter + blank line + new body + blank line + footer
        if footer:
            new_content = f"{new_fm}\n{new_body}\n\n---\n\n{footer.lstrip('-').strip()}\n"
        else:
            new_content = f"{new_fm}\n{new_body}\n"

        # Write new file, delete old
        new_path.write_text(new_content, encoding="utf-8")
        old_path.unlink()
        print(f"      Saved: {new_path.name}")

        if i < len(SLUG_MAP):
            time.sleep(1)

    print(f"\nDone. {len(SLUG_MAP)} posts renamed and rewritten.")


if __name__ == "__main__":
    main()
