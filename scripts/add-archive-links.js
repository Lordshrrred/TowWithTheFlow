#!/usr/bin/env node
/**
 * add-archive-links.js — injects internal links into archive post HTML files
 * Run: node scripts/add-archive-links.js
 */
import fs   from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname  = path.dirname(__filename);
const POSTS_DIR  = path.resolve(__dirname, "..", "static", "blog", "matt", "posts");

// slug -> HTML paragraph to insert before the closing <hr>
const RELATED = {
  "vibration-of-awesome": `<p>Years later, the same questions that started here shaped how I built the <a href="/blog/matt/posts/why-i-built-forest-temple/">Forest Temple system</a> - and eventually led to the honest reckoning in <a href="/blog/matt/posts/twenty-years-internet-marketing.html">Why I Spent 20 Years Doing Internet Marketing Wrong</a>.</p>`,

  "empower-your-life": `<p>This philosophy later became the foundation for the <a href="/blog/matt/posts/why-i-built-forest-temple/">Forest Temple</a> - a personal operating system built around the same idea: structure your life around who you actually are, not who you think you should be.</p>`,

  "paradigm-of-abundance": `<p>The scarcity-vs-abundance tension I was working through here eventually shaped everything I came to understand about <a href="/blog/matt/posts/twenty-years-internet-marketing.html">twenty years of doing internet marketing wrong</a>. Worth reading side by side.</p>`,

  "law-of-attraction-manifesting-abundance": `<p>If this topic resonates, the <a href="/blog/matt/posts/paradigm-of-abundance/">Paradigm of Abundance</a> post from the same era goes deeper into the mindset shift that makes manifestation more than wishful thinking.</p>`,

  "self-love-acceptance": `<p>The inner work that starts with self-acceptance leads somewhere. The <a href="/blog/matt/posts/empower-your-life/">Empower Your Life</a> post picks up the thread.</p>`,

  "qi-gong-understanding-chi-energy": `<p>The energy work explored here connects directly to the broader framework in <a href="/blog/matt/posts/empower-your-life/">Empower Your Life</a> - and to the <a href="/blog/matt/posts/self-love-acceptance/">self-acceptance practice</a> that makes it all sustainable.</p>`,

  "the-most-awesome-thing-ever": `<p>The exploration here eventually converged into a more structured framework - see the <a href="/blog/matt/posts/vibration-of-awesome/">Vibration of Awesome</a> post from the same era for where the thinking landed.</p>`,

  "ayahuasca-experience": `<p>The dissolution and rebuilding documented here changed how I thought about almost everything - including the work in <a href="/blog/matt/posts/self-love-acceptance/">self-love and acceptance</a> and what it means to <a href="/blog/matt/posts/empower-your-life/">empower your own life</a>.</p>`,
};

let updated = 0;
for (const [slug, linkPara] of Object.entries(RELATED)) {
  const filePath = path.join(POSTS_DIR, slug, "index.html");
  if (!fs.existsSync(filePath)) {
    console.log(`SKIP (not found): ${filePath}`);
    continue;
  }
  let html = fs.readFileSync(filePath, "utf8");
  if (html.includes(linkPara.slice(0, 40))) {
    console.log(`SKIP (already done): ${slug}`);
    continue;
  }
  // Insert before the last <hr> in post-body
  const marker = "\n  <hr>";
  const idx = html.lastIndexOf(marker);
  if (idx === -1) {
    console.log(`SKIP (no <hr>): ${slug}`);
    continue;
  }
  html = html.slice(0, idx) + "\n\n  " + linkPara + marker + html.slice(idx + marker.length);
  fs.writeFileSync(filePath, html, "utf8");
  console.log(`UPDATED: ${slug}`);
  updated++;
}
console.log(`\nDone. Updated ${updated} files.`);
