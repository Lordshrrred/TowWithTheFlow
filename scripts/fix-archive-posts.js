#!/usr/bin/env node
/**
 * fix-archive-posts.js
 *
 * TASK 1: Convert <span class="lane-badge"> to a clickable <a> link
 *         pointing to /blog/matt/ in every Matt archive post.
 *
 * TASK 2: Remove legacy WordPress sharedaddy / Google+ share widget
 *         from every archive post that contains one.
 */

import fs   from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT      = path.resolve(__dirname, "..");
const POSTS_DIR = path.join(ROOT, "static", "blog", "matt", "posts");

// All archive post index.html files (subdirectory format)
const ARCHIVE_DIRS = [
  "ayahuasca-experience",
  "empower-your-life",
  "how-to-find-happiness-without-a-partner",
  "law-of-attraction-manifesting-abundance",
  "light-workers-communication-impacting-the-masses",
  "paradigm-of-abundance",
  "qi-gong-understanding-chi-energy",
  "self-love-acceptance",
  "synonyms-for-awesome",
  "the-ayahuasca-experience-is-it-your-time",
  "the-most-awesome-thing-ever",
  "vibration-of-awesome",
].map(d => path.join(POSTS_DIR, d, "index.html"));

// Current posts (.html files, not subdirs)
const CURRENT_POSTS = [
  path.join(POSTS_DIR, "twenty-years-internet-marketing.html"),
  path.join(POSTS_DIR, "why-i-built-forest-temple.html"),
];

// ── TASK 1: Convert span.lane-badge to anchor ─────────────────────────────────

function fixLaneBadge(html) {
  // Convert <span class="lane-badge">...</span> to <a href="/blog/matt/" class="lane-badge">...</a>
  html = html.replace(
    /<span class="lane-badge">([\s\S]*?)<\/span>/g,
    '<a href="/blog/matt/" class="lane-badge">$1</a>'
  );

  // Add text-decoration:none to the .lane-badge CSS so it doesn't look underlined
  // Handle both inline and multiline CSS definitions
  html = html.replace(
    /(\.lane-badge\s*\{[^}]*)(padding:[^;]+;)(\s*\})/,
    '$1$2 text-decoration: none;$3'
  );

  return html;
}

// ── TASK 2: Remove sharedaddy / Google+ share widget ─────────────────────────

function removeShareWidget(html) {
  if (!html.includes("sharedaddy")) return html;

  // Remove everything from the opening sharedaddy div through </ul>,
  // then the <hr> separator line, keeping only the attribution <p> tags
  // and removing the orphaned closing </div> of sd-content.
  //
  // Original structure (compressed):
  //   <div class="sharedaddy sd-sharing-enabled">
  //     <div class="robots-nocontent ...">
  //       <h3>Share this:</h3>
  //       <div class="sd-content">
  //         <ul><li>Click to share on Google+...</li></ul>
  //                                              ← remove above
  //         <hr>
  //         <p><em>Originally published...</em></p>
  //         <p><em>Matt Dunn...</em></p>
  //       </div>                                ← orphaned: remove
  //     </div>                                  ← orphaned (browser-closed): remove
  //   </div>                                    ← orphaned: remove

  // Step 1: Remove from <div class="sharedaddy"> through </ul>
  html = html.replace(
    /<div class="sharedaddy sd-sharing-enabled">[\s\S]*?<\/ul>\s*\n/,
    ""
  );

  // Step 2: Remove the <hr> separator that was part of the widget
  // (the <hr> sits right after </ul> and before the attribution text)
  html = html.replace(/^\s*<hr>\s*\n/m, "");

  // Step 3: Remove the orphaned </div> that was closing sd-content,
  // which now appears right before <div class="post-footer">
  html = html.replace(/\n<\/div>\s*\n\n<div class="post-footer">/, '\n\n<div class="post-footer">');

  return html;
}

// ── Process files ─────────────────────────────────────────────────────────────

let updated = 0;
let skipped = 0;

for (const file of [...ARCHIVE_DIRS, ...CURRENT_POSTS]) {
  if (!fs.existsSync(file)) {
    console.warn("  MISSING:", path.relative(ROOT, file));
    skipped++;
    continue;
  }

  const original = fs.readFileSync(file, "utf8");
  let   html     = original;

  html = fixLaneBadge(html);
  html = removeShareWidget(html);

  if (html !== original) {
    fs.writeFileSync(file, html, "utf8");
    const hadWidget = original.includes("sharedaddy") ? " [share widget removed]" : "";
    console.log("  Updated:", path.relative(ROOT, file) + hadWidget);
    updated++;
  } else {
    console.log("  Unchanged:", path.relative(ROOT, file));
  }
}

console.log(`\nDone. ${updated} files updated, ${skipped} missing.`);
