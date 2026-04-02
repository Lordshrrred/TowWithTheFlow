#!/usr/bin/env python3
"""
Tow With The Flow — Daily Post Generator
Usage:
  python generate_post.py --type general   # highest scored non-local keyword
  python generate_post.py --type local     # highest scored local/city keyword
Saves slug to last_general_slug.txt or last_local_slug.txt for syndication jobs.
"""

import argparse
import os
import re
import sys
import random
import subprocess
from datetime import date
from pathlib import Path
from dotenv import load_dotenv
import anthropic
import requests

# Load .env from repo root
ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
    sys.exit(1)

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
IMAGES_DIR = ROOT / "static" / "images"

KEYWORDS_FILE = Path(__file__).parent / "keywords.txt"
POSTS_DIR = ROOT / "content" / "posts"
POSTS_DIR.mkdir(parents=True, exist_ok=True)

CITIES = ["Denver", "Houston", "Phoenix", "Atlanta", "Chicago", "Seattle", "Dallas", "Miami"]

SYSTEM_PROMPT = """You are writing a page for towwiththeflow.com, a car breakdown and roadside emergency help site. Write in the voice of a knowledgeable mechanic who is direct and wastes no words.

TARGET LENGTH: 400-600 words total (body only, not counting frontmatter). Be concise. No filler, no padding, no AI-sounding transitions, no conclusions.

STRUCTURE:
1. Quick Answer block: 50-80 words inside a markdown blockquote starting with **Quick Answer:**
2. What To Do: numbered steps, direct and actionable
3. What It Might Cost: if relevant, keep it short
4. Stay Safe: if relevant, bullet points only

BACKLINK REQUIREMENT — NON-NEGOTIABLE:
Every post MUST end with EXACTLY this block (substituting the actual slug):

---

*Need roadside help? Visit [Tow With The Flow](https://towwiththeflow.com/{slug}/) for real answers when your car breaks down.*

This block is mandatory. Never omit it. Place it as the very last lines of the post body.

OTHER RULES:
- Return ONLY valid Hugo markdown with frontmatter
- Frontmatter fields: title, date (today), description (under 155 chars), tags (array of 3-5 relevant tags), slug
- NEVER use em dashes (—) under any circumstances. Use periods, commas, or colons instead.
- Do not use double hyphens (--) as em dashes either."""


PEXELS_SEARCH_MAP = {
    'battery': ('car battery jumper cables', 'mechanic checking car battery', 'auto repair shop mechanic'),
    'tow': ('tow truck road', 'tow truck loading car', 'roadside assistance highway'),
    'overheated': ('car overheating engine steam', 'mechanic engine coolant', 'tow truck highway'),
    'overheating': ('car overheating engine steam', 'mechanic engine coolant', 'tow truck highway'),
    'cost': ('mechanic repair shop', 'tow truck road', 'roadside assistance car'),
    'how-much': ('mechanic repair shop', 'tow truck road', 'roadside assistance car'),
    'highway': ('car broken down highway', 'hazard lights car road', 'tow truck highway'),
    'snow': ('car snow winter road', 'car jump start cold weather', 'snow car winter emergency'),
    'cold': ('car snow winter road', 'car jump start cold weather', 'snow car winter emergency'),
    'winter': ('car snow winter road', 'car jump start cold weather', 'snow car winter emergency'),
    'frozen': ('car snow winter road', 'frozen car battery cold', 'snow car winter emergency'),
    'tire': ('flat tire roadside', 'changing tire car', 'roadside assistance'),
    'axle': ('car broken down road', 'mechanic under car repair', 'tow truck loading car'),
    'oil': ('car engine oil', 'mechanic checking oil dipstick', 'car repair shop'),
    'grind': ('mechanic car repair', 'car wheel brake inspection', 'auto mechanic shop'),
    'noise': ('mechanic car repair', 'car wheel brake inspection', 'auto mechanic shop'),
    'shake': ('mechanic car repair', 'car wheel alignment', 'auto repair shop'),
    'stall': ('car broken down roadside', 'mechanic car engine', 'roadside assistance car'),
    'dies': ('car broken down roadside', 'mechanic car engine', 'roadside assistance car'),
    'start': ('car broken down roadside', 'mechanic car engine diagnostic', 'roadside assistance car'),
    'check-engine': ('car dashboard warning lights', 'mechanic obd scanner', 'auto repair diagnostic'),
    'alternator': ('car alternator mechanic', 'car electrical system', 'auto repair shop'),
    'insurance': ('car insurance road', 'tow truck road', 'roadside assistance'),
    'night': ('car broken down night road', 'hazard triangle road safety', 'tow truck night'),
    'emergency': ('car emergency kit supplies', 'roadside emergency equipment', 'car trunk emergency supplies'),
    'kit': ('car emergency kit supplies', 'roadside emergency equipment', 'car trunk emergency supplies'),
    'illegal': ('car parked road shoulder', 'car hazard lights road', 'tow truck impound'),
    'roadside': ('car breakdown roadside', 'roadside assistance car', 'tow truck road'),
}
PEXELS_DEFAULT = ('car breakdown roadside', 'mechanic car repair', 'tow truck road')


