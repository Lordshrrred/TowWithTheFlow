#!/usr/bin/env node
/**
 * get-facebook-token.js
 * ─────────────────────────────────────────────────────────────────────────────
 * Runs a local Express server that completes a Facebook OAuth flow, exchanges
 * the auth code for a long-lived user token (~60 days), fetches all connected
 * page tokens, and writes the results directly back into .env.
 *
 * Tokens saved:
 *   META_USER_TOKEN              (long-lived user token, valid ~60 days)
 *   META_PAGE_TOKEN_VOA          (page token — matched by name/ID)
 *   META_PAGE_TOKEN_EARTHSTAR    (page token — matched by name/ID)
 *   META_PAGE_TOKEN_RUZINDLA     (page token — matched by name/ID)
 *   META_PAGE_ID_VOA             (page ID — saved if not already set)
 *   META_PAGE_ID_EARTHSTAR
 *   META_PAGE_ID_RUZINDLA
 *
 * Usage:
 *   node scripts/get-facebook-token.js
 *
 * Prerequisites:
 *   1. META_APP_ID and META_APP_SECRET must be set in .env
 *   2. Add http://localhost:3000/callback as a Valid OAuth Redirect URI in your
 *      Meta app:  https://developers.facebook.com/apps/ → your app →
 *      Facebook Login → Settings → Valid OAuth Redirect URIs
 */

import dotenv            from "dotenv";
import express           from "express";
import { exec }          from "child_process";
import { readFileSync, writeFileSync, existsSync } from "fs";
import path              from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname  = path.dirname(__filename);
const ROOT       = path.resolve(__dirname, "..");
const ENV_PATH   = path.join(ROOT, ".env");

dotenv.config({ path: ENV_PATH, override: true });

// ── Config ────────────────────────────────────────────────────────────────────
const APP_ID     = process.env.META_APP_ID;
const APP_SECRET = process.env.META_APP_SECRET;
const PORT       = 3000;
const REDIRECT   = `http://localhost:${PORT}/callback`;

const SCOPES = [
  "pages_show_list",
  "pages_manage_posts",
  "pages_read_engagement",
  "business_management",
].join(",");

// How to match page names → env key suffixes.
// Keys are lowercase substrings to search for in the page name.
const PAGE_MATCHERS = [
  { patterns: ["vibration", "voa"],                suffix: "VOA"       },
  { patterns: ["earthstar", "earth star", "earth"], suffix: "EARTHSTAR" },
  { patterns: ["ruzindla"],                         suffix: "RUZINDLA"  },
];

if (!APP_ID || !APP_SECRET) {
  console.error("✗  META_APP_ID and META_APP_SECRET must be set in .env");
  process.exit(1);
}

// ── .env writer ───────────────────────────────────────────────────────────────
/**
 * Read .env, upsert every key in `updates`, write back.
 * Preserves comments, blank lines, and ordering for unchanged keys.
 */
function upsertEnv(updates) {
  const existing = existsSync(ENV_PATH) ? readFileSync(ENV_PATH, "utf8") : "";
  const lines    = existing.split(/\r?\n/);
  const touched  = new Set();

  const updated = lines.map(line => {
    const m = line.match(/^([A-Z0-9_]+)\s*=/);
    if (m && updates[m[1]] !== undefined) {
      touched.add(m[1]);
      return `${m[1]}=${updates[m[1]]}`;
    }
    return line;
  });

  // Append any keys that weren't already in the file
  for (const [key, val] of Object.entries(updates)) {
    if (!touched.has(key)) {
      updated.push(`${key}=${val}`);
    }
  }

  writeFileSync(ENV_PATH, updated.join("\n"), "utf8");
}

// ── Match page → suffix ───────────────────────────────────────────────────────
function matchSuffix(pageName, pageId) {
  const lower = pageName.toLowerCase();
  for (const { patterns, suffix } of PAGE_MATCHERS) {
    if (patterns.some(p => lower.includes(p))) return suffix;
  }
  // Fall back to checking existing PAGE_IDs in env
  for (const { suffix } of PAGE_MATCHERS) {
    if (process.env[`META_PAGE_ID_${suffix}`] === String(pageId)) return suffix;
  }
  return null;
}

