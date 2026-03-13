#!/usr/bin/env node
/**
 * get-page-tokens.js
 * Fetches long-lived Facebook Page Access Tokens via OAuth and writes them to .env
 * Usage: node scripts/get-page-tokens.js
 */

require('dotenv').config();
const express = require('express');
const open = (...args) => import('open').then(m => m.default(...args));
const https = require('https');
const fs = require('fs');
const path = require('path');

const APP_ID = process.env.META_APP_ID;
const APP_SECRET = process.env.META_APP_SECRET;
const PORT = 3000;
const REDIRECT_URI = `http://localhost:${PORT}/callback`;
const GRAPH_VERSION = 'v19.0';

const SCOPES = [
  'pages_show_list',
  'pages_manage_posts',
  'pages_read_engagement',
  'instagram_basic',
  'instagram_content_publish',
  'threads_basic',
  'threads_content_publish',
].join(',');

if (!APP_ID || !APP_SECRET) {
  console.error('\n❌  META_APP_ID or META_APP_SECRET not found in .env');
  console.error('    Add them and re-run.\n');
  process.exit(1);
}

// ─── Tiny fetch wrapper using built-in https ─────────────────────────────────
function httpsGet(url) {
  return new Promise((resolve, reject) => {
    https.get(url, (res) => {
      let data = '';
      res.on('data', (chunk) => (data += chunk));
      res.on('end', () => {
        try {
          resolve(JSON.parse(data));
        } catch {
          reject(new Error(`Non-JSON response: ${data}`));
        }
      });
    }).on('error', reject);
  });
}

// ─── Update (or append) a key=value line in .env ─────────────────────────────
function upsertEnv(envPath, key, value) {
  let content = fs.existsSync(envPath) ? fs.readFileSync(envPath, 'utf8') : '';
  const regex = new RegExp(`^${key}=.*$`, 'm');
  const line = `${key}=${value}`;
  if (regex.test(content)) {
    content = content.replace(regex, line);
  } else {
    content = content.trimEnd() + '\n' + line + '\n';
  }
  fs.writeFileSync(envPath, content, 'utf8');
}

