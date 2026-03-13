#!/usr/bin/env node
/**
 * syndicate.js — Full content syndication engine for vibrationofawesome.com
 *
 * Platforms: Bluesky · Mastodon · Facebook (VOA + EarthStar) · Pinterest
 *            Dev.to · Hashnode · Tumblr · Instagram (Publer) · Threads (Publer)
 *
 * CLI:  node scripts/syndicate.js --lane [matt|boombot] --slug <post-slug> [--keyword "search term"]
 * API:  import { syndicatePost } from "./syndicate.js"
 */

import Anthropic from "@anthropic-ai/sdk";
import crypto    from "crypto";
import dotenv    from "dotenv";
import { fileURLToPath } from "url";
import path      from "path";
import fs        from "fs";
import minimist  from "minimist";

import { generateCaptions } from "./generate-captions.js";
import { selectImage }      from "./select-image.js";

dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname  = path.dirname(__filename);
const ROOT       = path.resolve(__dirname, "..");
const LOG_FILE   = path.join(ROOT, "static", "_data", "syndication-log.json");
const CACHE_DIR  = path.join(ROOT, ".cache");

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Strip HTML tags, collapse whitespace */
function stripHtml(html) {
  return html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}

/** First N words of a string */
function firstWords(str, n) {
  return str.split(/\s+/).slice(0, n).join(" ");
}

