#!/usr/bin/env node
/**
 * build-archive.js
 * Fetches archived posts from the Wayback Machine, generates HTML files
 * in the Forest Temple style, fetches Pexels images, and updates matt-posts.json.
 *
 * Run: node scripts/build-archive.js
 */

import dotenv from "dotenv";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

dotenv.config({ override: true });

const __filename = fileURLToPath(import.meta.url);
const __dirname  = path.dirname(__filename);
const ROOT       = path.resolve(__dirname, "..");
const POSTS_DIR  = path.join(ROOT, "static", "blog", "matt", "posts");
const DATA_FILE  = path.join(ROOT, "static", "_data", "matt-posts.json");

// ── Archive post definitions ──────────────────────────────────────────────────

const ARCHIVE_POSTS = [
  {
    waybackUrl: "https://web.archive.org/web/20160619044056/http://vibrationofawesome.com/self-love-acceptance/",
    slug:        "self-love-acceptance",
    canonicalUrl:"http://vibrationofawesome.com/self-love-acceptance/",
    approxDate:  "2016-06-19",
    displayDate: "June 2016",
    imageQuery:  "self love acceptance peace",
  },
  {
    waybackUrl: "https://web.archive.org/web/20150719083611/http://vibrationofawesome.com/the-most-awesome-thing-ever/",
    slug:        "the-most-awesome-thing-ever",
    canonicalUrl:"http://vibrationofawesome.com/the-most-awesome-thing-ever/",
    approxDate:  "2015-07-19",
    displayDate: "July 2015",
    imageQuery:  "joy celebration life energy",
  },
  {
    waybackUrl: "https://web.archive.org/web/20160117054636/http://vibrationofawesome.com/synonyms-for-awesome/",
    slug:        "synonyms-for-awesome",
    canonicalUrl:"http://vibrationofawesome.com/synonyms-for-awesome/",
    approxDate:  "2016-01-17",
    displayDate: "January 2016",
    imageQuery:  "words language inspiration letters",
  },
  {
    waybackUrl: "https://web.archive.org/web/20151208105422/http://vibrationofawesome.com/is-the-law-of-attraction-real-3-key-elements-to-manifesting-abundance/",
    slug:        "law-of-attraction-manifesting-abundance",
    canonicalUrl:"http://vibrationofawesome.com/is-the-law-of-attraction-real-3-key-elements-to-manifesting-abundance/",
    approxDate:  "2015-12-08",
    displayDate: "December 2015",
    imageQuery:  "abundance manifestation cosmos energy",
  },
  {
    waybackUrl: "https://web.archive.org/web/20160619044428/http://vibrationofawesome.com/qi-gong-understanding-chi-energy/",
    slug:        "qi-gong-understanding-chi-energy",
    canonicalUrl:"http://vibrationofawesome.com/qi-gong-understanding-chi-energy/",
    approxDate:  "2016-06-19",
    displayDate: "June 2016",
    imageQuery:  "qi gong tai chi meditation energy",
  },
  {
    waybackUrl: "https://web.archive.org/web/20160620165943/http://vibrationofawesome.com/ayahuasca-experience/",
    slug:        "ayahuasca-experience",
    canonicalUrl:"http://vibrationofawesome.com/ayahuasca-experience/",
    approxDate:  "2016-06-20",
    displayDate: "June 2016",
    imageQuery:  "jungle ceremony night stars plant medicine",
  },
  {
    waybackUrl: "https://web.archive.org/web/20160620165943/http://vibrationofawesome.com/the-ayahuasca-experience-is-it-your-time/",
    slug:        "the-ayahuasca-experience-is-it-your-time",
    canonicalUrl:"http://vibrationofawesome.com/the-ayahuasca-experience-is-it-your-time/",
    approxDate:  "2016-06-20",
    displayDate: "June 2016",
    imageQuery:  "spiritual awakening forest night mystical",
  },
  {
    waybackUrl: "https://web.archive.org/web/20160620165943/http://vibrationofawesome.com/how-to-find-happiness-in-yourself-without-a-partner/",
    slug:        "how-to-find-happiness-without-a-partner",
    canonicalUrl:"http://vibrationofawesome.com/how-to-find-happiness-in-yourself-without-a-partner/",
    approxDate:  "2016-06-20",
    displayDate: "June 2016",
    imageQuery:  "solitude happiness inner peace person nature",
  },
  {
    waybackUrl: "https://web.archive.org/web/20160620165943/http://vibrationofawesome.com/light-workers-a-lesson-in-communication-for-impacting-the-masses/",
    slug:        "light-workers-communication-impacting-the-masses",
    canonicalUrl:"http://vibrationofawesome.com/light-workers-a-lesson-in-communication-for-impacting-the-masses/",
    approxDate:  "2016-06-20",
    displayDate: "June 2016",
    imageQuery:  "light communication connection people inspire",
  },
  {
    waybackUrl: "https://web.archive.org/web/20160520190559/http://vibrationofawesome.com/vibration-of-awesome/",
    slug:        "vibration-of-awesome",
    canonicalUrl:"http://vibrationofawesome.com/vibration-of-awesome/",
    approxDate:  "2016-05-20",
    displayDate: "May 2016",
    imageQuery:  "vibration frequency music wave energy",
  },
  {
    waybackUrl: "https://web.archive.org/web/20160520190743/http://vibrationofawesome.com/paradigm-of-abundance/",
    slug:        "paradigm-of-abundance",
    canonicalUrl:"http://vibrationofawesome.com/paradigm-of-abundance/",
    approxDate:  "2016-05-20",
    displayDate: "May 2016",
    imageQuery:  "abundance prosperity nature growth",
  },
  {
    waybackUrl: "https://web.archive.org/web/20160520185541/http://vibrationofawesome.com/empower-your-life/",
    slug:        "empower-your-life",
    canonicalUrl:"http://vibrationofawesome.com/empower-your-life/",
    approxDate:  "2016-05-20",
    displayDate: "May 2016",
    imageQuery:  "empowerment strength person standing sunrise",
  },
];

