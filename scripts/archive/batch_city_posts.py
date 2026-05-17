#!/usr/bin/env python3
"""
Batch-generate 30 city towing-cost posts for towwiththeflow.com.
- Uses city-specific enhanced system prompt (600-900 words)
- Slug format: towing-cost-{city}-{state}  (no 'in' connector, matches feeder site)
- Does NOT call syndicate_post.py — syndication handled separately
- Marks each keyword DONE in keywords.txt
- Fetches Pexels images same as generate_post.py
Run once: python scripts/batch_city_posts.py
"""

import os, re, sys, time
from datetime import date
from pathlib import Path
from dotenv import load_dotenv
import anthropic, requests

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env", override=True)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
PEXELS_API_KEY    = os.getenv("PEXELS_API_KEY", "")

if not ANTHROPIC_API_KEY:
    sys.exit("ERROR: ANTHROPIC_API_KEY not set")

KEYWORDS_FILE = Path(__file__).parent / "keywords.txt"
POSTS_DIR     = ROOT / "content" / "posts"
IMAGES_DIR    = ROOT / "static" / "images"
POSTS_DIR.mkdir(parents=True, exist_ok=True)

# ── 30 city keywords in priority order ────────────────────────────────────────
CITY_KEYWORDS = [
    "towing cost in Denver Colorado",
    "towing cost in Houston Texas",
    "towing cost in Phoenix Arizona",
    "towing cost in Atlanta Georgia",
    "towing cost in Chicago Illinois",
    "towing cost in Seattle Washington",
    "towing cost in Dallas Texas",
    "towing cost in Miami Florida",
    "towing cost in Los Angeles California",
    "towing cost in New York City",
    "towing cost in Las Vegas Nevada",
    "towing cost in San Antonio Texas",
    "towing cost in Austin Texas",
    "towing cost in Nashville Tennessee",
    "towing cost in Portland Oregon",
    "towing cost in Minneapolis Minnesota",
    "towing cost in Detroit Michigan",
    "towing cost in Charlotte North Carolina",
    "towing cost in Indianapolis Indiana",
    "towing cost in Columbus Ohio",
    "towing cost in San Diego California",
    "towing cost in Jacksonville Florida",
    "towing cost in Memphis Tennessee",
    "towing cost in Baltimore Maryland",
    "towing cost in Boston Massachusetts",
    "towing cost in Fort Worth Texas",
    "towing cost in El Paso Texas",
    "towing cost in Oklahoma City Oklahoma",
    "towing cost in Tucson Arizona",
    "towing cost in Albuquerque New Mexico",
]

SYSTEM_PROMPT = """You are writing a page for towwiththeflow.com, a car breakdown and roadside emergency help site. \
This post covers towing costs AND what to do when broken down in a specific city. \
Write 600-900 words total. Voice: knowledgeable mechanic, direct, no filler, no AI-sounding language.

Structure:
1. Quick Answer block: 60-90 words inside a markdown blockquote starting with **Quick Answer:** \
   — include the city's typical towing cost range.
2. ## What Towing Costs in [City] — specific price ranges: base hookup fee, per-mile rate, \
   after-hours surcharge, highway vs local difference. Vary realistically by city cost of living.
3. ## What To Do When You Break Down in [City] — numbered steps with city-specific detail \
   (major highways, local dispatch services, AAA availability, typical wait times).
4. ## Local Tips for [City] — 4-5 bullet points: city-specific hazards, traffic patterns, \
   time-of-day considerations, any local regulations or impound rules worth knowing.
5. ## What Affects the Final Price — 4-5 bullet points covering vehicle type, distance, \
   time of day, membership discounts, insurance coverage.
6. ## Stay Safe — 3-4 bullet points on staying safe while waiting for a tow in that city.

Rules:
- NEVER use em dashes (—). Use commas, colons, or periods instead.
- Do not use double hyphens (--) as em dashes.
- No conclusions, no sign-offs, no "In summary" phrases.
- Return ONLY valid Hugo markdown with frontmatter.
- Frontmatter fields: title, date (today), description (under 155 chars), \
  tags (array including city name, state name, "towing cost", "roadside emergency"), \
  slug (IMPORTANT: use format towing-cost-{city}-{state} with NO 'in' connector, \
  all lowercase, hyphens only — e.g. "towing cost in Denver Colorado" -> "towing-cost-denver-colorado", \
  "towing cost in New York City" -> "towing-cost-new-york-city", \
  "towing cost in Fort Worth Texas" -> "towing-cost-fort-worth-texas")."""


