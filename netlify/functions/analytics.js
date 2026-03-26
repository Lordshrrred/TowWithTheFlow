/*
  TWTF Analytics Netlify Function
  Endpoint: /.netlify/functions/analytics?metric=overview|toppages|sources|realtime|geo|devices

  REQUIRED NETLIFY ENVIRONMENT VARIABLES:

  GA_CREDENTIALS_JSON — full service account JSON as single-line string
    (minify the downloaded JSON to one line, paste as env var value)

  GA_PROPERTY_ID — TWTF GA4 property ID
    Property ID: 530033133
    (GA4 → Admin → Property Settings for towwiththeflow.com)

  Service account email:
    towwiththeflow@towwiththeflowroadside.iam.gserviceaccount.com
    Add as Viewer in GA4 → Admin → Account Access Management

  DASHBOARD_PASSWORD — your dashboard password

  All vars set in Netlify dashboard under:
  Site settings → Environment variables

  Setup steps:
  1. console.cloud.google.com → enable "Google Analytics Data API"
  2. IAM & Admin → Service Accounts → find or create service account → download JSON key
  3. GA4 → Admin → Account Access Management → add service account email as Viewer
  4. Minify the JSON key to one line and paste as GA_CREDENTIALS_JSON
  5. Set GA_PROPERTY_ID = 530033133
  6. Redeploy
*/

import { GoogleAuth } from 'google-auth-library';

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
  'Content-Type': 'application/json',
};

const GA4_BASE = 'https://analyticsdata.googleapis.com/v1beta';

// ── AUTH ──────────────────────────────────────────────────────────
async function getAccessToken() {
  const credsJson = process.env.GA_CREDENTIALS_JSON;
  if (!credsJson) throw new Error('GA_CREDENTIALS_JSON not set');
  const creds = JSON.parse(credsJson);
  const auth = new GoogleAuth({
    credentials: creds,
    scopes: ['https://www.googleapis.com/auth/analytics.readonly'],
  });
  const client = await auth.getClient();
  const token = await client.getAccessToken();
  return token.token;
}

// ── GA4 REPORTS ───────────────────────────────────────────────────
async function runReport(propertyId, token, body) {
  const res = await fetch(`${GA4_BASE}/properties/${propertyId}:runReport`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`GA4 runReport ${res.status}: ${await res.text()}`);
  return res.json();
}

async function runRealtimeReport(propertyId, token, body) {
  const res = await fetch(`${GA4_BASE}/properties/${propertyId}:runRealtimeReport`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`GA4 realtime ${res.status}: ${await res.text()}`);
  return res.json();
}

function rows(data) {
  return (data.rows || []).map(row => ({
    dims: (row.dimensionValues || []).map(d => d.value),
    mets: (row.metricValues  || []).map(m => m.value),
  }));
}

// ── OVERVIEW ──────────────────────────────────────────────────────
async function getOverview(propertyId, token) {
  const [summary, daily] = await Promise.all([
    runReport(propertyId, token, {
      dateRanges: [{ startDate: '30daysAgo', endDate: 'today' }],
      metrics: [
        { name: 'screenPageViews' },
        { name: 'sessions' },
        { name: 'averageSessionDuration' },
        { name: 'bounceRate' },
        { name: 'newUsers' },
        { name: 'totalUsers' },
      ],
    }),
    runReport(propertyId, token, {
      dateRanges: [{ startDate: '30daysAgo', endDate: 'today' }],
      dimensions: [{ name: 'date' }],
      metrics: [{ name: 'screenPageViews' }],
      orderBys: [{ dimension: { dimensionName: 'date' } }],
    }),
  ]);

  const met = (summary.rows?.[0]?.metricValues || []).map(m => m.value);
  const totalUsers  = parseInt(met[5] || 0);
  const newUsers    = parseInt(met[4] || 0);

  return {
    pageviews:      parseInt(met[0] || 0),
    sessions:       parseInt(met[1] || 0),
    avgSessionDur:  Math.round(parseFloat(met[2] || 0)),   // seconds — matches VOA field name
    bounceRate:     parseFloat(met[3] || 0),               // 0–1 fraction — matches VOA
    newUsers,
    returningUsers: totalUsers - newUsers,
    // "daily" array with YYYYMMDD date and pageviews — matches VOA field names
    daily: rows(daily).map(r => ({ date: r.dims[0], pageviews: parseInt(r.mets[0]) })),
  };
}

