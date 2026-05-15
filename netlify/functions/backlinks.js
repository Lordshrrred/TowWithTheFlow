const TWTF_BASE = 'https://towwiththeflow.com';
const FEEDER_OWNER = 'Lordshrrred';
const FEEDER_REPO = 'TWTF_Feeder';
const FEEDER_SUFFIXES = ['-tips', '-advice', '-help', '-guide'];
const RAW_BASE = `https://raw.githubusercontent.com/${FEEDER_OWNER}/${FEEDER_REPO}/main/content/posts`;
const BLOGGER_BASE = process.env.BLOGGER_BASE_URL || 'https://towingandflowingroadsidedenver.blogspot.com';
const TUMBLR_BLOG = 'towwiththeflow';
const ALLOWED_PLATFORMS = new Set(['dev', 'tumblr', 'blog', 'wordpress', 'feeder']);

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Content-Type': 'application/json',
};

function json(statusCode, body) {
  return {
    statusCode,
    headers: CORS_HEADERS,
    body: JSON.stringify(body),
  };
}

function cleanSlug(slug) {
  const out = String(slug || '').trim().toLowerCase();
  return /^[a-z0-9][a-z0-9-]{2,120}$/.test(out) ? out : '';
}

function expectedUrls(slug) {
  return [`${TWTF_BASE}/${slug}/`.toLowerCase(), `${TWTF_BASE}/${slug}`.toLowerCase()];
}

function hrefLinks(html) {
  const out = [];
  const rx = /href\s*=\s*["'](https?:\/\/towwiththeflow\.com[^"']*)["']/gi;
  for (const match of String(html || '').matchAll(rx)) out.push(match[1]);
  return out;
}

function matchesSlug(link, slug) {
  const [withSlash, withoutSlash] = expectedUrls(slug);
  const normalized = String(link || '').trim().toLowerCase();
  return (
    normalized === withSlash ||
    normalized.startsWith(`${withSlash}?`) ||
    normalized === withoutSlash ||
    normalized.startsWith(`${withoutSlash}?`)
  );
}

function firstTowAnchor(html) {
  const match = String(html || '').match(/href\s*=\s*["']https?:\/\/towwiththeflow\.com[^"']*["'][^>]*>([^<]+)</i);
  return match ? match[1].trim() : '';
}

function lastPathSegment(url) {
  try {
    const parts = new URL(url).pathname.split('/').filter(Boolean);
    return parts.at(-1) || '';
  } catch {
    return '';
  }
}

async function fetchText(url, timeoutMs = 20000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      signal: controller.signal,
      headers: { 'User-Agent': 'TWTF-Backlink-Checker/1.0' },
    });
    const text = await res.text();
    return { ok: res.ok, status: res.status, text, url: res.url || url };
  } finally {
    clearTimeout(timer);
  }
}

async function fetchJson(url, timeoutMs = 20000) {
  const res = await fetchText(url, timeoutMs);
  if (!res.ok) return { ...res, data: null };
  return { ...res, data: JSON.parse(res.text) };
}

async function verifyHtml(slug, url) {
  if (!url) return { verified: null, reason: 'no_url', url: '' };
  try {
    const res = await fetchText(url, 25000);
    if (!res.ok) return { verified: false, reason: `http_${res.status}`, url };
    const exact = hrefLinks(res.text).find(link => matchesSlug(link, slug));
    return {
      verified: Boolean(exact),
      reason: exact ? 'ok' : 'slug_mismatch',
      anchor: firstTowAnchor(res.text),
      matched: exact || '',
      url: res.url || url,
    };
  } catch (error) {
    return { verified: null, reason: `error:${error.name || 'FetchError'}`, url };
  }
}

