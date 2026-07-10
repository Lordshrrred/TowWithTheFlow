#!/usr/bin/env python3
"""
Tow With The Flow — Daily Post Generator
Usage:
  python generate_post.py --type general   # highest scored non-local keyword
  python generate_post.py --type local     # highest scored local/city keyword
Saves slug to last_general_slug.txt or last_local_slug.txt for syndication jobs.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import subprocess
import hashlib
import json
from datetime import date
from pathlib import Path
from dotenv import load_dotenv
import anthropic
import requests

from claude_utils import make_client, create_message
from clusters import assign_cluster
from assign_clusters import set_cluster_field

# Load .env from repo root
ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

def env_clean(key: str, default: str = "") -> str:
    val = os.getenv(key, default)
    if not isinstance(val, str):
        return default
    val = val.strip()
    if len(val) >= 2 and (
        (val[0] == '"' and val[-1] == '"') or
        (val[0] == "'" and val[-1] == "'")
    ):
        val = val[1:-1].strip()
    return val


ANTHROPIC_API_KEY = env_clean("ANTHROPIC_API_KEY")

PEXELS_API_KEY = env_clean("PEXELS_API_KEY")
IMAGES_DIR = ROOT / "static" / "images"
PEXELS_INDEX_FILE = IMAGES_DIR / "_pexels_index.json"

KEYWORDS_FILE = Path(__file__).parent / "keywords.txt"
POSTS_DIR = ROOT / "content" / "posts"
POSTS_DIR.mkdir(parents=True, exist_ok=True)

SYSTEM_PROMPT = """You are writing a page for towwiththeflow.com, a car breakdown and roadside emergency help site. Write in the voice of a knowledgeable mechanic who is direct and wastes no words.

TARGET LENGTH: 700-1100 words total (body only, not counting frontmatter). Be thorough but tight. Every sentence must earn its place. No filler, no padding, no AI-sounding transitions, no conclusions that just restate what you said.

STRUCTURE:
1. Quick Answer block: 50-80 words inside a markdown blockquote starting with **Quick Answer:**
2. 3-5 body sections. EVERY section heading (H2, "## ...") MUST be phrased as a real question, the way someone would actually type it or ask a mechanic out loud. Not a label, a question.
   - Bad: "## What To Do"
   - Good: "## What Do I Do If My Car Won't Start on I-25?" (local) or "## What Do I Do If My Brakes Fail While Driving?" (general)
   - Cover the same ground the old fixed sections did (immediate steps, cost, safety) but let the specific keyword drive the actual questions. Not every post needs a cost question or a safety question. Use judgment: ask what this reader would actually ask next.
3. DIRECT-ANSWER-FIRST (REQUIRED, every section): The first 1-2 sentences under EVERY H2 must directly answer that section's question in plain language, before any steps, list, or table. A reader skimming just the first sentence of each section should get the real answer, not a setup sentence.
   - Bad: "There are several factors that affect towing cost in Denver. Let's look at them:" (this is a setup sentence, not an answer)
   - Good: "A local tow in Denver runs $75 to $150 for the first few miles. Here's the full breakdown:"
4. Common Questions: exactly 5 Q&A pairs, formatted EXACTLY like this (this exact format is required, it gets parsed programmatically):

## Common Questions