// ── Disclaimer HTML ───────────────────────────────────────────────────────────

const DISCLAIMER_HTML = `<div class="archive-disclaimer">
  <div class="disclaimer-inner">
    <p>These words were written by a younger, more idealistic version of me ~ wide-eyed, searching, and certain of things I am still learning. Life has humbled me in ways I could not have predicted. My spirit has nonetheless persevered. I continue to embrace the unknown with an open heart, trusting that all is unfolding as it should.</p>
    <p>The journey continues.</p>
    <p class="disclaimer-sig">~ Matt</p>
  </div>
</div>`;

// ── Pexels fetch ─────────────────────────────────────────────────────────────

async function fetchPexelsImage(query) {
  const key = process.env.PEXELS_API_KEY;
  if (!key) return null;
  try {
    const qs   = new URLSearchParams({ query, per_page: "12", orientation: "landscape" });
    const resp = await fetch(`https://api.pexels.com/v1/search?${qs}`, {
      headers: { Authorization: key },
    });
    if (!resp.ok) return null;
    const data = await resp.json();
    if (!data.photos || data.photos.length === 0) return null;
    const pool  = data.photos.slice(0, Math.min(data.photos.length, 8));
    const photo = pool[Math.floor(Math.random() * pool.length)];
    return {
      url:          photo.src.large2x || photo.src.large,
      thumbUrl:     photo.src.medium,
      attribution:  `Photo by ${photo.photographer} on Pexels`,
      photographer: photo.photographer,
    };
  } catch { return null; }
}

// ── Wayback Machine fetch + parse ─────────────────────────────────────────────

function stripWaybackToolbar(html) {
  // Remove Wayback Machine toolbar/scripts up to the first real HTML
  return html
    .replace(/<!--[\s\S]*?-->/g, "")         // html comments
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/<style[\s\S]*?<\/style>/gi, "")
    .replace(/&nbsp;/g, " ")
    .replace(/\r\n/g, "\n");
}

function extractText(html) {
  // Remove remaining HTML tags
  return html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}

