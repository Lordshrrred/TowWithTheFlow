#!/usr/bin/env python3
"""
Tow With The Flow — low-cost SEO intelligence report.

Uses Google Search Console and GA4 Data API data when credentials are available,
then blends in existing TWTF intent-map, backlink, syndication, and authority
backlog evidence. Normal runs make no paid SERP or LLM calls.

Outputs:
  reports/seo-intelligence-latest.md
  reports/seo-intelligence-latest.json

Raw API responses are cached under .cache/seo-intelligence/ and are not
committed or published.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
REPORTS_DIR = ROOT / "reports"
CACHE_DIR = ROOT / ".cache" / "seo-intelligence"
POSTS_DIR = ROOT / "content" / "posts"
STATIC_DATA_DIR = ROOT / "static" / "data"
SCRIPTS_DIR = ROOT / "scripts"
BASE_URL = "https://towwiththeflow.com"

GSC_BASE = "https://searchconsole.googleapis.com/webmasters/v3"
GA4_BASE = "https://analyticsdata.googleapis.com/v1beta"
REQUEST_COUNT = {"gsc": 0, "ga4": 0}

CATEGORY_PATTERNS = {
    "towing cost": [r"\bcost\b", r"\bprice\b", r"\brate\b", r"\bfee\b", r"\btow truck\b"],
    "roadside emergency": [r"break(?:s|ing)? down", r"won'?t start", r"overheat", r"flat tire", r"dead battery", r"emergency"],
    "insurance": [r"insurance", r"\baaa\b", r"geico", r"state farm", r"progressive", r"allstate", r"roadside assistance"],
    "city/location": [r"denver", r"colorado", r"phoenix", r"houston", r"chicago", r"atlanta", r"los angeles", r"miami", r"las vegas", r"austin", r"dallas", r"new york"],
    "vehicle type": [r"\brv\b", r"trailer", r"boat", r"motorcycle", r"truck", r"luxury", r"tesla", r"ev\b"],
    "laws/consumer rights": [r"law", r"legal", r"rights", r"illegal", r"police", r"impound", r"private property"],
}

AUTHORITY_ASSET_PATTERNS = {
    "Tow Cost Estimator": [r"tow(?:ing)? cost", r"tow truck cost", r"price", r"rate", r"per mile", r"hook"],
    "Tow or Drive Decision Tree": [r"can i drive", r"safe to drive", r"tow or drive", r"need a tow"],
    "Roadside Checklists": [r"what to do", r"checklist", r"emergency kit", r"road trip", r"winter driving"],
    "Insurance Comparison": [r"insurance", r"\baaa\b", r"geico", r"state farm", r"progressive", r"allstate", r"roadside assistance"],
    "State Law Resources": [r"law", r"illegal", r"rights", r"impound", r"private property", r"police"],
}


@dataclass
class ApiStatus:
    source: str
    status: str
    message: str
    cached: bool = False
    rows: int = 0


def load_dotenv() -> None:
    try:
        from dotenv import load_dotenv as _load_dotenv

        _load_dotenv(ROOT / ".env", override=True)
    except ImportError:
        return


def today_utc() -> date:
    return datetime.now(timezone.utc).date()


def seo_date_ranges() -> dict[str, tuple[str, str]]:
    # GSC data is often delayed. Use yesterday as the end date for stability.
    end = today_utc() - timedelta(days=1)
    current_start = end - timedelta(days=27)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=27)
    return {
        "current": (current_start.isoformat(), end.isoformat()),
        "previous": (previous_start.isoformat(), previous_end.isoformat()),
    }


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def cache_key(prefix: str, payload: Any) -> Path:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(raw).hexdigest()[:24]
    return CACHE_DIR / f"{prefix}-{digest}.json"


def load_cached(path: Path, max_age_hours: int) -> Any | None:
    if not path.exists():
        return None
    age = datetime.now(timezone.utc) - datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    if age > timedelta(hours=max_age_hours):
        return None
    return read_json(path, None)


def service_account_token(creds_json: str, scopes: list[str]) -> str:
    try:
        import google.auth.transport.requests as gtr
        import google.oauth2.service_account as sa
    except ImportError as exc:
        raise RuntimeError("google-auth not installed — run: pip install google-auth") from exc

    creds = sa.Credentials.from_service_account_info(json.loads(creds_json), scopes=scopes)
    creds.refresh(gtr.Request())
    return creds.token


def post_json(url: str, token: str, body: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_gsc_window(site_url: str, token: str, start_date: str, end_date: str, row_limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    encoded_site = urllib.parse.quote(site_url, safe="")
    start_row = 0
    while True:
        body = {
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": ["query", "page"],
            "rowLimit": row_limit,
            "startRow": start_row,
        }
        REQUEST_COUNT["gsc"] += 1
        data = post_json(f"{GSC_BASE}/sites/{encoded_site}/searchAnalytics/query", token, body)
        batch = data.get("rows") or []
        rows.extend(batch)
        if len(batch) < row_limit:
            break
        start_row += row_limit
    return rows


def fetch_search_console(force_refresh: bool, max_age_hours: int) -> tuple[dict[str, Any], ApiStatus]:
    site_url = os.getenv("SEARCH_CONSOLE_SITE_URL") or os.getenv("GSC_SITE_URL") or BASE_URL + "/"
    creds_json = (
        os.getenv("SEARCH_CONSOLE_CREDENTIALS_JSON")
        or os.getenv("GSC_CREDENTIALS_JSON")
        or os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        or os.getenv("GA_CREDENTIALS_JSON")
        or ""
    )
    if not creds_json:
        return {"current": [], "previous": [], "site_url": site_url}, ApiStatus("search_console", "missing_credentials", "No Search Console service-account JSON env var found.")

    ranges = seo_date_ranges()
    cache_path = cache_key("gsc", {"site_url": site_url, "ranges": ranges, "dimensions": ["query", "page"]})
    if not force_refresh:
        cached = load_cached(cache_path, max_age_hours)
        if cached is not None:
            count = len(cached.get("current", [])) + len(cached.get("previous", []))
            return cached, ApiStatus("search_console", "ok", "Loaded Search Console data from private cache.", True, count)

    try:
        token = service_account_token(creds_json, ["https://www.googleapis.com/auth/webmasters.readonly"])
        current = fetch_gsc_window(site_url, token, *ranges["current"], row_limit=25000)
        previous = fetch_gsc_window(site_url, token, *ranges["previous"], row_limit=25000)
    except Exception as exc:
        cached = read_json(cache_path, None)
        if cached:
            return cached, ApiStatus("search_console", "cached_after_error", f"API failed; using private cache. Error: {exc}", True, len(cached.get("current", [])))
        return {"current": [], "previous": [], "site_url": site_url}, ApiStatus("search_console", "error", str(exc))

    payload = {"site_url": site_url, "ranges": ranges, "current": current, "previous": previous}
    write_json(cache_path, payload)
    return payload, ApiStatus("search_console", "ok", "Fetched Search Console query/page data.", False, len(current) + len(previous))


def run_ga4_report(property_id: str, token: str, metrics: list[str]) -> dict[str, Any]:
    ranges = seo_date_ranges()
    body = {
        "dateRanges": [
            {"name": "current", "startDate": ranges["current"][0], "endDate": ranges["current"][1]},
            {"name": "previous", "startDate": ranges["previous"][0], "endDate": ranges["previous"][1]},
        ],
        "dimensions": [{"name": "dateRange"}, {"name": "landingPagePlusQueryString"}],
        "metrics": [{"name": name} for name in metrics],
        "dimensionFilter": {
            "filter": {
                "fieldName": "sessionDefaultChannelGrouping",
                "stringFilter": {"matchType": "EXACT", "value": "Organic Search"},
            }
        },
        "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}],
        "limit": 1000,
    }
    REQUEST_COUNT["ga4"] += 1
    return post_json(f"{GA4_BASE}/properties/{property_id}:runReport", token, body)


def fetch_ga4(force_refresh: bool, max_age_hours: int) -> tuple[dict[str, Any], ApiStatus]:
    property_id = os.getenv("GA_PROPERTY_ID", "").strip()
    creds_json = os.getenv("GA_CREDENTIALS_JSON") or os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or ""
    if not property_id:
        return {"rows": [], "property_id": None}, ApiStatus("ga4", "missing_property", "GA_PROPERTY_ID not set.")
    if not creds_json:
        return {"rows": [], "property_id": property_id}, ApiStatus("ga4", "missing_credentials", "GA4 service-account JSON env var not found.")

    metrics = [
        "sessions",
        "activeUsers",
        "newUsers",
        "engagedSessions",
        "engagementRate",
        "averageSessionDuration",
        "screenPageViews",
        "keyEvents",
    ]
    cache_path = cache_key("ga4", {"property_id": property_id, "ranges": seo_date_ranges(), "metrics": metrics})
    if not force_refresh:
        cached = load_cached(cache_path, max_age_hours)
        if cached is not None:
            return cached, ApiStatus("ga4", "ok", "Loaded GA4 organic landing-page data from private cache.", True, len(cached.get("rows", [])))

    try:
        token = service_account_token(creds_json, ["https://www.googleapis.com/auth/analytics.readonly"])
        try:
            data = run_ga4_report(property_id, token, metrics)
        except urllib.error.HTTPError:
            # Some properties may not have key events configured or exposed.
            metrics = [m for m in metrics if m != "keyEvents"]
            data = run_ga4_report(property_id, token, metrics)
    except Exception as exc:
        cached = read_json(cache_path, None)
        if cached:
            return cached, ApiStatus("ga4", "cached_after_error", f"API failed; using private cache. Error: {exc}", True, len(cached.get("rows", [])))
        return {"rows": [], "property_id": property_id}, ApiStatus("ga4", "error", str(exc))

    payload = {"property_id": property_id, "metrics": metrics, "ranges": seo_date_ranges(), "rows": data.get("rows") or []}
    write_json(cache_path, payload)
    return payload, ApiStatus("ga4", "ok", "Fetched GA4 organic landing-page behavior.", False, len(payload["rows"]))


def path_from_url(value: str) -> str:
    if not value:
        return "/"
    parsed = urllib.parse.urlparse(value)
    path = parsed.path if parsed.scheme or parsed.netloc else value.split("?", 1)[0]
    if not path.startswith("/"):
        path = "/" + path
    if not path.endswith("/") and "." not in Path(path).name:
        path += "/"
    return path


def slug_from_path(path: str) -> str:
    stripped = path_from_url(path).strip("/")
    return stripped.split("/")[-1] if stripped else "home"


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def classify_text(text: str) -> list[str]:
    lowered = text.lower()
    out = []
    for category, patterns in CATEGORY_PATTERNS.items():
        if any(re.search(pattern, lowered) for pattern in patterns):
            out.append(category)
    return out or ["general roadside"]


def load_post_titles() -> dict[str, str]:
    titles: dict[str, str] = {}
    for path in POSTS_DIR.glob("*.md"):
        if path.name.startswith("_"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        title = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', text, re.MULTILINE)
        slug = re.search(r'^slug:\s*["\']?(.+?)["\']?\s*$', text, re.MULTILINE)
        key = slug.group(1) if slug else path.stem
        titles[key] = title.group(1) if title else key.replace("-", " ").title()
    return titles


def normalize_gsc_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        keys = row.get("keys") or ["", ""]
        query = keys[0] if len(keys) > 0 else ""
        page = keys[1] if len(keys) > 1 else ""
        normalized.append(
            {
                "query": query,
                "page": page,
                "path": path_from_url(page),
                "clicks": int(row.get("clicks", 0)),
                "impressions": int(row.get("impressions", 0)),
                "ctr": float(row.get("ctr", 0) or 0),
                "position": float(row.get("position", 0) or 0),
                "categories": classify_text(f"{query} {page}"),
            }
        )
    return normalized


def aggregate_gsc(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    agg: dict[str, dict[str, Any]] = {}
    for row in rows:
        ident = row[key]
        item = agg.setdefault(
            ident,
            {"id": ident, "clicks": 0, "impressions": 0, "weighted_position": 0.0, "queries": {}, "categories": set()},
        )
        item["clicks"] += row["clicks"]
        item["impressions"] += row["impressions"]
        item["weighted_position"] += row["position"] * max(row["impressions"], 1)
        item["queries"][row["query"]] = item["queries"].get(row["query"], 0) + row["impressions"]
        item["categories"].update(row["categories"])
    for item in agg.values():
        impressions = max(item["impressions"], 1)
        item["ctr"] = item["clicks"] / impressions
        item["position"] = item["weighted_position"] / impressions
        item["top_queries"] = sorted(item["queries"].items(), key=lambda kv: kv[1], reverse=True)[:5]
        item["categories"] = sorted(item["categories"])
    return agg


def normalize_ga_rows(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    metric_names = payload.get("metrics") or []
    by_path: dict[str, dict[str, Any]] = {}
    for row in payload.get("rows") or []:
        dims = [d.get("value", "") for d in row.get("dimensionValues", [])]
        mets = [m.get("value", "0") for m in row.get("metricValues", [])]
        if len(dims) < 2:
            continue
        period, landing = dims[0], dims[1]
        path = path_from_url(landing)
        entry = by_path.setdefault(path, {"path": path, "current": {}, "previous": {}})
        period_key = "current" if period == "current" else "previous"
        for name, value in zip(metric_names, mets):
            try:
                parsed: float | int = float(value)
                if parsed.is_integer():
                    parsed = int(parsed)
            except ValueError:
                parsed = 0
            entry[period_key][name] = parsed
    return by_path


def load_backlink_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in [SCRIPTS_DIR / "backlink_audit.json", SCRIPTS_DIR / "wordpress_backlink_audit.json"]:
        data = read_json(path, {})
        for slug, platforms in (data.get("slugs") or {}).items():
            if not isinstance(platforms, dict):
                continue
            counts[slug] = counts.get(slug, 0) + sum(1 for p in platforms.values() if isinstance(p, dict) and p.get("verified"))
    return counts


def load_syndication_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    log_path = SCRIPTS_DIR / "syndication_log.txt"
    if not log_path.exists():
        return counts
    pattern = re.compile(r"\]\s+([A-Z_]+)\s+\|\s+([\w-]+)\s+\|\s+SUCCESS")
    for line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = pattern.search(line)
        if not m:
            continue
        platform, slug = m.group(1), m.group(2)
        if platform in {"DEVTO", "TUMBLR", "BLOGGER", "WORDPRESS", "FEEDER"}:
            counts[slug] = counts.get(slug, 0) + 1
    return counts


def load_authority_assets() -> list[dict[str, Any]]:
    return read_json(ROOT / "data" / "authority_backlog.json", {}).get("assets") or []


def load_intent_map() -> dict[str, Any]:
    return read_json(REPORTS_DIR / "intent-map.json", {})


def opportunity_rows(gsc_current: list[dict[str, Any]], ga_pages: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    near = []
    ctr = []
    for row in gsc_current:
        if row["impressions"] >= 10 and 8 <= row["position"] <= 20:
            near.append(row)
        if row["impressions"] >= 20 and row["position"] <= 10 and row["ctr"] < 0.03:
            ctr.append(row)

    engagement = []
    weak = []
    for path, data in ga_pages.items():
        cur = data.get("current") or {}
        sessions = int(cur.get("sessions", 0) or 0)
        if sessions < 2:
            continue
        engagement_rate = float(cur.get("engagementRate", 0) or 0)
        avg_duration = float(cur.get("averageSessionDuration", 0) or 0)
        row = {
            "path": path,
            "sessions": sessions,
            "engagementRate": engagement_rate,
            "averageSessionDuration": avg_duration,
            "views": int(cur.get("screenPageViews", 0) or 0),
        }
        if engagement_rate >= 0.65 or avg_duration >= 90:
            engagement.append(row)
        if engagement_rate <= 0.35 and sessions >= 3:
            weak.append(row)

    return {
        "near_page_one": sorted(near, key=lambda r: (r["position"], -r["impressions"]))[:20],
        "ctr_opportunities": sorted(ctr, key=lambda r: (-r["impressions"], r["ctr"]))[:20],
        "engagement_winners": sorted(engagement, key=lambda r: (-r["sessions"], -r["engagementRate"]))[:20],
        "weak_engagement": sorted(weak, key=lambda r: (-r["sessions"], r["engagementRate"]))[:20],
    }


def cannibalization_evidence(gsc_current: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_query: dict[str, dict[str, Any]] = {}
    for row in gsc_current:
        if row["impressions"] < 3:
            continue
        q = row["query"]
        entry = by_query.setdefault(q, {"query": q, "pages": {}})
        page = entry["pages"].setdefault(row["path"], {"path": row["path"], "impressions": 0, "clicks": 0, "position": 0.0})
        page["impressions"] += row["impressions"]
        page["clicks"] += row["clicks"]
        page["position"] += row["position"] * row["impressions"]
    findings = []
    for entry in by_query.values():
        pages = []
        for page in entry["pages"].values():
            if page["impressions"]:
                page["position"] = page["position"] / page["impressions"]
            pages.append(page)
        pages = sorted(pages, key=lambda p: p["impressions"], reverse=True)
        if len(pages) >= 2 and sum(p["impressions"] for p in pages) >= 10:
            findings.append({"query": entry["query"], "pages": pages[:5], "total_impressions": sum(p["impressions"] for p in pages)})
    return sorted(findings, key=lambda f: f["total_impressions"], reverse=True)[:20]


def authority_asset_opportunities(gsc_current: list[dict[str, Any]], authority_assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    support: dict[str, dict[str, Any]] = {}
    text_rows = gsc_current
    for label, patterns in AUTHORITY_ASSET_PATTERNS.items():
        matches = []
        for row in text_rows:
            hay = f"{row['query']} {row['page']}".lower()
            if any(re.search(p, hay) for p in patterns):
                matches.append(row)
        support[label] = {
            "asset": label,
            "evidence_queries": sorted(matches, key=lambda r: r["impressions"], reverse=True)[:8],
            "impressions": sum(r["impressions"] for r in matches),
            "clicks": sum(r["clicks"] for r in matches),
        }

    known = {asset.get("title"): asset for asset in authority_assets}
    for title, asset in known.items():
        if title in support:
            support[title]["backlog_status"] = asset.get("status")
            support[title]["priority"] = asset.get("priority")
            support[title]["url"] = asset.get("slug")

    return sorted(support.values(), key=lambda x: (x["impressions"], x["clicks"]), reverse=True)


def city_opportunities(gsc_current: list[dict[str, Any]], ga_pages: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in gsc_current:
        if "city/location" not in row["categories"] or row["impressions"] < 5:
            continue
        ga = (ga_pages.get(row["path"]) or {}).get("current") or {}
        rows.append(
            {
                **row,
                "sessions": int(ga.get("sessions", 0) or 0),
                "engagementRate": float(ga.get("engagementRate", 0) or 0),
            }
        )
    return sorted(rows, key=lambda r: (-r["impressions"], r["position"]))[:20]


def backlink_supported_pages(
    page_agg: dict[str, dict[str, Any]], backlink_counts: dict[str, int], syndication_counts: dict[str, int]
) -> list[dict[str, Any]]:
    rows = []
    for path, item in page_agg.items():
        slug = slug_from_path(path)
        backlinks = backlink_counts.get(slug, 0)
        if backlinks <= 0:
            continue
        rows.append(
            {
                "path": path,
                "clicks": item["clicks"],
                "impressions": item["impressions"],
                "position": item["position"],
                "backlinks": backlinks,
                "syndications": syndication_counts.get(slug, 0),
            }
        )
    return sorted(rows, key=lambda r: (-r["backlinks"], -r["impressions"]))[:20]


def top_actions(classified: dict[str, Any], authority: list[dict[str, Any]], cannibal: list[dict[str, Any]], city: list[dict[str, Any]]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    if authority and authority[0]["impressions"] > 0:
        a = authority[0]
        actions.append(
            {
                "title": f"Build or refine authority asset: {a['asset']}",
                "reason": f"{a['impressions']} Search Console impressions match this asset pattern.",
                "next_action": "Use the authority backlog and build as a separate scoped asset.",
            }
        )
    if classified["near_page_one"]:
        r = classified["near_page_one"][0]
        actions.append(
            {
                "title": f"Improve near-page-one page: {r['path']}",
                "reason": f"Query '{r['query']}' averages position {r['position']:.1f} with {r['impressions']} impressions.",
                "next_action": "Refresh title/intro/internal links around the exact query intent.",
            }
        )
    if classified["ctr_opportunities"]:
        r = classified["ctr_opportunities"][0]
        actions.append(
            {
                "title": f"Rewrite title/meta for CTR: {r['path']}",
                "reason": f"Position {r['position']:.1f}, {r['impressions']} impressions, CTR {pct(r['ctr'])}.",
                "next_action": "Improve SERP promise without changing the URL.",
            }
        )
    if cannibal:
        c = cannibal[0]
        actions.append(
            {
                "title": f"Review cannibalization for query: {c['query']}",
                "reason": f"{len(c['pages'])} pages split {c['total_impressions']} impressions.",
                "next_action": "Compare intent before choosing keep, merge, canonicalize, or hub.",
            }
        )
    if city:
        c = city[0]
        actions.append(
            {
                "title": f"Differentiate city/local page: {c['path']}",
                "reason": f"Local query '{c['query']}' has {c['impressions']} impressions.",
                "next_action": "Add local-specific pricing/context only if it improves user value.",
            }
        )
    if classified["engagement_winners"]:
        e = classified["engagement_winners"][0]
        actions.append(
            {
                "title": f"Use engagement winner as an internal-link hub: {e['path']}",
                "reason": f"{e['sessions']} organic sessions with {pct(e['engagementRate'])} engagement.",
                "next_action": "Add contextual links to the closest authority asset or cluster page.",
            }
        )
    return actions[:5]


def render_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]], empty: str) -> list[str]:
    if not rows:
        return [empty, ""]
    lines = ["| " + " | ".join(label for label, _key in columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    for row in rows:
        vals = []
        for _label, key in columns:
            val = row
            for part in key.split("."):
                val = val.get(part, "") if isinstance(val, dict) else ""
            if isinstance(val, float):
                val = pct(val) if "ctr" in key.lower() or "rate" in key.lower() else f"{val:.1f}"
            vals.append(str(val).replace("|", "\\|"))
        lines.append("| " + " | ".join(vals) + " |")
    lines.append("")
    return lines


def build_markdown(payload: dict[str, Any]) -> str:
    lines = ["# TWTF SEO Intelligence Report", ""]
    lines.append(f"Generated: {payload['generated_at']}")
    lines.append("")
    lines.append("## 1. Data Connection/Freshness")
    lines.append("")
    for status in payload["statuses"]:
        cache_note = " from private cache" if status.get("cached") else ""
        lines.append(f"- **{status['source']}**: {status['status']}{cache_note}. {status['message']} Rows: {status.get('rows', 0)}.")
    lines.append(f"- **Normal-run API requests**: Search Console {payload['request_counts']['gsc']}; GA4 {payload['request_counts']['ga4']}; paid SERP/LLM/web-search 0.")
    lines.append("")

    lines.append("## 2. Top Organic Landing Pages")
    lines += render_table(payload["top_landing_pages"][:10], [("Page", "path"), ("Clicks", "clicks"), ("Impressions", "impressions"), ("CTR", "ctr"), ("Avg position", "position")], "No Search Console landing-page data available.")

    lines.append("## 3. Top Real Queries")
    lines += render_table(payload["top_queries"][:15], [("Query", "id"), ("Clicks", "clicks"), ("Impressions", "impressions"), ("CTR", "ctr"), ("Avg position", "position")], "No Search Console query data available.")

    lines.append("## 4. Near-Page-One Opportunities")
    lines += render_table(payload["classifications"]["near_page_one"][:10], [("Query", "query"), ("Page", "path"), ("Impressions", "impressions"), ("Position", "position")], "None found with current thresholds.")

    lines.append("## 5. CTR Opportunities")
    lines += render_table(payload["classifications"]["ctr_opportunities"][:10], [("Query", "query"), ("Page", "path"), ("Impressions", "impressions"), ("Position", "position"), ("CTR", "ctr")], "None found with current thresholds.")

    lines.append("## 6. Engagement Winners")
    lines += render_table(payload["classifications"]["engagement_winners"][:10], [("Page", "path"), ("Sessions", "sessions"), ("Engagement rate", "engagementRate"), ("Avg seconds", "averageSessionDuration"), ("Views", "views")], "No GA4 organic engagement winners available.")

    lines.append("## 7. Weak-Engagement Pages")
    lines += render_table(payload["classifications"]["weak_engagement"][:10], [("Page", "path"), ("Sessions", "sessions"), ("Engagement rate", "engagementRate"), ("Avg seconds", "averageSessionDuration")], "No weak-engagement pages found with current thresholds.")

    lines.append("## 8. Cannibalization Evidence")
    if payload["cannibalization"]:
        for item in payload["cannibalization"][:10]:
            lines.append(f"- **{item['query']}**: {item['total_impressions']} impressions split across " + ", ".join(f"{p['path']} ({p['impressions']})" for p in item["pages"]))
    else:
        lines.append("No Search Console-confirmed cannibalization found. Keep using the intent-map as a review queue, not an automatic merge list.")
    lines.append("")

    lines.append("## 9. City/Local Opportunities")
    lines += render_table(payload["city_opportunities"][:10], [("Query", "query"), ("Page", "path"), ("Impressions", "impressions"), ("Position", "position"), ("Sessions", "sessions")], "No city/local opportunities found with current thresholds.")

    lines.append("## 10. Backlink-Supported Pages")
    lines += render_table(payload["backlink_supported"][:10], [("Page", "path"), ("Backlinks", "backlinks"), ("Syndications", "syndications"), ("Impressions", "impressions"), ("Clicks", "clicks")], "No backlink-supported organic winners found yet.")

    lines.append("## 11. Recommended Authority Assets")
    asset_rows = [
        {
            "asset": a["asset"],
            "impressions": a["impressions"],
            "clicks": a["clicks"],
            "backlog_status": a.get("backlog_status", ""),
            "priority": a.get("priority", ""),
        }
        for a in payload["authority_asset_opportunities"][:8]
        if a["impressions"] > 0
    ]
    lines += render_table(asset_rows, [("Asset", "asset"), ("Impressions", "impressions"), ("Clicks", "clicks"), ("Backlog", "backlog_status"), ("Priority", "priority")], "No Search Console asset-pattern evidence yet. Backlog order remains the fallback.")

    lines.append("## 12. Top Five Actions")
    if payload["top_actions"]:
        for i, action in enumerate(payload["top_actions"], 1):
            lines.append(f"{i}. **{action['title']}** — {action['reason']} Next: {action['next_action']}")
    else:
        lines.append("No evidence-ranked actions yet. Configure Search Console and GA4 credentials, then rerun.")
    lines.append("")

    lines.append("## 13. Data Limitations")
    lines.append("")
    lines.append("- Search Console data is delayed and aggregated; use it for direction, not exact real-time rank tracking.")
    lines.append("- GA4 organic behavior is grouped by landing page and avoids user-level data.")
    lines.append("- Backlink and syndication data show operational distribution, not organic search value by themselves.")
    lines.append("- Intent-map overlap groups remain recommendations until Search Console confirms split query ownership.")
    lines.append("- No paid SERP, Claude web-search, or rank-check calls are made by this report.")
    lines.append("")

    return "\n".join(lines)


def compact_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "generated_at": payload["generated_at"],
        "statuses": payload["statuses"],
        "request_counts": payload["request_counts"],
        "top_actions": payload["top_actions"][:3],
        "near_page_one_count": len(payload["classifications"]["near_page_one"]),
        "ctr_opportunity_count": len(payload["classifications"]["ctr_opportunities"]),
        "cannibalization_count": len(payload["cannibalization"]),
        "report_path": "reports/seo-intelligence-latest.md",
    }


def build_payload(gsc_payload: dict[str, Any], gsc_status: ApiStatus, ga_payload: dict[str, Any], ga_status: ApiStatus) -> dict[str, Any]:
    gsc_current = normalize_gsc_rows(gsc_payload.get("current") or [])
    gsc_previous = normalize_gsc_rows(gsc_payload.get("previous") or [])
    page_agg = aggregate_gsc(gsc_current, "path")
    query_agg = aggregate_gsc(gsc_current, "query")
    ga_pages = normalize_ga_rows(ga_payload)
    backlinks = load_backlink_counts()
    syndications = load_syndication_counts()
    authority_assets = load_authority_assets()
    intent_map = load_intent_map()
    classified = opportunity_rows(gsc_current, ga_pages)
    cannibal = cannibalization_evidence(gsc_current)
    authority = authority_asset_opportunities(gsc_current, authority_assets)
    city = city_opportunities(gsc_current, ga_pages)
    backlink_supported = backlink_supported_pages(page_agg, backlinks, syndications)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "periods": seo_date_ranges(),
        "statuses": [gsc_status.__dict__, ga_status.__dict__],
        "request_counts": dict(REQUEST_COUNT),
        "top_landing_pages": sorted(page_agg.values(), key=lambda r: (-r["clicks"], -r["impressions"]))[:50],
        "top_queries": sorted(query_agg.values(), key=lambda r: (-r["clicks"], -r["impressions"]))[:100],
        "classifications": classified,
        "cannibalization": cannibal,
        "city_opportunities": city,
        "backlink_supported": backlink_supported,
        "authority_asset_opportunities": authority,
        "intent_map": {
            "generatedAt": intent_map.get("generatedAt"),
            "overlapGroupCount": intent_map.get("overlapGroupCount", 0),
            "metadataFlagCount": intent_map.get("metadataFlagCount", 0),
        },
    }
    payload["top_actions"] = top_actions(classified, authority, cannibal, city)
    payload["summary"] = compact_summary(payload)
    # Keep previous row count visible without storing a second full report section.
    payload["comparison"] = {
        "previous_gsc_rows": len(gsc_previous),
        "current_gsc_rows": len(gsc_current),
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the TWTF SEO intelligence report from GSC, GA4, and existing local evidence.")
    parser.add_argument("--force-refresh", action="store_true", help="Ignore fresh private cache and call Google APIs.")
    parser.add_argument("--cache-hours", type=int, default=20, help="Private API cache freshness window. Default: 20 hours.")
    args = parser.parse_args()

    load_dotenv()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    gsc_payload, gsc_status = fetch_search_console(args.force_refresh, args.cache_hours)
    ga_payload, ga_status = fetch_ga4(args.force_refresh, args.cache_hours)
    payload = build_payload(gsc_payload, gsc_status, ga_payload, ga_status)

    latest_json = REPORTS_DIR / "seo-intelligence-latest.json"
    latest_md = REPORTS_DIR / "seo-intelligence-latest.md"
    dated_json = REPORTS_DIR / f"seo-intelligence-{today_utc().isoformat()}.json"
    dated_md = REPORTS_DIR / f"seo-intelligence-{today_utc().isoformat()}.md"
    write_json(latest_json, payload)
    write_json(dated_json, payload)
    report = build_markdown(payload)
    latest_md.write_text(report, encoding="utf-8")
    dated_md.write_text(report, encoding="utf-8")

    print(f"Wrote {latest_md.relative_to(ROOT)}")
    print(f"Wrote {latest_json.relative_to(ROOT)}")
    print(f"API requests: Search Console {REQUEST_COUNT['gsc']}, GA4 {REQUEST_COUNT['ga4']}, paid SERP/LLM/web-search 0")
    for status in payload["statuses"]:
        print(f"{status['source']}: {status['status']} ({status.get('rows', 0)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