**Q: [question in the reader's own words]?**
A: [direct answer, 1-3 sentences, no filler]

**Q: [second question]?**
A: [answer]

(continue for a total of 5 pairs)

Pick questions a reader would actually type into Google right after this one, not generic filler questions. Answers must be genuinely useful on their own, not just a teaser pointing back into the article.

SPECIFIC DETAIL (REQUIRED):
Every post must include at least one concrete, real, verifiable detail, not generic filler. For local posts: a real highway name/number, a real neighborhood, a real interchange, or similarly specific local detail (e.g. "I-25 near the Colorado Boulevard exit," "the foothills west of C-470"). For general posts: a real part name, a real symptom, a real brand/model detail, or a similarly specific mechanical detail. Never fabricate a statistic, survey result, or percentage that you cannot ground in something real, if you're not sure a number is true, describe the situation instead of inventing a number.

NEVER invent a phone number, direct dial extension, street address, or named contact for any third party (tow company, government agency, dispatch line, hospital, etc.), even if it sounds plausible. You cannot verify these are current or correct, and a wrong number in roadside-emergency content is actively dangerous. It is fine to reference well-known, genuinely universal services by name only (911, 511 for state road conditions, AAA, a state DOT's traffic app by name) without a specific phone number attached. Do not state or imply a specific agency's dispatch number.

INTERNAL LINKING (REQUIRED):
The user message will include a list of existing articles on towwiththeflow.com. Include 2-4 internal links using markdown [anchor text](/{slug}/) where the link is genuinely useful to the reader mid-sentence or at the end of a relevant paragraph. Only link to articles that are semantically related to the topic being written. Never dump a link list. Never force a link that does not fit.
- If this is a LOCAL post and the article list includes other posts about the SAME city, prefer linking to those same-city posts over generic ones when they're genuinely relevant (e.g. a Denver towing-cost post linking to another Denver post about response times or insurance, rather than a Phoenix post about the same topic). Don't force a same-city link that isn't actually relevant.

BACKLINK REQUIREMENT — NON-NEGOTIABLE:
Every post MUST end with EXACTLY this block (substituting the actual slug):

---

*Need roadside help? Visit [Tow With The Flow](https://towwiththeflow.com/{slug}/) for real answers when your car breaks down.*

This block is mandatory. Never omit it. Place it as the very last lines of the post body.

OTHER RULES:
- Return ONLY valid Hugo markdown with frontmatter
- Frontmatter fields: title, date (today), description (under 155 chars), tags (array of 3-5 relevant tags), slug
- NEVER use em dashes (—) under any circumstances. Use periods, commas, or colons instead.
- Do not use double hyphens (--) as em dashes either.

CONTENT STRATEGY:
- The site intentionally publishes both nationwide roadside-help posts and local/city posts.
- For general keywords, write for drivers anywhere in the United States. Do not force Denver, Colorado, or any city into the article unless the keyword asks for it.
- For local or city keywords, include useful local context. Denver is the core local market, but other high-density, high-traffic metros are valid when the keyword names them.
- Do not create local context for small, low-volume places unless the keyword already targets that place.

VOICE:
- Calm, practical, and specific. Help the reader make the next good decision while they are stressed.
- Open by naming the exact car problem or towing question in plain language.
- Use short paragraphs, concrete examples, and at least one specific actionable tip.
- Never open with "In today's world" or "In this article we will".
- Never end with "I hope this helps".
"""


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


def load_pexels_index() -> dict:
    if not PEXELS_INDEX_FILE.exists():
        return {"used_ids": [], "by_slug": {}}
    try:
        data = json.loads(PEXELS_INDEX_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"used_ids": [], "by_slug": {}}
        data.setdefault("used_ids", [])
        data.setdefault("by_slug", {})
        return data
    except Exception:
        return {"used_ids": [], "by_slug": {}}


def save_pexels_index(index: dict) -> None:
    PEXELS_INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    PEXELS_INDEX_FILE.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _seed_int(*parts: str) -> int:
    raw = "|".join(parts).encode("utf-8")
    return int(hashlib.sha1(raw).hexdigest()[:8], 16)


def fetch_pexels_photo(search_term: str, slug: str, slot: str, used_ids: set[int] | None = None) -> dict | None:
    if not PEXELS_API_KEY:
        return None
    try:
        used_ids = used_ids or set()
        seed = _seed_int(slug, slot, search_term)
        per_page = 30
        page = (seed % 8) + 1
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": PEXELS_API_KEY},
            params={
                "query": search_term,
                "orientation": "landscape",
                "per_page": per_page,
                "size": "large",
                "page": page,
            },
            timeout=20
        )
        if resp.status_code != 200:
            detail = ""
            try:
                detail = resp.json().get("error", "")
            except Exception:
                detail = resp.text[:160]
            print(f"Pexels API error {resp.status_code} for '{search_term}': {detail}")
            return None
        photos = resp.json().get("photos", [])
        if not photos:
            return None
        # Prefer photos not used before across the site.
        fresh = [p for p in photos if int(p.get("id", 0) or 0) not in used_ids]
        pool = fresh if fresh else photos
        if not pool:
            return None
        idx = seed % len(pool)
        return pool[idx]
    except Exception as e:
        print(f"Pexels fetch error: {e}")
        return None


MAX_IMAGE_WIDTH = 1200
JPEG_QUALITY = 80


def resize_and_compress_image(path: Path, max_width: int = MAX_IMAGE_WIDTH, quality: int = JPEG_QUALITY) -> None:
    """Downscale + re-compress an image in place. Pexels 'large2x' downloads
    can be 3-4MB at full resolution — far larger than this site ever displays
    them (hero images cap at 460px tall in a 760px container). Silently
    no-ops if Pillow isn't installed or the file can't be processed, so a
    slow image pipeline never blocks a post from publishing."""
    try:
        from PIL import Image
    except ImportError:
        return
    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            if img.width > max_width:
                new_height = round(img.height * (max_width / img.width))
                img = img.resize((max_width, new_height), Image.LANCZOS)
            img.save(path, "JPEG", quality=quality, optimize=True, progressive=True)
    except Exception as e:
        print(f"Image optimize error ({path.name}): {e}")


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
        resize_and_compress_image(save_path)
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
    pindex = load_pexels_index()
    used_ids = {int(x) for x in pindex.get("used_ids", []) if isinstance(x, int) or str(x).isdigit()}

    def _remember(slot: str, term: str, photo: dict) -> None:
        pid = int(photo.get("id", 0) or 0)
        if pid:
            used_ids.add(pid)
        pindex["used_ids"] = sorted(list(used_ids))
        by_slug = pindex.setdefault("by_slug", {})
        row = by_slug.setdefault(slug, {})
        row[slot] = {
            "id": pid,
            "query": term,
            "url": photo.get("url", ""),
            "photographer": photo.get("photographer", ""),
        }
        save_pexels_index(pindex)

    # Hero image
    hero_path = img_dir / "hero.jpg"
    hero_ok = hero_path.exists()
    if not hero_path.exists():
        photo = fetch_pexels_photo(hero_term, slug, "hero", used_ids)
        if photo:
            if download_pexels_image(photo, hero_path):
                print(f"Downloaded hero: {hero_path}")
                _remember("hero", hero_term, photo)
                hero_ok = True
            else:
                print(f"Failed to download hero image for {slug}")

    # Mid image
    mid_path = img_dir / "mid.jpg"
    mid_ok = mid_path.exists()
    if not mid_path.exists():
        photo = fetch_pexels_photo(mid_term, slug, "mid", used_ids)
        if photo:
            if download_pexels_image(photo, mid_path):
                print(f"Downloaded mid: {mid_path}")
                _remember("mid", mid_term, photo)
                mid_ok = True

    # Bottom image
    bottom_path = img_dir / "bottom.jpg"
    bottom_ok = bottom_path.exists()
    if not bottom_path.exists():
        photo = fetch_pexels_photo(bottom_term, slug, "bottom", used_ids)
        if photo:
            if download_pexels_image(photo, bottom_path):
                print(f"Downloaded bottom: {bottom_path}")
                _remember("bottom", bottom_term, photo)
                bottom_ok = True

    # Add image field to frontmatter only when hero file exists.
    image_field = f'image: "/images/{slug}/hero.jpg"'
    if hero_ok and 'image:' not in content[:500]:
        content = re.sub(r'^(---\n)', f'\\1{image_field}\n', content, count=1)
    elif not hero_ok:
        # Prevent broken featured image URLs if downloads failed.
        content = re.sub(r'^image:\s*["\']?.+?["\']?\s*$', '', content, flags=re.MULTILINE)

    # Insert mid image after "What To Do" section (before next ## heading)
    if mid_ok:
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
    if bottom_ok:
        bottom_md = f'\n![{bottom_term}](/images/{slug}/bottom.jpg)\n*Photo: Pexels*\n'
        # Find last ## section (## Stay Safe or last heading) to insert before it
        matches = list(re.finditer(r'\n## ', content))
        if len(matches) >= 2:
            last_section = matches[-1].start()
            content = content[:last_section] + '\n' + bottom_md + content[last_section:]
        else:
            content = content.rstrip() + '\n' + bottom_md

    if not any([hero_ok, mid_ok, bottom_ok]):
        print(f"Pexels image downloads unavailable for '{slug}' — post will publish without local images.")

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


def generate_post(keyword: str, post_index: list[tuple[str, str]] | None = None, city: str | None = None) -> str:
    """Call Claude API and return Hugo markdown content"""
    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    client = make_client(ANTHROPIC_API_KEY)
    today = date.today().isoformat()

    index_section = ""
    if post_index:
        entries = post_index[:80]
        note = ""
        if city:
            # Surface same-city posts first so Claude actually sees them
            # within the 80-entry window, and can prefer linking to them.
            same_city = [(s, t) for s, t in post_index if city.split(",")[0].lower() in t.lower()]
            other = [(s, t) for s, t in post_index if (s, t) not in same_city]
            entries = (same_city + other)[:80]
            note = f"\n\nEntries marked [SAME CITY] are other {city} posts — prefer linking to these when relevant."
        lines = [
            f"/{slug}/ | {title}" + (" [SAME CITY]" if city and city.split(",")[0].lower() in title.lower() else "")
            for slug, title in entries
        ]
        index_section = (
            "\n\nEXISTING ARTICLES ON towwiththeflow.com (for internal linking):\n"
            + "\n".join(lines)
            + "\n\nInclude 2-4 internal links to semantically related articles from this list."
            + note
        )

    city_note = f"\nThis is a LOCAL post for {city}. Use real {city.split(',')[0]} details (highways, neighborhoods, interchanges)." if city else ""

    user_message = (
        f"Write a complete Hugo markdown post for the keyword: \"{keyword}\"\n"
        f"Today's date: {today}\n"
        f"Make it genuinely useful for someone searching this exact phrase in a stressful moment."
        f"{city_note}"
        f"{index_section}"
    )

    message = create_message(
        client,
        model="claude-sonnet-4-6",
        max_tokens=3200,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
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


def load_post_index() -> list[tuple[str, str]]:
    """Return (slug, title) for all existing posts, newest first."""
    entries = []
    for f in POSTS_DIR.glob("*.md"):
        if f.name in {"_index.md", "tow-content-log.md"}:
            continue
        try:
            text = f.read_text(encoding="utf-8")
            date_m = re.search(r'^date:\s*(.+?)\s*$', text, re.MULTILINE)
            post_date = date_m.group(1).strip()[:10] if date_m else "2000-01-01"
            title_m = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', text, re.MULTILINE)
            title = title_m.group(1).strip().strip("\"'") if title_m else f.stem
        except Exception:
            post_date, title = "2000-01-01", f.stem
        entries.append((post_date, f.stem, title))
    entries.sort(reverse=True)
    return [(slug, title) for _, slug, title in entries]


def count_body_words(content: str) -> int:
    """Count words in post body, excluding frontmatter and image markdown."""
    body = re.sub(r'^---\n.*?\n---\n?', '', content, flags=re.DOTALL)
    body = re.sub(r'!\[.*?\]\(.*?\)', '', body)
    return len(body.split())


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


# Real city name -> "City, ST" display string, for LocalBusiness/areaServed
# schema and for grouping local posts by city. Only actual place names —
# not the generic "near me" / "local" / "nearby" indicators above.
CITY_STATE = {
    "denver": "Denver, CO", "houston": "Houston, TX", "phoenix": "Phoenix, AZ",
    "atlanta": "Atlanta, GA", "chicago": "Chicago, IL", "seattle": "Seattle, WA",
    "dallas": "Dallas, TX", "miami": "Miami, FL", "los angeles": "Los Angeles, CA",
    "new york": "New York, NY", "las vegas": "Las Vegas, NV",
    "san antonio": "San Antonio, TX", "austin": "Austin, TX",
    "nashville": "Nashville, TN", "portland": "Portland, OR",
    "minneapolis": "Minneapolis, MN", "detroit": "Detroit, MI",
    "charlotte": "Charlotte, NC", "indianapolis": "Indianapolis, IN",
    "columbus": "Columbus, OH", "san diego": "San Diego, CA",
    "jacksonville": "Jacksonville, FL", "memphis": "Memphis, TN",
    "baltimore": "Baltimore, MD", "boston": "Boston, MA",
    "fort worth": "Fort Worth, TX", "el paso": "El Paso, TX",
    "oklahoma city": "Oklahoma City, OK", "tucson": "Tucson, AZ",
    "albuquerque": "Albuquerque, NM",
}


def extract_city(text: str) -> str | None:
    """Return the "City, ST" display string for the first recognized real
    city name in the text, or None (e.g. for "near me" / general keywords)."""
    t = text.lower()
    for city, display in CITY_STATE.items():
        if city in t:
            return display
    return None


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
    Appends the standard block if missing. Only the exact self-referential
    link counts — an internal link to some *other* post's slug also contains
    "towwiththeflow.com" and must not be mistaken for the canonical backlink."""
    if f"towwiththeflow.com/{slug}/" in content:
        return content
    backlink = (
        "\n\n---\n\n"
        f"*Need roadside help? Visit [Tow With The Flow](https://towwiththeflow.com/{slug}/) "
        "for real answers when your car breaks down.*"
    )
    return content.rstrip() + backlink + "\n"


FAQ_PATTERN = re.compile(
    r'\*\*Q:\s*(.+?)\*\*\s*\nA:\s*(.+?)(?=\n\s*\n\*\*Q:|\n\s*\n##|\n\s*\n---|\Z)',
    re.DOTALL,
)


def extract_faq_pairs(content: str) -> list[tuple[str, str]]:
    """Pull (question, answer) pairs out of a '**Q: ...**\\nA: ...' formatted
    Common Questions section. Returns [] if the post has none — FAQ schema
    is optional, not every post needs it."""
    pairs = []
    for q, a in FAQ_PATTERN.findall(content):
        q = " ".join(q.split()).strip()
        a = " ".join(a.split()).strip()
        if q and a:
            pairs.append((q, a))
    return pairs


def build_faq_yaml(pairs: list[tuple[str, str]]) -> str:
    """YAML frontmatter block for a list of (question, answer) pairs,
    consumed by the theme to emit FAQPage JSON-LD."""
    if not pairs:
        return ""
    lines = ["faq:"]
    for q, a in pairs:
        q_esc = q.replace('"', '\\"')
        a_esc = a.replace('"', '\\"')
        lines.append(f'  - q: "{q_esc}"')
        lines.append(f'    a: "{a_esc}"')
    return "\n".join(lines)


def insert_faq_frontmatter(content: str, faq_yaml: str) -> str:
    if not faq_yaml:
        return content
    if re.search(r'^faq:\s*$', content, re.MULTILINE):
        # Already has a faq: block from a previous run — replace it wholesale.
        content = re.sub(
            r'^faq:\s*\n(?:^  -.*\n?)+',
            '',
            content,
            count=1,
            flags=re.MULTILINE,
        )
    return re.sub(
        r'(^clusters:\s*.+$)',
        f'\\1\n{faq_yaml}',
        content,
        count=1,
        flags=re.MULTILINE,
    )


def main():
    parser = argparse.ArgumentParser(description="Generate a TWTF blog post")
    parser.add_argument(
        "--type",
        choices=["general", "local"],
        default="general",
        help="general = non-local keyword; local = city/location keyword",
    )
    parser.add_argument(
        "--slug-file",
        default=None,
        help="Override slug output filename (relative to scripts/). E.g. last_general_slug_2.txt",
    )
    args = parser.parse_args()
    post_type = args.type

    keyword, score = pick_keyword(post_type)
    city = extract_city(keyword)
    if city:
        print(f"Detected city: {city}")

    post_index = load_post_index()
    print(f"Loaded {len(post_index)} existing posts for internal linking")

    content = generate_post(keyword, post_index, city=city)
    slug = extract_slug(content, keyword)
    filename = POSTS_DIR / f"{slug}.md"

    # Avoid overwriting existing posts. Hugo builds the live URL from the
    # frontmatter `slug:` field, not the filename — so the disambiguated
    # slug must be written back into the frontmatter too, or this post
    # silently collides with the original at the same URL (one clobbers
    # the other in the build with no warning).
    if filename.exists():
        slug = slug + "-2"
        filename = POSTS_DIR / f"{slug}.md"
        content = re.sub(
            r'^slug:\s*.+$',
            f'slug: "{slug}"',
            content,
            count=1,
            flags=re.MULTILINE,
        )

    # Assign a content cluster (see clusters.py) — drives the /clusters/*/
    # hub pages and the automatic "Related Guides" internal linking.
    title_m = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE)
    cluster_slug, _cluster_label = assign_cluster(title_m.group(1) if title_m else keyword)
    content = set_cluster_field(content, cluster_slug)

    # Pull the Common Questions section (if present) into faq: frontmatter
    # so the theme can emit FAQPage JSON-LD from real, visible content.
    faq_pairs = extract_faq_pairs(content)
    content = insert_faq_frontmatter(content, build_faq_yaml(faq_pairs))

    # Local posts get a serviceArea field — drives AutomotiveBusiness schema
    # and the "Nearby <City> Guides" cross-linking in the theme.
    if city and not re.search(r'^serviceArea:\s*.+$', content, re.MULTILINE):
        content = re.sub(
            r'(^clusters:\s*.+$)',
            f'\\1\nserviceArea: "{city}"',
            content,
            count=1,
            flags=re.MULTILINE,
        )

    # Add images from Pexels
    content = add_images_to_post(content, slug)

    # Guarantee backlink is present
    content = ensure_backlink(content, slug)

    # Quality gate: reject posts that are too thin
    word_count = count_body_words(content)
    print(f"Word count: {word_count} words")
    if word_count < 400:
        print(
            f"ERROR: Post too thin ({word_count} words, minimum 400). "
            "The model may have truncated output. Check the keyword and rerun.",
            file=sys.stderr,
        )
        sys.exit(1)
    if word_count < 500:
        print(f"WARNING: Post is below target ({word_count} words, target 500-900). Proceeding.")

    filename.write_text(content, encoding='utf-8')
    print(f"Saved: {filename}")

    # Record slug for the syndication job that follows
    if args.slug_file:
        slug_file = Path(__file__).parent / args.slug_file
    else:
        slug_key = "last_local_slug.txt" if post_type == "local" else "last_general_slug.txt"
        slug_file = Path(__file__).parent / slug_key
    slug_file.write_text(slug, encoding='utf-8')
    # Also update legacy file so any existing tooling still works
    (Path(__file__).parent / "last_generated_slug.txt").write_text(slug, encoding='utf-8')
    print(f"Slug written to {slug_file.name}")

    mark_done(keyword)


if __name__ == "__main__":
    main()