function extractArticleContent(html) {
  // Try multiple WordPress content container patterns
  const patterns = [
    /<div[^>]+class="[^"]*entry-content[^"]*"[^>]*>([\s\S]*?)<\/div>\s*(?=<div[^>]+class="[^"]*(?:entry-footer|post-footer|comments|navigation)[^"]*")/i,
    /<div[^>]+class="[^"]*entry-content[^"]*"[^>]*>([\s\S]*?)<\/div>\s*<\/(?:article|div)>/i,
    /<div[^>]+class="[^"]*post-content[^"]*"[^>]*>([\s\S]*?)<\/div>\s*<(?:div|footer)/i,
    /<article[^>]*>([\s\S]*?)<\/article>/i,
    /<div[^>]+id="post-\d+"[^>]*>([\s\S]*?)<\/div>\s*<div/i,
  ];

  for (const pat of patterns) {
    const m = html.match(pat);
    if (m && m[1] && m[1].length > 200) {
      return cleanContent(m[1]);
    }
  }

  // Broad fallback: everything between <body> tags minus header/footer
  const bodyMatch = html.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
  if (bodyMatch) {
    let body = bodyMatch[1];
    // Strip obvious non-content zones
    body = body
      .replace(/<header[\s\S]*?<\/header>/gi, "")
      .replace(/<nav[\s\S]*?<\/nav>/gi, "")
      .replace(/<footer[\s\S]*?<\/footer>/gi, "")
      .replace(/<aside[\s\S]*?<\/aside>/gi, "")
      .replace(/<div[^>]+(?:sidebar|widget|comment|share|related|social)[^>]*>[\s\S]*?<\/div>/gi, "");
    return cleanContent(body);
  }

  return null;
}

function extractTitle(html) {
  const patterns = [
    /<h1[^>]+class="[^"]*entry-title[^"]*"[^>]*>([\s\S]*?)<\/h1>/i,
    /<h2[^>]+class="[^"]*entry-title[^"]*"[^>]*>([\s\S]*?)<\/h2>/i,
    /<h1[^>]*>([\s\S]*?)<\/h1>/i,
    /<title>([\s\S]*?)<\/title>/i,
  ];
  for (const p of patterns) {
    const m = html.match(p);
    if (m) {
      const t = extractText(m[1]).trim();
      // Clean "| VibrationofAwesome" suffixes
      return t.replace(/\s*[\|–-]\s*vibration.*$/i, "").trim();
    }
  }
  return null;
}

