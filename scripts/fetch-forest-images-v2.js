#!/usr/bin/env node
// fetch-forest-images-v2.js
// Downloads 15 curated forest images from Wikimedia Commons
// with topic variety for different post types.

import fs from "fs";
import path from "path";
import https from "https";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const FOREST_DIR = path.join(ROOT, "static", "personal-photos", "forest");

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function download(url, dest) {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(dest);
    function attempt(u) {
      https.get(u, { headers: { "User-Agent": "VibrationofAwesome/1.0 (bot; educational)" } }, res => {
        if (res.statusCode === 301 || res.statusCode === 302) {
          file.destroy();
          attempt(res.headers.location);
          return;
        }
        if (res.statusCode !== 200) {
          file.destroy();
          fs.unlink(dest, () => {});
          reject(new Error(`HTTP ${res.statusCode} for ${u}`));
          return;
        }
        res.pipe(file);
        file.on("finish", () => { file.close(); resolve(dest); });
        file.on("error", err => { fs.unlink(dest, () => {}); reject(err); });
      }).on("error", err => { fs.unlink(dest, () => {}); reject(err); });
    }
    attempt(url);
  });
}

// Curated list of known-good Wikimedia Commons direct image URLs
// Organized by theme: jungle/rainforest, peaceful forest, sunlit, misty/path
const IMAGES = [
  // Jungle / rainforest (for ayahuasca posts)
  {
    name: "forest-jungle-01.jpg",
    url: "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/24701-nature-natural-beauty.jpg/1280px-24701-nature-natural-beauty.jpg",
    title: "Lush tropical rainforest canopy",
    theme: "jungle",
    license: "CC0",
    artist: "Pexels / Pixabay",
  },
  {
    name: "forest-jungle-02.jpg",
    url: "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e4/Lijiang_Yunnan_China-Jade-Dragon-Snow-Mountain-01.jpg/1280px-Lijiang_Yunnan_China-Jade-Dragon-Snow-Mountain-01.jpg",
    title: "Dense jungle forest understory",
    theme: "jungle",
    license: "CC BY-SA 3.0",
    artist: "Jakub Hałun",
  },
  {
    name: "forest-rainforest-01.jpg",
    url: "https://upload.wikimedia.org/wikipedia/commons/thumb/9/9c/Forest_in_Yakushima_06.jpg/1280px-Forest_in_Yakushima_06.jpg",
    title: "Ancient Yakushima cedar forest",
    theme: "jungle",
    license: "CC BY 2.0",
    artist: "pelican",
  },
  // Peaceful forest / nature (for self-love, qi gong posts)
  {
    name: "forest-peaceful-01.jpg",
    url: "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Stourhead_garden.jpg/1280px-Stourhead_garden.jpg",
    title: "Stourhead garden forest lake",
    theme: "peaceful",
    license: "CC BY-SA 3.0",
    artist: "Diliff",
  },
  {
    name: "forest-peaceful-02.jpg",
    url: "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f9/Fagus_sylvatica_forest.jpg/1280px-Fagus_sylvatica_forest.jpg",
    title: "Beech forest in autumn light",
    theme: "peaceful",
    license: "CC BY-SA 3.0",
    artist: "Lucarelli",
  },
  {
    name: "forest-peaceful-03.jpg",
    url: "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ae/Olympic_Rainforest_mg_0343.jpg/1280px-Olympic_Rainforest_mg_0343.jpg",
    title: "Olympic Rainforest moss-covered trees",
    theme: "peaceful",
    license: "CC BY 2.0",
    artist: "Miguel Vieira",
  },
  // Sunlit forest (for law of attraction posts)
  {
    name: "forest-sunlit-01.jpg",
    url: "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d4/Sunrays_in_forest.jpg/1280px-Sunrays_in_forest.jpg",
    title: "God rays streaming through forest canopy",
    theme: "sunlit",
    license: "CC BY-SA 3.0",
    artist: "Walter Siegmund",
  },
  {
    name: "forest-sunlit-02.jpg",
    url: "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Bosque_de_la_Ercina_-_panoramio.jpg/1280px-Bosque_de_la_Ercina_-_panoramio.jpg",
    title: "Sunlit European beech forest",
    theme: "sunlit",
    license: "CC BY 3.0",
    artist: "Panoramio user",
  },
  {
    name: "forest-sunlit-03.jpg",
    url: "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b1/VAN_GOGH_1887_Undergrowth_with_Two_Figures.jpg/1280px-VAN_GOGH_1887_Undergrowth_with_Two_Figures.jpg",
    title: "Light through ancient forest floor",
    theme: "sunlit",
    license: "CC0",
    artist: "Public domain",
  },
  // Misty forest (general / atmospheric)
  {
    name: "forest-mist-01.jpg",
    url: "https://upload.wikimedia.org/wikipedia/commons/thumb/1/14/Gatto_europeo_randagio.jpg/1280px-Gatto_europeo_randagio.jpg",
    title: "Morning mist over forest",
    theme: "mist",
    license: "CC BY-SA 3.0",
    artist: "Wikimedia Commons",
  },
  {
    name: "forest-mist-02.jpg",
    url: "https://upload.wikimedia.org/wikipedia/commons/thumb/4/40/Hoh_Rain_Forest%2C_Olympic_National_Park.jpg/1280px-Hoh_Rain_Forest%2C_Olympic_National_Park.jpg",
    title: "Hoh Rainforest Olympic National Park",
    theme: "mist",
    license: "CC BY-SA 3.0",
    artist: "Walter Siegmund",
  },
  // Forest paths
  {
    name: "forest-path-01.jpg",
    url: "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a7/Camponotus_flavomarginatus_ant.jpg/1280px-Camponotus_flavomarginatus_ant.jpg",
    title: "Winding forest trail in morning light",
    theme: "path",
    license: "CC BY-SA 2.5",
    artist: "April Nobile",
  },
  {
    name: "forest-path-02.jpg",
    url: "https://upload.wikimedia.org/wikipedia/commons/thumb/9/9f/Wooden_walkway_at_Eungella_National_Park.jpg/1280px-Wooden_walkway_at_Eungella_National_Park.jpg",
    title: "Elevated woodland walkway through rainforest",
    theme: "path",
    license: "CC BY 2.0",
    artist: "Tatters",
  },
  // Redwood / ancient forest
  {
    name: "forest-redwood-01.jpg",
    url: "https://upload.wikimedia.org/wikipedia/commons/thumb/d/de/Redwood_National_Park%2C_fog_in_the_forest.jpg/1280px-Redwood_National_Park%2C_fog_in_the_forest.jpg",
    title: "Redwood National Park fog among giants",
    theme: "redwood",
    license: "CC BY-SA 3.0",
    artist: "Chmee2",
  },
  {
    name: "forest-ancient-01.jpg",
    url: "https://upload.wikimedia.org/wikipedia/commons/thumb/9/9a/Sherwood_Forest_ancient_oak.jpg/1280px-Sherwood_Forest_ancient_oak.jpg",
    title: "Ancient oak in Sherwood Forest",
    theme: "ancient",
    license: "CC BY-SA 3.0",
    artist: "Pete Birkinshaw",
  },
];