def get_image_search_terms(slug: str) -> tuple[str, str, str]:
    s = slug.lower()
    for key, terms in PEXELS_SEARCH_MAP.items():
        if key in s:
            return terms
    return PEXELS_DEFAULT


def fetch_pexels_photo(search_term: str, index: int = 1) -> dict | None:
    if not PEXELS_API_KEY:
        return None
    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": search_term, "orientation": "landscape", "per_page": 5, "size": "large"},
            timeout=20
        )
        if resp.status_code != 200:
            print(f"Pexels API error {resp.status_code} for '{search_term}'")
            return None
        photos = resp.json().get("photos", [])
        if not photos:
            return None
        return photos[min(index, len(photos) - 1)]
    except Exception as e:
        print(f"Pexels fetch error: {e}")
        return None


def download_pexels_image(photo: dict, save_path: Path) -> bool:
    url = photo.get("src", {}).get("large2x") or photo.get("src", {}).get("large")
    if not url:
        return False
    try:
        resp = requests.get(url, stream=True, timeout=30)
        if resp.status_code != 200:
            return False
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"Image download error: {e}")
        return False


def add_images_to_post(content: str, slug: str) -> str:
    """Fetch 3 images from Pexels and inject into post content + frontmatter."""
    if not PEXELS_API_KEY:
        print("PEXELS_API_KEY not set — skipping image fetch")
        return content

    hero_term, mid_term, bottom_term = get_image_search_terms(slug)
    img_dir = IMAGES_DIR / slug
    img_dir.mkdir(parents=True, exist_ok=True)

    # Hero image
    hero_path = img_dir / "hero.jpg"
    if not hero_path.exists():
        photo = fetch_pexels_photo(hero_term, index=1)
        if photo:
            if download_pexels_image(photo, hero_path):
                print(f"Downloaded hero: {hero_path}")
            else:
                print(f"Failed to download hero image for {slug}")

    # Mid image
    mid_path = img_dir / "mid.jpg"
    if not mid_path.exists():
        photo = fetch_pexels_photo(mid_term, index=1)
        if photo:
            if download_pexels_image(photo, mid_path):
                print(f"Downloaded mid: {mid_path}")

    # Bottom image
    bottom_path = img_dir / "bottom.jpg"
    if not bottom_path.exists():
        photo = fetch_pexels_photo(bottom_term, index=1)
        if photo:
            if download_pexels_image(photo, bottom_path):
                print(f"Downloaded bottom: {bottom_path}")

    # Add image field to frontmatter
    image_field = f'image: "/images/{slug}/hero.jpg"'
    if 'image:' not in content[:500]:
        content = re.sub(
            r'^(---\n)',
            f'\\1{image_field}\n',
            content,
            count=1
        )

    # Insert mid image after "What To Do" section (before next ## heading)
    if mid_path.exists():
        mid_md = f'\n![{mid_term}](/images/{slug}/mid.jpg)\n*Photo: Pexels*\n'
        # Find the ## What To Do section and the next ## after it
        match = re.search(r'(## What To Do.*?)(\n## )', content, re.DOTALL | re.IGNORECASE)
        if match:
            insert_pos = match.start(2)
            content = content[:insert_pos] + mid_md + content[insert_pos:]
        else:
            # Fallback: insert at rough midpoint of content body
            fm_end = content.find('---', 3) + 3
            body = content[fm_end:]
            mid_point = len(body) // 2
            content = content[:fm_end + mid_point] + mid_md + content[fm_end + mid_point:]

    # Insert bottom image before the end (just before last ## or at end)
    if bottom_path.exists():
        bottom_md = f'\n![{bottom_term}](/images/{slug}/bottom.jpg)\n*Photo: Pexels*\n'
        # Find last ## section (## Stay Safe or last heading) to insert before it
        matches = list(re.finditer(r'\n## ', content))
        if len(matches) >= 2:
            last_section = matches[-1].start()
            content = content[:last_section] + '\n' + bottom_md + content[last_section:]
        else:
            content = content.rstrip() + '\n' + bottom_md

    return content


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')


