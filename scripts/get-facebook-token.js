#!/usr/bin/env node
/**
 * get-facebook-token.js — Refresh Facebook long-lived user token + page tokens
 *
 * The Meta Graph API requires a USER access token to get long-lived page tokens.
 * Short-lived user tokens expire in ~1-2h; long-lived ones last 60 days.
 * Page tokens obtained from a long-lived user token never expire.
 *
 * Flow:
 *   1. Open browser to Facebook OAuth dialog
 *   2. User grants pages_manage_posts + pages_read_engagement permissions
 *   3. Callback received on localhost:9876
 *   4. Exchange code → short-lived user token
 *   5. Exchange short-lived → long-lived user token (60 days)
 *   6. Fetch all connected pages + their long-lived page tokens
 *   7. Print the env var lines to paste into .env
 *
 * Usage:
 *   node scripts/get-facebook-token.js
 *
 * Prerequisites: META_APP_ID and META_APP_SECRET must be set in .env
 */

import dotenv from "dotenv";
import http from "http";
import { exec } from "child_process";
import { fileURLToPath } from "url";
import path from "path";

dotenv.config({ override: true });

const __filename = fileURLToPath(import.meta.url);
const __dirname  = path.dirname(__filename);

const APP_ID     = process.env.META_APP_ID;
const APP_SECRET = process.env.META_APP_SECRET;
const PORT       = 9876;
const REDIRECT   = `http://localhost:${PORT}/callback`;

if (!APP_ID || !APP_SECRET) {
  console.error("Error: META_APP_ID and META_APP_SECRET must be set in .env");
  process.exit(1);
}

// Scopes needed to post to pages and read page info
const SCOPES = [
  "pages_manage_posts",
  "pages_read_engagement",
  "pages_show_list",
].join(",");

const authUrl =
  `https://www.facebook.com/dialog/oauth` +
  `?client_id=${APP_ID}` +
  `&redirect_uri=${encodeURIComponent(REDIRECT)}` +
  `&scope=${encodeURIComponent(SCOPES)}` +
  `&response_type=code`;

console.log("\n=== Facebook Token Refresh ===");
console.log("Opening browser for Facebook OAuth...");
console.log("If it doesn't open automatically, visit:\n");
console.log(authUrl + "\n");

// Open browser cross-platform
const openCmd =
  process.platform === "win32" ? `start "" "${authUrl}"` :
  process.platform === "darwin" ? `open "${authUrl}"` :
  `xdg-open "${authUrl}"`;
exec(openCmd);

// Local callback server
const server = http.createServer(async (req, res) => {
  const url    = new URL(req.url, `http://localhost:${PORT}`);
  const code   = url.searchParams.get("code");
  const errMsg = url.searchParams.get("error_description");

  if (errMsg) {
    res.end("OAuth error: " + errMsg + ". You can close this tab.");
    console.error("\nOAuth error:", errMsg);
    server.close();
    return;
  }

  if (!code) { res.end("No code received."); return; }

  res.end("Token received! Check your terminal. You can close this tab.");
  server.close();

  try {
    // Step 1: Exchange code → short-lived user token
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
    console.log("✓ Got short-lived user token");

    // Step 2: Exchange short-lived → long-lived user token (60 days)
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
    console.log("✓ Got long-lived user token (valid ~60 days)");

    // Step 3: Get all managed pages + their long-lived page tokens
    const pagesUrl =
      `https://graph.facebook.com/v19.0/me/accounts` +
      `?fields=id,name,access_token` +
      `&access_token=${encodeURIComponent(longToken)}`;

    const pagesResp = await fetch(pagesUrl);
    const pagesData = await pagesResp.json();
    if (pagesData.error) throw new Error(pagesData.error.message);

    const pages = pagesData.data || [];
    console.log(`✓ Found ${pages.length} connected page(s)\n`);

    // Print results
    console.log("═══════════════════════════════════════════════");
    console.log("  PASTE THESE INTO YOUR .env FILE:");
    console.log("═══════════════════════════════════════════════\n");
    console.log(`META_USER_TOKEN=${longToken}\n`);

    pages.forEach(p => {
      console.log(`# Page: ${p.name} (ID: ${p.id})`);
      console.log(`# META_PAGE_ID_???=${p.id}`);
      console.log(`# META_PAGE_TOKEN_???=${p.access_token}\n`);
    });

    if (pages.length === 0) {
      console.log("⚠️  No pages found. Make sure you granted pages_show_list permission");
      console.log("   and that your app is connected to at least one Facebook Page.\n");
    }

    console.log("═══════════════════════════════════════════════");
    console.log("Replace ??? with VOA, EARTHSTAR, RUZINDLA, etc.");
    console.log("Page tokens from long-lived user tokens never expire.");
    console.log("═══════════════════════════════════════════════\n");

  } catch (err) {
    console.error("Error:", err.message);
  }
});

server.listen(PORT, () => {
  console.log(`Waiting for OAuth callback on http://localhost:${PORT}/callback ...`);
});

server.on("error", err => {
  console.error("Server error:", err.message);
  if (err.code === "EADDRINUSE") {
    console.error(`Port ${PORT} is busy. Kill whatever is using it and retry.`);
  }
  process.exit(1);
});
