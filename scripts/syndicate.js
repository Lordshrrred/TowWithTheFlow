#!/usr/bin/env node
/**
 * syndicate.js — Social media syndication for vibrationofawesome.com
 *
 * Platforms: Facebook, Instagram, Twitter/X, Bluesky, Mastodon,
 *            Pinterest, Dev.to, Hashnode, Tumblr
 *
 * Standalone CLI usage:
 *   node scripts/syndicate.js --lane matt --slug my-post-slug
 *
 * Programmatic usage (from generate-post.js):
 *   import { syndicatePost } from "./syndicate.js";
 *   await syndicatePost({ title, excerpt, url, tags, bodyText });
 *
 * Required .env keys per platform:
 *   Facebook:  FACEBOOK_PAGE_ID, FACEBOOK_ACCESS_TOKEN
 *   Instagram: INSTAGRAM_ACCOUNT_ID, FACEBOOK_ACCESS_TOKEN
 *   Twitter:   TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET
 *   Bluesky:   BLUESKY_HANDLE, BLUESKY_APP_PASSWORD
 *   Mastodon:  MASTODON_INSTANCE, MASTODON_ACCESS_TOKEN
 *   Pinterest: PINTEREST_ACCESS_TOKEN (+ optional PINTEREST_BOARD_ID)
 *   Dev.to:    DEVTO_API_KEY
 *   Hashnode:  HASHNODE_API_KEY, HASHNODE_BLOG_SLUG
 *   Tumblr:    TUMBLR_CONSUMER_KEY, TUMBLR_CONSUMER_SECRET, TUMBLR_TOKEN, TUMBLR_TOKEN_SECRET
 */

import Anthropic from "@anthropic-ai/sdk";
import { TwitterApi } from "twitter-api-v2";
import minimist from "minimist";
import dotenv from "dotenv";
import fs from "fs";
import path from "path";
import crypto from "crypto";
import { fileURLToPath } from "url";

dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname  = path.dirname(__filename);
const ROOT       = path.resolve(__dirname, "..");

// ── HELPERS ──────────────────────────────────────────────────────────────────

function stripHtml(html) {
  return html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}

function firstWords(str, n) {
  return str.split(/\s+/).slice(0, n).join(" ");
}

function parseSections(text) {
  const parts = text.split(/^(?=FACEBOOK:|INSTAGRAM_CAPTION:|INSTAGRAM_HASHTAGS:|TWITTER_THREAD:)/m);
  const result = {};
  for (const part of parts) {
    const match = part.match(/^(FACEBOOK|INSTAGRAM_CAPTION|INSTAGRAM_HASHTAGS|TWITTER_THREAD):\s*([\s\S]*)/);
    if (match) result[match[1]] = match[2].trim();
  }
  return result;
}

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

// ── FACEBOOK ─────────────────────────────────────────────────────────────────

async function postToFacebook(caption) {
  const pageId      = process.env.FACEBOOK_PAGE_ID;
  const accessToken = process.env.FACEBOOK_ACCESS_TOKEN;
  if (!pageId || !accessToken) throw new Error("FACEBOOK_PAGE_ID or FACEBOOK_ACCESS_TOKEN not set");

  const url  = "https://graph.facebook.com/v19.0/" + pageId + "/feed";
  const body = new URLSearchParams({ message: caption, access_token: accessToken });
  const resp = await fetch(url, { method: "POST", body });
  const data = await resp.json();
  if (!resp.ok || data.error) throw new Error(data.error ? data.error.message : "HTTP " + resp.status);
  return data.id;
}

// ── INSTAGRAM ─────────────────────────────────────────────────────────────────

async function postToInstagram(caption) {
  const accountId  = process.env.INSTAGRAM_ACCOUNT_ID;
  const accessToken = process.env.FACEBOOK_ACCESS_TOKEN;
  if (!accountId || !accessToken) throw new Error("INSTAGRAM_ACCOUNT_ID or FACEBOOK_ACCESS_TOKEN not set");

  const base = "https://graph.facebook.com/v19.0/";

  const createBody = new URLSearchParams({ caption, media_type: "TEXT", access_token: accessToken });
  const createResp = await fetch(base + accountId + "/media", { method: "POST", body: createBody });
  const createData = await createResp.json();
  if (!createResp.ok || createData.error) {
    throw new Error(createData.error ? createData.error.message : "Create container HTTP " + createResp.status);
  }

  const publishBody = new URLSearchParams({ creation_id: createData.id, access_token: accessToken });
  const publishResp = await fetch(base + accountId + "/media_publish", { method: "POST", body: publishBody });
  const publishData = await publishResp.json();
  if (!publishResp.ok || publishData.error) {
    throw new Error(publishData.error ? publishData.error.message : "Publish HTTP " + publishResp.status);
  }
  return publishData.id;
}

