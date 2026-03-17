#!/usr/bin/env python3
"""
Tow With The Flow — Daily Post Generator
Reads next unused keyword from keywords.txt, generates a Hugo post via Claude API,
saves to content/posts/, marks keyword as done, appends 3 long-tail variations,
then calls syndicate_post.py.
"""

import os
import re
import sys
import random
import subprocess
from datetime import date
from pathlib import Path
from dotenv import load_dotenv
import anthropic

# Load .env from repo root
ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
    sys.exit(1)

KEYWORDS_FILE = Path(__file__).parent / "keywords.txt"
POSTS_DIR = ROOT / "content" / "posts"
POSTS_DIR.mkdir(parents=True, exist_ok=True)

CITIES = ["Denver", "Houston", "Phoenix", "Atlanta", "Chicago", "Seattle", "Dallas", "Miami"]

SYSTEM_PROMPT = """You are writing a page for towwiththeflow.com, a car breakdown and roadside emergency help site. Write in the voice of a knowledgeable mechanic who is direct and wastes no words. Structure: first a Quick Answer block (50-80 words inside a markdown blockquote starting with **Quick Answer:**), then What To Do as numbered steps, then What It Might Cost if relevant, then Stay Safe if relevant. No filler, no AI-sounding language, no conclusions. Return ONLY valid Hugo markdown with frontmatter. Frontmatter fields: title, date (today), description (under 155 chars), tags (array of 3-5 relevant tags), slug."""


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')


def load_keywords() -> list[tuple[int, str, bool]]:
    """Returns list of (line_index, keyword, is_done)"""
    if not KEYWORDS_FILE.exists():
        return []
    lines = KEYWORDS_FILE.read_text(encoding='utf-8').splitlines()
    result = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        is_done = stripped.startswith('# DONE')
        keyword = stripped.replace('# DONE', '').strip() if is_done else stripped
        result.append((i, keyword, is_done))
    return result


def mark_done(keyword: str):
    """Mark a keyword as # DONE in keywords.txt"""
    lines = KEYWORDS_FILE.read_text(encoding='utf-8').splitlines()
    for i, line in enumerate(lines):
        if line.strip() == keyword:
            lines[i] = f"# DONE {keyword}"
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


def main():
    keywords = load_keywords()
    pending = [(i, kw) for i, kw, done in keywords if not done]

    if not pending:
        print("No pending keywords found. Run keyword_research.py to add more.")
        sys.exit(0)

    line_idx, keyword = pending[0]
    print(f"Generating post for: {keyword}")

    content = generate_post(keyword)
    slug = extract_slug(content, keyword)
    filename = POSTS_DIR / f"{slug}.md"

    # Avoid overwriting existing posts
    if filename.exists():
        slug = slug + "-2"
        filename = POSTS_DIR / f"{slug}.md"

    filename.write_text(content, encoding='utf-8')
    print(f"Saved: {filename}")

    mark_done(keyword)
    append_long_tails(keyword)

    # Syndicate
    syndicate_script = Path(__file__).parent / "syndicate_post.py"
    if syndicate_script.exists():
        result = subprocess.run(
            [sys.executable, str(syndicate_script), slug],
            capture_output=False
        )
        if result.returncode != 0:
            print(f"WARNING: syndication script exited with code {result.returncode}")
    else:
        print("syndicate_post.py not found, skipping syndication.")


if __name__ == "__main__":
    main()
