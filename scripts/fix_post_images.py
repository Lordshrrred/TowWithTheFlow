#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections import defaultdict
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

POSTS_DIR = ROOT / "content" / "posts"
IMAGES_DIR = ROOT / "static" / "images"
PEXELS_INDEX_FILE = IMAGES_DIR / "_pexels_index.json"
PEXELS_API_KEY = (os.getenv("PEXELS_API_KEY") or "").strip().strip('"').strip("'")

if not PEXELS_API_KEY:
    raise SystemExit("ERROR: PEXELS_API_KEY not set")

STOPWORDS = {
    "a", "an", "the", "and", "or", "to", "for", "in", "on", "of", "with", "from", "at", "what", "do", "need",
}

CITY_WORDS = {
    "denver", "houston", "phoenix", "atlanta", "chicago", "seattle", "dallas", "miami", "albuquerque", "tucson",
    "austin", "nashville", "portland", "minneapolis", "detroit", "charlotte", "indianapolis", "columbus",
    "sandiego", "jacksonville", "memphis", "baltimore", "boston", "fortworth", "elpaso", "oklahomacity",
    "losangeles", "newyork", "lasvegas", "sanantonio",
}

THEME_MAP = {
    "battery": ["car battery jump start", "mechanic checking car battery terminals", "dead car battery roadside"],
    "alternator": ["car alternator mechanic", "car electrical system repair", "alternator warning light mechanic"],
    "overheat": ["car overheating steam from hood", "mechanic coolant system", "car radiator repair roadside"],
    "smoking": ["car smoking from hood roadside", "engine steam car breakdown", "tow truck for overheating car"],
    "grinding": ["car grinding noise mechanic", "brake inspection mechanic", "wheel bearing mechanic"],
    "clicking": ["car clicking wont start", "starter motor mechanic", "car ignition diagnosis"],
    "snow": ["car stuck in snow roadside", "winter roadside assistance", "tow truck in snow"],
    "tire": ["flat tire roadside assistance", "changing tire on shoulder", "tire blowout highway"],
    "axle": ["broken axle car tow truck", "cv axle mechanic repair", "drivetrain failure car"],
    "insurance": ["roadside assistance phone call", "tow truck paperwork", "car insurance roadside claim"],
    "cost": ["tow truck on roadside", "roadside service invoice", "mechanic discussing towing cost"],
    "tow": ["tow truck loading broken car", "tow truck highway shoulder", "roadside assistance tow operator"],
    "roadside": ["roadside assistance at night", "car with hazard lights roadside", "tow truck arriving breakdown"],
}
DEFAULT_QUERIES = ["tow truck roadside assistance", "car breakdown on highway shoulder", "mechanic inspecting broken car"]


def load_index() -> dict:
    if not PEXELS_INDEX_FILE.exists():
        return {"used_ids": [], "by_slug": {}}
    try:
        data = json.loads(PEXELS_INDEX_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("used_ids", [])
    data.setdefault("by_slug", {})
    return data


def save_index(data: dict) -> None:
    PEXELS_INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    PEXELS_INDEX_FILE.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_image_field(md: str) -> str:
    m = re.search(r'^image:\s*["\']?([^"\'\n]+)["\']?\s*$', md, re.M)
    return (m.group(1).strip() if m else "")


def set_image_field(md: str, slug: str) -> str:
    desired = f'/images/{slug}/hero.jpg'
    if re.search(r'^image:\s*["\']?[^"\'\n]+["\']?\s*$', md, re.M):
        return re.sub(r'^image:\s*["\']?[^"\'\n]+["\']?\s*$', f'image: "{desired}"', md, count=1, flags=re.M)
    return re.sub(r'^(---\n)', f'\\1image: "{desired}"\n', md, count=1)


def slug_words(slug: str) -> list[str]:
    return [w for w in slug.lower().split("-") if w and w not in STOPWORDS]


def build_queries(slug: str) -> list[str]:
    words = slug_words(slug)
    city_terms = [w for w in words if w in CITY_WORDS]
    queries: list[str] = []
    for key, vals in THEME_MAP.items():
        if key in slug:
            queries.extend(vals)
            break
    if city_terms:
        city = " ".join(city_terms)
        queries.extend([
            f"tow truck roadside assistance {city}",
            f"car breakdown highway {city}",
            f"mechanic car repair {city}",
        ])
    if len(words) >= 2:
        queries.append(" ".join(words[:6]))
    queries.extend(DEFAULT_QUERIES)

    out: list[str] = []
    seen = set()
    for q in queries:
        qn = q.strip().lower()
        if qn and qn not in seen:
            seen.add(qn)
            out.append(q.strip())
    return out[:8]


def seed_int(*parts: str) -> int:
    return int(hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:8], 16)


