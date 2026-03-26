/*
  TWTF Analytics Netlify Function
  Endpoint: /.netlify/functions/analytics?metric=overview|toppages|sources|realtime|geo|devices

  REQUIRED ENVIRONMENT VARIABLES — add to Netlify:

  GA_CREDENTIALS_JSON — service account JSON contents as a single-line string
    (copy the entire downloaded JSON, minify to one line, paste as env var value)

  GA_PROPERTY_ID — TWTF's GA4 property ID (numbers only, e.g. "123456789")
    Get it from: GA4 → Admin → Property Settings for towwiththeflow.com

  DASHBOARD_PASSWORD — password for the dashboard gate

  Setup steps:
  1. Go to console.cloud.google.com → select or create a project
  2. Enable the "Google Analytics Data API"
  3. IAM & Admin → Service Accounts → Create service account → download JSON key
  4. In GA4: Admin → Account Access Management → Add the service account email as Viewer
  5. Add all 3 vars to Netlify: Site Settings → Environment Variables
  6. Redeploy site
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

// ── GA4 REPORT ────────────────────────────────────────────────────
async function runReport(propertyId, token, body) {
  const res = await fetch(`${GA4_BASE}/properties/${propertyId}:runReport`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`GA4 runReport ${res.status}: ${err}`);
  }
  return res.json();
}

async function runRealtimeReport(propertyId, token, body) {
  const res = await fetch(`${GA4_BASE}/properties/${propertyId}:runRealtimeReport`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`GA4 runRealtimeReport ${res.status}: ${err}`);
  }
  return res.json();
}

// ── HELPER: extract rows ──────────────────────────────────────────
function rows(data) {
  return (data.rows || []).map(row => ({
    dims: (row.dimensionValues || []).map(d => d.value),
    mets: (row.metricValues || []).map(m => m.value),
  }));
}

// ── METRIC HANDLERS ───────────────────────────────────────────────

async function getOverview(propertyId, token) {
  // Summary metrics
  const summary = await runReport(propertyId, token, {
    dateRanges: [{ startDate: '30daysAgo', endDate: 'today' }],
    metrics: [
      { name: 'screenPageViews' },
      { name: 'sessions' },
      { name: 'averageSessionDuration' },
      { name: 'bounceRate' },
      { name: 'newUsers' },
      { name: 'totalUsers' },
    ],
  });

  const met = (summary.rows?.[0]?.metricValues || []).map(m => m.value);
  const pageviews = parseInt(met[0] || 0);
  const sessions = parseInt(met[1] || 0);
  const avgDuration = parseFloat(met[2] || 0);
  const bounceRate = parseFloat(met[3] || 0);
  const newUsers = parseInt(met[4] || 0);
  const totalUsers = parseInt(met[5] || 0);

  // Daily sparkline — last 30 days
  const daily = await runReport(propertyId, token, {
    dateRanges: [{ startDate: '30daysAgo', endDate: 'today' }],
    dimensions: [{ name: 'date' }],
    metrics: [{ name: 'screenPageViews' }],
    orderBys: [{ dimension: { dimensionName: 'date' } }],
  });

  const sparkline = rows(daily).map(r => ({ date: r.dims[0], views: parseInt(r.mets[0]) }));

  return {
    pageviews,
    sessions,
    avgDurationSeconds: Math.round(avgDuration),
    bounceRate: Math.round(bounceRate * 100) / 100,
    newUsers,
    returningUsers: totalUsers - newUsers,
    totalUsers,
    sparkline,
  };
}

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
    rank: i + 1,
    path: r.dims[0],
    title: r.dims[1],
    pageviews: parseInt(r.mets[0]),
    avgDurationSeconds: Math.round(parseFloat(r.mets[1])),
    bounceRate: Math.round(parseFloat(r.mets[2]) * 100) / 100,
    sessions: parseInt(r.mets[3]),
  }));
}

async function getSources(propertyId, token) {
  const data = await runReport(propertyId, token, {
    dateRanges: [{ startDate: '30daysAgo', endDate: 'today' }],
    dimensions: [{ name: 'sessionDefaultChannelGrouping' }],
    metrics: [{ name: 'sessions' }],
    orderBys: [{ metric: { metricName: 'sessions' }, desc: true }],
  });

  const total = rows(data).reduce((s, r) => s + parseInt(r.mets[0]), 0);

  return rows(data).map(r => ({
    channel: r.dims[0],
    sessions: parseInt(r.mets[0]),
    pct: total > 0 ? Math.round((parseInt(r.mets[0]) / total) * 1000) / 10 : 0,
  }));
}

async function getRealtime(propertyId, token) {
  const [active, pages, countries, devices] = await Promise.all([
    runRealtimeReport(propertyId, token, {
      metrics: [{ name: 'activeUsers' }],
    }),
    runRealtimeReport(propertyId, token, {
      dimensions: [{ name: 'pagePath' }, { name: 'pageTitle' }],
      metrics: [{ name: 'activeUsers' }],
      orderBys: [{ metric: { metricName: 'activeUsers' }, desc: true }],
      limit: 10,
    }),
    runRealtimeReport(propertyId, token, {
      dimensions: [{ name: 'countryId' }, { name: 'country' }],
      metrics: [{ name: 'activeUsers' }],
      orderBys: [{ metric: { metricName: 'activeUsers' }, desc: true }],
      limit: 10,
    }),
    runRealtimeReport(propertyId, token, {
      dimensions: [{ name: 'deviceCategory' }],
      metrics: [{ name: 'activeUsers' }],
    }),
  ]);

  return {
    activeUsers: parseInt(active.rows?.[0]?.metricValues?.[0]?.value || 0),
    topPages: rows(pages).map(r => ({
      path: r.dims[0],
      title: r.dims[1],
      users: parseInt(r.mets[0]),
    })),
    countries: rows(countries).map(r => ({
      code: r.dims[0],
      name: r.dims[1],
      users: parseInt(r.mets[0]),
    })),
    devices: rows(devices).map(r => ({
      type: r.dims[0],
      users: parseInt(r.mets[0]),
    })),
  };
}

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
    countries: rows(countries).map((r, i) => ({
      rank: i + 1,
      country: r.dims[0],
      sessions: parseInt(r.mets[0]),
    })),
    cities: rows(cities).map((r, i) => ({
      rank: i + 1,
      city: r.dims[0],
      sessions: parseInt(r.mets[0]),
    })),
  };
}

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
    categories: rows(deviceCats).map(r => ({
      type: r.dims[0],
      sessions: parseInt(r.mets[0]),
    })),
    browsers: rows(browsers).map(r => ({
      browser: r.dims[0],
      sessions: parseInt(r.mets[0]),
    })),
    operatingSystems: rows(os).map(r => ({
      os: r.dims[0],
      sessions: parseInt(r.mets[0]),
    })),
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
      body: JSON.stringify({ metric, data, generatedAt: new Date().toISOString() }),
    };
  } catch (err) {
    console.error('Analytics function error:', err.message);
    return {
      statusCode: 500,
      headers: CORS_HEADERS,
      body: JSON.stringify({ error: err.message }),
    };
  }
};