/** RFC 3986 percent-encode (for OAuth 1.0a) */
function pctEncode(s) {
  return encodeURIComponent(String(s))
    .replace(/!/g, "%21").replace(/'/g, "%27")
    .replace(/\(/g, "%28").replace(/\)/g, "%29").replace(/\*/g, "%2A");
}

// ── OAuth 1.0a (Tumblr) ───────────────────────────────────────────────────────

/**
 * Build an OAuth 1.0a Authorization header (HMAC-SHA1).
 * bodyParams: plain object of extra non-oauth request body params to include in signature.
 */
function buildOAuthHeader({ method, url, bodyParams = {}, consumerKey, consumerSecret, token, tokenSecret }) {
  const oauthParams = {
    oauth_consumer_key:     consumerKey,
    oauth_nonce:            crypto.randomBytes(16).toString("hex"),
    oauth_signature_method: "HMAC-SHA1",
    oauth_timestamp:        String(Math.floor(Date.now() / 1000)),
    oauth_token:            token,
    oauth_version:          "1.0",
  };

  const allParams = { ...oauthParams, ...bodyParams };
  const paramStr  = Object.keys(allParams).sort()
    .map(k => `${pctEncode(k)}=${pctEncode(allParams[k])}`).join("&");

  const baseStr    = `${method.toUpperCase()}&${pctEncode(url)}&${pctEncode(paramStr)}`;
  const signingKey = `${pctEncode(consumerSecret)}&${pctEncode(tokenSecret)}`;
  const signature  = crypto.createHmac("sha1", signingKey).update(baseStr).digest("base64");

  oauthParams.oauth_signature = signature;
  const headerParts = Object.entries(oauthParams)
    .filter(([k]) => k.startsWith("oauth_"))
    .map(([k, v]) => `${pctEncode(k)}="${pctEncode(v)}"`).join(", ");

  return `OAuth ${headerParts}`;
}

// ── Facebook: long-lived token exchange ───────────────────────────────────────

/**
 * Exchange a short-lived page token for a long-lived one (60 days).
 * Requires META_APP_ID and META_APP_SECRET in .env.
 * Results are cached in .cache/fb-tokens.json so this runs once per token.
 */
async function getLongLivedToken(label, shortToken) {
  const appId     = process.env.META_APP_ID;
  const appSecret = process.env.META_APP_SECRET;
  if (!appId || !appSecret) return shortToken; // Can't exchange without app creds

  // Check cache
  fs.mkdirSync(CACHE_DIR, { recursive: true });
  const cacheFile = path.join(CACHE_DIR, "fb-tokens.json");
  let cache = {};
  try { cache = JSON.parse(fs.readFileSync(cacheFile, "utf8")); } catch (_) { /* fresh */ }

  if (cache[label]) {
    const expiresAt = new Date(cache[label].expiresAt);
    if (expiresAt > new Date()) {
      return cache[label].token;
    }
  }

  // Exchange token
  try {
    const qs   = new URLSearchParams({
      grant_type:         "fb_exchange_token",
      client_id:          appId,
      client_secret:      appSecret,
      fb_exchange_token:  shortToken,
    });
    const resp = await fetch(`https://graph.facebook.com/v19.0/oauth/access_token?${qs}`);
    const data = await resp.json();
    if (data.error) throw new Error(data.error.message);

    const expiresAt = new Date(Date.now() + (data.expires_in || 5184000) * 1000).toISOString();
    cache[label] = { token: data.access_token, expiresAt };
    fs.writeFileSync(cacheFile, JSON.stringify(cache, null, 2));
    console.log(`  [fb-tokens] Exchanged long-lived token for ${label} (expires ${expiresAt})`);
    return data.access_token;
  } catch (err) {
    console.warn(`  [fb-tokens] Token exchange failed for ${label}: ${err.message} — using original`);
    return shortToken;
  }
}

// ── Platform post functions ───────────────────────────────────────────────────

/** Post to Bluesky using AT Protocol */
async function postToBluesky(caption, postUrl, postTitle, postExcerpt) {
  const handle   = process.env.BLUESKY_HANDLE;
  const password = process.env.BLUESKY_APP_PASSWORD;
  if (!handle || !password) throw new Error("BLUESKY_HANDLE or BLUESKY_APP_PASSWORD not set");

  const base = "https://bsky.social/xrpc";

  // Create session
  const sessionResp = await fetch(`${base}/com.atproto.server.createSession`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ identifier: handle, password }),
  });
  const session = await sessionResp.json();
  if (!sessionResp.ok) throw new Error(`Bluesky auth failed: ${session.message || sessionResp.status}`);

  const { accessJwt, did } = session;

  // Build post record with external link embed
  const record = {
    $type:     "app.bsky.feed.post",
    text:      caption.slice(0, 300),
    createdAt: new Date().toISOString(),
    embed: {
      $type:    "app.bsky.embed.external",
      external: {
        uri:         postUrl,
        title:       postTitle,
        description: postExcerpt || "",
      },
    },
  };

  const postResp = await fetch(`${base}/com.atproto.repo.createRecord`, {
    method:  "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessJwt}` },
    body:    JSON.stringify({ repo: did, collection: "app.bsky.feed.post", record }),
  });
  const postData = await postResp.json();
  if (!postResp.ok) throw new Error(`Bluesky post failed: ${postData.message || postResp.status}`);

  const rkey    = postData.uri?.split("/").pop();
  const handle2 = handle.replace("@", "");
  return {
    postId:  postData.uri,
    postUrl: `https://bsky.app/profile/${handle2}/post/${rkey}`,
  };
}