def fetch_photo(queries: list[str], slug: str, used_ids: set[int]) -> tuple[dict | None, str]:
    headers = {"Authorization": PEXELS_API_KEY}
    for i, q in enumerate(queries):
        seed = seed_int(slug, "hero", q, str(i))
        page = (seed % 10) + 1
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            headers=headers,
            params={"query": q, "orientation": "landscape", "per_page": 40, "size": "large", "page": page},
            timeout=25,
        )
        if resp.status_code != 200:
            continue
        photos = resp.json().get("photos", [])
        if not photos:
            continue
        fresh = [p for p in photos if int(p.get("id", 0) or 0) not in used_ids]
        pool = fresh if fresh else photos
        if not pool:
            continue
        chosen = pool[seed % len(pool)]
        return chosen, q
    return None, ""


def download(photo: dict, path: Path) -> bool:
    src = photo.get("src", {})
    url = src.get("large2x") or src.get("large")
    if not url:
        return False
    r = requests.get(url, stream=True, timeout=30)
    if r.status_code != 200:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    return True


def hero_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    posts = sorted([p for p in POSTS_DIR.glob("*.md") if p.stem != "_index"])
    index = load_index()
    used_ids = {int(x) for x in index.get("used_ids", []) if isinstance(x, int) or str(x).isdigit()}

    # Detect duplicates among current heroes.
    by_hash: dict[str, list[str]] = defaultdict(list)
    for post in posts:
        slug = post.stem
        hp = IMAGES_DIR / slug / "hero.jpg"
        if hp.exists():
            by_hash[hero_hash(hp)].append(slug)
    duplicate_replace = set()
    for slugs in by_hash.values():
        if len(slugs) > 1:
            duplicate_replace.update(slugs[1:])

    targets = []
    for post in posts:
        slug = post.stem
        md = post.read_text(encoding="utf-8", errors="ignore")
        img = parse_image_field(md)
        hp = IMAGES_DIR / slug / "hero.jpg"
        need = False
        reason = []
        if not img:
            need = True
            reason.append("missing_image_field")
        if img and (not img.startswith("/images/") or not (ROOT / "static" / img.lstrip("/")).exists()):
            need = True
            reason.append("broken_image_path")
        if not hp.exists():
            need = True
            reason.append("missing_hero_file")
        if slug in duplicate_replace:
            need = True
            reason.append("duplicate_hero")
        if need:
            targets.append((post, reason))

    print(f"Posts scanned: {len(posts)}")
    print(f"Hero duplicates to replace: {len(duplicate_replace)}")
    print(f"Targets: {len(targets)}")

    updated = 0
    for post, reason in targets:
        slug = post.stem
        md = post.read_text(encoding="utf-8", errors="ignore")
        queries = build_queries(slug)
        photo, q = fetch_photo(queries, slug, used_ids)
        if not photo:
            print(f"[skip] {slug}: no pexels photo ({','.join(reason)})")
            continue

        hp = IMAGES_DIR / slug / "hero.jpg"
        if not download(photo, hp):
            print(f"[skip] {slug}: download failed")
            continue

        pid = int(photo.get("id", 0) or 0)
        if pid:
            used_ids.add(pid)
        index["used_ids"] = sorted(list(used_ids))
        by_slug = index.setdefault("by_slug", {})
        row = by_slug.setdefault(slug, {})
        row["hero"] = {
            "id": pid,
            "query": q,
            "url": photo.get("url", ""),
            "photographer": photo.get("photographer", ""),
            "updated": int(time.time()),
        }

        new_md = set_image_field(md, slug)
        if new_md != md:
            post.write_text(new_md, encoding="utf-8")
        save_index(index)
        updated += 1
        print(f"[ok] {slug}: {','.join(reason)} -> hero updated (id={pid})")
        time.sleep(0.25)

    print(f"Done. Updated {updated}/{len(targets)} target posts.")


if __name__ == "__main__":
    main()
