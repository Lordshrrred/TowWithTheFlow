#!/usr/bin/env node
/**
 * syndicate.js — Social media syndication for vibrationofawesome.com
 *
 * Reads a published blog post, generates platform-specific captions via Claude,
 * then posts to Facebook, Instagram, and Twitter/X.
 *
 * Usage:
 *   node scripts/syndicate.js --lane matt --slug my-post-slug
 *   node scripts/syndicate.js --lane boombot --slug ai-tools-for-musicians
 */

import Anthropic from "@anthropic-ai/sdk";
import { TwitterApi } from "twitter-api-v2";
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
  string: ["lane", "slug"],
  alias: { l: "lane", s: "slug" },
});

if (!argv.lane || !["matt", "boombot"].includes(argv.lane)) {
  console.error('Error: --lane must be "matt" or "boombot"'); process.exit(1);
}
if (!argv.slug) {
  console.error('Error: --slug is required (e.g. --slug my-post-title)'); process.exit(1);
}
if (!process.env.ANTHROPIC_API_KEY) {
  console.error("Error: ANTHROPIC_API_KEY not set."); process.exit(1);
}

const lane = argv.lane;
const slug = argv.slug;

// ── HELPERS ──

/** Strip HTML tags and return plain text */
function stripHtml(html) {
  return html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}

/** Return first N words of a string */
function firstWords(str, n) {
  return str.split(/\s+/).slice(0, n).join(" ");
}

/**
 * Parse Claude's labeled-section response into a map.
 * Sections are delimited by uppercase labels like FACEBOOK:, TWITTER_THREAD:, etc.
 */
function parseSections(text) {
  const sectionPattern = /^(FACEBOOK|INSTAGRAM_CAPTION|INSTAGRAM_HASHTAGS|TWITTER_THREAD):\s*/m;
  const parts = text.split(/^(?=FACEBOOK:|INSTAGRAM_CAPTION:|INSTAGRAM_HASHTAGS:|TWITTER_THREAD:)/m);
  const result = {};
  for (const part of parts) {
    const match = part.match(/^(FACEBOOK|INSTAGRAM_CAPTION|INSTAGRAM_HASHTAGS|TWITTER_THREAD):\s*([\s\S]*)/);
    if (match) {
      result[match[1]] = match[2].trim();
    }
  }
  return result;
}

/**
 * Parse a TWITTER_THREAD section into an array of tweet strings.
 * Expects lines like: TWEET_1: text, TWEET_2: text, etc.
 */
function parseTweets(threadText) {
  const tweets = [];
  const tweetPattern = /TWEET_\d+:\s*([\s\S]*?)(?=TWEET_\d+:|$)/g;
  let match;
  while ((match = tweetPattern.exec(threadText)) !== null) {
    const t = match[1].trim();
    if (t) tweets.push(t);
  }
  return tweets;
}

// ── PLATFORM POST FUNCTIONS ──

/** Post to Facebook Page feed via Meta Graph API */
async function postToFacebook(caption) {
  const pageId      = process.env.FACEBOOK_PAGE_ID;
  const accessToken = process.env.FACEBOOK_ACCESS_TOKEN;
  if (!pageId || !accessToken) {
    throw new Error("FACEBOOK_PAGE_ID or FACEBOOK_ACCESS_TOKEN not set in .env");
  }

  const url  = "https://graph.facebook.com/v19.0/" + pageId + "/feed";
  const body = new URLSearchParams({ message: caption, access_token: accessToken });

  const resp = await fetch(url, { method: "POST", body });
  const data = await resp.json();

  if (!resp.ok || data.error) {
    throw new Error(data.error ? data.error.message : "HTTP " + resp.status);
  }
  return data.id;
}

/** Publish a text post to Instagram via two-step Media API */
async function postToInstagram(caption) {
  const accountId  = process.env.INSTAGRAM_ACCOUNT_ID;
  const accessToken = process.env.FACEBOOK_ACCESS_TOKEN;
  if (!accountId || !accessToken) {
    throw new Error("INSTAGRAM_ACCOUNT_ID or FACEBOOK_ACCESS_TOKEN not set in .env");
  }

  const base = "https://graph.facebook.com/v19.0/";

  // Step 1: Create media container
  const createBody = new URLSearchParams({
    caption:    caption,
    media_type: "TEXT",
    access_token: accessToken,
  });
  const createResp = await fetch(base + accountId + "/media", {
    method: "POST",
    body:   createBody,
  });
  const createData = await createResp.json();
  if (!createResp.ok || createData.error) {
    throw new Error(createData.error ? createData.error.message : "Create container HTTP " + createResp.status);
  }
  const containerId = createData.id;

  // Step 2: Publish container
  const publishBody = new URLSearchParams({
    creation_id:  containerId,
    access_token: accessToken,
  });
  const publishResp = await fetch(base + accountId + "/media_publish", {
    method: "POST",
    body:   publishBody,
  });
  const publishData = await publishResp.json();
  if (!publishResp.ok || publishData.error) {
    throw new Error(publishData.error ? publishData.error.message : "Publish HTTP " + publishResp.status);
  }
  return publishData.id;
}