/** Post to Mastodon */
async function postToMastodon(caption) {
  const instance = process.env.MASTODON_INSTANCE?.replace(/\/+$/, "");
  const token    = process.env.MASTODON_ACCESS_TOKEN;
  if (!instance || !token) throw new Error("MASTODON_INSTANCE or MASTODON_ACCESS_TOKEN not set");

  const resp = await fetch(`${instance}/api/v1/statuses`, {
    method:  "POST",
    headers: {
      "Content-Type":  "application/json",
      Authorization:   `Bearer ${token}`,
    },
    body: JSON.stringify({ status: caption.slice(0, 500), visibility: "public" }),
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(`Mastodon: ${data.error || resp.status}`);
  return { postId: data.id, postUrl: data.url };
}

/** Post to a Facebook Page */
async function postToFacebookPage(pageId, pageToken, caption, postUrl) {
  const longToken = await getLongLivedToken(pageId, pageToken);
  const body      = new URLSearchParams({
    message:      caption,
    link:         postUrl,
    access_token: longToken,
  });
  const resp = await fetch(`https://graph.facebook.com/v19.0/${pageId}/feed`, {
    method: "POST",
    body,
  });
  const data = await resp.json();
  if (!resp.ok || data.error) throw new Error(data.error?.message || `Facebook HTTP ${resp.status}`);
  return { postId: data.id, postUrl: `https://www.facebook.com/${data.id}` };
}

/** Post a Pin to Pinterest */
async function postToPinterest(caption, postTitle, postUrl, imageUrl) {
  const token   = process.env.PINTEREST_ACCESS_TOKEN;
  const boardId = process.env.PINTEREST_BOARD_ID;
  if (!token)   throw new Error("PINTEREST_ACCESS_TOKEN not set");
  if (!boardId) throw new Error("PINTEREST_BOARD_ID not set");

  const body = {
    link:        postUrl,
    title:       postTitle.slice(0, 100),
    description: caption.slice(0, 800),
    board_id:    boardId,
    ...(imageUrl ? { media_source: { source_type: "image_url", url: imageUrl } } : {}),
  };

  const resp = await fetch("https://api.pinterest.com/v5/pins", {
    method:  "POST",
    headers: {
      Authorization:  `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(`Pinterest: ${data.message || resp.status}`);
  return { postId: data.id, postUrl: `https://www.pinterest.com/pin/${data.id}/` };
}

/** Publish a teaser article on Dev.to */
async function postToDevTo(postTitle, caption, postUrl, tags) {
  const key = process.env.DEVTO_API_KEY;
  if (!key) throw new Error("DEVTO_API_KEY not set");

  const safeTags = (tags || [])
    .map(t => t.replace(/[^a-z0-9]/gi, "").toLowerCase().slice(0, 30))
    .filter(Boolean)
    .slice(0, 4);
  if (safeTags.length === 0) safeTags.push("ai", "creators");

  const bodyMarkdown = [
    caption,
    "",
    `---`,
    `*Originally published at [vibrationofawesome.com](${postUrl})*`,
  ].join("\n");

  const resp = await fetch("https://dev.to/api/articles", {
    method:  "POST",
    headers: { "Content-Type": "application/json", "api-key": key },
    body:    JSON.stringify({
      article: {
        title:         postTitle,
        body_markdown: bodyMarkdown,
        published:     true,
        canonical_url: postUrl,
        tags:          safeTags,
      },
    }),
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(`Dev.to: ${data.error || JSON.stringify(data.errors) || resp.status}`);
  return { postId: String(data.id), postUrl: data.url };
}

/** Publish a teaser on Hashnode (GraphQL) */
async function postToHashnode(postTitle, caption, postUrl, tags, imageUrl) {
  const key           = process.env.HASHNODE_API_KEY;
  const publicationId = process.env.HASHNODE_PUBLICATION_ID;
  if (!key)           throw new Error("HASHNODE_API_KEY not set");
  if (!publicationId) throw new Error("HASHNODE_PUBLICATION_ID not set (set in .env)");

  const contentMarkdown = [
    caption,
    "",
    `---`,
    `*Originally published at [vibrationofawesome.com](${postUrl})*`,
  ].join("\n");

  const mutation = `
    mutation PublishPost($input: PublishPostInput!) {
      publishPost(input: $input) {
        post { id url }
      }
    }
  `;

  const variables = {
    input: {
      title:               postTitle,
      contentMarkdown,
      publicationId,
      originalArticleURL:  postUrl,
      tags:                (tags || []).slice(0, 5).map(t => ({ slug: t.toLowerCase().replace(/\s+/g, "-"), name: t })),
      ...(imageUrl ? { coverImageOptions: { coverImageURL: imageUrl } } : {}),
    },
  };

  const resp = await fetch("https://gql.hashnode.com", {
    method:  "POST",
    headers: { "Content-Type": "application/json", Authorization: key },
    body:    JSON.stringify({ query: mutation, variables }),
  });
  const data = await resp.json();
  if (data.errors) throw new Error(`Hashnode: ${data.errors[0]?.message || JSON.stringify(data.errors)}`);
  const post = data.data?.publishPost?.post;
  return { postId: post?.id, postUrl: post?.url };
}

/** Post to Tumblr using OAuth 1.0a (NPF format) */
async function postToTumblr(caption, tags) {
  const consumerKey    = process.env.TUMBLR_CONSUMER_KEY;
  const consumerSecret = process.env.TUMBLR_CONSUMER_SECRET;
  const token          = process.env.TUMBLR_TOKEN;
  const tokenSecret    = process.env.TUMBLR_TOKEN_SECRET;
  const blogName       = process.env.TUMBLR_BLOG_NAME;

  if (!consumerKey || !consumerSecret || !token || !tokenSecret) {
    throw new Error("One or more TUMBLR_* env vars not set");
  }
  if (!blogName) throw new Error("TUMBLR_BLOG_NAME not set");

  const url  = `https://api.tumblr.com/v2/blog/${blogName}/posts`;
  const body = JSON.stringify({
    content: [{ type: "text", text: caption }],
    tags:    (tags || []).slice(0, 30),
  });

  // Extract body params that are included in the OAuth signature base string
  // For JSON bodies, the content-type is application/json and body params
  // are NOT included in the OAuth base string — only URL params are.
  const authHeader = buildOAuthHeader({
    method:         "POST",
    url,
    bodyParams:     {},
    consumerKey,
    consumerSecret,
    token,
    tokenSecret,
  });

  const resp = await fetch(url, {
    method:  "POST",
    headers: { "Content-Type": "application/json", Authorization: authHeader },
    body,
  });
  const data = await resp.json();
  if (!resp.ok || data.meta?.status >= 400) {
    throw new Error(`Tumblr: ${data.errors?.[0]?.detail || data.meta?.msg || resp.status}`);
  }
  const postId = data.response?.id_string || data.response?.id;
  return {
    postId:  String(postId || ""),
    postUrl: `https://${blogName}.tumblr.com/post/${postId}`,
  };
}

/** Post Instagram or Threads via Publer API */
async function postViaPubler(platform, caption, imageUrl) {
  const key = process.env.PUBLER_API_KEY;
  if (!key) throw new Error("PUBLER_API_KEY not set");

  // Publer API — verify endpoint and payload against Publer's docs if this fails
  const resp = await fetch("https://api.publer.io/v1/posts", {
    method:  "POST",
    headers: {
      "Content-Type":  "application/json",
      Authorization:   `Bearer ${key}`,
    },
    body: JSON.stringify({
      platforms:   [platform],          // "instagram" or "threads"
      text:        caption,
      publish_now: true,
      ...(imageUrl && platform === "instagram" ? { media_urls: [imageUrl] } : {}),
    }),
  });

  const data = await resp.json();
  if (!resp.ok) throw new Error(`Publer (${platform}): ${data.message || data.error || resp.status}`);
  const postId = data.post?.id || data.id;
  return { postId: String(postId || ""), postUrl: null };
}

// ── Syndication log ───────────────────────────────────────────────────────────

function loadLog() {
  try {
    if (fs.existsSync(LOG_FILE)) {
      const raw = JSON.parse(fs.readFileSync(LOG_FILE, "utf8"));
      return Array.isArray(raw.entries) ? raw : { entries: [] };
    }
  } catch (_) { /* corrupt file — start fresh */ }
  return { entries: [] };
}

function saveLog(log, entry) {
  log.entries.unshift(entry);
  // Keep last 100 entries
  if (log.entries.length > 100) log.entries = log.entries.slice(0, 100);
  log.lastUpdated = new Date().toISOString();
  fs.mkdirSync(path.dirname(LOG_FILE), { recursive: true });
  fs.writeFileSync(LOG_FILE, JSON.stringify(log, null, 2), "utf8");
}

/** Write dashboard password hash config from DASHBOARD_PASSWORD env var */
function writeDashboardConfig() {
  const password = process.env.DASHBOARD_PASSWORD;
  if (!password) return; // nothing to do

  const hash        = crypto.createHash("sha256").update(password).digest("hex");
  const configFile  = path.join(ROOT, "static", "_data", "dashboard-config.json");
  const existing    = fs.existsSync(configFile)
    ? JSON.parse(fs.readFileSync(configFile, "utf8"))
    : {};

  if (existing.passwordHash !== hash) {
    fs.writeFileSync(configFile, JSON.stringify({ passwordHash: hash }, null, 2), "utf8");
    console.log("  [dashboard] Password config updated.");
  }
}

// ── Core syndication function ─────────────────────────────────────────────────

/**
 * Syndicate a published post to all configured platforms.
 *
 * @param {string} lane    - "matt" or "boombot"
 * @param {string} slug    - Post slug
 * @param {object} options - { keyword?: string, anthropic?: Anthropic }
 * @returns {Promise<object>} Log entry with per-platform results
 */
export async function syndicatePost(lane, slug, options = {}) {
  // ── 1. Load post metadata ──
  const dataFile = path.join(ROOT, "static", "_data", `${lane}-posts.json`);
  if (!fs.existsSync(dataFile)) throw new Error(`Data file not found: ${dataFile}`);

  const posts = JSON.parse(fs.readFileSync(dataFile, "utf8"));
  const post  = posts.find(p => p.slug === slug);
  if (!post) throw new Error(`Post "${slug}" not found in ${dataFile}`);

  const postUrl = `https://vibrationofawesome.com${post.url}`;

  // ── 2. Extract plain-text body excerpt ──
  const htmlFile  = path.join(ROOT, "static", "blog", lane, "posts", `${slug}.html`);
  let bodyText    = post.excerpt || "";
  if (fs.existsSync(htmlFile)) {
    const raw      = fs.readFileSync(htmlFile, "utf8");
    const artMatch = raw.match(/<article[^>]*>([\s\S]*?)<\/article>/i);
    bodyText       = artMatch ? firstWords(stripHtml(artMatch[1]), 200) : firstWords(stripHtml(raw), 200);
  }

  console.log(`\nSyndicating: ${post.title}`);
  console.log(`URL: ${postUrl}\n`);

  // ── 3. Generate captions ──
  const anthropic = options.anthropic || new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
  console.log("Generating captions...");
  const captions = await generateCaptions({ ...post, lane }, anthropic);

  // ── 4. Select image ──
  const keyword = options.keyword || (post.tags || [])[0] || post.title;
  const image   = await selectImage(keyword);
  const imageUrl = image?.url || null;

  // ── 5. Extract hashtags from tumblr/instagram captions ──
  function extractHashtags(text) {
    return (text.match(/#\w+/g) || []).map(t => t.slice(1));
  }

  // ── 6. Post to each platform ──
  const results = {};

  async function attempt(platform, fn) {
    try {
      const r = await fn();
      console.log(`  ✓ ${platform}${r.postUrl ? ` → ${r.postUrl}` : ""}`);
      results[platform] = { success: true, postId: r.postId || null, postUrl: r.postUrl || null, error: null };
    } catch (err) {
      console.error(`  ✗ ${platform}: ${err.message}`);
      results[platform] = { success: false, postId: null, postUrl: null, error: err.message };
    }
  }

  // Bluesky
  await attempt("bluesky", () =>
    postToBluesky(captions.bluesky, postUrl, post.title, post.excerpt));

  // Mastodon
  await attempt("mastodon", () =>
    postToMastodon(captions.mastodon));

  // Facebook VOA
  if (process.env.META_PAGE_ID_VOA && process.env.META_PAGE_TOKEN_VOA) {
    await attempt("facebook_voa", () =>
      postToFacebookPage(process.env.META_PAGE_ID_VOA, process.env.META_PAGE_TOKEN_VOA, captions.facebook, postUrl));
  } else {
    console.warn("  — facebook_voa: META_PAGE_ID_VOA or META_PAGE_TOKEN_VOA not set");
    results.facebook_voa = { success: false, postId: null, postUrl: null, error: "env vars not set" };
  }

  // Facebook EarthStar
  if (process.env.META_PAGE_ID_EARTHSTAR && process.env.META_PAGE_TOKEN_EARTHSTAR) {
    await attempt("facebook_earthstar", () =>
      postToFacebookPage(process.env.META_PAGE_ID_EARTHSTAR, process.env.META_PAGE_TOKEN_EARTHSTAR, captions.facebook, postUrl));
  } else {
    console.warn("  — facebook_earthstar: META_PAGE_ID_EARTHSTAR or META_PAGE_TOKEN_EARTHSTAR not set");
    results.facebook_earthstar = { success: false, postId: null, postUrl: null, error: "env vars not set" };
  }

  // Pinterest
  await attempt("pinterest", () =>
    postToPinterest(captions.pinterest, post.title, postUrl, imageUrl));

  // Dev.to
  await attempt("devto", () =>
    postToDevTo(post.title, captions.devto, postUrl, post.tags));

  // Hashnode
  await attempt("hashnode", () =>
    postToHashnode(post.title, captions.hashnode, postUrl, post.tags, imageUrl));

  // Tumblr
  await attempt("tumblr", () =>
    postToTumblr(captions.tumblr, extractHashtags(captions.tumblr)));

  // Instagram via Publer
  await attempt("instagram", () =>
    postViaPubler("instagram", captions.instagram, imageUrl));

  // Threads via Publer
  await attempt("threads", () =>
    postViaPubler("threads", captions.threads, null));

  // ── 7. Build log entry ──
  const entry = {
    id:          String(Date.now()),
    timestamp:   new Date().toISOString(),
    lane,
    postSlug:    slug,
    postTitle:   post.title,
    postUrl,
    imageUrl,
    imageSource: image?.source || null,
    captions,
    platforms:   results,
  };

  // ── 8. Write log + dashboard config ──
  const log = loadLog();
  saveLog(log, entry);
  writeDashboardConfig();

  // ── 9. Summary ──
  const succeeded = Object.values(results).filter(r => r.success).length;
  const total     = Object.keys(results).length;
  console.log(`\nSyndication complete: ${succeeded}/${total} platforms succeeded.`);
  console.log(`Log saved → static/_data/syndication-log.json\n`);

  return entry;
}

// ── CLI entry point ───────────────────────────────────────────────────────────

const isCli = process.argv[1] && path.resolve(process.argv[1]) === path.resolve(__filename);
if (isCli) {
  if (!process.env.ANTHROPIC_API_KEY) {
    console.error("Error: ANTHROPIC_API_KEY not set."); process.exit(1);
  }

  const argv = minimist(process.argv.slice(2), {
    string:  ["lane", "slug", "keyword"],
    alias:   { l: "lane", s: "slug", k: "keyword" },
  });

  if (!argv.lane || !["matt", "boombot"].includes(argv.lane)) {
    console.error('Error: --lane must be "matt" or "boombot"'); process.exit(1);
  }
  if (!argv.slug) {
    console.error("Error: --slug is required"); process.exit(1);
  }

  try {
    await syndicatePost(argv.lane, argv.slug, { keyword: argv.keyword });
  } catch (err) {
    console.error("Fatal:", err.message);
    process.exit(1);
  }
}