def _parse_keyword_line(raw: str) -> tuple[str, int | None]:
    """Return (keyword, score_or_None) from a raw line (after stripping # DONE)."""
    m = re.match(r'^\[(\d+)\]\s*(.+)$', raw.strip())
    if m:
        return m.group(2).strip(), int(m.group(1))
    return raw.strip(), None


def load_keywords() -> list[tuple[int, str, int | None, bool]]:
    """Returns list of (line_index, keyword, score_or_None, is_done)"""
    if not KEYWORDS_FILE.exists():
        return []
    lines = KEYWORDS_FILE.read_text(encoding='utf-8').splitlines()
    result = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        is_done = stripped.startswith('# DONE')
        raw = stripped.replace('# DONE', '').strip() if is_done else stripped
        keyword, score = _parse_keyword_line(raw)
        result.append((i, keyword, score, is_done))
    return result


def mark_done(keyword: str):
    """Mark a keyword as # DONE in keywords.txt, preserving any [N] score prefix."""
    lines = KEYWORDS_FILE.read_text(encoding='utf-8').splitlines()
    for i, line in enumerate(lines):
        raw = line.strip()
        if raw.startswith('# DONE'):
            continue
        kw, _score = _parse_keyword_line(raw)
        if kw.lower() == keyword.lower():
            lines[i] = f"# DONE {raw}"
            break
    KEYWORDS_FILE.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def append_long_tails(keyword: str):
    """Add 3 long-tail variations to keywords.txt"""
    city = random.choice(CITIES)
    variations = [
        f"{keyword} in winter",
        f"{keyword} at night",
        f"{keyword} in {city}",
    ]
    with KEYWORDS_FILE.open('a', encoding='utf-8') as f:
        for v in variations:
            f.write(v + '\n')
    print(f"Appended 3 long-tail variations for: {keyword}")


def generate_post(keyword: str) -> str:
    """Call Claude API and return Hugo markdown content"""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    today = date.today().isoformat()

    user_message = f"Write a complete Hugo markdown post for the keyword: \"{keyword}\"\nToday's date: {today}\nMake it genuinely useful for someone searching this exact phrase in a stressful moment."

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}]
    )

    content = message.content[0].text.strip()

    # Strip markdown code fences if present
    if content.startswith('```'):
        content = re.sub(r'^```\w*\n?', '', content)
        content = re.sub(r'\n?```$', '', content)

    return content


def extract_slug(content: str, keyword: str) -> str:
    """Extract slug from frontmatter, or derive from keyword"""
    match = re.search(r'^slug:\s*["\']?([^"\'|\n]+)["\']?\s*$', content, re.MULTILINE)
    if match:
        return match.group(1).strip().strip('"\'')
    return slugify(keyword)


# City/location keywords — used to distinguish local vs general
LOCAL_INDICATORS = [
    "denver", "houston", "phoenix", "atlanta", "chicago", "seattle", "dallas",
    "miami", "los angeles", "new york", "las vegas", "san antonio", "austin",
    "nashville", "portland", "minneapolis", "detroit", "charlotte", "indianapolis",
    "columbus", "san diego", "jacksonville", "memphis", "baltimore", "boston",
    "fort worth", "el paso", "oklahoma city", "tucson", "albuquerque",
    "near me", "in my city", "in my area", "local", "nearby",
]