/** Post a tweet thread using twitter-api-v2 */
async function postToTwitter(tweets) {
  const client = new TwitterApi({
    appKey:            process.env.TWITTER_API_KEY,
    appSecret:         process.env.TWITTER_API_SECRET,
    accessToken:       process.env.TWITTER_ACCESS_TOKEN,
    accessSecret:      process.env.TWITTER_ACCESS_SECRET,
  });

  if (!process.env.TWITTER_API_KEY || !process.env.TWITTER_API_SECRET ||
      !process.env.TWITTER_ACCESS_TOKEN || !process.env.TWITTER_ACCESS_SECRET) {
    throw new Error("One or more TWITTER_* env vars not set in .env");
  }

  const rwClient = client.readWrite;
  let lastTweetId = null;

  for (const tweetText of tweets) {
    const params = lastTweetId
      ? { text: tweetText, reply: { in_reply_to_tweet_id: lastTweetId } }
      : { text: tweetText };
    const result = await rwClient.v2.tweet(params);
    lastTweetId = result.data.id;
  }
  return tweets.length;
}

// ── MAIN ──
async function main() {
  // 1. Load post metadata from JSON index
  const dataFile = path.join(ROOT, "static", "_data", lane + "-posts.json");
  if (!fs.existsSync(dataFile)) {
    console.error("Error: " + dataFile + " not found. Run generate-post.js first.");
    process.exit(1);
  }

  let posts;
  try { posts = JSON.parse(fs.readFileSync(dataFile, "utf8")); }
  catch (e) { console.error("Error parsing " + dataFile + ": " + e.message); process.exit(1); }

  const post = posts.find((p) => p.slug === slug);
  if (!post) {
    console.error("Error: Post with slug \"" + slug + "\" not found in " + dataFile);
    process.exit(1);
  }

  // 2. Read the HTML file and extract body text (plain text, first 500 words)
  const htmlFile = path.join(ROOT, "static", "blog", lane, "posts", slug + ".html");
  if (!fs.existsSync(htmlFile)) {
    console.error("Error: HTML file not found at " + htmlFile);
    process.exit(1);
  }
  const rawHtml   = fs.readFileSync(htmlFile, "utf8");
  // Extract only the article body (between <article ...> and </article>)
  const bodyMatch = rawHtml.match(/<article[^>]*>([\s\S]*?)<\/article>/i);
  const bodyText  = bodyMatch ? firstWords(stripHtml(bodyMatch[1]), 500) : firstWords(stripHtml(rawHtml), 500);

  const postUrl = "https://vibrationofawesome.com" + post.url;
  console.log("\nSyndicating: " + post.title);
  console.log("URL: " + postUrl);
  console.log("Generating captions via Claude...\n");

  // 3. Generate platform captions via Claude
  const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
  let captionsText;
  try {
    const message = await client.messages.create({
      model: "claude-opus-4-5",
      max_tokens: 2048,
      system: "You are a social media copywriter for vibrationofawesome.com. " +
              "The site serves spiritually awakening creators, neurodivergent entrepreneurs, " +
              "musicians learning AI, and abundance-minded outliers. Write in a real, slightly " +
              "eccentric voice — never corporate, never generic.",
      messages: [{
        role: "user",
        content: [
          "Generate social media copy for the following blog post.",
          "",
          "Title: " + post.title,
          "Excerpt: " + post.excerpt,
          "URL: " + postUrl,
          "Body preview: " + bodyText.slice(0, 800),
          "",
          "Return EXACTLY these four labeled sections (no extra commentary):",
          "",
          "FACEBOOK: (150-200 words, conversational, includes the link, 2-3 hashtags)",
          "",
          "INSTAGRAM_CAPTION: (hook line + 5-7 sentences + CTA to visit the link)",
          "",
          "INSTAGRAM_HASHTAGS: (10-15 relevant hashtags, space-separated, no caption text)",
          "",
          "TWITTER_THREAD: (5-7 tweets; first is the hook, last includes the link; " +
          "label each as TWEET_1:, TWEET_2:, etc.; keep each tweet under 280 chars)",
        ].join("\n"),
      }],
    });
    captionsText = message.content[0].text;
    console.log("Captions generated. Posting to platforms...\n");
  } catch (err) {
    console.error("Error calling Claude API: " + err.message);
    process.exit(1);
  }

  // 4. Parse captions
  const sections          = parseSections(captionsText);
  const facebookCaption   = sections.FACEBOOK || "";
  const instagramCaption  = (sections.INSTAGRAM_CAPTION || "") + "\n\n" + (sections.INSTAGRAM_HASHTAGS || "");
  const tweetTexts        = parseTweets(sections.TWITTER_THREAD || "");

  // 5. Post to each platform (failures are non-fatal)
  // ── Facebook ──
  try {
    const postId = await postToFacebook(facebookCaption);
    console.log("Facebook: posted successfully (post ID: " + postId + ")");
  } catch (err) {
    console.error("Facebook: " + err.message + " — continuing...");
  }

  // ── Instagram ──
  try {
    const mediaId = await postToInstagram(instagramCaption);
    console.log("Instagram: published (media ID: " + mediaId + ")");
  } catch (err) {
    console.error("Instagram: " + err.message + " — continuing...");
  }

  // ── Twitter ──
  try {
    if (tweetTexts.length === 0) throw new Error("No tweets parsed from Claude response");
    const count = await postToTwitter(tweetTexts);
    console.log("Twitter: thread posted (" + count + " tweets)");
  } catch (err) {
    console.error("Twitter: " + err.message + " — continuing...");
  }

  console.log("\nSyndication complete.");
}

main();
