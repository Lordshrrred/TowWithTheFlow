#!/usr/bin/env python3
"""
Fetch GA4 analytics data and write static/data/analytics.json

Required env vars:
  GA_CREDENTIALS_JSON  -- service account JSON as a single-line string
  GA_PROPERTY_ID       -- GA4 property ID (e.g. 530033133)

Output:
  static/data/analytics.json
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUT  = ROOT / "static" / "data" / "analytics.json"

GA4_BASE = "https://analyticsdata.googleapis.com/v1beta"

# ── Auth ──────────────────────────────────────────────────────────────────────
def get_access_token():
    creds_json = os.environ.get("GA_CREDENTIALS_JSON", "")
    if not creds_json:
        raise RuntimeError("GA_CREDENTIALS_JSON not set")

    try:
        import google.oauth2.service_account as sa
        import google.auth.transport.requests as gtr
    except ImportError:
        raise RuntimeError(
            "google-auth not installed — run: pip install google-auth"
        )

    creds = sa.Credentials.from_service_account_info(
        json.loads(creds_json),
        scopes=["https://www.googleapis.com/auth/analytics.readonly"],
    )
    req = gtr.Request()
    creds.refresh(req)
    return creds.token


# ── GA4 helpers ───────────────────────────────────────────────────────────────
def run_report(property_id, token, body):
    import urllib.request
    url = f"{GA4_BASE}/properties/{property_id}:runReport"
    data = json.dumps(body).encode()
    req  = urllib.request.Request(
        url, data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def rows(data):
    return [
        {
            "dims": [d["value"] for d in r.get("dimensionValues", [])],
            "mets": [m["value"] for m in r.get("metricValues",   [])],
        }
        for r in (data.get("rows") or [])
    ]


# ── Sections ──────────────────────────────────────────────────────────────────
def fetch_overview(pid, token):
    summary = run_report(pid, token, {
        "dateRanges": [{"startDate": "30daysAgo", "endDate": "today"}],
        "metrics": [
            {"name": "screenPageViews"},
            {"name": "sessions"},
            {"name": "averageSessionDuration"},
            {"name": "bounceRate"},
            {"name": "newUsers"},
            {"name": "totalUsers"},
        ],
    })
    daily = run_report(pid, token, {
        "dateRanges": [{"startDate": "30daysAgo", "endDate": "today"}],
        "dimensions": [{"name": "date"}],
        "metrics":    [{"name": "screenPageViews"}],
        "orderBys":   [{"dimension": {"dimensionName": "date"}}],
    })

    met = [m["value"] for m in (summary.get("rows") or [{}])[0].get("metricValues", [])]
    while len(met) < 6:
        met.append("0")

    total_users = int(met[5])
    new_users   = int(met[4])

    return {
        "pageviews":      int(met[0]),
        "sessions":       int(met[1]),
        "avgSessionDur":  round(float(met[2])),
        "bounceRate":     float(met[3]),
        "newUsers":       new_users,
        "returningUsers": total_users - new_users,
        "daily": [
            {"date": r["dims"][0], "pageviews": int(r["mets"][0])}
            for r in rows(daily)
        ],
    }


def fetch_top_pages(pid, token):
    data = run_report(pid, token, {
        "dateRanges": [{"startDate": "30daysAgo", "endDate": "today"}],
        "dimensions": [{"name": "pagePath"}, {"name": "pageTitle"}],
        "metrics": [
            {"name": "screenPageViews"},
            {"name": "averageSessionDuration"},
            {"name": "bounceRate"},
            {"name": "sessions"},
        ],
        "orderBys": [{"metric": {"metricName": "screenPageViews"}, "desc": True}],
        "limit": 30,
    })
    return [
        {
            "rank":       i + 1,
            "page":       r["dims"][0],
            "title":      r["dims"][1],
            "pageviews":  int(r["mets"][0]),
            "avgDur":     round(float(r["mets"][1])),
            "bounceRate": round(float(r["mets"][2]) * 1000) / 10,
            "sessions":   int(r["mets"][3]),
        }
        for i, r in enumerate(rows(data))
    ]


def fetch_sources(pid, token):
    data = run_report(pid, token, {
        "dateRanges": [{"startDate": "30daysAgo", "endDate": "today"}],
        "dimensions": [{"name": "sessionDefaultChannelGrouping"}],
        "metrics":    [{"name": "sessions"}],
        "orderBys":   [{"metric": {"metricName": "sessions"}, "desc": True}],
    })
    all_rows = rows(data)
    total = sum(int(r["mets"][0]) for r in all_rows)
    return [
        {
            "channel":  r["dims"][0],
            "sessions": int(r["mets"][0]),
            "pct":      round((int(r["mets"][0]) / total) * 1000) / 10 if total else 0,
        }
        for r in all_rows
    ]


def fetch_geo(pid, token):
    countries = run_report(pid, token, {
        "dateRanges": [{"startDate": "30daysAgo", "endDate": "today"}],
        "dimensions": [{"name": "country"}],
        "metrics":    [{"name": "sessions"}],
        "orderBys":   [{"metric": {"metricName": "sessions"}, "desc": True}],
        "limit": 20,
    })
    cities = run_report(pid, token, {
        "dateRanges": [{"startDate": "30daysAgo", "endDate": "today"}],
        "dimensions": [{"name": "city"}],
        "metrics":    [{"name": "sessions"}],
        "orderBys":   [{"metric": {"metricName": "sessions"}, "desc": True}],
        "limit": 10,
    })
    return {
        "topCountries": [{"country": r["dims"][0], "sessions": int(r["mets"][0])} for r in rows(countries)],
        "topCities":    [{"city":    r["dims"][0], "sessions": int(r["mets"][0])} for r in rows(cities)],
    }


def fetch_devices(pid, token):
    device_cats = run_report(pid, token, {
        "dateRanges": [{"startDate": "30daysAgo", "endDate": "today"}],
        "dimensions": [{"name": "deviceCategory"}],
        "metrics":    [{"name": "sessions"}],
        "orderBys":   [{"metric": {"metricName": "sessions"}, "desc": True}],
    })
    browsers = run_report(pid, token, {
        "dateRanges": [{"startDate": "30daysAgo", "endDate": "today"}],
        "dimensions": [{"name": "browser"}],
        "metrics":    [{"name": "sessions"}],
        "orderBys":   [{"metric": {"metricName": "sessions"}, "desc": True}],
        "limit": 5,
    })
    os_data = run_report(pid, token, {
        "dateRanges": [{"startDate": "30daysAgo", "endDate": "today"}],
        "dimensions": [{"name": "operatingSystem"}],
        "metrics":    [{"name": "sessions"}],
        "orderBys":   [{"metric": {"metricName": "sessions"}, "desc": True}],
        "limit": 5,
    })
    return {
        "devices":  [{"device":  r["dims"][0], "sessions": int(r["mets"][0])} for r in rows(device_cats)],
        "browsers": [{"browser": r["dims"][0], "sessions": int(r["mets"][0])} for r in rows(browsers)],
        "os":       [{"os":      r["dims"][0], "sessions": int(r["mets"][0])} for r in rows(os_data)],
    }


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=True)
    except ImportError:
        pass

    property_id = os.environ.get("GA_PROPERTY_ID", "").strip()
    if not property_id:
        print("ERROR: GA_PROPERTY_ID not set", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching GA4 data for property {property_id}...")
    token = get_access_token()

    overview   = fetch_overview(property_id, token)
    top_pages  = fetch_top_pages(property_id, token)
    sources    = fetch_sources(property_id, token)
    geo        = fetch_geo(property_id, token)
    devices    = fetch_devices(property_id, token)

    payload = {
        **overview,
        "topPages":      top_pages,
        "trafficSources": sources,
        **geo,
        **devices,
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)}  ({len(top_pages)} pages, {overview['pageviews']:,} pageviews)")


if __name__ == "__main__":
    main()
