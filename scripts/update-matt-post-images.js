#!/usr/bin/env node
// update-matt-post-images.js
// Replaces Pexels/external hero background URLs in Matt lane posts
// with local forest images from static/personal-photos/forest/

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const POSTS_DIR = path.join(ROOT, "static", "blog", "matt", "posts");
const BASE_URL = "/personal-photos/forest/";

// Topic → forest image mapping
// Post slug → image filename
const POST_IMAGE_MAP = {
  // Ayahuasca posts: jungle / rainforest
  "ayahuasca-experience":                       "forest-15-sinharaja-jungle.jpg",
  "the-ayahuasca-experience-is-it-your-time":   "forest-16-jungle-lake-palawan.jpg",

  // Self love / qi gong: peaceful ancient forest
  "self-love-acceptance":                        "forest-05-ancient-oak-trees-in-sherwood-forest---geograph.org.uk---6356602.jpg",
  "qi-gong-understanding-chi-energy":            "forest-09-ancient-tree-ingleby-forest---geograph.org.uk---1196216.jpg",

  // Law of attraction: sunlit forest
  "law-of-attraction-manifesting-abundance":     "forest-08-rays-of-sunlight-bless-the-soul---panoramio.jpg",

  // Happiness without a partner: misty, peaceful
  "how-to-find-happiness-without-a-partner":     "forest-12-stourhead-misty-lake.jpg",

  // Light workers / communication: morning mist
  "light-workers-communication-impacting-the-masses": "forest-03-duke-forest-misty-morning-h.jpg",

  // Paradigm of abundance: sunlit path
  "paradigm-of-abundance":                       "forest-11-sunlit-forest-path.jpg",

  // Synonyms for awesome / most awesome: forest trail / path
  "synonyms-for-awesome":                        "forest-10-sandstone-trail-in-delamere-forest---geograph.org.uk---5241156.jpg",
  "the-most-awesome-thing-ever":                 "forest-04-elevated-wooden-woodland-path-in-hatfield-forest-essex-england.jpg",

  // Empower your life: rays of light
  "empower-your-life":                           "forest-02-on-shutlingsloe---first-rays-of-sunlight-on-trig-point---geograph.org.uk---76797.jpg",

  // Vibration of awesome: misty meadow
  "vibration-of-awesome":                        "forest-07-mist-covering-a-meadow-under-forest-encroachment.jpg",

  // Twenty years internet marketing: redwood fog
  "twenty-years-internet-marketing":             "forest-13-redwood-fog.jpg",

  // Why I built forest temple: sequoia (rooted, elemental)
  "why-i-built-forest-temple":                   "forest-01-sequoia-sempervirens-mhnt.bot.2007.52.2.jpg",
};

// Regex to match .post-hero background url(...)
const HERO_BG_RE = /(\.post-hero\s*\{[^}]*background:[^;]*url\(')[^']*(')/;

function getSlug(filePath) {
  // For index.html: parent dir name is the slug
  // For flat .html files: filename without .html
  const parts = filePath.split(path.sep);
  const file = parts[parts.length - 1];
  if (file === "index.html") {
    return parts[parts.length - 2];
  }
  return file.replace(/\.html$/, "");
}

function updateFile(filePath) {
  const slug = getSlug(filePath);
  const imageName = POST_IMAGE_MAP[slug];
  if (!imageName) {
    console.log(`  · no mapping: ${slug}`);
    return false;
  }

  // Verify image exists
  const imgPath = path.join(ROOT, "static", "personal-photos", "forest", imageName);
  if (!fs.existsSync(imgPath)) {
    console.log(`  ✗ image not found: ${imageName}`);
    return false;
  }

  const original = fs.readFileSync(filePath, "utf8");
  const newUrl = BASE_URL + imageName;

  // Replace in .post-hero background url('...')
  // Pattern: url('https://...') or url("https://...")
  let updated = original.replace(
    /(\.post-hero\s*\{[^}]*background:[^;]*url\()(['"])[^'"]*(['"])/,
    (match, prefix, q1, q2) => `${prefix}${q1}${newUrl}${q2}`
  );

  // Also handle url without quotes if present
  if (updated === original) {
    updated = original.replace(
      /(\.post-hero\s*\{[^}]*background:[^;]*url\()\s*([^\)]*)\s*(\))/,
      (match, prefix, urlVal, suffix) => {
        const cleaned = urlVal.replace(/['"]/g, "");
        if (cleaned.startsWith("http") || cleaned.startsWith("/")) {
          const q = urlVal.includes('"') ? '"' : "'";
          return `${prefix}${q}${newUrl}${q}`;
        }
        return match;
      }
    );
  }

  if (updated === original) {
    console.log(`  · no URL pattern found: ${slug}`);
    return false;
  }

  fs.writeFileSync(filePath, updated, "utf8");
  console.log(`  ✓ ${slug} → ${imageName}`);
  return true;
}

// Gather all Matt post HTML files
function gatherFiles(dir) {
  const results = [];
  function walk(d) {
    for (const entry of fs.readdirSync(d, { withFileTypes: true })) {
      const full = path.join(d, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (entry.isFile() && entry.name.endsWith(".html")) results.push(full);
    }
  }
  walk(dir);
  return results;
}

const files = gatherFiles(POSTS_DIR);
console.log(`Processing ${files.length} Matt post files...\n`);

let updated = 0;
for (const f of files) {
  if (updateFile(f)) updated++;
}

console.log(`\nDone. Updated ${updated}/${files.length} files.`);
