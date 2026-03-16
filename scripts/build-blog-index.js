/**
 * build-blog-index.js
 * Reads static/_data/matt-posts.json and bakes the posts list directly
 * into static/blog/matt/index.html — no runtime fetch needed.
 * Run this whenever matt-posts.json changes.
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

const MONTHS = ['January','February','March','April','May','June',
                'July','August','September','October','November','December'];

function fmtDate(d) {
  const [y, m, day] = d.split('-');
  return `${MONTHS[parseInt(m, 10) - 1]} ${parseInt(day, 10)}, ${y}`;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function postUrl(p) {
  // Current posts use .html paths; archives use directory paths
  if (p.isArchive) return `/blog/matt/posts/${p.slug}/`;
  // Use explicit url if it ends in .html, else construct
  if (p.url && p.url.endsWith('.html')) return p.url;
  return `/blog/matt/posts/${p.slug}/`;
}

const postsPath = path.join(ROOT, 'static', '_data', 'matt-posts.json');
const indexPath = path.join(ROOT, 'static', 'blog', 'matt', 'index.html');

const posts = JSON.parse(fs.readFileSync(postsPath, 'utf8'));

// Build static HTML for all posts
const postsHtml = posts.map(p => {
  const url = postUrl(p);
  const archiveBadge = p.isArchive
    ? `<span class="post-tag" style="opacity:0.55;font-size:0.65rem">Archive</span>`
    : '';
  return `<div class="post-item">
  <div class="post-meta">
    <span class="post-date">${fmtDate(p.date)}</span>
    ${archiveBadge}
  </div>
  <h2 class="post-title"><a href="${url}">${escapeHtml(p.title)}</a></h2>
  <p class="post-excerpt">${escapeHtml(p.excerpt)}</p>
  <a href="${url}" class="post-read-more">Read more &rarr;</a>
</div>`;
}).join('\n');

// Read current index HTML
let html = fs.readFileSync(indexPath, 'utf8');

// Replace the post-list div content AND remove the fetch script
// Replace: <div class="post-list" id="post-list">...</div>
html = html.replace(
  /<div class="post-list" id="post-list">[\s\S]*?<\/div>/,
  `<div class="post-list" id="post-list">\n${postsHtml}\n</div>`
);

// Remove the loadMattPosts fetch function and call (no longer needed)
// Keep only the stars animation script
html = html.replace(
  /\s*function fmtDate[\s\S]*?loadMattPosts\(\);/,
  ''
);

fs.writeFileSync(indexPath, html, 'utf8');
console.log(`Built blog index with ${posts.length} posts`);
posts.forEach(p => console.log(`  ${p.isArchive ? '[archive]' : '[current]'} ${p.date} ${p.slug}`));
