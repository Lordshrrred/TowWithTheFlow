#!/usr/bin/env node
/**
 * update-sitemap.js — Regenerates static/sitemap.xml from post JSON indexes.
 *
 * Called automatically by generate-post.js after every new post.
 * Run manually any time:  node scripts/update-sitemap.js
 */
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname  = path.dirname(__filename);
const ROOT       = path.resolve(__dirname, "..");
const BASE       = "https://vibrationofawesome.com";

// Static pages that are always included regardless of JSON indexes.
// Update lastmod here when a page design changes significantly.
const STATIC_PAGES = [
  { loc: "/",                          lastmod: "2026-03-04", changefreq: "weekly",  priority: "1.0" },
  { loc: "/blog/",                     lastmod: "2026-03-04", changefreq: "weekly",  priority: "0.9" },
  { loc: "/blog/matt/",                lastmod: "2026-03-04", changefreq: "weekly",  priority: "0.8" },
  { loc: "/blog/boombot/",             lastmod: "2026-03-04", changefreq: "weekly",  priority: "0.8" },
  { loc: "/aura/",                     lastmod: "2026-03-03", changefreq: "monthly", priority: "0.6" },
  { loc: "/art-store/",                lastmod: "2026-03-03", changefreq: "monthly", priority: "0.6" },
  { loc: "/posts/",                    lastmod: "2026-03-03", changefreq: "monthly", priority: "0.5" },
  { loc: "/posts/first-transmission/", lastmod: "2026-03-03", changefreq: "monthly", priority: "0.5" },
];

function toDateStr(val) {
  if (!val) return new Date().toISOString().slice(0, 10);
  return new Date(val).toISOString().slice(0, 10);
}

function readPosts(jsonPath) {
  try {
    const raw   = fs.readFileSync(jsonPath, "utf8");
    const posts = JSON.parse(raw);
    return Array.isArray(posts) ? posts : [];
  } catch (_) { return []; }
}

function urlBlock({ loc, lastmod, changefreq, priority }) {
  return [
    "  <url>",
    `    <loc>${BASE}${loc}</loc>`,
    `    <lastmod>${toDateStr(lastmod)}</lastmod>`,
    `    <changefreq>${changefreq}</changefreq>`,
    `    <priority>${priority}</priority>`,
    "  </url>",
  ].join("\n");
}

export function updateSitemap() {
  const mattPosts    = readPosts(path.join(ROOT, "static/_data/matt-posts.json"));
  const boombotPosts = readPosts(path.join(ROOT, "static/_data/boombot-posts.json"));

  const staticBlocks = STATIC_PAGES.map(urlBlock);
  const postBlocks   = [...mattPosts, ...boombotPosts].map((p) =>
    urlBlock({ loc: p.url, lastmod: p.date, changefreq: "monthly", priority: "0.7" })
  );

  const xml = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    "",
    "  <!-- Static Pages -->",
    staticBlocks.join("\n\n"),
    "",
    "  <!-- Blog Posts -->",
    postBlocks.join("\n\n"),
    "",
    "</urlset>",
    "",
  ].join("\n");

  const outFile = path.join(ROOT, "static/sitemap.xml");
  fs.writeFileSync(outFile, xml, "utf8");
  console.log(
    `Sitemap updated: static/sitemap.xml (${mattPosts.length + boombotPosts.length} posts indexed)`
  );
}

// Run directly: node scripts/update-sitemap.js
if (process.argv[1] === __filename) {
  updateSitemap();
}
