#!/usr/bin/env node
/**
 * generate-post.js — Dual-lane blog post generator for vibrationofawesome.com
 *
 * Usage:
 *   node scripts/generate-post.js --lane matt --title "My Post Title"
 *   node scripts/generate-post.js --lane boombot --keyword "ai tools for musicians" --topic "AI music creation"
 */
import Anthropic from "@anthropic-ai/sdk";
import { marked } from "marked";
import minimist from "minimist";
import dotenv from "dotenv";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { spawnSync } from "child_process";
import { updateSitemap } from "./update-sitemap.js";

dotenv.config({ override: true });
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT = path.resolve(__dirname, "..");

// ── CLI ARGS ──
const argv = minimist(process.argv.slice(2), {
  string:  ["lane", "title", "keyword", "topic"],
  boolean: ["no-syndicate"],
  alias:   { l: "lane", t: "title", k: "keyword", p: "topic" },
});
const lane = argv.lane;
if (!lane || !["matt", "boombot"].includes(lane)) {
  console.error('Error: --lane must be "matt" or "boombot"'); process.exit(1);
}
if (lane === "matt" && !argv.title) {
  console.error('Error: Matt lane requires --title "Post Title"'); process.exit(1);
}
if (lane === "boombot" && (!argv.keyword || !argv.topic)) {
  console.error('Error: BoomBot lane requires --keyword "..." and --topic "..."'); process.exit(1);
}
if (!process.env.ANTHROPIC_API_KEY) {
  console.error("Error: ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key.");
  process.exit(1);
}

// ── SYSTEM PROMPTS ──
const MATT_SYSTEM = [
  "You are Matt Dunn, writing for your personal blog \"From the Forest Temple.\"",
  "Matt is a musician (EarthStar rock/metal/electronic, Ruzindla EDM/psytrance),",
  "digital creator, Apple Tech Expert, and someone who has been grinding at internet",
  "marketing for 20 years. He organizes his life through a personal system called",
  "Forest Temple. His writing is raw, direct, and honest. No motivational fluff.",
  "No generic self-help hooks. He writes like he talks — real stories, real lessons,",
  "real frustration when warranted. His audience is spiritually awakening,",
  "purpose-driven, neurodivergent, HSP, and alternative abundance seekers.",
  "Write a full blog post based on the given title. Return raw markdown only.",
].join("\n");

const BOOMBOT_SYSTEM = [
  "You are Matty BoomBoom, an AI writer for the blog \"Boom Frequency\" at",
  "vibrationofawesome.com. You are inspired by the spirit of Matt Dunn — a musician,",
  "digital creator, and 20-year internet marketing veteran who has gone deep on AI tools.",
  "Your job is to write SEO-optimized, genuinely helpful long-form posts targeting",
  "specific long-tail keywords. Your audience: spiritually awakening creators,",
  "neurodivergent entrepreneurs, musicians learning AI, and abundance-minded outliers.",
  "Write in a voice that is helpful, slightly eccentric, and real — never corporate,",
  "never generic. Include H2 and H3 subheadings, a meta description on the first line",
  "(format: META: your description here), and a CTA at the end pointing readers to",
  "vibrationofawesome.com. Return raw markdown only.",
].join("\n");

// ── HELPERS ──

/** Convert title to URL-safe slug */
function slugify(str) {
  return str.toLowerCase().replace(/[^a-z0-9\s-]/g, "").trim().replace(/\s+/g, "-").replace(/-+/g, "-");
}

/** Extract first real paragraph (skip headings/META/rules), truncate at 150 chars */
function extractExcerpt(markdown) {
  const lines = markdown.split("\n").filter((l) => l.trim() !== "");
  for (const line of lines) {
    const t = line.trim();
    if (t.startsWith("META:") || t.startsWith("#") || t.startsWith("---") || t.startsWith("***")) continue;
    return t.slice(0, 150);
  }
  return "";
}

/** Strip META: line from BoomBot output. Returns { metaDescription, cleanMarkdown } */
function stripMeta(markdown) {
  const lines = markdown.split("\n");
  let metaDescription = "";
  const cleanLines = [];
  for (const line of lines) {
    if (line.trim().startsWith("META:")) {
      metaDescription = line.replace(/^META:\s*/i, "").trim();
    } else {
      cleanLines.push(line);
    }
  }
  return { metaDescription, cleanMarkdown: cleanLines.join("\n") };
}

