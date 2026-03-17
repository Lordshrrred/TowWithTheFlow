#!/usr/bin/env node
/**
 * select-image.js — Image selector for blog posts
 *
 * Lane routing:
 *   lane "matt"    → random image from static/personal-photos/forest/
 *                    fallback: static/personal-photos/
 *   lane "boombot" → NASA APOD API
 *                    fallback: static/personal-photos/
 *   (default)      → NASA APOD API
 *
 * Exports:
 *   selectImage(query, lane)  — picks one image for a post's hero
 *   fetchNasaImages(count)    — returns array of NASA APOD image objects
 *   fetchForestImages(count)  — returns array of forest image objects
 */

import dotenv from "dotenv";
import { fileURLToPath } from "url";
import path from "path";
import fs from "fs";

dotenv.config({ override: true });

const __filename  = fileURLToPath(import.meta.url);
const __dirname   = path.dirname(__filename);
const ROOT        = path.resolve(__dirname, "..");
const PHOTOS_DIR  = path.join(ROOT, "static", "personal-photos");
const FOREST_DIR  = path.join(ROOT, "static", "personal-photos", "forest");
const IMAGE_EXTS  = new Set([".jpg", ".jpeg", ".png", ".webp", ".avif"]);
const APOD_BASE   = "https://api.nasa.gov/planetary/apod";

// ── Personal photos fallback ──────────────────────────────────────────────────

function pickPersonalPhoto() {
  if (!fs.existsSync(PHOTOS_DIR)) return null;
  const files = fs.readdirSync(PHOTOS_DIR).filter(f => {
    const ext = path.extname(f).toLowerCase();
    return IMAGE_EXTS.has(ext) && !f.startsWith(".");
  });
  if (files.length === 0) return null;
  const file = files[Math.floor(Math.random() * files.length)];
  return {
    url:          "https://vibrationofawesome.com/personal-photos/" + file,
    thumbUrl:     "https://vibrationofawesome.com/personal-photos/" + file,
    localPath:    path.join(PHOTOS_DIR, file),
    source:       "personal",
    attribution:  null,
    photographer: null,
  };
}

// ── Forest photos (Matt / Forest Temple lane) ─────────────────────────────────

/**
 * Pick one random forest image from static/personal-photos/forest/.
 */
function pickForestPhoto() {
  const dir = fs.existsSync(FOREST_DIR) ? FOREST_DIR : PHOTOS_DIR;
  if (!fs.existsSync(dir)) return null;
  const files = fs.readdirSync(dir).filter(f => {
    const ext = path.extname(f).toLowerCase();
    return IMAGE_EXTS.has(ext) && !f.startsWith(".") && f !== "manifest.json";
  });
  if (files.length === 0) return pickPersonalPhoto();
  const file = files[Math.floor(Math.random() * files.length)];
  const subpath = dir === FOREST_DIR ? "personal-photos/forest/" : "personal-photos/";
  return {
    url:          "https://vibrationofawesome.com/" + subpath + file,
    thumbUrl:     "https://vibrationofawesome.com/" + subpath + file,
    localPath:    path.join(dir, file),
    source:       "forest",
    attribution:  null,
    photographer: null,
  };
}

/**
 * Return an array of `count` randomly chosen forest images.
 * Used for injecting inline images into Forest Temple posts.
 */
export function fetchForestImages(count) {
  count = count || 1;
  const dir = fs.existsSync(FOREST_DIR) ? FOREST_DIR : PHOTOS_DIR;
  if (!fs.existsSync(dir)) return [];

  const files = fs.readdirSync(dir).filter(f => {
    const ext = path.extname(f).toLowerCase();
    return IMAGE_EXTS.has(ext) && !f.startsWith(".") && f !== "manifest.json";
  });
  if (files.length === 0) return [];

  // Fisher-Yates shuffle, then take first `count`
  const shuffled = [...files];
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }

  const subpath = dir === FOREST_DIR ? "personal-photos/forest/" : "personal-photos/";
  return shuffled.slice(0, count).map(file => ({
    url:          "https://vibrationofawesome.com/" + subpath + file,
    thumbUrl:     "https://vibrationofawesome.com/" + subpath + file,
    localPath:    path.join(dir, file),
    source:       "forest",
    title:        path.basename(file, path.extname(file)).replace(/[-_]/g, " "),
    attribution:  null,
    photographer: null,
  }));
}