// ── TWITTER/X ─────────────────────────────────────────────────────────────────

async function postToTwitter(tweets) {
  const { TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET } = process.env;
  if (!TWITTER_API_KEY || !TWITTER_API_SECRET || !TWITTER_ACCESS_TOKEN || !TWITTER_ACCESS_SECRET) {
    throw new Error("One or more TWITTER_* env vars not set");
  }

  const client    = new TwitterApi({ appKey: TWITTER_API_KEY, appSecret: TWITTER_API_SECRET,
                                     accessToken: TWITTER_ACCESS_TOKEN, accessSecret: TWITTER_ACCESS_SECRET });
  const rwClient  = client.readWrite;
  let lastTweetId = null;

  for (const tweetText of tweets) {
    const params = lastTweetId
      ? { text: tweetText, reply: { in_reply_to_tweet_id: lastTweetId } }
      : { text: tweetText };
    const result = await rwClient.v2.tweet(params);
    lastTweetId  = result.data.id;
  }
  return tweets.length;
}

// ── BLUESKY ───────────────────────────────────────────────────────────────────

async function postToBluesky({ title, excerpt, url }) {
  const handle   = process.env.BLUESKY_HANDLE;
  const password = process.env.BLUESKY_APP_PASSWORD;
  if (!handle || !password) throw new Error("BLUESKY_HANDLE or BLUESKY_APP_PASSWORD not set");

  // 1. Authenticate
  const authResp = await fetch("https://bsky.social/xrpc/com.atproto.server.createSession", {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ identifier: handle, password }),
  });
  const auth = await authResp.json();
  if (!authResp.ok) throw new Error(auth.message || "Bluesky auth failed: HTTP " + authResp.status);

  // 2. Build post text (AT Protocol limit: 300 chars)
  const base    = title + "\n\n";
  const suffix  = "\n\n" + url;
  const maxBody = 300 - Buffer.byteLength(base, "utf8") - Buffer.byteLength(suffix, "utf8");
  const snippet = excerpt.length > maxBody ? excerpt.slice(0, Math.max(0, maxBody - 1)) + "…" : excerpt;
  const text    = base + snippet + suffix;

  // 3. Compute byte offsets for URL facet (Bluesky uses UTF-8 byte positions)
  const bytesBefore = Buffer.byteLength(text.slice(0, text.lastIndexOf(url)), "utf8");
  const bytesUrl    = Buffer.byteLength(url, "utf8");

  const record = {
    $type:     "app.bsky.feed.post",
    text,
    facets: [{
      index:    { byteStart: bytesBefore, byteEnd: bytesBefore + bytesUrl },
      features: [{ $type: "app.bsky.richtext.facet#link", uri: url }],
    }],
    createdAt: new Date().toISOString(),
  };

  const postResp = await fetch("https://bsky.social/xrpc/com.atproto.repo.createRecord", {
    method:  "POST",
    headers: { "Content-Type": "application/json", Authorization: "Bearer " + auth.accessJwt },
    body:    JSON.stringify({ repo: auth.did, collection: "app.bsky.feed.post", record }),
  });
  const postData = await postResp.json();
  if (!postResp.ok) throw new Error(postData.message || "Bluesky createRecord failed: HTTP " + postResp.status);
  return postData.uri;
}

// ── MASTODON ──────────────────────────────────────────────────────────────────