function cleanContent(raw) {
  // Remove scripts, style blocks, forms, ads, WordPress shortcodes, share buttons
  let c = raw
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/<style[\s\S]*?<\/style>/gi, "")
    .replace(/<form[\s\S]*?<\/form>/gi, "")
    .replace(/\[[\w_-]+[\s\S]*?\]/g, "")          // WP shortcodes
    .replace(/<div[^>]+(?:share|social|related|sidebar|widget|ad-|comment)[^>]*>[\s\S]{0,2000}?<\/div>/gi, "")
    .replace(/<img[^>]+>/gi, "")                   // strip images (we'll use our own)
    .replace(/<a\s+[^>]*href="[^"]*(?:facebook|twitter|pinterest|instagram|youtube|google\.com\/ads)[^"]*"[^>]*>[\s\S]*?<\/a>/gi, "")
    .replace(/<[^>]+(onclick|onload|data-share)[^>]*>[\s\S]*?<\/[a-z]+>/gi, "");

  // Convert headings and paragraphs to clean HTML
  c = c
    .replace(/<h1[^>]*>([\s\S]*?)<\/h1>/gi, (_,t) => `<h2>${extractText(t)}</h2>`)
    .replace(/<h2[^>]*>([\s\S]*?)<\/h2>/gi, (_,t) => `<h2>${extractText(t)}</h2>`)
    .replace(/<h3[^>]*>([\s\S]*?)<\/h3>/gi, (_,t) => `<h3>${extractText(t)}</h3>`)
    .replace(/<h4[^>]*>([\s\S]*?)<\/h4>/gi, (_,t) => `<h3>${extractText(t)}</h3>`)
    .replace(/<p[^>]*>([\s\S]*?)<\/p>/gi,   (_,t) => {
      const text = t.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      return text ? `<p>${text}</p>` : "";
    })
    .replace(/<li[^>]*>([\s\S]*?)<\/li>/gi, (_,t) => {
      const text = t.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      return text ? `<li>${text}</li>` : "";
    })
    .replace(/<ul[^>]*>/gi, "<ul>")
    .replace(/<ol[^>]*>/gi, "<ol>")
    .replace(/<blockquote[^>]*>([\s\S]*?)<\/blockquote>/gi, (_,t) => {
      const text = t.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      return text ? `<blockquote>${text}</blockquote>` : "";
    });

  // Replace em dashes with hyphens
  c = c
    .replace(/\u2014/g, " - ")
    .replace(/&mdash;/g, " - ")
    .replace(/&#8212;/g, " - ");

  // Clean up empty tags and excessive whitespace
  c = c
    .replace(/<p>\s*<\/p>/g, "")
    .replace(/<li>\s*<\/li>/g, "")
    .replace(/<h[23]>\s*<\/h[23]>/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();

  return c;
}

function estimateReadTime(text) {
  const words = text.replace(/<[^>]+>/g, " ").split(/\s+/).filter(Boolean).length;
  return Math.max(1, Math.round(words / 200));
}

// ── HTML template ─────────────────────────────────────────────────────────────

function buildPostHTML({ post, title, content, imageUrl, imageAttribution, readMins }) {
  const pageTitle = `${title} | From the Forest Temple`;
  const description = content
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 155);

  const heroStyle = imageUrl
    ? `background:linear-gradient(to bottom, rgba(2,10,8,0.55) 0%, rgba(2,10,8,0.85) 60%, #020a0a 100%), url('${imageUrl}') center/cover no-repeat;`
    : `background:linear-gradient(135deg, #020a0a 0%, #0a1a0a 30%, #050f05 60%, #020a0a 100%);`;

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${pageTitle}</title>
<meta name="description" content="${description.replace(/"/g, "&quot;")}">
<link rel="canonical" href="${post.canonicalUrl}">
<meta name="robots" content="noindex, follow">
<meta name="theme-color" content="#ffb300">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Vibration of Awesome">
<meta property="og:title" content="${title.replace(/"/g, "&quot;")} ~ From the Forest Temple">
<meta property="og:description" content="${description.replace(/"/g, "&quot;")}">
<meta property="og:url" content="${post.canonicalUrl}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="${title.replace(/"/g, "&quot;")} ~ From the Forest Temple">
<meta name="twitter:description" content="${description.replace(/"/g, "&quot;")}">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"BlogPosting","headline":${JSON.stringify(title)},"description":${JSON.stringify(description)},"url":"${post.canonicalUrl}","datePublished":"${post.approxDate}T00:00:00.000Z","author":{"@type":"Person","name":"Matt Dunn","url":"https://vibrationofawesome.com"},"publisher":{"@type":"Organization","name":"Vibration of Awesome","url":"https://vibrationofawesome.com"}}</script>
<script async src="https://www.googletagmanager.com/gtag/js?id=G-G5HF0WKZT9"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','G-G5HF0WKZT9');</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cinzel+Decorative:wght@400;700&family=Lora:ital,wght@0,400;0,600;1,400&family=Rajdhani:wght@400;500;700&display=swap" rel="stylesheet">
<style>
  :root { --amber:#ffb300; --deep:#020a0a; --cream:#f5ead8; --muted:#7a8c6e; --body-text:rgba(245,234,216,0.85); }
  * { margin:0; padding:0; box-sizing:border-box; }
  html { scroll-behavior:smooth; }
  body { background:var(--deep); color:var(--cream); font-family:'Lora',serif; overflow-x:hidden; }
  .stars { position:fixed; top:0; left:0; width:100%; height:100%; pointer-events:none; z-index:0; overflow:hidden; }
  .star { position:absolute; background:white; border-radius:50%; animation:twinkle var(--dur,3s) ease-in-out infinite; animation-delay:var(--delay,0s); opacity:0; }
  @keyframes twinkle { 0%,100%{opacity:0;transform:scale(0.5)} 50%{opacity:var(--brightness,0.6);transform:scale(1)} }
  nav { position:fixed; top:0; left:0; right:0; z-index:100; padding:1.2rem 3rem; display:flex; align-items:center; justify-content:space-between; background:linear-gradient(to bottom, rgba(2,10,8,0.97), transparent); border-bottom:1px solid rgba(255,179,0,0.08); }
  .nav-logo { font-family:'Cinzel Decorative',serif; font-size:1rem; color:var(--amber); text-decoration:none; letter-spacing:0.15em; }
  .nav-breadcrumb { display:flex; align-items:center; gap:0.75rem; }
  .nav-breadcrumb a { font-family:'Rajdhani',sans-serif; font-size:0.72rem; letter-spacing:0.2em; text-transform:uppercase; color:var(--muted); text-decoration:none; transition:color 0.2s; }
  .nav-breadcrumb a:hover { color:var(--amber); }
  .nav-sep { color:var(--muted); opacity:0.4; font-size:0.7rem; }
  .post-hero { position:relative; z-index:1; padding:9rem 4rem 4rem; border-bottom:1px solid rgba(255,179,0,0.08); ${heroStyle} }
  .post-hero-inner { max-width:720px; margin:0 auto; }
  .lane-badge { display:inline-block; margin-bottom:1rem; font-family:'Rajdhani',sans-serif; font-size:0.68rem; letter-spacing:0.3em; text-transform:uppercase; color:var(--amber); border:1px solid rgba(255,179,0,0.3); background:rgba(255,179,0,0.05); padding:0.3rem 0.8rem; }
  .archive-badge { display:inline-block; margin-bottom:1.5rem; margin-left:0.75rem; font-family:'Rajdhani',sans-serif; font-size:0.62rem; letter-spacing:0.25em; text-transform:uppercase; color:rgba(245,234,216,0.45); border:1px solid rgba(245,234,216,0.15); padding:0.3rem 0.7rem; }
  .post-title { font-family:'Cinzel Decorative',serif; font-size:clamp(1.6rem,3.5vw,2.8rem); color:var(--cream); line-height:1.2; margin-bottom:1.5rem; letter-spacing:0.02em; }
  .post-meta { display:flex; align-items:center; gap:1.5rem; flex-wrap:wrap; font-family:'Rajdhani',sans-serif; font-size:0.72rem; letter-spacing:0.2em; text-transform:uppercase; color:var(--muted); }
  .meta-dot { width:3px; height:3px; background:var(--amber); border-radius:50%; opacity:0.4; }
  /* Disclaimer pull-quote box */
  .archive-disclaimer { max-width:720px; margin:0 auto 0; padding:3rem 4rem 0; position:relative; z-index:1; }
  .disclaimer-inner { background:rgba(30,20,5,0.6); border:1px solid rgba(255,179,0,0.18); border-left:3px solid rgba(255,179,0,0.45); padding:1.8rem 2.2rem; position:relative; }
  .disclaimer-inner::before { content:'Archive Note'; position:absolute; top:-0.65rem; left:1.5rem; background:var(--deep); padding:0 0.5rem; font-family:'Rajdhani',sans-serif; font-size:0.6rem; letter-spacing:0.3em; text-transform:uppercase; color:rgba(255,179,0,0.5); }
  .disclaimer-inner p { font-family:'Lora',serif; font-size:0.97rem; line-height:1.85; color:rgba(245,234,216,0.62); font-style:italic; margin-bottom:0.75rem; }
  .disclaimer-inner p:last-child { margin-bottom:0; }
  .disclaimer-sig { color:rgba(255,179,0,0.55) !important; font-style:italic !important; }
  /* Post body */
  .post-body { max-width:720px; margin:0 auto; padding:3.5rem 4rem 6rem; position:relative; z-index:1; }
  .post-divider { width:50px; height:1px; background:linear-gradient(to right, var(--amber), transparent); margin:0 0 2.5rem; }
  .post-body p { font-size:1.15rem; line-height:2; color:var(--body-text); margin-bottom:1.65rem; }
  .post-body h2 { font-family:'Cinzel Decorative',serif; font-size:clamp(1.2rem,2.5vw,1.8rem); color:var(--cream); margin:3rem 0 1.5rem; line-height:1.3; letter-spacing:0.02em; }
  .post-body h3 { font-family:'Rajdhani',sans-serif; font-size:1.1rem; font-weight:700; letter-spacing:0.15em; text-transform:uppercase; color:var(--amber); margin:2.5rem 0 1rem; }
  .post-body strong { color:var(--cream); font-weight:600; }
  .post-body em { color:#c8e6c9; font-style:italic; }
  .post-body blockquote { border-left:2px solid var(--amber); padding:1rem 2rem; margin:2.5rem 0; background:rgba(255,179,0,0.03); font-size:1.1rem; line-height:1.8; color:rgba(245,234,216,0.75); font-style:italic; }
  .post-body ul, .post-body ol { margin:0 0 1.65rem 1.5rem; }
  .post-body li { font-size:1.1rem; line-height:1.9; color:var(--body-text); margin-bottom:0.4rem; }
  .post-body hr { border:none; border-top:1px solid rgba(255,179,0,0.1); margin:3rem 0; }
  .post-body a { color:var(--amber); text-decoration:none; border-bottom:1px solid rgba(255,179,0,0.3); transition:border-color 0.2s; }
  .post-body a:hover { border-bottom-color:var(--amber); }
  .image-credit { font-family:'Rajdhani',sans-serif; font-size:0.65rem; letter-spacing:0.15em; color:rgba(245,234,216,0.3); margin-top:-1.2rem; margin-bottom:1.5rem; }
  .post-footer { max-width:720px; margin:0 auto; padding:2.5rem 4rem 5rem; position:relative; z-index:1; border-top:1px solid rgba(255,179,0,0.08); display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:1.5rem; }
  .post-footer a { font-family:'Rajdhani',sans-serif; font-size:0.72rem; letter-spacing:0.2em; text-transform:uppercase; color:var(--muted); text-decoration:none; transition:color 0.2s; }
  .post-footer a:hover { color:var(--amber); }
  footer { padding:3rem 4rem; border-top:1px solid rgba(255,179,0,0.08); text-align:center; position:relative; z-index:1; }
  footer p { font-family:'Rajdhani',sans-serif; font-size:0.68rem; letter-spacing:0.2em; text-transform:uppercase; color:var(--muted); opacity:0.6; }
  footer a { color:var(--amber); text-decoration:none; }
  @media(max-width:768px) { nav{padding:1rem 1.5rem;} .post-hero{padding:7rem 1.5rem 3rem;} .archive-disclaimer{padding:2rem 1.5rem 0;} .post-body{padding:2.5rem 1.5rem 4rem;} .post-footer{padding:2rem 1.5rem 3.5rem;} footer{padding:2rem 1.5rem;} .disclaimer-inner{padding:1.4rem 1.5rem;} }
</style>
</head>
<body>
<div class="stars" id="stars"></div>
<nav>
  <a href="/" class="nav-logo">VOA</a>
  <div class="nav-breadcrumb">
    <a href="/blog/">Blog</a>
    <span class="nav-sep">/</span>
    <a href="/blog/matt/">From the Forest Temple</a>
  </div>
</nav>

<div class="post-hero">
  <div class="post-hero-inner">
    <span class="lane-badge">Archive ~ From the Forest Temple</span>
    <span class="archive-badge">Originally published ${post.displayDate}</span>
    <h1 class="post-title">${title}</h1>
    <div class="post-meta">
      <span>${post.displayDate}</span>
      <div class="meta-dot"></div>
      <span>by Matt Dunn</span>
      <div class="meta-dot"></div>
      <span>${readMins} min read</span>
    </div>
  </div>
</div>

${DISCLAIMER_HTML}

<div class="post-body">
  <div class="post-divider"></div>
${imageAttribution ? `  <p class="image-credit">${imageAttribution}</p>\n` : ""}
${content}

  <hr>
  <p><em>Originally published on vibrationofawesome.com circa ${post.displayDate}. Archived here as part of the Vibration of Awesome legacy collection.</em></p>
  <p><em>Matt Dunn ~ musician, digital creator, explorer. Based at <a href="/">vibrationofawesome.com</a>.</em></p>
</div>

<div class="post-footer">
  <a href="/blog/matt/">← All Forest Temple Posts</a>
  <a href="/">vibrationofawesome.com</a>
</div>

<footer>
  <p>&copy; 2026 <a href="/">Vibration of Awesome</a></p>
</footer>

<script>
  const s = document.getElementById('stars');
  for (let i = 0; i < 100; i++) {
    const el = document.createElement('div'); el.className = 'star';
    const sz = Math.random() * 2 + 0.5;
    el.style.cssText = 'width:'+sz+'px;height:'+sz+'px;left:'+Math.random()*100+'%;top:'+Math.random()*100+'%;--dur:'+(Math.random()*4+2)+'s;--delay:'+(Math.random()*5)+'s;--brightness:'+(Math.random()*0.5+0.2)+';';
    s.appendChild(el);
  }
</script>
</body>
</html>`;
}

// ── Fallback content ──────────────────────────────────────────────────────────

function buildFallbackContent(post) {
  return `<p>This post was originally published on vibrationofawesome.com at <a href="${post.canonicalUrl}">${post.canonicalUrl}</a>.</p>
<p>The archived content could not be retrieved at this time. Please visit the original URL or check <a href="${post.waybackUrl}">the Wayback Machine archive</a> to read this post.</p>`;
}

// ── Main ──────────────────────────────────────────────────────────────────────

const results = [];

async function processPost(post) {
  console.log(`\nProcessing: ${post.slug}`);
  console.log(`  Fetching: ${post.waybackUrl}`);

  let title = null;
  let content = null;
  let fetchStatus = "ok";

  try {
    const resp = await fetch(post.waybackUrl, {
      headers: {
        "User-Agent": "Mozilla/5.0 (compatible; VibrationOfAwesome-Archiver/1.0)",
        "Accept": "text/html,application/xhtml+xml",
      },
      signal: AbortSignal.timeout(20000),
    });

    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`);
    }

    const html = await resp.text();
    title   = extractTitle(html)   || null;
    content = extractArticleContent(stripWaybackToolbar(html)) || null;

    if (!content || content.length < 100) {
      console.log(`  Warning: content extraction weak (${content?.length ?? 0} chars), using fallback`);
      content = buildFallbackContent(post);
      fetchStatus = "partial";
    } else {
      console.log(`  Extracted: title="${title}" content=${content.length} chars`);
    }
  } catch (err) {
    console.log(`  Fetch failed: ${err.message}`);
    title       = post.slug.replace(/-/g, " ").replace(/\b\w/g, c => c.toUpperCase());
    content     = buildFallbackContent(post);
    fetchStatus = "failed";
  }

  // Use slug-derived title if extraction failed
  if (!title) {
    title = post.slug.replace(/-/g, " ").replace(/\b\w/g, c => c.toUpperCase());
  }

  // Fetch Pexels image
  console.log(`  Fetching Pexels image: "${post.imageQuery}"`);
  const img = await fetchPexelsImage(post.imageQuery);
  if (img) {
    console.log(`  Image: ${img.attribution}`);
  } else {
    console.log(`  No Pexels image found, using gradient`);
  }

  const readMins = estimateReadTime(content);
  const html = buildPostHTML({
    post,
    title,
    content,
    imageUrl:          img?.url ?? null,
    imageAttribution:  img?.attribution ?? null,
    readMins,
  });

  // Write file
  const outDir  = path.join(POSTS_DIR, post.slug);
  const outFile = path.join(outDir, "index.html");
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(outFile, html, "utf8");
  console.log(`  Written: ${outFile.replace(ROOT, "")}`);

  // Build excerpt from content
  const plainText = content.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
  const excerpt   = plainText.slice(0, 180).trim() + (plainText.length > 180 ? "..." : "");

  return {
    title,
    slug:   post.slug,
    date:   post.approxDate,
    excerpt,
    url:    `/blog/matt/posts/${post.slug}/`,
    tags:   ["archive", "legacy"],
    fetchStatus,
    isArchive: true,
  };
}

