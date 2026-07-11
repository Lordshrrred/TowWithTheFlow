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

Normal runs do not call Claude, web search, paid competitive-research APIs, or rank-checking
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

## Competitive Research (Manual)

`scripts/competitive_research.py` is manual-only. It uses Claude web search and is
for bounded competitor research, not SEO Intelligence and not scheduled rank
tracking.

```bash
python3 scripts/competitive_research.py --query "tow truck cost denver" --max-cost-usd 1.00
```

The GitHub workflow requires an explicit query and confirmation. There is no
scheduled automatic competitive-research check.

## Tool Engine Event Plan

The Tow Cost Estimator (`content/tools/tow-cost-estimator.md`) is the first tool
built on the shared Tool Engine (`static/js/tool-engine.js` + `layouts/partials/tools/calculator.html`
+ `data/tools/*.json`). Every future calculator reuses the same engine and the
same event names — only a new `data/tools/<id>.json` config is needed, not new
tracking code. Events carry a `tool_id` parameter so the dashboard and GA4 can
tell tools apart:

- `calculator_open` — first interaction with any field
- `field_change` — fires per field on `change` (not every keystroke)
- `estimate_generated` — fires whenever the computed range updates
- `calculator_complete` — fires once, the first time an estimate is shown
- `related_article_click` — click on a related-guide link from a tool page

Allowed parameters: `tool_id`, `field_id`, `href`. Do not collect exact user
location, vehicle identifiers, free-text personal details, or full input
payloads — the engine only ever reports which field changed, not its value.