async function verifyDev(slug, url) {
  if (!url) return { verified: null, reason: 'no_url', url: '' };
  try {
    const parts = new URL(url).pathname.split('/').filter(Boolean);
    if (parts.length < 2) return { verified: null, reason: 'bad_url', url };
    const res = await fetchJson(`https://dev.to/api/articles/${parts[0]}/${parts[1]}`, 20000);
    if (!res.ok) return { verified: false, reason: `http_${res.status}`, url };
    const [withSlash, withoutSlash] = expectedUrls(slug);
    const canonical = String(res.data?.canonical_url || '').trim().toLowerCase();
    const body = String(res.data?.body_html || '');
    const bodyLinks = hrefLinks(body);
    const exact = bodyLinks.find(link => matchesSlug(link, slug));
    const canonicalOk = canonical === withSlash || canonical === withoutSlash;
    return {
      verified: canonicalOk || Boolean(exact),
      reason: canonicalOk || exact ? 'ok' : 'slug_mismatch',
      canonical: canonicalOk,
      anchor: firstTowAnchor(body),
      matched: exact || (canonicalOk ? canonical : ''),
      url,
    };
  } catch (error) {
    return { verified: null, reason: `error:${error.name || 'FetchError'}`, url };
  }
}

async function verifyFeeder(slug, url) {
  const candidates = [];
  const pathSlug = lastPathSegment(url);
  if (pathSlug) candidates.push(pathSlug);
  candidates.push(slug, ...FEEDER_SUFFIXES.map(suffix => `${slug}${suffix}`), `${slug}-guide`);

  const seen = new Set();
  const [withSlash, withoutSlash] = expectedUrls(slug);
  for (const candidate of candidates) {
    if (!candidate || seen.has(candidate)) continue;
    seen.add(candidate);
    try {
      const res = await fetchText(`${RAW_BASE}/${candidate}.md`, 20000);
      if (!res.ok) continue;
      const body = res.text.toLowerCase();
      if (body.includes(withSlash) || body.includes(withoutSlash)) {
        const anchor = (res.text.match(/\[([^\]]+)\]\(https?:\/\/towwiththeflow\.com[^)]*\)/i) || [])[1] || 'canonical link';
        return {
          verified: true,
          reason: 'ok',
          anchor,
          matched: withSlash,
          url: `https://${FEEDER_OWNER.toLowerCase()}.github.io/${FEEDER_REPO}/${candidate}/`,
        };
      }
    } catch {}
  }

  return { verified: false, reason: 'slug_mismatch', url: url || '' };
}

async function recoverDev(slug) {
  try {
    const [withSlash, withoutSlash] = expectedUrls(slug);
    const res = await fetchJson('https://dev.to/api/articles?username=towwiththeflowyoo&per_page=100', 20000);
    if (!res.ok || !Array.isArray(res.data)) return null;
    const article = res.data.find(row => {
      const canonical = String(row?.canonical_url || '').trim().toLowerCase();
      return canonical === withSlash || canonical === withoutSlash;
    });
    if (!article?.url) return null;
    const verified = await verifyDev(slug, article.url);
    return verified.verified ? { ...verified, recovered_live: true } : null;
  } catch {
    return null;
  }
}

async function recoverTumblr(slug) {
  try {
    const res = await fetchText(`https://${TUMBLR_BLOG}.tumblr.com/api/read/json?num=120`, 20000);
    if (!res.ok) return null;
    const match = res.text.match(/^var tumblr_api_read = (.*);\s*$/s);
    if (!match) return null;
    const data = JSON.parse(match[1]);
    const post = (data.posts || []).find(row => hrefLinks(row['regular-body'] || '').some(link => matchesSlug(link, slug)));
    if (!post?.id) return null;
    return {
      verified: true,
      reason: 'ok',
      matched: `${TWTF_BASE}/${slug}/`,
      url: `https://www.tumblr.com/${TUMBLR_BLOG}/${post.id}/${slug}`,
      recovered_live: true,
    };
  } catch {
    return null;
  }
}

