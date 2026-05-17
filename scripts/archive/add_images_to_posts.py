#!/usr/bin/env python3
"""
Tow With The Flow — Image Retrofit Script
Adds Pexels images to all existing posts that don't have them yet.
Run once after initial 30 posts are generated.
"""

import os
import re
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
import requests

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
if not PEXELS_API_KEY:
    print("ERROR: PEXELS_API_KEY not set in .env", file=sys.stderr)
    sys.exit(1)

POSTS_DIR = ROOT / "content" / "posts"
IMAGES_DIR = ROOT / "static" / "images"

# Search term mapping by slug keyword
PEXELS_SEARCH_MAP = {
    'battery':      ('car battery jumper cables',       'mechanic checking car battery',       'auto repair shop mechanic'),
    'tow':          ('tow truck road',                  'tow truck loading car',               'roadside assistance highway'),
    'overheated':   ('car overheating engine steam',    'mechanic engine coolant',             'tow truck highway'),
    'overheating':  ('car overheating engine steam',    'mechanic engine coolant',             'tow truck highway'),
    'cost':         ('mechanic repair shop',            'tow truck road',                      'roadside assistance car'),
    'how-much':     ('mechanic repair shop',            'tow truck road',                      'roadside assistance car'),
    'highway':      ('car broken down highway',         'hazard lights car road',              'tow truck highway'),
    'snow':         ('car snow winter road',            'car jump start cold weather',         'snow car winter emergency'),
    'cold':         ('car snow winter road',            'car jump start cold weather',         'snow car winter emergency'),
    'winter':       ('car snow winter road',            'car jump start cold weather',         'snow car winter emergency'),
    'frozen':       ('car snow winter road',            'frozen car battery cold',             'snow car winter emergency'),
    'tire':         ('flat tire roadside',              'changing tire car',                   'roadside assistance'),
    'axle':         ('car broken down road',            'mechanic under car repair',           'tow truck loading car'),
    'oil':          ('car engine oil',                  'mechanic checking oil dipstick',      'car repair shop'),
    'grind':        ('mechanic car repair',             'car wheel brake inspection',          'auto mechanic shop'),
    'noise':        ('mechanic car repair',             'car wheel brake inspection',          'auto mechanic shop'),
    'shake':        ('mechanic car repair',             'car wheel alignment',                 'auto repair shop'),
    'stall':        ('car broken down roadside',        'mechanic car engine',                 'roadside assistance car'),
    'dies':         ('car broken down roadside',        'mechanic car engine',                 'roadside assistance car'),
    'start':        ('car broken down roadside',        'mechanic car engine diagnostic',      'roadside assistance car'),
    'check-engine': ('car dashboard warning lights',    'mechanic obd scanner',                'auto repair diagnostic'),
    'alternator':   ('car alternator mechanic',         'car electrical system',               'auto repair shop'),
    'insurance':    ('car insurance road',              'tow truck road',                      'roadside assistance'),
    'night':        ('car broken down night road',      'hazard triangle road safety',         'tow truck night'),
    'emergency':    ('car emergency kit supplies',      'roadside emergency equipment',        'car trunk emergency supplies'),
    'kit':          ('car emergency kit supplies',      'roadside emergency equipment',        'car trunk emergency supplies'),
    'illegal':      ('car parked road shoulder',        'car hazard lights road',              'tow truck impound'),
    'roadside':     ('car breakdown roadside',          'roadside assistance car',             'tow truck road'),
    'run-out':      ('car engine oil warning',          'mechanic engine repair',              'tow truck road'),
    'broken-down':  ('car broken down road',            'hazard lights car',                   'tow truck loading car'),
}
PEXELS_DEFAULT = ('car breakdown roadside', 'mechanic car repair', 'tow truck road')


def get_search_terms(slug: str) -> tuple[str, str, str]:
    s = slug.lower()
    for key, terms in PEXELS_SEARCH_MAP.items():
        if key in s:
            return terms
    return PEXELS_DEFAULT


def fetch_pexels_photo(search_term: str, index: int = 1) -> dict | None:
    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": search_term, "orientation": "landscape", "per_page": 5, "size": "large"},
            timeout=20
        )
        if resp.status_code != 200:
            print(f"  Pexels error {resp.status_code} for '{search_term}'")
            return None
        photos = resp.json().get("photos", [])
        if not photos:
            print(f"  No photos found for '{search_term}'")
            return None
        return photos[min(index, len(photos) - 1)]
    except Exception as e:
        print(f"  Fetch error: {e}")
        return None


def download_image(photo: dict, save_path: Path) -> bool:
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
        print(f"  Download error: {e}")
        return False