# ── Pexels helpers (copied from generate_post.py) ─────────────────────────────
def fetch_pexels_photo(query: str, index: int = 1):
    if not PEXELS_API_KEY:
        return None
    try:
        r = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": query, "orientation": "landscape", "per_page": 5, "size": "large"},
            timeout=20,
        )
        photos = r.json().get("photos", []) if r.status_code == 200 else []
        return photos[min(index, len(photos) - 1)] if photos else None
    except Exception as e:
        print(f"  Pexels error: {e}")
        return None


def download_image(photo, save_path: Path) -> bool:
    url = (photo or {}).get("src", {}).get("large2x") or (photo or {}).get("src", {}).get("large")
    if not url:
        return False
    try:
        r = requests.get(url, stream=True, timeout=30)
        if r.status_code != 200:
            return False
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"  Image download error: {e}")
        return False


def add_hero_image(content: str, slug: str) -> str:
    img_dir  = IMAGES_DIR / slug
    img_dir.mkdir(parents=True, exist_ok=True)
    hero_path = img_dir / "hero.jpg"
    if not hero_path.exists():
        photo = fetch_pexels_photo("tow truck road city", 1)
        if photo and download_image(photo, hero_path):
            print(f"  Hero image downloaded")
    if hero_path.exists() and 'image:' not in content[:300]:
        content = re.sub(r'^(---\n)', f'\\1image: "/images/{slug}/hero.jpg"\n', content, count=1)
    return content


# ── Keyword file helpers ───────────────────────────────────────────────────────
def mark_keyword_done(keyword: str):
    text  = KEYWORDS_FILE.read_text(encoding="utf-8")
    lines = text.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("# DONE"):
            continue
        # Strip score prefix if present
        raw = re.sub(r'^\[\d+\]\s*', '', stripped)
        if raw.lower() == keyword.lower():
            lines[i] = f"# DONE {stripped}"
            break
    KEYWORDS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── Claude generation ──────────────────────────────────────────────────────────
def generate_post(keyword: str) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    today  = date.today().isoformat()
    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                f'Write a complete Hugo markdown post for the keyword: "{keyword}"\n'
                f"Today\'s date: {today}\n"
                "Make it genuinely useful for someone broken down in that city right now."
            ),
        }],
    )
    content = msg.content[0].text.strip()
    if content.startswith("```"):
        content = re.sub(r'^```\w*\n?', '', content)
        content = re.sub(r'\n?```$', '', content)
    return content


def extract_slug(content: str, keyword: str) -> str:
    m = re.search(r'^slug:\s*["\']?([^"\'\n]+)["\']?', content, re.MULTILINE)
    if m:
        return m.group(1).strip().strip("'\"")
    # Fallback: derive from keyword
    kw = keyword.lower()
    kw = re.sub(r'\bin\b', '', kw)
    kw = re.sub(r'[^\w\s-]', '', kw)
    kw = re.sub(r'[\s_]+', '-', kw.strip())
    return re.sub(r'-+', '-', kw).strip('-')


# ── Main loop ──────────────────────────────────────────────────────────────────
def main():
    done_slugs = []

    for i, keyword in enumerate(CITY_KEYWORDS, 1):
        print(f"\n[{i:02d}/30] {keyword}")

        content = generate_post(keyword)
        slug    = extract_slug(content, keyword)
        outfile = POSTS_DIR / f"{slug}.md"

        if outfile.exists():
            print(f"  SKIP — {outfile.name} already exists")
            mark_keyword_done(keyword)
            done_slugs.append(slug)
            continue

        content = add_hero_image(content, slug)
        outfile.write_text(content, encoding="utf-8")
        mark_keyword_done(keyword)
        done_slugs.append(slug)
        print(f"  Saved: {outfile.name}")

        # Polite pause between API calls
        if i < len(CITY_KEYWORDS):
            time.sleep(2)

    print(f"\n=== Done: {len(done_slugs)} posts generated ===")
    for s in done_slugs:
        print(f"  {s}")


if __name__ == "__main__":
    main()