def is_local(keyword: str) -> bool:
    kw = keyword.lower()
    return any(loc in kw for loc in LOCAL_INDICATORS)


def pick_keyword(post_type: str) -> tuple[str, int | None]:
    """Pick highest-scored keyword matching post_type ('general' or 'local').
    Falls back to unscored keywords if no scored ones exist.
    Runs keyword_research.py first if no pending keywords at all."""
    keywords = load_keywords()
    pending = [(i, kw, score) for i, kw, score, done in keywords if not done]

    if not pending:
        print("No pending keywords. Running keyword_research.py first...")
        import subprocess
        result = subprocess.run(
            [sys.executable, str(Path(__file__).parent / "keyword_research.py")],
            capture_output=False
        )
        if result.returncode != 0:
            print("ERROR: keyword_research.py failed", file=sys.stderr)
            sys.exit(1)
        keywords = load_keywords()
        pending = [(i, kw, score) for i, kw, score, done in keywords if not done]
        if not pending:
            print("Still no pending keywords after research.", file=sys.stderr)
            sys.exit(1)

    # Filter by type
    if post_type == "local":
        typed = [(i, kw, s) for i, kw, s in pending if is_local(kw)]
        type_label = "local/city"
    else:
        typed = [(i, kw, s) for i, kw, s in pending if not is_local(kw)]
        type_label = "general"

    if not typed:
        print(f"No pending {type_label} keywords found. Falling back to any pending keyword.")
        typed = pending

    # Sort scored ones by score desc; unscored go to end
    scored = [(i, kw, s) for i, kw, s in typed if s is not None]
    unscored = [(i, kw, s) for i, kw, s in typed if s is None]
    scored.sort(key=lambda x: x[2], reverse=True)
    ordered = scored + unscored

    _idx, keyword, score = ordered[0]
    if score is not None:
        print(f"Selected {type_label} keyword (score [{score}]): {keyword}")
    else:
        print(f"Selected {type_label} keyword (unscored): {keyword}")
    return keyword, score


def ensure_backlink(content: str, slug: str) -> str:
    """Ensure the post body contains a backlink to towwiththeflow.com/{slug}/.
    Appends the standard block if missing."""
    if f"towwiththeflow.com/{slug}/" in content:
        return content
    if "towwiththeflow.com" in content:
        return content  # has some backlink, leave it
    backlink = (
        "\n\n---\n\n"
        f"*Need roadside help? Visit [Tow With The Flow](https://towwiththeflow.com/{slug}/) "
        "for real answers when your car breaks down.*"
    )
    return content.rstrip() + backlink + "\n"


def main():
    parser = argparse.ArgumentParser(description="Generate a TWTF blog post")
    parser.add_argument(
        "--type",
        choices=["general", "local"],
        default="general",
        help="general = non-local keyword; local = city/location keyword",
    )
    args = parser.parse_args()
    post_type = args.type

    keyword, score = pick_keyword(post_type)

    content = generate_post(keyword)
    slug = extract_slug(content, keyword)
    filename = POSTS_DIR / f"{slug}.md"

    # Avoid overwriting existing posts
    if filename.exists():
        slug = slug + "-2"
        filename = POSTS_DIR / f"{slug}.md"

    # Add images from Pexels
    content = add_images_to_post(content, slug)

    # Guarantee backlink is present
    content = ensure_backlink(content, slug)

    filename.write_text(content, encoding='utf-8')
    print(f"Saved: {filename}")

    # Record slug for the syndication job that follows
    slug_key = "last_local_slug.txt" if post_type == "local" else "last_general_slug.txt"
    slug_file = Path(__file__).parent / slug_key
    slug_file.write_text(slug, encoding='utf-8')
    # Also update legacy file so any existing tooling still works
    (Path(__file__).parent / "last_generated_slug.txt").write_text(slug, encoding='utf-8')
    print(f"Slug written to scripts/{slug_key}")

    mark_done(keyword)
    append_long_tails(keyword)


if __name__ == "__main__":
    main()