def inject_images_into_post(content: str, slug: str, hero_term: str, mid_term: str, bottom_term: str) -> str:
    """Inject image frontmatter and inline image markdown into post content."""
    img_dir = IMAGES_DIR / slug

    # Add image field to frontmatter if missing
    if 'image:' not in content[:600]:
        image_field = f'image: "/images/{slug}/hero.jpg"'
        content = re.sub(r'^(---\n)', f'\\1{image_field}\n', content, count=1)

    mid_path = img_dir / "mid.jpg"
    bottom_path = img_dir / "bottom.jpg"

    # Insert mid image after the "What To Do" section
    if mid_path.exists() and f'/images/{slug}/mid.jpg' not in content:
        mid_md = f'\n![{mid_term}](/images/{slug}/mid.jpg)\n*Photo: Pexels*\n'
        match = re.search(r'(## What To Do.*?)(\n## )', content, re.DOTALL | re.IGNORECASE)
        if match:
            insert_pos = match.start(2)
            content = content[:insert_pos] + mid_md + content[insert_pos:]
        else:
            # Fallback: insert after first 40% of body
            fm_end = content.find('---', 3) + 3
            body_start = fm_end
            body_len = len(content) - body_start
            insert_at = body_start + int(body_len * 0.45)
            content = content[:insert_at] + mid_md + content[insert_at:]

    # Insert bottom image before last ## section
    if bottom_path.exists() and f'/images/{slug}/bottom.jpg' not in content:
        bottom_md = f'\n![{bottom_term}](/images/{slug}/bottom.jpg)\n*Photo: Pexels*\n'
        heading_matches = list(re.finditer(r'\n## ', content))
        if len(heading_matches) >= 2:
            last_section_pos = heading_matches[-1].start()
            content = content[:last_section_pos] + '\n' + bottom_md + content[last_section_pos:]
        else:
            content = content.rstrip() + '\n' + bottom_md

    return content


def process_post(md_file: Path) -> bool:
    """Process a single post file. Returns True if updated."""
    slug = md_file.stem
    if slug == '_index':
        return False

    content = md_file.read_text(encoding='utf-8')

    # Skip if images already present
    if 'image:' in content[:600] and f'/images/{slug}/hero.jpg' in content:
        print(f"  [skip] {slug} — already has images")
        return False

    print(f"\n[processing] {slug}")
    hero_term, mid_term, bottom_term = get_search_terms(slug)
    img_dir = IMAGES_DIR / slug
    img_dir.mkdir(parents=True, exist_ok=True)

    changed = False

    # Download hero
    hero_path = img_dir / "hero.jpg"
    if not hero_path.exists():
        print(f"  hero: '{hero_term}'")
        photo = fetch_pexels_photo(hero_term, index=1)
        if photo and download_image(photo, hero_path):
            print(f"  ✓ hero saved")
            changed = True
        else:
            print(f"  ✗ hero failed")
        time.sleep(0.4)  # respect rate limits

    # Download mid
    mid_path = img_dir / "mid.jpg"
    if not mid_path.exists():
        print(f"  mid: '{mid_term}'")
        photo = fetch_pexels_photo(mid_term, index=1)
        if photo and download_image(photo, mid_path):
            print(f"  ✓ mid saved")
            changed = True
        else:
            print(f"  ✗ mid failed")
        time.sleep(0.4)

    # Download bottom
    bottom_path = img_dir / "bottom.jpg"
    if not bottom_path.exists():
        print(f"  bottom: '{bottom_term}'")
        photo = fetch_pexels_photo(bottom_term, index=1)
        if photo and download_image(photo, bottom_path):
            print(f"  ✓ bottom saved")
            changed = True
        else:
            print(f"  ✗ bottom failed")
        time.sleep(0.4)

    # Update post content with image references
    updated_content = inject_images_into_post(content, slug, hero_term, mid_term, bottom_term)
    if updated_content != content:
        md_file.write_text(updated_content, encoding='utf-8')
        print(f"  ✓ post updated with image references")
        changed = True
    else:
        print(f"  post content unchanged")

    return changed


def main():
    posts = sorted(POSTS_DIR.glob("*.md"))
    print(f"Found {len(posts)} post files")
    print(f"Images directory: {IMAGES_DIR}\n")

    updated = 0
    skipped = 0

    for post_file in posts:
        if post_file.stem == '_index':
            continue
        if process_post(post_file):
            updated += 1
        else:
            skipped += 1

    print(f"\n{'='*50}")
    print(f"Done. Updated: {updated}, Skipped: {skipped}")


if __name__ == "__main__":
    main()
