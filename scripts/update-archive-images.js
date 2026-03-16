#!/usr/bin/env node
/**
 * update-archive-images.js
 * Replaces Pexels hero images with NASA APOD images in all archive posts.
 * Removes all <p class="image-credit"> attribution lines.
 * Run from project root: node scripts/update-archive-images.js
 */

import dotenv from "dotenv";
import { fileURLToPath } from "url";
import path from "path";
import fs from "fs";
import { fetchNasaImages } from "./select-image.js";

dotenv.config({ override: true });

const __filename = fileURLToPath(import.meta.url);
const __dirname  = path.dirname(__filename);
const ROOT       = path.resolve(__dirname, "..");
const POSTS_DIR  = path.join(ROOT, "static", "blog", "matt", "posts");

// Find all archive post index.html files (directory-style posts only)
const archiveDirs = fs.readdirSync(POSTS_DIR).filter(name => {
  const full = path.join(POSTS_DIR, name);
  return fs.statSync(full).isDirectory();
});

console.log("Archive posts found: " + archiveDirs.length);
console.log(archiveDirs.map(d => "  " + d).join("\n") + "\n");

// Fetch enough NASA images for all posts in one API call
console.log("Fetching " + archiveDirs.length + " NASA APOD images...");
const nasaImages = await fetchNasaImages(archiveDirs.length + 5);

if (nasaImages.length < archiveDirs.length) {
  console.warn("Warning: only got " + nasaImages.length + " images for " + archiveDirs.length + " posts.");
  if (nasaImages.length === 0) {
    console.error("No NASA images returned. Check API key / network.");
    process.exit(1);
  }
}

let updated = 0;
let failed  = 0;

for (let i = 0; i < archiveDirs.length; i++) {
  const dir  = archiveDirs[i];
  const file = path.join(POSTS_DIR, dir, "index.html");

  if (!fs.existsSync(file)) {
    console.warn("  [skip] No index.html in " + dir);
    continue;
  }

  // Pick image (cycle if we ran short)
  const img = nasaImages[i % nasaImages.length];
  let html  = fs.readFileSync(file, "utf8");

  // 1. Replace the Pexels background URL in .post-hero CSS
  //    Pattern: url('https://images.pexels.com/...') inside the .post-hero rule
  const heroBefore = html;
  html = html.replace(
    /url\('https:\/\/images\.pexels\.com\/[^']+'\)/g,
    "url('" + img.url + "')"
  );

  // Also catch unquoted or double-quoted variants just in case
  html = html.replace(
    /url\("https:\/\/images\.pexels\.com\/[^"]+"\)/g,
    "url('" + img.url + "')"
  );
  html = html.replace(
    /url\(https:\/\/images\.pexels\.com\/[^)]+\)/g,
    "url('" + img.url + "')"
  );

  // 2. Remove <p class="image-credit">...</p> (any content, single line)
  html = html.replace(/<p class="image-credit">[^<]*<\/p>\s*/g, "");

  // 3. Remove .image-credit CSS rule (single-line rule in a <style> block)
  html = html.replace(/\s*\.image-credit\s*\{[^}]*\}\s*/g, "\n");

  if (html === heroBefore) {
    console.warn("  [warn] No Pexels URL found in " + dir + " - may already be updated");
    updated++;
  } else {
    fs.writeFileSync(file, html, "utf8");
    console.log("  [ok]   " + dir + " -> " + img.title + " (" + img.date + ")");
    updated++;
  }
}

console.log("\nDone. " + updated + " posts updated, " + failed + " failed.");