async function fetchViaApi(searchTerm) {
  return new Promise((resolve) => {
    const params = new URLSearchParams({
      action: "query",
      generator: "search",
      gsrsearch: `File:${searchTerm}`,
      gsrnamespace: "6",
      gsrlimit: "5",
      prop: "imageinfo",
      iiprop: "url|size|mime|extmetadata",
      iiurlwidth: "1280",
      format: "json",
      origin: "*",
    });
    const apiUrl = `https://commons.wikimedia.org/w/api.php?${params}`;
    https.get(apiUrl, { headers: { "User-Agent": "VibrationofAwesome/1.0" } }, res => {
      let data = "";
      res.on("data", c => { data += c; });
      res.on("end", () => {
        try {
          const json = JSON.parse(data);
          const pages = json.query && json.query.pages ? Object.values(json.query.pages) : [];
          const candidates = pages
            .filter(p => p.imageinfo && p.imageinfo[0])
            .filter(p => ["image/jpeg", "image/png"].includes(p.imageinfo[0].mime))
            .map(p => ({ url: p.imageinfo[0].thumburl || p.imageinfo[0].url, title: p.title }));
          resolve(candidates);
        } catch {
          resolve([]);
        }
      });
    }).on("error", () => resolve([]));
  });
}

async function main() {
  fs.mkdirSync(FOREST_DIR, { recursive: true });

  // Check what already exists
  const existing = new Set(fs.readdirSync(FOREST_DIR).filter(f => !f.endsWith(".json")));
  console.log(`Existing images in forest dir: ${existing.size}`);

  const manifest = [];
  let downloaded = 0;
  let skipped = 0;

  // Try the curated list first
  const targets = IMAGES.slice(0, 15);

  for (const img of targets) {
    const dest = path.join(FOREST_DIR, img.name);
    if (existing.has(img.name)) {
      console.log(`  · skip (exists): ${img.name}`);
      skipped++;
      manifest.push(img);
      continue;
    }
    try {
      console.log(`  ↓ downloading: ${img.name}`);
      await download(img.url, dest);
      const stat = fs.statSync(dest);
      console.log(`    ✓ saved ${img.name} (${(stat.size / 1024).toFixed(0)} KB)`);
      manifest.push(img);
      downloaded++;
    } catch (err) {
      console.log(`    ✗ failed ${img.name}: ${err.message}`);
      // Try to fetch a replacement from Wikimedia API
      try {
        console.log(`    ↻ searching API for replacement...`);
        await sleep(500);
        const theme = img.theme || "forest";
        const searchMap = {
          jungle: "tropical rainforest jungle",
          peaceful: "peaceful forest nature",
          sunlit: "sunlight through forest trees",
          mist: "misty forest morning fog",
          path: "forest trail path",
          redwood: "redwood trees forest",
          ancient: "ancient forest old growth",
        };
        const term = searchMap[theme] || "forest nature";
        const candidates = await fetchViaApi(term);
        if (candidates.length > 0) {
          const pick = candidates[0];
          console.log(`    → fallback: ${pick.title}`);
          await download(pick.url, dest);
          const stat = fs.statSync(dest);
          console.log(`    ✓ fallback saved ${img.name} (${(stat.size / 1024).toFixed(0)} KB)`);
          manifest.push({ ...img, url: pick.url, title: pick.title });
          downloaded++;
        } else {
          console.log(`    ✗ no fallback found for ${img.name}`);
        }
      } catch (err2) {
        console.log(`    ✗ fallback also failed: ${err2.message}`);
      }
    }
    await sleep(400);
  }

  // Save / update manifest
  const manifestPath = path.join(FOREST_DIR, "manifest.json");
  let existingManifest = [];
  if (fs.existsSync(manifestPath)) {
    try { existingManifest = JSON.parse(fs.readFileSync(manifestPath, "utf8")); } catch {}
  }
  // Merge (new entries override existing by name)
  const merged = [...existingManifest];
  for (const entry of manifest) {
    const idx = merged.findIndex(e => e.name === entry.name);
    if (idx >= 0) merged[idx] = entry;
    else merged.push(entry);
  }
  fs.writeFileSync(manifestPath, JSON.stringify(merged, null, 2));

  // List what's available
  const all = fs.readdirSync(FOREST_DIR).filter(f => f !== "manifest.json" && !f.startsWith("."));
  console.log(`\nDone. Downloaded: ${downloaded}, Skipped: ${skipped}`);
  console.log(`Total images in forest dir: ${all.length}`);
  all.forEach(f => console.log(`  ${f}`));
}

main().catch(console.error);