/** Build complete post HTML. Uses string array join to avoid template-literal/quoting issues. */
function buildHtml(lane, title, dateStr, bodyHtml, slug, metaDescription) {
  const isMatt      = lane === "matt";
  const accent      = isMatt ? "#ffb300" : "#00e5ff";
  const accentLight = isMatt ? "#ffe082" : "#b2f5ff";
  const accentDark  = isMatt ? "#c67c00" : "#0097a7";
  const fontFamily  = isMatt ? "Lora, Georgia, serif" : "Space Grotesk, Inter, sans-serif";
  const gfBase      = "https://fonts.googleapis.com";
  const gfStatic    = "https://fonts.gstatic.com";
  const googleFont  = isMatt
    ? '<link rel="preconnect" href="' + gfBase + '">'
      + '<link rel="preconnect" href="' + gfStatic + '" crossorigin>'
      + '<link href="' + gfBase + '/css2?family=Lora:ital,wght@0,400;0,600;0,700;1,400&display=swap" rel="stylesheet">'
    : '<link rel="preconnect" href="' + gfBase + '">'
      + '<link rel="preconnect" href="' + gfStatic + '" crossorigin>'
      + '<link href="' + gfBase + '/css2?family=Space+Grotesk:wght@300;400;500;600;700&display=swap" rel="stylesheet">';

  const laneName    = isMatt ? "From the Forest Temple" : "Boom Frequency";
  const byline      = isMatt ? "by Matt Dunn" : "by Matty BoomBoom (AI)";
  const badge       = isMatt ? "FOREST TEMPLE" : "BOOM FREQUENCY";
  const displayDate = new Date(dateStr).toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });

  // Parse hex accent colour to RGB for the stars canvas
  const hexClean = accent.replace("#", "");
  const accentR  = parseInt(hexClean.slice(0, 2), 16);
  const accentG  = parseInt(hexClean.slice(2, 4), 16);
  const accentB  = parseInt(hexClean.slice(4, 6), 16);

  const metaContent = metaDescription
    ? metaDescription.replace(/"/g, "&quot;")
    : title + " — " + laneName + " at Vibration of Awesome";
  const yearNow = new Date().getFullYear();

  // Build HTML as array of strings, joined at the end
  const H = [];
  H.push("<!DOCTYPE html>");
  H.push('<html lang="en">');
  H.push("<head>");
  H.push('  <meta charset="UTF-8">');
  H.push('  <meta name="viewport" content="width=device-width, initial-scale=1.0">');
  H.push("  <title>" + title + " | " + laneName + " | Vibration of Awesome</title>");
  H.push('  <meta name="description" content="' + metaContent + '">');
  const postUrl = "https://vibrationofawesome.com/blog/" + lane + "/posts/" + slug + ".html";
  const datePublished = new Date(dateStr).toISOString();
  const authorName = isMatt ? "Matt Dunn" : "Matty BoomBoom";
  H.push('  <link rel="canonical" href="' + postUrl + '">');
  H.push('  <meta name="robots" content="index, follow">');
  H.push('  <meta name="theme-color" content="' + accent + '">');
  H.push("  <!-- Open Graph -->");
  H.push('  <meta property="og:type" content="article">');
  H.push('  <meta property="og:site_name" content="Vibration of Awesome">');
  H.push('  <meta property="og:title" content="' + title + '">');
  H.push('  <meta property="og:description" content="' + metaContent + '">');
  H.push('  <meta property="og:url" content="' + postUrl + '">');
  H.push('  <meta property="og:image" content="https://vibrationofawesome.com/images/earthstar-hero.jpg">');
  H.push('  <meta property="og:image:width" content="1200">');
  H.push('  <meta property="og:image:height" content="630">');
  H.push("  <!-- Twitter / X Cards -->");
  H.push('  <meta name="twitter:card" content="summary_large_image">');
  H.push('  <meta name="twitter:title" content="' + title + '">');
  H.push('  <meta name="twitter:description" content="' + metaContent + '">');
  H.push('  <meta name="twitter:image" content="https://vibrationofawesome.com/images/earthstar-hero.jpg">');
  H.push("  <!-- Structured Data -->");
  H.push('  <script type="application/ld+json">');
  H.push('  {"@context":"https://schema.org","@type":"BlogPosting","headline":"' + title.replace(/"/g, '\\"') + '","description":"' + metaContent.replace(/"/g, '\\"') + '","url":"' + postUrl + '","datePublished":"' + datePublished + '","author":{"@type":"Person","name":"' + authorName + '","url":"https://vibrationofawesome.com"},"publisher":{"@type":"Organization","name":"Vibration of Awesome","url":"https://vibrationofawesome.com"},"image":"https://vibrationofawesome.com/images/earthstar-hero.jpg","mainEntityOfPage":{"@type":"WebPage","@id":"' + postUrl + '"}}');
  H.push("  </script>");
  H.push("  " + googleFont);
  H.push("  <!-- Google Analytics GA4 -->");
  H.push('  <script async src="https://www.googletagmanager.com/gtag/js?id=G-G5HF0WKZT9"></script>');
  H.push("  <script>");
  H.push("    window.dataLayer = window.dataLayer || [];");
  H.push("    function gtag(){dataLayer.push(arguments);}");
  H.push('    gtag("js", new Date());');
  H.push('    gtag("config", "G-G5HF0WKZT9");');
  H.push("  </script>");
  H.push("  <style>");
  H.push("    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }");
  H.push("    :root {");
  H.push("      --bg: #020a0a; --surface: #060f10; --surface2: #0b1a1c;");
  H.push("      --accent: " + accent + "; --accent-light: " + accentLight + "; --accent-dark: " + accentDark + ";");
  H.push("      --text: #e8f4f0; --text-muted: #7a9e9a; --border: rgba(255,255,255,0.06);");
  H.push("    }");
  H.push("    html { scroll-behavior: smooth; }");
  H.push("    body { background: var(--bg); color: var(--text); font-family: " + fontFamily + "; font-size: 18px; line-height: 1.75; min-height: 100vh; overflow-x: hidden; }");
  H.push("    #stars-canvas { position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: 0; pointer-events: none; }");
  H.push("    .site-wrapper { position: relative; z-index: 1; display: flex; flex-direction: column; min-height: 100vh; }");
  H.push("    .container { max-width: 760px; margin: 0 auto; padding: 0 1.5rem; width: 100%; }");
  H.push("    .site-header { border-bottom: 1px solid var(--border); background: rgba(2,10,10,0.85); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); padding: 1rem 0; position: sticky; top: 0; z-index: 100; }");
  H.push("    .site-header .container { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }");
  H.push("    .voa-logo { font-family: Space Grotesk, sans-serif; font-weight: 700; font-size: 1rem; letter-spacing: 0.12em; text-transform: uppercase; color: var(--text); text-decoration: none; opacity: 0.9; transition: opacity 0.2s; }");
  H.push("    .voa-logo span { color: var(--accent); }");
  H.push("    .voa-logo:hover { opacity: 1; }");
  H.push("    .header-blog-name { font-size: 0.8rem; letter-spacing: 0.08em; text-transform: uppercase; color: var(--accent); opacity: 0.8; }");
  H.push("    .breadcrumb { padding: 0.75rem 0; font-size: 0.82rem; color: var(--text-muted); }");
  H.push("    .breadcrumb a { color: var(--text-muted); text-decoration: none; transition: color 0.2s; }");
  H.push("    .breadcrumb a:hover { color: var(--accent); }");
  H.push("    .breadcrumb .sep { margin: 0 0.4rem; opacity: 0.4; }");
  H.push("    .post-header { padding: 2.5rem 0 2rem; border-bottom: 1px solid var(--border); }");
  H.push("    .lane-badge { display: inline-block; font-family: Space Grotesk, sans-serif; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.15em; text-transform: uppercase; color: var(--accent); border: 1px solid var(--accent); border-radius: 2px; padding: 0.2em 0.6em; margin-bottom: 1.2rem; }");
  H.push("    .post-title { font-size: clamp(1.8rem, 4vw, 2.6rem); font-weight: 700; line-height: 1.2; color: var(--text); margin-bottom: 1rem; }");
  H.push("    .post-meta { font-size: 0.85rem; color: var(--text-muted); display: flex; gap: 1rem; flex-wrap: wrap; align-items: center; }");
  H.push("    .post-meta .author { color: var(--accent-light); }");
  H.push("    .post-body { padding: 2.5rem 0 3rem; flex: 1; }");
  H.push("    .post-body p { margin-bottom: 1.4em; }");
  H.push("    .post-body h2 { font-size: 1.5rem; font-weight: 700; color: var(--accent-light); margin: 2.5rem 0 0.8rem; padding-bottom: 0.3rem; border-bottom: 1px solid var(--border); }");
  H.push("    .post-body h3 { font-size: 1.2rem; font-weight: 600; color: var(--text); margin: 1.8rem 0 0.6rem; }");
  H.push("    .post-body h4, .post-body h5, .post-body h6 { font-size: 1.05rem; font-weight: 600; color: var(--text-muted); margin: 1.4rem 0 0.5rem; }");
  H.push("    .post-body a { color: var(--accent); text-decoration: underline; text-underline-offset: 3px; transition: color 0.2s; }");
  H.push("    .post-body a:hover { color: var(--accent-light); }");
  H.push("    .post-body ul, .post-body ol { margin: 0.8em 0 1.4em 1.6em; }");
  H.push("    .post-body li { margin-bottom: 0.4em; }");
  H.push("    .post-body blockquote { border-left: 3px solid var(--accent); padding: 0.6em 1.2em; margin: 1.5em 0; color: var(--text-muted); font-style: italic; background: var(--surface2); border-radius: 0 4px 4px 0; }");
  H.push("    .post-body code { background: var(--surface2); color: var(--accent-light); padding: 0.15em 0.4em; border-radius: 3px; font-size: 0.88em; font-family: JetBrains Mono, Fira Code, monospace; }");
  H.push("    .post-body pre { background: var(--surface2); border: 1px solid var(--border); border-radius: 6px; padding: 1.2em; overflow-x: auto; margin: 1.5em 0; }");
  H.push("    .post-body pre code { background: none; padding: 0; color: var(--text); }");
  H.push("    .post-body hr { border: none; border-top: 1px solid var(--border); margin: 2.5em 0; }");
  H.push("    .post-body strong { color: var(--accent-light); font-weight: 600; }");
  H.push("    .post-body em { font-style: italic; }");
  H.push("    .post-cta { background: var(--surface2); border: 1px solid var(--accent-dark); border-radius: 8px; padding: 2rem; margin: 2rem 0; text-align: center; }");
  H.push("    .post-cta h3 { color: var(--accent); font-size: 1.1rem; margin-bottom: 0.6rem; }");
  H.push("    .post-cta p { color: var(--text-muted); font-size: 0.95rem; margin: 0 0 1.2rem; }");
  H.push("    .post-cta a { display: inline-block; background: var(--accent); color: #020a0a; font-family: Space Grotesk, sans-serif; font-weight: 700; font-size: 0.9rem; letter-spacing: 0.06em; text-transform: uppercase; padding: 0.7em 1.6em; border-radius: 4px; text-decoration: none; transition: opacity 0.2s, transform 0.15s; }");
  H.push("    .post-cta a:hover { opacity: 0.85; transform: translateY(-1px); }");
  H.push("    .site-footer { border-top: 1px solid var(--border); padding: 2rem 0; text-align: center; font-size: 0.82rem; color: var(--text-muted); }");
  H.push("    .site-footer a { color: var(--accent); text-decoration: none; }");
  H.push("    .site-footer a:hover { text-decoration: underline; }");
  H.push("    @media (max-width: 600px) { body { font-size: 16px; } .post-header { padding: 1.8rem 0 1.4rem; } }");
  H.push("  </style>");
  H.push("</head>");
  H.push("<body>");
  H.push("");
  H.push('<canvas id="stars-canvas" aria-hidden="true"></canvas>');
  H.push("");
  H.push('<div class="site-wrapper">');
  H.push("  <header class=\"site-header\">");
  H.push("    <div class=\"container\">");
  H.push('      <a href="/" class="voa-logo">Vibration<span>of</span>Awesome</a>');
  H.push('      <span class="header-blog-name">' + laneName + "</span>");
  H.push("    </div>");
  H.push("  </header>");
  H.push("  <main>");
  H.push("    <div class=\"container\">");
  H.push('      <nav class="breadcrumb" aria-label="Breadcrumb">');
  H.push('        <a href="/">Home</a><span class="sep">&#8250;</span>');
  H.push('        <a href="/blog/">Blog</a><span class="sep">&#8250;</span>');
  H.push('        <a href="/blog/' + lane + '/">' + laneName + '</a><span class="sep">&#8250;</span>');
  H.push("        <span>" + title + "</span>");
  H.push("      </nav>");
  H.push("      <header class=\"post-header\">");
  H.push('        <div class="lane-badge">' + badge + "</div>");
  H.push('        <h1 class="post-title">' + title + "</h1>");
  H.push("        <div class=\"post-meta\">");
  H.push('          <span class="author">' + byline + "</span>");
  H.push("          <span>&middot;</span>");
  H.push('          <time datetime="' + dateStr + '">' + displayDate + "</time>");
  H.push("        </div>");
  H.push("      </header>");
  H.push("      <article class=\"post-body\">");
  H.push("        " + bodyHtml);
  H.push('        <div class="post-cta">');
  H.push("          <h3>Explore More at Vibration of Awesome</h3>");
  H.push("          <p>Music, AI tools, digital creation, and the weird beautiful intersection of all three.</p>");
  H.push('          <a href="https://vibrationofawesome.com">Visit vibrationofawesome.com</a>');
  H.push("        </div>");
  H.push("      </article>");
  H.push("    </div>");
  H.push("  </main>");
  H.push("  <footer class=\"site-footer\">");
  H.push("    <div class=\"container\">");
  H.push('      <p>&copy; ' + yearNow + ' <a href="https://vibrationofawesome.com">Vibration of Awesome</a>');
  H.push("      &nbsp;&middot;&nbsp; " + laneName + ' &nbsp;&middot;&nbsp; <a href="/blog/">All Posts</a></p>');
  H.push("    </div>");
  H.push("  </footer>");
  H.push("</div>");
  H.push("<script>");
  H.push("(function() {");
  H.push('  var canvas = document.getElementById("stars-canvas");');
  H.push('  var ctx = canvas.getContext("2d");');
  H.push("  var stars = [];");
  H.push("  var STAR_COUNT = 160;");
  H.push("  var AR = " + accentR + ", AG = " + accentG + ", AB = " + accentB + ";");
  H.push("  function resize() { canvas.width = window.innerWidth; canvas.height = window.innerHeight; }");
  H.push("  function initStars() {");
  H.push("    stars = [];");
  H.push("    for (var i = 0; i < STAR_COUNT; i++) {");
  H.push("      stars.push({ x: Math.random() * canvas.width, y: Math.random() * canvas.height,");
  H.push("        r: Math.random() * 1.2 + 0.2, speed: Math.random() * 0.15 + 0.03,");
  H.push("        opacity: Math.random() * 0.6 + 0.2, pulse: Math.random() * Math.PI * 2,");
  H.push("        pulseSpeed: Math.random() * 0.008 + 0.003, isAccent: Math.random() < 0.04 });");
  H.push("    }");
  H.push("  }");
  H.push("  function draw() {");
  H.push("    ctx.clearRect(0, 0, canvas.width, canvas.height);");
  H.push("    for (var i = 0; i < stars.length; i++) {");
  H.push("      var s = stars[i];");
  H.push("      s.pulse += s.pulseSpeed;");
  H.push("      var op = s.opacity * (0.7 + 0.3 * Math.sin(s.pulse));");
  H.push("      ctx.beginPath(); ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);");
  H.push('      if (s.isAccent) { ctx.fillStyle = "rgba(" + AR + "," + AG + "," + AB + "," + op + ")"; }');
  H.push('      else { ctx.fillStyle = "rgba(255,255,255," + op + ")"; }');
  H.push("      ctx.fill();");
  H.push("      s.y += s.speed;");
  H.push("      if (s.y > canvas.height + 2) { s.y = -2; s.x = Math.random() * canvas.width; }");
  H.push("    }");
  H.push("    requestAnimationFrame(draw);");
  H.push("  }");
  H.push('  window.addEventListener("resize", function() { resize(); initStars(); });');
  H.push("  resize(); initStars(); draw();");
  H.push("})();");
  H.push("<\/script>");
  H.push("</body>");
  H.push("</html>");
  return H.join("\n");
}

// ── MAIN ──
async function main() {
  const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
  let postTitle, userMessage, systemPrompt;

  if (lane === "matt") {
    postTitle    = argv.title;
    systemPrompt = MATT_SYSTEM;
    userMessage  = "Write a full blog post with the title: \"" + argv.title + "\"";
  } else {
    postTitle    = argv.keyword;
    systemPrompt = BOOMBOT_SYSTEM;
    userMessage  = [
      "Write a long-form SEO blog post targeting the long-tail keyword: \"" + argv.keyword + "\"",
      "Broader topic context: \"" + argv.topic + "\"",
      "Make the H1 title compelling and include the keyword naturally.",
    ].join("\n");
  }

  console.log("\nGenerating " + (lane === "matt" ? "Forest Temple" : "Boom Frequency") + " post...");
  console.log("Title/Keyword: " + postTitle + "\n");

  let markdown;
  try {
    const message = await client.messages.create({
      model: "claude-opus-4-5",
      max_tokens: 4096,
      system: systemPrompt,
      messages: [{ role: "user", content: userMessage }],
    });
    markdown = message.content[0].text;
    console.log("Claude response received. Processing...\n");
  } catch (err) {
    console.error("Error calling Claude API:");
    if (err.status === 401) console.error("  -> Invalid API key. Check ANTHROPIC_API_KEY in your .env file.");
    else if (err.status === 429) console.error("  -> Rate limited. Wait a moment and try again.");
    else console.error(" ", err.message);
    process.exit(1);
  }

  // Strip META line for BoomBot
  let metaDescription = "";
  let cleanMarkdown   = markdown;
  if (lane === "boombot") {
    const result    = stripMeta(markdown);
    metaDescription = result.metaDescription;
    cleanMarkdown   = result.cleanMarkdown;
  }

  // Extract H1 title from generated content, then remove it from the body
  const h1Match = cleanMarkdown.match(/^#\s+(.+)$/m);
  if (h1Match) postTitle = h1Match[1].trim();
  const bodyMarkdown = cleanMarkdown.replace(/^#\s+.+$/m, "").trim();

  const bodyHtml = marked.parse(bodyMarkdown);
  const slug     = slugify(postTitle);

  const outputDir  = path.join(ROOT, "static", "blog", lane, "posts");
  const outputFile = path.join(outputDir, slug + ".html");
  const dataDir    = path.join(ROOT, "static", "_data");
  const dataFile   = path.join(dataDir, lane + "-posts.json");

  fs.mkdirSync(outputDir, { recursive: true });
  fs.mkdirSync(dataDir,   { recursive: true });

  const dateStr = new Date().toISOString();
  fs.writeFileSync(outputFile, buildHtml(lane, postTitle, dateStr, bodyHtml, slug, metaDescription), "utf8");
  console.log("Post created: /blog/" + lane + "/posts/" + slug + ".html");

  // Update the JSON post index
  let posts = [];
  if (fs.existsSync(dataFile)) {
    try { posts = JSON.parse(fs.readFileSync(dataFile, "utf8")); if (!Array.isArray(posts)) posts = []; }
    catch (_) { posts = []; }
  }
  posts.unshift({
    title: postTitle, slug, date: dateStr,
    excerpt: extractExcerpt(bodyMarkdown),
    url: "/blog/" + lane + "/posts/" + slug + ".html",
    tags: [],
  });
  fs.writeFileSync(dataFile, JSON.stringify(posts, null, 2), "utf8");
  console.log("JSON index updated: static/_data/" + lane + "-posts.json");

  // Always regenerate sitemap after adding a post
  updateSitemap();

  // ── Auto-syndication ──
  if (argv["no-syndicate"]) {
    console.log("\n[syndication skipped — --no-syndicate flag set]");
  } else {
    console.log("\nStarting auto-syndication...");
    const syndicateArgs = [
      "scripts/syndicate.js",
      "--lane",  lane,
      "--slug",  slug,
    ];
    // Pass keyword as image search term for BoomBot posts
    if (lane === "boombot" && argv.keyword) {
      syndicateArgs.push("--keyword", argv.keyword);
    } else if (lane === "matt" && argv.title) {
      syndicateArgs.push("--keyword", argv.title);
    }

    const result = spawnSync("node", syndicateArgs, { stdio: "inherit", cwd: ROOT });
    if (result.error) console.error("Syndication spawn error:", result.error.message);
    else if (result.status !== 0) console.warn(`Syndication exited with code ${result.status}`);
  }
}

main();