async function recoverFromSitemap(slug, sitemapUrl, hostMustContain = '') {
  try {
    const res = await fetchText(sitemapUrl, 20000);
    if (!res.ok) return null;
    const locs = [...res.text.matchAll(/<loc>(https?:\/\/[^<]+)<\/loc>/gi)].map(match => match[1]);
    const core = slug.split('-').filter(word => !['what', 'to', 'do', 'the', 'a', 'an', 'in', 'for', 'and', 'or', 'with'].includes(word));
    const scored = locs
      .filter(candidate => !hostMustContain || candidate.toLowerCase().includes(hostMustContain.toLowerCase()))
      .map(candidate => {
        const lower = candidate.toLowerCase();
        let score = lower.includes(slug) ? 8 : 0;
        for (const word of core.slice(0, 8)) if (lower.includes(word)) score += 1;
        return { candidate, score };
      })
      .filter(row => row.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, 10);

    for (const { candidate } of scored) {
      const checked = await verifyHtml(slug, candidate);
      if (checked.verified) return { ...checked, recovered_live: true };
    }
  } catch {}
  return null;
}

async function recoverBlogger(slug) {
  return recoverFromSitemap(slug, `${BLOGGER_BASE}/sitemap.xml`, new URL(BLOGGER_BASE).hostname);
}

async function recoverWordPress(slug) {
  const tag = await verifyHtml(slug, `https://towwiththeflowyo.wordpress.com/tag/${slug}/`);
  if (tag.verified) return { ...tag, recovered_live: true };
  return recoverFromSitemap(slug, 'https://towwiththeflowyo.wordpress.com/sitemap.xml', 'towwiththeflowyo.wordpress.com');
}

async function checkOne(input) {
  const slug = cleanSlug(input?.slug);
  const platform = String(input?.platform || '').trim().toLowerCase();
  const url = String(input?.url || '').trim();

  if (!slug) return { verified: null, reason: 'bad_slug', url };
  if (!ALLOWED_PLATFORMS.has(platform)) return { verified: null, reason: 'bad_platform', url };

  let result;
  if (platform === 'dev') result = await verifyDev(slug, url);
  if (platform === 'tumblr') result = await verifyHtml(slug, url);
  if (platform === 'blog') result = await verifyHtml(slug, url);
  if (platform === 'wordpress') result = await verifyHtml(slug, url);
  if (platform === 'feeder') result = await verifyFeeder(slug, url);

  if (result?.verified === true) return result;

  let recovered = null;
  if (platform === 'dev') recovered = await recoverDev(slug);
  if (platform === 'tumblr') recovered = await recoverTumblr(slug);
  if (platform === 'blog') recovered = await recoverBlogger(slug);
  if (platform === 'wordpress') recovered = await recoverWordPress(slug);
  if (platform === 'feeder') {
    const feeder = await verifyFeeder(slug, '');
    recovered = feeder.verified ? { ...feeder, recovered_live: true } : null;
  }

  return recovered || result || { verified: null, reason: 'not_checked', url };
}

export const handler = async event => {
  if (event.httpMethod === 'OPTIONS') return { statusCode: 200, headers: CORS_HEADERS, body: '' };
  if (!['GET', 'POST'].includes(event.httpMethod)) {
    return json(405, { error: 'Method not allowed' });
  }

  try {
    const checks = [];
    if (event.httpMethod === 'POST') {
      const body = event.body ? JSON.parse(event.body) : {};
      if (Array.isArray(body.checks)) checks.push(...body.checks.slice(0, 50));
      else checks.push(body);
    } else {
      checks.push(event.queryStringParameters || {});
    }

    const validChecks = checks
      .map(check => ({
        check,
        slug: cleanSlug(check?.slug),
        platform: String(check?.platform || '').trim().toLowerCase(),
      }))
      .filter(row => row.slug && ALLOWED_PLATFORMS.has(row.platform));

    const checkedRows = await Promise.all(validChecks.map(async row => ({
      ...row,
      result: await checkOne(row.check),
    })));

    const results = {};
    for (const { slug, platform, result } of checkedRows) {
      results[slug] ||= {};
      results[slug][platform] = result;
    }

    return json(200, {
      ok: true,
      generated_at: new Date().toISOString(),
      checked: Object.values(results).reduce((sum, row) => sum + Object.keys(row).length, 0),
      slugs: results,
    });
  } catch (error) {
    console.error('backlink checker error:', error);
    return json(500, { ok: false, error: error.message || 'Backlink checker failed' });
  }
};
