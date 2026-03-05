#!/usr/bin/env node
/**
 * seo-research.js — SEO keyword research tool for vibrationofawesome.com
 *
 * Generates 20 long-tail keyword variations for a given topic using Claude,
 * outputs a formatted terminal table, and appends results to topic-queue.json.
 *
 * Usage:
 *   node scripts/seo-research.js --topic "AI tools for musicians"
 */

import Anthropic from "@anthropic-ai/sdk";
import minimist from "minimist";
import dotenv from "dotenv";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname  = path.dirname(__filename);
const ROOT       = path.resolve(__dirname, "..");

// ── CLI ARGS ──
const argv = minimist(process.argv.slice(2), {
  string: ["topic"],
  alias: { t: "topic" },
});

if (!argv.topic) {
  console.error('Error: --topic is required (e.g. --topic "AI tools for musicians")');
  process.exit(1);
}
if (!process.env.ANTHROPIC_API_KEY) {
  console.error("Error: ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key.");
  process.exit(1);
}

const topic = argv.topic;

// ── HELPERS ──

/** Pad or truncate a string to exactly `len` characters */
function pad(str, len) {
  if (str.length >= len) return str.slice(0, len - 1) + "…";
  return str + " ".repeat(len - str.length);
}

/** Print the formatted terminal table */
function printTable(topic, keywords, date) {
  const divider = "━".repeat(60);
  console.log("\n" + divider);
  console.log("SEO RESEARCH: " + topic);
  console.log("Generated: " + date);
  console.log(divider + "\n");

  keywords.forEach((kw, i) => {
    const num     = String(i + 1).padStart(2, " ");
    const outline = Array.isArray(kw.h2_outline)
      ? kw.h2_outline.map((h) => "H2: " + h).join(" | ")
      : String(kw.h2_outline || "");

    console.log(num + ". " + kw.keyword);
    console.log("    Intent: " + (kw.search_intent || "unknown"));
    console.log("    Title:  " + (kw.suggested_title || ""));
    console.log("    Outline: " + outline);
    console.log("");
  });

  console.log(divider + "\n");
}

// ── MAIN ──
async function main() {
  const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
  const today  = new Date().toISOString().slice(0, 10); // YYYY-MM-DD

  console.log("\nResearching topic: \"" + topic + "\"");
  console.log("Calling Claude for 20 keyword variations...\n");

  // 1. Call Claude API
  let keywords;
  try {
    const message = await client.messages.create({
      model: "claude-opus-4-5",
      max_tokens: 4096,
      system: [
        "You are an SEO strategist for vibrationofawesome.com.",
        "The site targets: spiritually awakening creators, neurodivergent entrepreneurs,",
        "musicians learning AI, abundance-minded outliers.",
        "Return only valid JSON — no markdown fences, no commentary.",
      ].join(" "),
      messages: [{
        role: "user",
        content: [
          "Generate 20 long-tail keyword variations for the topic: " + topic,
          "",
          "For each keyword return a JSON object with these exact fields:",
          "  keyword         (string)",
          "  search_intent   (one of: informational, navigational, transactional)",
          "  suggested_title (string — compelling blog post title)",
          "  h2_outline      (array of 4-5 H2 heading strings)",
          "",
          "Return a JSON array only. No other text, no code fences.",
        ].join("\n"),
      }],
    });

    const raw = message.content[0].text.trim();

    // Strip markdown code fences if Claude adds them despite the instruction
    const cleaned = raw.replace(/^```json\s*/i, "").replace(/```\s*$/, "").trim();

    try {
      keywords = JSON.parse(cleaned);
    } catch (parseErr) {
      console.error("Error: Could not parse Claude's JSON response.");
      console.error("Raw response:\n" + raw);
      process.exit(1);
    }

    if (!Array.isArray(keywords)) {
      console.error("Error: Expected a JSON array from Claude, got: " + typeof keywords);
      process.exit(1);
    }
  } catch (err) {
    console.error("Error calling Claude API: " + err.message);
    process.exit(1);
  }

  // 2. Print formatted table
  printTable(topic, keywords, today);

  // 3. Save to topic-queue.json (append new session)
  const dataDir  = path.join(ROOT, "static", "_data");
  const dataFile = path.join(dataDir, "topic-queue.json");

  fs.mkdirSync(dataDir, { recursive: true });

  let queue = [];
  if (fs.existsSync(dataFile)) {
    try {
      queue = JSON.parse(fs.readFileSync(dataFile, "utf8"));
      if (!Array.isArray(queue)) queue = [];
    } catch (_) {
      queue = [];
    }
  }

  queue.push({ date: today, topic, keywords });
  fs.writeFileSync(dataFile, JSON.stringify(queue, null, 2), "utf8");
  console.log("Research saved to static/_data/topic-queue.json (" + keywords.length + " keywords)");
}

main();