async function main() {
  console.log("=== VibrationofAwesome Archive Builder ===\n");
  fs.mkdirSync(POSTS_DIR, { recursive: true });

  // Process all posts (with small delay between requests to be polite)
  const archiveEntries = [];
  for (const post of ARCHIVE_POSTS) {
    const result = await processPost(post);
    archiveEntries.push(result);
    await new Promise(r => setTimeout(r, 500)); // 500ms between requests
  }

  // Update matt-posts.json: add archive entries at the end (oldest dates)
  const existing = JSON.parse(fs.readFileSync(DATA_FILE, "utf8"));

  // Remove any existing archive entries (re-run safe)
  const current = existing.filter(p => !p.isArchive);

  // Merge and sort: current posts (newest first), then archives (oldest first)
  const archives = archiveEntries
    .filter(e => e.fetchStatus !== "failed" || true) // include all even if fetch failed
    .map(({ fetchStatus: _f, ...rest }) => rest)      // remove fetchStatus from output
    .sort((a, b) => new Date(b.date) - new Date(a.date));

  const merged = [...current, ...archives];
  fs.writeFileSync(DATA_FILE, JSON.stringify(merged, null, 2), "utf8");
  console.log(`\nUpdated: ${DATA_FILE.replace(ROOT, "")}`);

  // Summary
  console.log("\n=== SUMMARY ===");
  for (const r of archiveEntries) {
    const icon = r.fetchStatus === "ok" ? "✓" : r.fetchStatus === "partial" ? "~" : "✗";
    console.log(`${icon} ${r.slug} (${r.fetchStatus})`);
  }

  const ok      = archiveEntries.filter(r => r.fetchStatus === "ok").length;
  const partial = archiveEntries.filter(r => r.fetchStatus === "partial").length;
  const failed  = archiveEntries.filter(r => r.fetchStatus === "failed").length;
  console.log(`\nTotal: ${archiveEntries.length} | OK: ${ok} | Partial: ${partial} | Failed: ${failed}`);
}

main().catch(err => { console.error(err); process.exit(1); });
