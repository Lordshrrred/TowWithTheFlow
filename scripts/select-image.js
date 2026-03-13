#!/usr/bin/env node
/**
 * select-image.js — Image selector for syndicated posts
 *
 * Primary:  Pexels API (PEXELS_API_KEY), searches by query keyword
 * Fallback: Randomly picks from static/personal-photos/ folder
 *
 * Exports: selectImage(query)
 * Returns: { url, thumbUrl, source, attribution, photographer } or null
 *
 * CLI: node scripts/select-image.js "music technology"
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
const IMAGE_EXTS  = new Set([".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"]);
const PEXELS_BASE = "https://api.pexels.com/v1";

// ── Personal photos fallback ──────────────────────────────────────────────────

/** Pick a random image from static/personal-photos/. Returns null if folder is empty. */
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

// ── Pexels API ────────────────────────────────────────────────────────────────

/**
 * Fetch a landscape image from Pexels matching the query.
 * Returns null on any failure (missing key, API error, no results).
 */
async function fetchPexelsImage(query) {
  const key = process.env.PEXELS_API_KEY;
  if (!key) {
    console.warn("[select-image] PEXELS_API_KEY not set — skipping Pexels.");
    return null;
  }

  try {
    const qs   = new URLSearchParams({ query, per_page: "15", orientation: "landscape" });
    const resp = await fetch(`${PEXELS_BASE}/search?${qs}`, {
      headers: { Authorization: key },
    });

    if (!resp.ok) {
      console.warn(`[select-image] Pexels API returned ${resp.status}: ${await resp.text()}`);
      return null;
    }

    const data = await resp.json();
    if (!data.photos || data.photos.length === 0) {
      console.warn(`[select-image] Pexels returned 0 photos for query: "${query}"`);
      return null;
    }

    // Pick randomly from the top 8 results to add variety
    const pool  = data.photos.slice(0, Math.min(data.photos.length, 8));
    const photo = pool[Math.floor(Math.random() * pool.length)];

    return {
      url:          photo.src.large2x || photo.src.large || photo.src.original,
      thumbUrl:     photo.src.medium  || photo.src.small,
      source:       "pexels",
      attribution:  `Photo by ${photo.photographer} on Pexels`,
      photographer: photo.photographer,
      pexelsUrl:    photo.url,
      pexelsId:     photo.id,
    };
  } catch (err) {
    console.warn(`[select-image] Pexels fetch error: ${err.message}`);
    return null;
  }
}

// ── Main export ───────────────────────────────────────────────────────────────

/**
 * Select an image for a syndicated post.
 *
 * @param {string} query - Search keyword(s) sent to Pexels
 * @returns {Promise<object|null>} Image info, or null if nothing available
 */
export async function selectImage(query) {
  // 1. Try Pexels
  const pexels = await fetchPexelsImage(query);
  if (pexels) {
    console.log(`[select-image] Pexels: "${pexels.attribution}"`);
    return pexels;
  }

  // 2. Fall back to personal photos
  const personal = pickPersonalPhoto();
  if (personal) {
    console.log(`[select-image] Personal photo: ${path.basename(personal.localPath)}`);
    return personal;
  }

  console.warn("[select-image] No image available from Pexels or personal-photos/.");
  return null;
}

// ── CLI entry point ───────────────────────────────────────────────────────────

const isCli = process.argv[1] && path.resolve(process.argv[1]) === path.resolve(__filename);
if (isCli) {
  const query = process.argv.slice(2).join(" ") || "music technology creativity";
  console.log(`Searching for: "${query}"\n`);
  const image = await selectImage(query);
  console.log(image ? JSON.stringify(image, null, 2) : "No image found.");
}
