#!/usr/bin/env node
/**
 * generate-captions.js — Platform-specific caption generator for vibrationofawesome.com
 *
 * Generates unique captions for 9 social platforms using Claude.
 *
 * Exports: generateCaptions(post, client?)
 * CLI:     node scripts/generate-captions.js --lane [matt|boombot] --slug <slug>
 */

import Anthropic from "@anthropic-ai/sdk";
import dotenv from "dotenv";
import { fileURLToPath } from "url";
import path from "path";
import fs from "fs";
import minimist from "minimist";

dotenv.config({ override: true });

const __filename = fileURLToPath(import.meta.url);
const __dirname  = path.dirname(__filename);
const ROOT       = path.resolve(__dirname, "..");

// Ordered list of platform labels — order matters for the section parser
const LABELS = [
  "FACEBOOK", "BLUESKY", "MASTODON", "PINTEREST",
  "DEVTO", "HASHNODE", "TUMBLR", "INSTAGRAM", "THREADS",
];

const SYSTEM_PROMPT = `You are a social media copywriter for vibrationofawesome.com.

The site serves spiritually awakening creators, neurodivergent entrepreneurs, musicians
learning AI, and abundance-minded outliers. Matt Dunn is the creator — musician (EarthStar
rock/metal/electronic, Ruzindla EDM/psytrance), digital creator, 20-year internet marketing
veteran who runs a personal operating system called Forest Temple.

Write in a real, slightly eccentric voice — never corporate, never generic. Each caption must
be completely unique and tailored for that platform's culture and norms.

Return ONLY the labeled sections in exact order with no preamble or commentary.`;

// ── Parser ────────────────────────────────────────────────────────────────────

/**
 * Parse Claude's labeled-section response into a plain object keyed by lowercase platform name.
 * Handles Claude's tendency to wrap labels in markdown bold (**LABEL:**) and
 * separate sections with --- horizontal rules.
 */
function parseCaptions(text) {
  const result = {};

  // Label pattern: optional leading **, optional trailing **, colon, optional trailing whitespace/newlines
  // e.g. matches: "FACEBOOK:", "**FACEBOOK:**", "**FACEBOOK:** "
  function labelRe(label) {
    return new RegExp(`^\\*{0,2}\\s*${label}:\\s*\\*{0,2}\\s*`, "mi");
  }

  for (let i = 0; i < LABELS.length; i++) {
    const label = LABELS[i];
    const next  = LABELS[i + 1];

    // Use exec() so we get startM.index — reliable even if the string appears elsewhere
    const startM = labelRe(label).exec(text);
    if (!startM) { result[label.toLowerCase()] = ""; continue; }

    const start = startM.index + startM[0].length;
    let end = text.length;

    if (next) {
      const endM = labelRe(next).exec(text.slice(start));
      if (endM) end = start + endM.index;
    }

    result[label.toLowerCase()] = text
      .slice(start, end)
      .replace(/\s*\n?---+\n?\s*$/m, "")  // strip trailing --- separator
      .trim();
  }
  return result;
}

// ── Main export ───────────────────────────────────────────────────────────────

/**
 * Generate platform-specific captions for a blog post.
 *
 * @param {object} post - { title, excerpt, url, tags, lane }
 * @param {Anthropic} [client] - Optional pre-created Anthropic client
 * @returns {Promise<object>} Captions keyed by platform (facebook, bluesky, mastodon, etc.)
 */
export async function generateCaptions(post, client) {
  const anthropic = client || new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
  const postUrl   = post.url.startsWith("http")
    ? post.url
    : `https://vibrationofawesome.com${post.url}`;
  const laneLabel = post.lane === "matt"
    ? "From the Forest Temple (raw personal blog by Matt Dunn)"
    : "Boom Frequency (AI/creator-tools blog by Matty BoomBoom)";

  const userContent = [
    `Title: ${post.title}`,
    `URL: ${postUrl}`,
    `Excerpt: ${(post.excerpt || "").slice(0, 300)}`,
    `Lane: ${laneLabel}`,
    `Tags: ${(post.tags || []).join(", ")}`,
    "",
    "Generate captions for each platform below. Follow every tone rule exactly.",
    "Include the URL naturally in each caption unless noted otherwise.",
    "",
    `FACEBOOK: conversational tone, 2-3 sentences, end with a genuine question to spark comments, include the URL`,
    `BLUESKY: punchy single thought or sentence, under 300 chars total including URL, zero hashtags`,
    `MASTODON: thoughtful and contextual, 2-3 sentences, end with 2-3 relevant #hashtags`,
    `PINTEREST: descriptive keyword-rich paragraph (good for search), end with 3-5 #hashtags, include URL`,
    `DEVTO: short compelling intro paragraph with a technical/AI-automation angle, suitable as a Dev.to article teaser, must mention AI or automation angle, end with URL`,
    `HASHNODE: same technical angle as Dev.to but more personal and first-person story-driven, end with URL`,
    `TUMBLR: creative, aesthetic, slightly poetic, 2-4 sentences, then 5-8 #hashtags on a new line separated from the caption`,
    `INSTAGRAM: visual and inspiring, 1-2 punchy sentences MAX (no hashtags in caption body), then on a separate new line: 5-8 relevant #hashtags`,
    `THREADS: conversational and punchy, under 500 chars total including hashtags, 2-3 #hashtags at end`,
  ].join("\n");

  const msg = await anthropic.messages.create({
    model:      "claude-sonnet-4-6",
    max_tokens: 2048,
    system:     SYSTEM_PROMPT,
    messages:   [{ role: "user", content: userContent }],
  });

  return parseCaptions(msg.content[0].text);
}

// ── CLI entry point ───────────────────────────────────────────────────────────

const isCli = process.argv[1] && path.resolve(process.argv[1]) === path.resolve(__filename);
if (isCli) {
  if (!process.env.ANTHROPIC_API_KEY) {
    console.error("Error: ANTHROPIC_API_KEY not set."); process.exit(1);
  }

  const argv = minimist(process.argv.slice(2), { string: ["lane", "slug"] });
  if (!argv.lane || !["matt", "boombot"].includes(argv.lane) || !argv.slug) {
    console.error("Usage: node scripts/generate-captions.js --lane [matt|boombot] --slug <post-slug>");
    process.exit(1);
  }

  const dataFile = path.join(ROOT, "static", "_data", `${argv.lane}-posts.json`);
  if (!fs.existsSync(dataFile)) { console.error(`No data file: ${dataFile}`); process.exit(1); }

  const posts = JSON.parse(fs.readFileSync(dataFile, "utf8"));
  const post  = posts.find(p => p.slug === argv.slug);
  if (!post) { console.error(`Post "${argv.slug}" not found in ${dataFile}`); process.exit(1); }

  console.log(`\nGenerating captions for: ${post.title}\n`);
  const captions = await generateCaptions({ ...post, lane: argv.lane });
  console.log(JSON.stringify(captions, null, 2));
}
