#!/usr/bin/env node
/**
 * select-image.js — Image selector for blog posts
 *
 * Primary:  NASA APOD API (NASA_API_KEY in .env, falls back to DEMO_KEY)
 *           Fetches random images, filters to media_type === "image",
 *           picks one at random. Returns hdurl or url.
 * Fallback: Randomly picks from static/personal-photos/ folder
 *
 * Exports: selectImage(query)   — picks one NASA image
 *          fetchNasaImages(n)   — returns array of n NASA image objects
 *
 * CLI: node scripts/select-image.js
 */

import dotenv from "dotenv";
import { fileURLToPath } from "url";
import path from "path";
import fs from "fs";

dotenv.config({ override: true });

const __filename = fileURLToPath(import.meta.url);
const __dirname  = path.dirname(__filename);
const ROOT       = path.resolve(__dirname, "..");
const PHOTOS_DIR = path.join(ROOT, "static", "personal-photos");
const IMAGE_EXTS = new Set([".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"]);
const APOD_BASE  = "https://api.nasa.gov/planetary/apod";

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
    url:          `https://vibrationofawesome.com/personal-photos/${file}`,
    thumbUrl:     `https://vibrationofawesome.com/personal-photos/${file}`,
    localPath:    path.join(PHOTOS_DIR, file),
    source:       "personal",
    attribution:  null,
    photographer: null,
  };
}

// ── NASA APOD API ─────────────────────────────────────────────────────────────

/**
 * Fetch `count` random APOD images from NASA.
 * Filters to media_type === "image" only (skips video APODs).
 * Returns array of { url, thumbUrl, source, title, date } objects.
 * Uses NASA_API_KEY from env; falls back to DEMO_KEY (30 req/hr, 50/day).
 */
export async function fetchNasaImages(count) {
  count = count || 1;
  const key = process.env.NASA_API_KEY || "DEMO_KEY";
  // Request more than needed to have buffer after filtering out video entries
  const fetchCount = Math.min(count * 4, 100);

  try {
    const resp = await fetch(APOD_BASE + "?api_key=" + key + "&count=" + fetchCount);
    if (!resp.ok) {
      const body = await resp.text().catch(function(){ return ""; });
      console.warn("[select-image] NASA APOD " + resp.status + ": " + body.slice(0, 120));
      return [];
    }
    const items = await resp.json();
    const all = Array.isArray(items) ? items : [items];
    const images = all.filter(function(item) {
      return item.media_type === "image" && (item.hdurl || item.url);
    });

    if (images.length === 0) {
      console.warn("[select-image] NASA APOD returned no image-type results");
      return [];
    }

    // Fisher-Yates shuffle
    for (let i = images.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
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
 * Select one image. query parameter accepted for API compatibility but unused
 * (NASA APOD is randomly selected, not keyword-searched).
 */
export async function selectImage(_query) {
  // 1. Try NASA APOD
  const results = await fetchNasaImages(1);
  if (results.length > 0) {
    const img = results[0];
    console.log("[select-image] NASA APOD: \"" + img.title + "\" (" + img.date + ")");
    return img;
  }

  // 2. Fall back to personal photos
  const personal = pickPersonalPhoto();
  if (personal) {
    console.log("[select-image] Personal photo: " + path.basename(personal.localPath));
    return personal;
  }

  console.warn("[select-image] No image available from NASA APOD or personal-photos/.");
  return null;
}

// ── CLI entry point ───────────────────────────────────────────────────────────

const isCli = process.argv[1] && path.resolve(process.argv[1]) === path.resolve(__filename);
if (isCli) {
  console.log("Fetching NASA APOD image...\n");
  const image = await selectImage("");
  console.log(image ? JSON.stringify(image, null, 2) : "No image found.");
}