// ── TOP PAGES ─────────────────────────────────────────────────────
async function getTopPages(propertyId, token) {
  const data = await runReport(propertyId, token, {
    dateRanges: [{ startDate: '30daysAgo', endDate: 'today' }],
    dimensions: [{ name: 'pagePath' }, { name: 'pageTitle' }],
    metrics: [
      { name: 'screenPageViews' },
      { name: 'averageSessionDuration' },
      { name: 'bounceRate' },
      { name: 'sessions' },
    ],
    orderBys: [{ metric: { metricName: 'screenPageViews' }, desc: true }],
    limit: 20,
  });

  return rows(data).map((r, i) => ({
    rank:      i + 1,
    path:      r.dims[0],
    title:     r.dims[1],
    pageviews: parseInt(r.mets[0]),
    avgDur:    Math.round(parseFloat(r.mets[1])),
    bounceRate: Math.round(parseFloat(r.mets[2]) * 1000) / 10,
    sessions:  parseInt(r.mets[3]),
  }));
}

// ── SOURCES ───────────────────────────────────────────────────────
async function getSources(propertyId, token) {
  const data = await runReport(propertyId, token, {
    dateRanges: [{ startDate: '30daysAgo', endDate: 'today' }],
    dimensions: [{ name: 'sessionDefaultChannelGrouping' }],
    metrics: [{ name: 'sessions' }],
    orderBys: [{ metric: { metricName: 'sessions' }, desc: true }],
  });

  const total = rows(data).reduce((s, r) => s + parseInt(r.mets[0]), 0);
  return rows(data).map(r => ({
    channel:  r.dims[0],
    sessions: parseInt(r.mets[0]),
    pct:      total > 0 ? Math.round((parseInt(r.mets[0]) / total) * 1000) / 10 : 0,
  }));
}

// ── REALTIME ──────────────────────────────────────────────────────
async function getRealtime(propertyId, token) {
  const [active, pages, countries] = await Promise.all([
    runRealtimeReport(propertyId, token, {
      metrics: [{ name: 'activeUsers' }],
    }),
    runRealtimeReport(propertyId, token, {
      dimensions: [{ name: 'pagePath' }],
      metrics: [{ name: 'activeUsers' }],
      orderBys: [{ metric: { metricName: 'activeUsers' }, desc: true }],
      limit: 10,
    }),
    runRealtimeReport(propertyId, token, {
      dimensions: [{ name: 'country' }],
      metrics: [{ name: 'activeUsers' }],
      orderBys: [{ metric: { metricName: 'activeUsers' }, desc: true }],
      limit: 10,
    }),
  ]);

  return {
    activeUsers: parseInt(active.rows?.[0]?.metricValues?.[0]?.value || 0),
    // "pages" array with { page, users } — matches VOA field names
    pages: rows(pages).map(r => ({
      page:  r.dims[0],
      users: parseInt(r.mets[0]),
    })),
    // "countries" array with { country, users } — matches VOA field names
    countries: rows(countries).map(r => ({
      country: r.dims[0],
      users:   parseInt(r.mets[0]),
    })),
  };
}

