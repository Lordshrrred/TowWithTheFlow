#!/usr/bin/env node
// fix-share-widgets.js
// Removes ALL Google+/sharedaddy share widget remnants from every HTML file
// in static/blog/matt/posts/ and static/blog/boombot/posts/

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");

const DIRS = [
  path.join(ROOT, "static", "blog", "matt", "posts"),
  path.join(ROOT, "static", "blog", "boombot", "posts"),
];

function gatherHtmlFiles(dir) {
  const results = [];
  if (!fs.existsSync(dir)) return results;
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

function cleanShareWidgets(html) {
  let changed = false;
  let out = html;

  // ── 1. Remove full sharedaddy block: outer div through </ul> ─────────────
  // Pattern covers the full opening structure down to and including </ul>
  // and any blank lines that follow it
  const widgetRe = /\n?<div class="sharedaddy sd-sharing-enabled">[\s\S]*?<\/ul>\s*\n/g;
  if (widgetRe.test(out)) {
    out = out.replace(
      /\n?<div class="sharedaddy sd-sharing-enabled">[\s\S]*?<\/ul>\s*\n/g,
      "\n"
    );
    changed = true;
  }

  // ── 2. Remove any standalone Google+ list item (in case widget structure differs)
  if (/<li[^>]*>Click to share on Google\+[^<]*<\/li>/i.test(out)) {
    out = out.replace(/<li[^>]*>Click to share on Google\+[^<]*<\/li>\s*\n?/gi, "");
    changed = true;
  }

  // ── 3. Remove <h3>Share this:</h3> lines
  if (/<h3[^>]*>\s*Share this:\s*<\/h3>/i.test(out)) {
    out = out.replace(/<h3[^>]*>\s*Share this:\s*<\/h3>\s*\n?/gi, "");
    changed = true;
  }

  // ── 4. Remove remaining opening divs from widget if any survived
  const sdDivs = [
    /<div class="sharedaddy[^"]*">\s*\n?/g,
    /<div class="robots-nocontent[^"]*">\s*\n?/g,
    /<div class="sd-block[^"]*">\s*\n?/g,
    /<div class="sd-social[^"]*">\s*\n?/g,
    /<div class="sd-content[^"]*">\s*\n?/g,
  ];
  for (const re of sdDivs) {
    if (re.test(out)) {
      // reset lastIndex since we tested above
    }
  }
  for (const rePat of [
    /\n?<div class="sharedaddy[^"]*">\s*\n?/g,
    /\n?<div class="robots-nocontent[^"]*">\s*\n?/g,
    /\n?<div class="sd-block[^"]*">\s*\n?/g,
    /\n?<div class="sd-social[^"]*">\s*\n?/g,
    /\n?<div class="sd-content[^"]*">\s*\n?/g,
  ]) {
    if (rePat.test(out)) {
      out = out.replace(rePat, "\n");
      changed = true;
    }
  }

  // ── 5. Remove empty <ul></ul> blocks left behind
  if (/<ul>\s*<\/ul>/i.test(out)) {
    out = out.replace(/<ul>\s*<\/ul>\s*\n?/gi, "");
    changed = true;
  }

  // ── 6. Remove the orphaned </div> that was closing sd-content
  //    It sits between attribution content and <div class="post-footer">
  //    Pattern: a </div> that appears on its own line directly before post-footer
  if (/<\/div>\s*\n\s*\n?<div class="post-footer">/i.test(out)) {
    out = out.replace(/<\/div>(\s*\n\s*\n?)(<div class="post-footer">)/i, "$1$2");
    changed = true;
  }

  // ── 7. Remove addthis / sharethis blocks entirely
  if (/addthis|sharethis/i.test(out)) {
    out = out.replace(/<div[^>]*(?:addthis|sharethis)[^>]*>[\s\S]*?<\/div>/gi, "");
    changed = true;
  }

  // ── 8. Collapse triple+ blank lines down to double
  out = out.replace(/\n{3,}/g, "\n\n");

  return { html: out, changed };
}

// ── Main ─────────────────────────────────────────────────────────────────────
let totalFiles = 0;
let modifiedFiles = 0;

for (const dir of DIRS) {
  const files = gatherHtmlFiles(dir);
  for (const file of files) {
    totalFiles++;
    const original = fs.readFileSync(file, "utf8");
    const { html, changed } = cleanShareWidgets(original);
    if (changed) {
      fs.writeFileSync(file, html, "utf8");
      modifiedFiles++;
      console.log(`  ✓ cleaned: ${path.relative(ROOT, file)}`);
    } else {
      console.log(`  · no change: ${path.relative(ROOT, file)}`);
    }
  }
}

console.log(`\nDone. ${modifiedFiles}/${totalFiles} files modified.`);
