"""Preview or consolidate repeated titles, preserving established URLs and redirects."""
import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent


def identity(value):
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def field(text, name, fallback=""):
    match = re.search(r"^" + name + r":\s*(.*?)\s*$", text, re.M)
    return match.group(1).strip("\"'") if match else fallback


def body(text):
    return re.sub(r"^---\s*\n.*?\n---\s*\n?", "", text, count=1, flags=re.S).strip()


def repeated_body(content, articles):
    def tokens(text):
        words = identity(body(text)).split()
        return {" ".join(words[i:i + 5]) for i in range(max(0, len(words) - 4))}
    candidate = tokens(content)
    if len(candidate) < 100:
        return None
    for slug, text in articles:
        prior = tokens(text)
        common = len(candidate & prior)
        if common / max(1, len(candidate) + len(prior) - common) >= .5:
            return slug
    return None


def plan(rows):
    groups = {}
    for row in rows:
        groups.setdefault(identity(row["title"]), []).append(row)
    redirects, survivors = {}, []
    for group in groups.values():
        group.sort(key=lambda row: (row["date"], row["slug"]))
        keep = next((row for row in group if len(body(row["text"]).split()) >= 400), group[0])
        survivors.append(keep)
        redirects.update({row["slug"]: keep["slug"] for row in group if row is not keep})
    seen = {}
    for row in sorted(survivors, key=lambda row: row["date"]):
        fingerprint = hashlib.sha256(identity(body(row["text"])).encode()).hexdigest()
        if fingerprint in seen:
            redirects[row["slug"]] = seen[fingerprint]
        else:
            seen[fingerprint] = row["slug"]
    for slug in redirects:
        while redirects[slug] in redirects:
            redirects[slug] = redirects[redirects[slug]]
    return redirects


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    rows = []
    for file in (ROOT / "content/posts").glob("*.md"):
        if file.name in {"_index.md", "tow-content-log.md"}:
            continue
        text = file.read_text()
        title = field(text, "title")
        if title:
            rows.append({"file": file, "title": title, "slug": field(text, "slug", file.stem), "date": field(text, "date"), "text": text})
    redirects = plan(rows)
    print(json.dumps({"execute": args.execute, "original": len(rows), "retained": len(rows) - len(redirects), "redirects": redirects}, indent=2))
    if not args.execute:
        return
    archive = ROOT / ".cache/article-consolidation" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive.mkdir(parents=True, exist_ok=True)
    for row in rows:
        if row["slug"] in redirects:
            shutil.move(str(row["file"]), archive / row["file"].name)
    metadata = ROOT / "scripts/article-redirects.json"
    mapping = json.loads(metadata.read_text()) if metadata.exists() else {}
    mapping.update(redirects)
    metadata.write_text(json.dumps(mapping, indent=2) + "\n")
    config_file = ROOT / "vercel.json"
    config = json.loads(config_file.read_text())
    rules = [{"source": "/" + slug + suffix, "destination": "/" + target + "/", "permanent": True} for slug, target in mapping.items() for suffix in ("", "/", ".html")]
    sources = {rule["source"] for rule in rules}
    config["redirects"] = rules + [rule for rule in config.get("redirects", []) if rule["source"] not in sources]
    config_file.write_text(json.dumps(config, indent=2) + "\n")
    pattern = re.compile(r"(https://towwiththeflow\.com)?/([a-z0-9-]+)/(?=[\s)\"'#?]|$)")
    for file in (ROOT / "content").rglob("*.md"):
        text = file.read_text()
        updated = pattern.sub(lambda match: (match.group(1) or "") + "/" + mapping[match.group(2)] + "/" if match.group(2) in mapping else match.group(0), text)
        if updated != text:
            file.write_text(updated)


if __name__ == "__main__":
    main()