// ─── Main ─────────────────────────────────────────────────────────────────────
async function main() {
  const app = express();
  let server;

  const authUrl =
    `https://www.facebook.com/${GRAPH_VERSION}/dialog/oauth` +
    `?client_id=${APP_ID}` +
    `&redirect_uri=${encodeURIComponent(REDIRECT_URI)}` +
    `&scope=${encodeURIComponent(SCOPES)}` +
    `&response_type=code`;

  app.get('/callback', async (req, res) => {
    const { code, error, error_description } = req.query;

    if (error) {
      res.send(`<h2>OAuth Error</h2><pre>${error}: ${error_description}</pre>`);
      server.close();
      process.exit(1);
    }

    if (!code) {
      res.send('<h2>No code received.</h2>');
      server.close();
      process.exit(1);
    }

    res.send(
      '<h2>✅ Auth code received! You can close this tab.</h2>' +
      '<p>Check your terminal for the tokens.</p>'
    );

    try {
      // 1. Exchange code → short-lived user token
      console.log('\n🔄  Exchanging auth code for short-lived user token…');
      const tokenUrl =
        `https://graph.facebook.com/${GRAPH_VERSION}/oauth/access_token` +
        `?client_id=${APP_ID}` +
        `&redirect_uri=${encodeURIComponent(REDIRECT_URI)}` +
        `&client_secret=${APP_SECRET}` +
        `&code=${code}`;

      const tokenData = await httpsGet(tokenUrl);
      if (tokenData.error) throw new Error(JSON.stringify(tokenData.error));
      const shortLivedToken = tokenData.access_token;
      console.log('✅  Short-lived user token obtained.');

      // 2. Exchange → long-lived user token (60-day)
      console.log('🔄  Exchanging for long-lived user token (60 days)…');
      const longTokenUrl =
        `https://graph.facebook.com/${GRAPH_VERSION}/oauth/access_token` +
        `?grant_type=fb_exchange_token` +
        `&client_id=${APP_ID}` +
        `&client_secret=${APP_SECRET}` +
        `&fb_exchange_token=${shortLivedToken}`;

      const longTokenData = await httpsGet(longTokenUrl);
      if (longTokenData.error) throw new Error(JSON.stringify(longTokenData.error));
      const longLivedUserToken = longTokenData.access_token;
      const expiresIn = longTokenData.expires_in;
      console.log(`✅  Long-lived user token obtained (expires in ${Math.round(expiresIn / 86400)} days).`);

      // 3. Fetch all pages
      console.log('🔄  Fetching pages via /me/accounts…');
      const accountsUrl =
        `https://graph.facebook.com/${GRAPH_VERSION}/me/accounts` +
        `?access_token=${longLivedUserToken}` +
        `&fields=id,name,access_token,category`;

      const accountsData = await httpsGet(accountsUrl);
      if (accountsData.error) throw new Error(JSON.stringify(accountsData.error));

      const pages = accountsData.data || [];

      // ─── Print results ────────────────────────────────────────────────────
      console.log('\n' + '═'.repeat(60));
      console.log('  LONG-LIVED USER TOKEN (60 days)');
      console.log('═'.repeat(60));
      console.log(`  ${longLivedUserToken}`);

      console.log('\n' + '═'.repeat(60));
      console.log(`  PAGES FOUND: ${pages.length}`);
      console.log('═'.repeat(60));

      if (pages.length === 0) {
        console.log('  ⚠️   No pages found. Make sure you manage at least one Facebook Page.');
      }

      pages.forEach((page, i) => {
        console.log(`\n  [${i + 1}] ${page.name}`);
        console.log(`      Category : ${page.category}`);
        console.log(`      Page ID  : ${page.id}`);
        console.log(`      Token    : ${page.access_token}`);
      });

      console.log('\n' + '═'.repeat(60));

      // ─── Write to .env ────────────────────────────────────────────────────
      const envPath = path.resolve(__dirname, '..', '.env');
      console.log(`\n📝  Writing to ${envPath}…`);

      upsertEnv(envPath, 'META_USER_ACCESS_TOKEN', longLivedUserToken);

      if (pages.length > 0) {
        const primary = pages[0];
        upsertEnv(envPath, 'FACEBOOK_PAGE_ID', primary.id);
        upsertEnv(envPath, 'FACEBOOK_ACCESS_TOKEN', primary.access_token);
        console.log(`✅  Wrote primary page "${primary.name}" (ID: ${primary.id}) to .env`);

        if (pages.length > 1) {
          pages.slice(1).forEach((page) => {
            const slug = page.name.toUpperCase().replace(/[^A-Z0-9]/g, '_');
            upsertEnv(envPath, `FACEBOOK_PAGE_ID_${slug}`, page.id);
            upsertEnv(envPath, `FACEBOOK_ACCESS_TOKEN_${slug}`, page.access_token);
            console.log(`✅  Also wrote page "${page.name}" as FACEBOOK_PAGE_ID_${slug}`);
          });
        }
      }

      console.log('\n🎉  Done! Your .env has been updated.\n');
    } catch (err) {
      console.error('\n❌  Error:', err.message);
    } finally {
      server.close();
    }
  });

  server = app.listen(PORT, () => {
    console.log('\n' + '═'.repeat(60));
    console.log('  Facebook Page Token Fetcher');
    console.log('═'.repeat(60));
    console.log(`\n  App ID      : ${APP_ID}`);
    console.log(`  Permissions : ${SCOPES.split(',').join(', ')}`);
    console.log(`\n  🌐  Opening browser for Facebook login…`);
    console.log(`      (If it doesn't open, visit the URL below)\n`);
    console.log(`  ${authUrl}\n`);
    open(authUrl);
  });
}

main().catch((err) => {
  console.error('Fatal:', err);
  process.exit(1);
});