// ── NASA APOD API ─────────────────────────────────────────────────────────────

/**
 * Fetch `count` random APOD images from NASA.
 * Filters to media_type === "image" only (skips video APODs).
 * Uses NASA_API_KEY from env; falls back to DEMO_KEY (30 req/hr, 50/day).
 */
export async function fetchNasaImages(count) {
  count = count || 1;
  const key        = process.env.NASA_API_KEY || "DEMO_KEY";
  const fetchCount = Math.min(count * 4, 100);

  try {
    const resp = await fetch(APOD_BASE + "?api_key=" + key + "&count=" + fetchCount);
    if (!resp.ok) {
      const body = await resp.text().catch(function(){ return ""; });
      console.warn("[select-image] NASA APOD " + resp.status + ": " + body.slice(0, 120));
      return [];
    }
    const items = await resp.json();
    const all   = Array.isArray(items) ? items : [items];
    const images = all.filter(function(item) {
      return item.media_type === "image" && (item.hdurl || item.url);
    });

    if (images.length === 0) {
      console.warn("[select-image] NASA APOD returned no image-type results");
      return [];
    }

    // Fisher-Yates shuffle
    for (let i = images.length - 1; i > 0; i--) {
      const j   = Math.floor(Math.random() * (i + 1));
      const tmp = images[i]; images[i] = images[j]; images[j] = tmp;
    }

    return images.slice(0, count).map(function(item) {
      return {
        url:          item.hdurl || item.url,
        thumbUrl:     item.url,
        source:       "nasa",
        title:        item.title  || "",
        date:         item.date   || "",
        attribution:  null,
        photographer: null,
      };
    });
  } catch (err) {
    console.warn("[select-image] NASA APOD fetch error: " + err.message);
    return [];
  }
}

// ── Main export ───────────────────────────────────────────────────────────────

/**
 * Select one image for a post's hero.
 *
 * @param {string} _query  - search hint (unused for both sources)
 * @param {string} lane    - "matt" | "boombot" | undefined
 *
 * lane "matt"    → forest photo first, personal-photos fallback
 * lane "boombot" → NASA APOD first, personal-photos fallback
 * (default)      → NASA APOD first, personal-photos fallback
 */
export async function selectImage(_query, lane) {
  if (lane === "matt") {
    // Forest Temple: use local forest images
    const forest = pickForestPhoto();
    if (forest) {
      console.log("[select-image] Forest photo: " + path.basename(forest.localPath));
      return forest;
    }
    // Fallback to personal photos
    const personal = pickPersonalPhoto();
    if (personal) {
      console.log("[select-image] Personal photo fallback: " + path.basename(personal.localPath));
      return personal;
    }
  } else {
    // BoomBot / default: use NASA APOD
    const results = await fetchNasaImages(1);
    if (results.length > 0) {
      const img = results[0];
      console.log("[select-image] NASA APOD: \"" + img.title + "\" (" + img.date + ")");
      return img;
    }
    // Fallback to personal photos
    const personal = pickPersonalPhoto();
    if (personal) {
      console.log("[select-image] Personal photo fallback: " + path.basename(personal.localPath));
      return personal;
    }
  }

  console.warn("[select-image] No image available.");
  return null;
}

// ── CLI entry point ───────────────────────────────────────────────────────────

const isCli = process.argv[1] && path.resolve(process.argv[1]) === path.resolve(__filename);
if (isCli) {
  const lane = process.argv[2] || "boombot";
  console.log("Testing image selection for lane:", lane, "\n");
  const image = await selectImage("", lane);
  console.log(image ? JSON.stringify(image, null, 2) : "No image found.");

  if (lane === "matt") {
    console.log("\nForest images batch (3):");
    const batch = fetchForestImages(3);
    batch.forEach((img, i) => console.log("  " + (i + 1) + ".", img.url));
  }
}