// ── OAuth URL ─────────────────────────────────────────────────────────────────
const authUrl =
  `https://www.facebook.com/dialog/oauth` +
  `?client_id=${APP_ID}` +
  `&redirect_uri=${encodeURIComponent(REDIRECT)}` +
  `&scope=${encodeURIComponent(SCOPES)}` +
  `&response_type=code`;

// ── Express app ───────────────────────────────────────────────────────────────
const app = express();

app.get("/", (_req, res) => {
  res.send(`
    <html><body style="font-family:sans-serif;padding:2rem">
      <h2>Facebook Token Refresh</h2>
      <p>Click the button below to authorize vibrationofawesome with Facebook.</p>
      <a href="${authUrl}" style="
        display:inline-block;background:#1877f2;color:#fff;
        padding:.75rem 1.5rem;border-radius:6px;text-decoration:none;font-weight:bold
      ">Connect with Facebook</a>
    </body></html>
  `);
});

app.get("/callback", async (req, res) => {
  const { code, error, error_description } = req.query;

  if (error) {
    res.send(`<html><body><h2>OAuth Error</h2><pre>${error}: ${error_description}</pre></body></html>`);
    console.error(`\n✗  OAuth error: ${error_description}`);
    server.close();
    return;
  }

  if (!code) {
    res.send("<html><body><p>No code in callback.</p></body></html>");
    return;
  }

  try {
    // ── Step 1: code → short-lived user token ──────────────────────────────
    const tokenUrl =
      `https://graph.facebook.com/v19.0/oauth/access_token` +
      `?client_id=${APP_ID}` +
      `&redirect_uri=${encodeURIComponent(REDIRECT)}` +
      `&client_secret=${APP_SECRET}` +
      `&code=${code}`;

    const tokenResp = await fetch(tokenUrl);
    const tokenData = await tokenResp.json();
    if (tokenData.error) throw new Error(tokenData.error.message);
    const shortToken = tokenData.access_token;
    console.log("  ✓  Short-lived user token received");

    // ── Step 2: short-lived → long-lived user token (~60 days) ────────────
    const llUrl =
      `https://graph.facebook.com/v19.0/oauth/access_token` +
      `?grant_type=fb_exchange_token` +
      `&client_id=${APP_ID}` +
      `&client_secret=${APP_SECRET}` +
      `&fb_exchange_token=${encodeURIComponent(shortToken)}`;

    const llResp = await fetch(llUrl);
    const llData = await llResp.json();
    if (llData.error) throw new Error(llData.error.message);
    const longToken = llData.access_token;
    console.log("  ✓  Long-lived user token received (~60 days)");

    // ── Step 3: /me/accounts → page tokens ────────────────────────────────
    const pagesUrl =
      `https://graph.facebook.com/v19.0/me/accounts` +
      `?fields=id,name,access_token&limit=50` +
      `&access_token=${encodeURIComponent(longToken)}`;

    const pagesResp = await fetch(pagesUrl);
    const pagesData = await pagesResp.json();
    if (pagesData.error) throw new Error(pagesData.error.message);
    const pages = pagesData.data || [];
    console.log(`  ✓  ${pages.length} page(s) found`);

    // ── Step 4: match pages → env keys ────────────────────────────────────
    const updates = { META_USER_TOKEN: longToken };
    const matched = [];
    const unmatched = [];

    for (const page of pages) {
      const suffix = matchSuffix(page.name, page.id);
      if (suffix) {
        updates[`META_PAGE_TOKEN_${suffix}`] = page.access_token;
        updates[`META_PAGE_ID_${suffix}`]    = page.id;
        matched.push({ suffix, name: page.name, id: page.id });
      } else {
        unmatched.push({ name: page.name, id: page.id });
      }
    }

    // ── Step 5: write to .env ─────────────────────────────────────────────
    upsertEnv(updates);

    // ── Terminal report ───────────────────────────────────────────────────
    console.log("\n╔══════════════════════════════════════════════════════════╗");
    console.log("  ✅  .env updated successfully");
    console.log("╚══════════════════════════════════════════════════════════╝\n");

    console.log("  META_USER_TOKEN          → saved  (valid ~60 days)");
    for (const { suffix, name, id } of matched) {
      console.log(`  META_PAGE_TOKEN_${suffix.padEnd(10)} → saved  (${name} / ${id})`);
      console.log(`  META_PAGE_ID_${suffix.padEnd(13)} → saved`);
    }

    if (unmatched.length) {
      console.log("\n  ⚠️  These pages were NOT matched to a known suffix:");
      for (const { name, id } of unmatched) {
        console.log(`     "${name}" (${id})`);
      }
      console.log("  Add a pattern for them in PAGE_MATCHERS at the top of this script,");
      console.log("  or manually copy the tokens from the log above into .env.\n");

      // Print raw tokens for unmatched pages so user can paste them manually
      for (const pg of pages) {
        if (unmatched.some(u => u.id === pg.id)) {
          console.log(`  # ${pg.name} (${pg.id})`);
          console.log(`  META_PAGE_TOKEN_???=${pg.access_token}\n`);
        }
      }
    }

    console.log("\n  Run `node scripts/syndicate.js` to retry Facebook posts.\n");

    // ── Browser response ──────────────────────────────────────────────────
    res.send(`
      <html><body style="font-family:sans-serif;padding:2rem;max-width:600px">
        <h2 style="color:#1a7f4b">✅ Tokens saved to .env</h2>
        <p>The following were updated:</p>
        <ul>
          <li><code>META_USER_TOKEN</code></li>
          ${matched.map(m => `
            <li><code>META_PAGE_TOKEN_${m.suffix}</code> — ${m.name}</li>
            <li><code>META_PAGE_ID_${m.suffix}</code> — ${m.id}</li>
          `).join("")}
        </ul>
        ${unmatched.length ? `
          <p style="color:#c00"><strong>⚠️ Unmatched pages:</strong>
          ${unmatched.map(u => `${u.name} (${u.id})`).join(", ")}</p>
          <p>Check your terminal for the raw tokens to paste manually.</p>
        ` : ""}
        <p>You can close this tab. Check your terminal for details.</p>
      </body></html>
    `);

  } catch (err) {
    console.error(`\n✗  Error: ${err.message}`);
    res.send(`<html><body><h2>Error</h2><pre>${err.message}</pre><p>Check terminal.</p></body></html>`);
  } finally {
    setTimeout(() => server.close(), 1500);
  }
});

// ── Launch ────────────────────────────────────────────────────────────────────
const server = app.listen(PORT, () => {
  const localUrl = `http://localhost:${PORT}`;
  console.log("\n╔══════════════════════════════════════════════════════════╗");
  console.log("  Facebook Token Refresh");
  console.log("╚══════════════════════════════════════════════════════════╝\n");
  console.log("  IMPORTANT — before proceeding, make sure this redirect URI");
  console.log("  is registered in your Meta app:");
  console.log(`    http://localhost:${PORT}/callback`);
  console.log("  → developers.facebook.com/apps → your app →");
  console.log("    Facebook Login → Settings → Valid OAuth Redirect URIs\n");
  console.log(`  Opening browser → ${localUrl}`);
  console.log("  Waiting for OAuth callback...\n");

  const openCmd =
    process.platform === "win32"  ? `start "" "${localUrl}"` :
    process.platform === "darwin" ? `open "${localUrl}"` :
    `xdg-open "${localUrl}"`;
  exec(openCmd);
});

server.on("error", err => {
  if (err.code === "EADDRINUSE") {
    console.error(`✗  Port ${PORT} is already in use. Stop whatever is running on it and retry.`);
  } else {
    console.error("✗  Server error:", err.message);
  }
  process.exit(1);
});
