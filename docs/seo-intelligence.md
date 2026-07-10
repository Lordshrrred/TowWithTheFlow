# TWTF SEO Intelligence

This repo uses a low-cost evidence loop to decide which pages, clusters, and
future authority assets deserve work next.

Normal runs use:

- Google Search Console Search Analytics API
- GA4 Data API
- existing backlink audit JSON
- existing syndication logs
- `reports/intent-map.json`
- `data/authority_backlog.json`

Normal runs do not call Claude, web search, paid SERP APIs, or rank-checking
vendors.

## Command

```bash
python3 scripts/seo_intelligence.py
python3 scripts/build_seo_data.py
```

Use `--force-refresh` only when you deliberately want to bypass the private
cache:

```bash
python3 scripts/seo_intelligence.py --force-refresh
```

## Credentials

Set these environment variables locally or as GitHub Actions secrets:

- `SEARCH_CONSOLE_CREDENTIALS_JSON`: service-account JSON with Search Console
  read access.
- `SEARCH_CONSOLE_SITE_URL`: Search Console property URL, usually
  `https://towwiththeflow.com/`.
- `GA_CREDENTIALS_JSON`: service-account JSON with GA4 read access.
- `GA_PROPERTY_ID`: GA4 property ID.

`SEARCH_CONSOLE_CREDENTIALS_JSON` may be omitted if the GA service account also
has Search Console access; in that case the script falls back to
`GA_CREDENTIALS_JSON`.

Never commit credential values or paste them into reports.

## Caching

Raw Search Console and GA4 responses are cached under:

```text
.cache/seo-intelligence/
```

That directory is ignored by Git and is not copied to `static/`. The dashboard
receives only the compact `summary` object from
`reports/seo-intelligence-latest.json`.

## Report Outputs

- `reports/seo-intelligence-latest.md`
- `reports/seo-intelligence-latest.json`
- dated copies matching the run date

The markdown report contains aggregated queries, landing pages, opportunity
classes, and top recommended actions. It does not contain user-level data,
precise location, vehicle identifiers, free-text personal details, or full
calculator input payloads.

## Optional SERP Research

`scripts/serp_intelligence.py` is manual-only. It uses Claude web search and is
for bounded competitor/SERP research, not scheduled rank tracking.

```bash
python3 scripts/serp_intelligence.py --query "tow truck cost denver" --max-cost-usd 1.00
```

The GitHub workflow requires an explicit query. There is no scheduled automatic
SERP check.

## Tow Cost Estimator Event Plan

When the Tow Cost Estimator is built, use these minimal GA4 events:

- `tow_cost_estimator_start`
- `tow_cost_estimate_generated`
- `tow_cost_estimator_complete`
- `calculator_related_resource_click`

Allowed coarse parameters:

- `distance_band`
- `service_type`
- `timing_category`
- `vehicle_category`

Do not collect:

- exact user location
- vehicle identifiers
- free-text personal details
- full input payloads

Build calculator analytics as a tiny shared helper only if it is independently
testable and useful beyond the first estimator.