// ── GEO ───────────────────────────────────────────────────────────
async function getGeo(propertyId, token) {
  const [countries, cities] = await Promise.all([
    runReport(propertyId, token, {
      dateRanges: [{ startDate: '30daysAgo', endDate: 'today' }],
      dimensions: [{ name: 'country' }],
      metrics: [{ name: 'sessions' }],
      orderBys: [{ metric: { metricName: 'sessions' }, desc: true }],
      limit: 20,
    }),
    runReport(propertyId, token, {
      dateRanges: [{ startDate: '30daysAgo', endDate: 'today' }],
      dimensions: [{ name: 'city' }],
      metrics: [{ name: 'sessions' }],
      orderBys: [{ metric: { metricName: 'sessions' }, desc: true }],
      limit: 10,
    }),
  ]);

  return {
    countries: rows(countries).map(r => ({ country: r.dims[0], sessions: parseInt(r.mets[0]) })),
    cities:    rows(cities).map(r    => ({ city: r.dims[0],    sessions: parseInt(r.mets[0]) })),
  };
}

// ── DEVICES ───────────────────────────────────────────────────────
async function getDevices(propertyId, token) {
  const [deviceCats, browsers, os] = await Promise.all([
    runReport(propertyId, token, {
      dateRanges: [{ startDate: '30daysAgo', endDate: 'today' }],
      dimensions: [{ name: 'deviceCategory' }],
      metrics: [{ name: 'sessions' }],
      orderBys: [{ metric: { metricName: 'sessions' }, desc: true }],
    }),
    runReport(propertyId, token, {
      dateRanges: [{ startDate: '30daysAgo', endDate: 'today' }],
      dimensions: [{ name: 'browser' }],
      metrics: [{ name: 'sessions' }],
      orderBys: [{ metric: { metricName: 'sessions' }, desc: true }],
      limit: 5,
    }),
    runReport(propertyId, token, {
      dateRanges: [{ startDate: '30daysAgo', endDate: 'today' }],
      dimensions: [{ name: 'operatingSystem' }],
      metrics: [{ name: 'sessions' }],
      orderBys: [{ metric: { metricName: 'sessions' }, desc: true }],
      limit: 5,
    }),
  ]);

  return {
    // "devices" array with { device, sessions } — matches VOA field names
    devices:  rows(deviceCats).map(r => ({ device:  r.dims[0], sessions: parseInt(r.mets[0]) })),
    browsers: rows(browsers).map(r   => ({ browser: r.dims[0], sessions: parseInt(r.mets[0]) })),
    // "os" array with { os, sessions } — matches VOA field names
    os:       rows(os).map(r         => ({ os:      r.dims[0], sessions: parseInt(r.mets[0]) })),
  };
}

// ── HANDLER ───────────────────────────────────────────────────────
export const handler = async (event) => {
  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 200, headers: CORS_HEADERS, body: '' };
  }
  if (event.httpMethod !== 'GET') {
    return { statusCode: 405, headers: CORS_HEADERS, body: JSON.stringify({ error: 'Method not allowed' }) };
  }

  const propertyId = process.env.GA_PROPERTY_ID;
  if (!propertyId) {
    return { statusCode: 500, headers: CORS_HEADERS, body: JSON.stringify({ error: 'GA_PROPERTY_ID not configured' }) };
  }

  const metric = event.queryStringParameters?.metric || 'overview';

  try {
    const token = await getAccessToken();
    let data;
    switch (metric) {
      case 'overview':  data = await getOverview(propertyId, token);  break;
      case 'toppages':  data = await getTopPages(propertyId, token);  break;
      case 'sources':   data = await getSources(propertyId, token);   break;
      case 'realtime':  data = await getRealtime(propertyId, token);  break;
      case 'geo':       data = await getGeo(propertyId, token);       break;
      case 'devices':   data = await getDevices(propertyId, token);   break;
      default:
        return { statusCode: 400, headers: CORS_HEADERS, body: JSON.stringify({ error: `Unknown metric: ${metric}` }) };
    }
    return {
      statusCode: 200,
      headers: CORS_HEADERS,
      body: JSON.stringify(data),
    };
  } catch (err) {
    console.error('analytics error:', err.message);
    return {
      statusCode: 500,
      headers: CORS_HEADERS,
      body: JSON.stringify({ error: err.message }),
    };
  }
};
