#!/usr/bin/env node
/**
 * fetch-forest-images.js
 *
 * Downloads 15-20 high-quality public domain / CC forest images
 * from Wikimedia Commons and saves them to:
 *   static/personal-photos/forest/
 *
 * Uses the Wikimedia Commons API to search for images and
 * retrieves direct image URLs via imageinfo.
 *
 * Run: node scripts/fetch-forest-images.js
 */

import fs   from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname  = path.dirname(fileURLToPath(import.meta.url));
const ROOT       = path.resolve(__dirname, "..");
const FOREST_DIR = path.join(ROOT, "static", "personal-photos", "forest");
const API_BASE   = "https://commons.wikimedia.org/w/api.php";
const UA         = "VibrationofAwesome/1.0 (https://vibrationofawesome.com; personal-use)";

const SEARCHES = [
  "forest sunlight rays",
  "misty forest morning",
  "ancient forest trees",
  "forest path trail",
  "redwood forest",
  "forest fog mist",
];

const MAX_PER_SEARCH = 5;
const IMAGE_EXTS     = new Set([".jpg", ".jpeg", ".png"]);
const MAX_BYTES      = 8 * 1024 * 1024; // 8 MB ceiling
const MIN_BYTES      = 50 * 1024;        // 50 KB floor (skip tiny thumbnails)
const TARGET_COUNT   = 18;

fs.mkdirSync(FOREST_DIR, { recursive: true });

// ── Wikimedia API helpers ─────────────────────────────────────────────────────

async function searchImages(query) {
  const params = new URLSearchParams({
    action:      "query",
    generator:   "search",
    gsrsearch:   query,
    gsrnamespace:"6",       // File namespace
    gsrlimit:    String(MAX_PER_SEARCH),
    prop:        "imageinfo",
    iiprop:      "url|size|mime|extmetadata",
    iiextmetadatafilter: "LicenseShortName|Artist",
    format:      "json",
    formatversion: "2",
  });

  const url  = API_BASE + "?" + params.toString();
  const resp = await fetch(url, { headers: { "User-Agent": UA } });
  if (!resp.ok) {
    console.warn("  Wikimedia API error", resp.status, "for query:", query);
    return [];
  }

  const data  = await resp.json();
  const pages = data?.query?.pages;
  if (!pages) return [];

  const results = [];
  for (const page of pages) {
    const info = page?.imageinfo?.[0];
    if (!info) continue;

    const mime = info.mime || "";
    if (!mime.startsWith("image/jpeg") && !mime.startsWith("image/png")) continue;

    const fileSize = info.size || 0;
    if (fileSize > MAX_BYTES || fileSize < MIN_BYTES) continue;

    const directUrl = info.url;
    if (!directUrl) continue;

    const ext = path.extname(new URL(directUrl).pathname).toLowerCase();
    if (!IMAGE_EXTS.has(ext)) continue;

    const license = info?.extmetadata?.LicenseShortName?.value || "Unknown";
    const artist  = info?.extmetadata?.Artist?.value || "";

    results.push({
      title:    page.title.replace("File:", ""),
      url:      directUrl,
      license,
      artist,
      fileSize,
    });
  }
  return results;
}

async function downloadImage(url, destPath) {
  const resp = await fetch(url, { headers: { "User-Agent": UA } });
  if (!resp.ok) throw new Error("HTTP " + resp.status);
  const buf = Buffer.from(await resp.arrayBuffer());
  fs.writeFileSync(destPath, buf);
  return buf.length;
}

// ── Main ──────────────────────────────────────────────────────────────────────

console.log("Searching Wikimedia Commons for forest images...\n");

const allCandidates = [];
const seen = new Set();

for (const query of SEARCHES) {
  console.log("  Searching:", query);
  try {
    const results = await searchImages(query);
    for (const r of results) {
      if (!seen.has(r.url)) {
        seen.add(r.url);
        allCandidates.push(r);
      }
    }
    console.log("    Found", results.length, "candidates");
  } catch (err) {
    console.warn("    Error:", err.message);
  }
  // Polite delay between API calls
  await new Promise(r => setTimeout(r, 300));
}

console.log("\nTotal unique candidates:", allCandidates.length);

// Shuffle candidates for variety
for (let i = allCandidates.length - 1; i > 0; i--) {
  const j = Math.floor(Math.random() * (i + 1));
  [allCandidates[i], allCandidates[j]] = [allCandidates[j], allCandidates[i]];
}

// Attempt to download up to TARGET_COUNT images
let downloaded = 0;
const manifest = [];

console.log("\nDownloading up to", TARGET_COUNT, "images...\n");

for (const candidate of allCandidates) {
  if (downloaded >= TARGET_COUNT) break;

  // Sanitize filename
  const safeName = candidate.title
    .replace(/[^a-zA-Z0-9._\- ]/g, "")
    .replace(/\s+/g, "-")
    .toLowerCase()
    .slice(0, 80);
  const ext      = path.extname(new URL(candidate.url).pathname).toLowerCase();
  const filename = "forest-" + String(downloaded + 1).padStart(2, "0") + "-" + safeName;
  const destPath = path.join(FOREST_DIR, filename + ext);

  if (fs.existsSync(destPath)) {
    console.log("  Skip (exists):", filename + ext);
    manifest.push({ file: filename + ext, ...candidate });
    downloaded++;
    continue;
  }

  try {
    process.stdout.write("  Downloading: " + candidate.title.slice(0, 55) + "... ");
    const bytes = await downloadImage(candidate.url, destPath);
    console.log("OK (" + Math.round(bytes / 1024) + " KB) [" + candidate.license + "]");
    manifest.push({ file: filename + ext, ...candidate });
    downloaded++;
    // Polite delay between downloads
    await new Promise(r => setTimeout(r, 400));
  } catch (err) {
    console.log("FAILED:", err.message);
  }
}

// Save manifest with attribution info
const manifestPath = path.join(FOREST_DIR, "manifest.json");
fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2), "utf8");

console.log("\nDownloaded:", downloaded, "images");
console.log("Saved to:  static/personal-photos/forest/");
console.log("Manifest:  static/personal-photos/forest/manifest.json");