async function postToMastodon({ title, excerpt, url }) {
  const instance = process.env.MASTODON_INSTANCE;
  const token    = process.env.MASTODON_ACCESS_TOKEN;
  if (!instance || !token) throw new Error("MASTODON_INSTANCE or MASTODON_ACCESS_TOKEN not set");

  // Mastodon limit: 500 chars (configurable per instance — 500 is the safe default)
  const base    = title + "\n\n";
  const suffix  = "\n\n" + url;
  const maxBody = 500 - base.length - suffix.length;
  const snippet = excerpt.length > maxBody ? excerpt.slice(0, Math.max(0, maxBody - 1)) + "…" : excerpt;
  const status  = base + snippet + suffix;

  const resp = await fetch("https://" + instance + "/api/v1/statuses", {
    method:  "POST",
    headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
    body:    JSON.stringify({ status }),
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || "Mastodon post failed: HTTP " + resp.status);
  return data.id;
}

// ── PINTEREST ─────────────────────────────────────────────────────────────────

async function postToPinterest({ title, excerpt, url }) {
  const token = process.env.PINTEREST_ACCESS_TOKEN;
  if (!token) throw new Error("PINTEREST_ACCESS_TOKEN not set");

  // Resolve board: explicit env var preferred; otherwise fetch the user's first board
  let boardId = process.env.PINTEREST_BOARD_ID;
  if (!boardId) {
    const boardsResp = await fetch("https://api.pinterest.com/v5/boards", {
      headers: { Authorization: "Bearer " + token },
    });
    const boardsData = await boardsResp.json();
    if (!boardsResp.ok || !boardsData.items?.length) {
      throw new Error("No Pinterest boards found — set PINTEREST_BOARD_ID in .env");
    }
    boardId = boardsData.items[0].id;
  }

  const resp = await fetch("https://api.pinterest.com/v5/pins", {
    method:  "POST",
    headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
    body:    JSON.stringify({
      title,
      description: excerpt,
      link:        url,
      board_id:    boardId,
      media_source: {
        source_type: "image_url",
        url:         "https://vibrationofawesome.com/images/earthstar-hero.jpg",
      },
    }),
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(JSON.stringify(data.message || data) || "Pinterest pin failed: HTTP " + resp.status);
  return data.id;
}

// ── DEV.TO ────────────────────────────────────────────────────────────────────

async function postToDevTo({ title, excerpt, url, tags }) {
  const apiKey = process.env.DEVTO_API_KEY;
  if (!apiKey) throw new Error("DEVTO_API_KEY not set");

  const bodyMarkdown = [
    "*Originally published at [Vibration of Awesome](" + url + ")*",
    "",
    excerpt,
    "",
    "---",
    "",
    "[Read the full article at vibrationofawesome.com →](" + url + ")",
  ].join("\n");

  // Dev.to accepts up to 4 tags, lowercase alphanumeric only
  const safeTags = (tags || [])
    .map(t => t.toLowerCase().replace(/[^a-z0-9]/g, ""))
    .filter(Boolean)
    .slice(0, 4);

  const resp = await fetch("https://dev.to/api/articles", {
    method:  "POST",
    headers: { "Content-Type": "application/json", "api-key": apiKey },
    body:    JSON.stringify({
      article: {
        title,
        body_markdown: bodyMarkdown,
        published:     true,
        canonical_url: url,
        tags:          safeTags,
      },
    }),
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || "Dev.to post failed: HTTP " + resp.status);
  return data.url;
}

// ── HASHNODE ──────────────────────────────────────────────────────────────────

async function postToHashnode({ title, excerpt, url }) {
  const apiKey   = process.env.HASHNODE_API_KEY;
  const blogSlug = process.env.HASHNODE_BLOG_SLUG;
  if (!apiKey || !blogSlug) throw new Error("HASHNODE_API_KEY or HASHNODE_BLOG_SLUG not set");

  const gql = async (query, variables) => {
    const resp = await fetch("https://gql.hashnode.com/", {
      method:  "POST",
      headers: { "Content-Type": "application/json", Authorization: apiKey },
      body:    JSON.stringify({ query, variables }),
    });
    const data = await resp.json();
    if (data.errors?.length) throw new Error(data.errors[0].message);
    return data.data;
  };

  // 1. Resolve publication ID from blog slug / host
  const pubData = await gql(
    "query GetPub($host: String!) { publication(host: $host) { id } }",
    { host: blogSlug }
  );
  const publicationId = pubData?.publication?.id;
  if (!publicationId) throw new Error("Hashnode: publication not found for host \"" + blogSlug + "\"");

  // 2. Build cross-post markdown
  const contentMarkdown = [
    "*Originally published at [Vibration of Awesome](" + url + ")*",
    "",
    excerpt,
    "",
    "---",
    "",
    "[Read the full article →](" + url + ")",
  ].join("\n");

  // 3. Publish
  const postData = await gql(
    `mutation Publish($input: PublishPostInput!) {
       publishPost(input: $input) { post { id slug url } }
     }`,
    { input: { title, contentMarkdown, publicationId, originalArticleURL: url, tags: [] } }
  );
  return postData?.publishPost?.post?.url;
}

// ── TUMBLR ────────────────────────────────────────────────────────────────────

/**
 * Build an OAuth 1.0a Authorization header.
 * bodyParams are included in the signature base string (required for form-urlencoded POSTs).
 */
function buildTumblrOAuthHeader(method, requestUrl, bodyParams,
                                consumerKey, consumerSecret, token, tokenSecret) {
  const oauth = {
    oauth_consumer_key:     consumerKey,
    oauth_nonce:            crypto.randomBytes(16).toString("hex"),
    oauth_signature_method: "HMAC-SHA1",
    oauth_timestamp:        Math.floor(Date.now() / 1000).toString(),
    oauth_token:            token,
    oauth_version:          "1.0",
  };

  // Merge all params for signature: oauth + body
  const allParams = { ...oauth, ...bodyParams };
  const paramStr  = Object.keys(allParams)
    .sort()
    .map(k => encodeURIComponent(k) + "=" + encodeURIComponent(allParams[k]))
    .join("&");

  const baseString  = [method.toUpperCase(), encodeURIComponent(requestUrl), encodeURIComponent(paramStr)].join("&");
  const signingKey  = encodeURIComponent(consumerSecret) + "&" + encodeURIComponent(tokenSecret);
  oauth.oauth_signature = crypto.createHmac("sha1", signingKey).update(baseString).digest("base64");

  return "OAuth " + Object.keys(oauth)
    .sort()
    .map(k => encodeURIComponent(k) + '="' + encodeURIComponent(oauth[k]) + '"')
    .join(", ");
}

async function postToTumblr({ title, excerpt, url, tags }) {
  const { TUMBLR_CONSUMER_KEY, TUMBLR_CONSUMER_SECRET, TUMBLR_TOKEN, TUMBLR_TOKEN_SECRET } = process.env;
  if (!TUMBLR_CONSUMER_KEY || !TUMBLR_CONSUMER_SECRET || !TUMBLR_TOKEN || !TUMBLR_TOKEN_SECRET) {
    throw new Error("One or more TUMBLR_* env vars not set");
  }

  // 1. Get primary blog name
  const infoUrl    = "https://api.tumblr.com/v2/user/info";
  const infoHeader = buildTumblrOAuthHeader(
    "GET", infoUrl, {},
    TUMBLR_CONSUMER_KEY, TUMBLR_CONSUMER_SECRET, TUMBLR_TOKEN, TUMBLR_TOKEN_SECRET
  );
  const infoResp = await fetch(infoUrl, { headers: { Authorization: infoHeader } });
  const infoData = await infoResp.json();
  if (infoData.meta?.status !== 200) {
    throw new Error("Tumblr user/info failed: " + (infoData.meta?.msg || JSON.stringify(infoData)));
  }
  const blogName = infoData.response?.user?.blogs?.[0]?.name;
  if (!blogName) throw new Error("Tumblr: could not determine primary blog name");

  // 2. Build HTML post body
  const safeExcerpt = excerpt.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const body        = "<p>" + safeExcerpt + "</p><p><a href=\"" + url + "\">Read the full post →</a></p>";
  const tagStr      = (tags || []).join(",");
  const postParams  = { type: "text", title, body, tags: tagStr };

  // 3. Post
  const postUrl    = "https://api.tumblr.com/v2/blog/" + blogName + "/posts";
  const postHeader = buildTumblrOAuthHeader(
    "POST", postUrl, postParams,
    TUMBLR_CONSUMER_KEY, TUMBLR_CONSUMER_SECRET, TUMBLR_TOKEN, TUMBLR_TOKEN_SECRET
  );
  const resp = await fetch(postUrl, {
    method:  "POST",
    headers: { Authorization: postHeader, "Content-Type": "application/x-www-form-urlencoded" },
    body:    new URLSearchParams(postParams),
  });
  const data = await resp.json();
  if (data.meta?.status !== 201 && data.meta?.status !== 200) {
    throw new Error("Tumblr post failed: " + (data.meta?.msg || JSON.stringify(data.errors || data)));
  }
  return data.response?.id;
}

// ── CORE SYNDICATION FUNCTION ─────────────────────────────────────────────────

/**
 * Syndicate a post to all configured platforms.
 *
 * @param {Object} post
 * @param {string} post.title    - Post title
 * @param {string} post.excerpt  - Short excerpt / first paragraph
 * @param {string} post.url      - Full canonical URL
 * @param {string[]} [post.tags] - Optional tag array
 * @param {string} [post.bodyText] - Optional plain-text body preview (used for Claude captions)
 * @returns {Promise<Array>} Results array with { platform, status, ... } per platform
 */
export async function syndicatePost(post) {
  const { title, excerpt, url, tags = [], bodyText = "" } = post;

  console.log("\n── Syndication ─────────────────────────────────");
  console.log("Post : " + title);
  console.log("URL  : " + url);

  // ── Generate Claude captions for Facebook / Instagram / Twitter ──
  let sections   = {};
  let tweetTexts = [];

  if (process.env.ANTHROPIC_API_KEY) {
    console.log("\nGenerating platform captions via Claude...");
    try {
      const claude = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
      const msg    = await claude.messages.create({
        model:      "claude-opus-4-5",
        max_tokens: 2048,
        system: "You are a social media copywriter for vibrationofawesome.com. " +
                "The site serves spiritually awakening creators, neurodivergent entrepreneurs, " +
                "musicians learning AI, and abundance-minded outliers. Write in a real, slightly " +
                "eccentric voice — never corporate, never generic.",
        messages: [{
          role:    "user",
          content: [
            "Generate social media copy for the following blog post.",
            "",
            "Title: "   + title,
            "Excerpt: " + excerpt,
            "URL: "     + url,
            bodyText ? "Body preview: " + bodyText.slice(0, 800) : "",
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
          ].filter(Boolean).join("\n"),
        }],
      });
      sections   = parseSections(msg.content[0].text);
      tweetTexts = parseTweets(sections.TWITTER_THREAD || "");
      console.log("Captions generated.\n");
    } catch (err) {
      console.error("Claude caption generation failed: " + err.message);
      console.error("Falling back to title + excerpt for FB/IG/Twitter.\n");
    }
  }

  // Fallback captions when Claude isn't available or caption generation failed
  const fbCaption = sections.FACEBOOK ||
    (title + "\n\n" + excerpt + "\n\n" + url);
  const igCaption = sections.INSTAGRAM_CAPTION
    ? sections.INSTAGRAM_CAPTION + "\n\n" + (sections.INSTAGRAM_HASHTAGS || "")
    : (title + "\n\n" + excerpt + "\n\n" + url);
  if (!tweetTexts.length) {
    tweetTexts = [title + " — " + excerpt.slice(0, 200) + " " + url];
  }

  const results = [];

  // ── Facebook ──
  try {
    const id = await postToFacebook(fbCaption);
    console.log("✓ Facebook  — post ID: " + id);
    results.push({ platform: "facebook", status: "ok", id });
  } catch (err) {
    console.error("✗ Facebook  — " + err.message);
    results.push({ platform: "facebook", status: "error", error: err.message });
  }

  // ── Instagram ──
  try {
    const id = await postToInstagram(igCaption);
    console.log("✓ Instagram — media ID: " + id);
    results.push({ platform: "instagram", status: "ok", id });
  } catch (err) {
    console.error("✗ Instagram — " + err.message);
    results.push({ platform: "instagram", status: "error", error: err.message });
  }

  // ── Twitter/X ──
  try {
    const count = await postToTwitter(tweetTexts);
    console.log("✓ Twitter   — " + count + " tweet(s) posted");
    results.push({ platform: "twitter", status: "ok", count });
  } catch (err) {
    console.error("✗ Twitter   — " + err.message);
    results.push({ platform: "twitter", status: "error", error: err.message });
  }

  // ── Bluesky ──
  try {
    const uri = await postToBluesky({ title, excerpt, url });
    console.log("✓ Bluesky   — " + uri);
    results.push({ platform: "bluesky", status: "ok", uri });
  } catch (err) {
    console.error("✗ Bluesky   — " + err.message);
    results.push({ platform: "bluesky", status: "error", error: err.message });
  }

  // ── Mastodon ──
  try {
    const id = await postToMastodon({ title, excerpt, url });
    console.log("✓ Mastodon  — status ID: " + id);
    results.push({ platform: "mastodon", status: "ok", id });
  } catch (err) {
    console.error("✗ Mastodon  — " + err.message);
    results.push({ platform: "mastodon", status: "error", error: err.message });
  }

  // ── Pinterest ──
  try {
    const id = await postToPinterest({ title, excerpt, url });
    console.log("✓ Pinterest — pin ID: " + id);
    results.push({ platform: "pinterest", status: "ok", id });
  } catch (err) {
    console.error("✗ Pinterest — " + err.message);
    results.push({ platform: "pinterest", status: "error", error: err.message });
  }

  // ── Dev.to ──
  try {
    const articleUrl = await postToDevTo({ title, excerpt, url, tags });
    console.log("✓ Dev.to    — " + articleUrl);
    results.push({ platform: "devto", status: "ok", url: articleUrl });
  } catch (err) {
    console.error("✗ Dev.to    — " + err.message);
    results.push({ platform: "devto", status: "error", error: err.message });
  }

  // ── Hashnode ──
  try {
    const postUrl = await postToHashnode({ title, excerpt, url });
    console.log("✓ Hashnode  — " + postUrl);
    results.push({ platform: "hashnode", status: "ok", url: postUrl });
  } catch (err) {
    console.error("✗ Hashnode  — " + err.message);
    results.push({ platform: "hashnode", status: "error", error: err.message });
  }

  // ── Tumblr ──
  try {
    const id = await postToTumblr({ title, excerpt, url, tags });
    console.log("✓ Tumblr    — post ID: " + id);
    results.push({ platform: "tumblr", status: "ok", id });
  } catch (err) {
    console.error("✗ Tumblr    — " + err.message);
    results.push({ platform: "tumblr", status: "error", error: err.message });
  }

  const ok   = results.filter(r => r.status === "ok").length;
  const fail = results.filter(r => r.status === "error").length;
  console.log("\nSyndication complete — " + ok + " succeeded, " + fail + " failed.");
  console.log("────────────────────────────────────────────────\n");
  return results;
}

// ── CLI MODE ──────────────────────────────────────────────────────────────────

async function main() {
  const argv = minimist(process.argv.slice(2), {
    string:  ["lane", "slug"],
    alias:   { l: "lane", s: "slug" },
  });

  if (!argv.lane || !["matt", "boombot"].includes(argv.lane)) {
    console.error('Error: --lane must be "matt" or "boombot"'); process.exit(1);
  }
  if (!argv.slug) {
    console.error("Error: --slug is required (e.g. --slug my-post-title)"); process.exit(1);
  }
  if (!process.env.ANTHROPIC_API_KEY) {
    console.error("Error: ANTHROPIC_API_KEY not set."); process.exit(1);
  }

  const { lane, slug } = argv;

  // Load post from JSON index
  const dataFile = path.join(ROOT, "static", "_data", lane + "-posts.json");
  if (!fs.existsSync(dataFile)) {
    console.error("Error: " + dataFile + " not found. Run generate-post.js first."); process.exit(1);
  }
  let posts;
  try { posts = JSON.parse(fs.readFileSync(dataFile, "utf8")); }
  catch (e) { console.error("Error parsing " + dataFile + ": " + e.message); process.exit(1); }

  const post = posts.find(p => p.slug === slug);
  if (!post) {
    console.error("Error: Post \"" + slug + "\" not found in " + dataFile); process.exit(1);
  }

  // Extract body text from HTML for Claude caption quality
  let bodyText = "";
  const htmlFile = path.join(ROOT, "static", "blog", lane, "posts", slug + ".html");
  if (fs.existsSync(htmlFile)) {
    const rawHtml   = fs.readFileSync(htmlFile, "utf8");
    const bodyMatch = rawHtml.match(/<article[^>]*>([\s\S]*?)<\/article>/i);
    bodyText = bodyMatch
      ? firstWords(stripHtml(bodyMatch[1]), 500)
      : firstWords(stripHtml(rawHtml), 500);
  }

  await syndicatePost({
    title:    post.title,
    excerpt:  post.excerpt,
    url:      "https://vibrationofawesome.com" + post.url,
    tags:     post.tags || [],
    bodyText,
  });
}

// Run main() only when executed directly (not when imported as a module)
if (process.argv[1] && path.resolve(process.argv[1]) === __filename) {
  main().catch(err => { console.error("Fatal:", err.message); process.exit(1); });
}
