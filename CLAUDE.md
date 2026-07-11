# CLAUDE.md — TowWithTheFlow Agent Instructions

This file is read by every agent that works on this repo. Follow these rules without exception.

---

## Automation First — Never Ask the User to Do Manual Steps

**Always wire it up yourself.** If a task requires adding GitHub secrets, environment variables, API keys, or any configuration to an external service — do it programmatically. Do not ask the user to go to the GitHub UI, Vercel dashboard, or any other UI if there is a CLI or API available.

**For GitHub secrets specifically**, use the `gh` CLI:
```
gh secret set SECRET_NAME --body "value" --repo Lordshrrred/TowWithTheFlow
```
The user is authenticated via keyring (account: Lordshrrred). This works from the terminal right now — use it.

**For Vercel env vars**, use the `vercel env add` CLI or Vercel API.

**Rule:** If you can do it in code or via CLI, do it. If you're about to write "you'll need to go to GitHub and add..." — stop and do it yourself instead.

---

## Project Overview

**Tow With The Flow** — a Hugo-based content site + automated multi-platform syndication engine for a Denver towing/roadside service business.

### Key Scripts
| Script | Purpose |
|--------|---------|
| `scripts/generate_post.py` | Generate daily blog posts via Claude API |
| `scripts/syndicate_post.py` | Syndicate new posts to 5 platforms |
| `scripts/syndicate_backlog.py` | Syndicate 1 oldest unsynced post/day |
| `scripts/syndicate_blogger_backlog.py` | Blogger-specific backlog |
| `scripts/syndicate_wordpress_backlog.py` | WordPress-specific backlog |
| `scripts/build_dashboard.py` | Rebuild the syndication/analytics/SEO dashboards |
| `scripts/dashboard_template.html` | Syndication dashboard frontend template |
| `scripts/keyword_research.py` | Discover + score new keyword opportunities (weekly) |
| `scripts/competitive_research.py` | Manual competitive research via Claude web search; never scheduled |
| `scripts/build_seo_data.py` | Aggregate keywords/Search Console/GA4/backlink/manual research data into `static/data/seo.json` for the SEO dashboard tab |
| `scripts/clusters.py` | Content-cluster taxonomy definitions (keyword/title -> cluster slug) |
| `scripts/assign_clusters.py` | Backfills the `clusters:` frontmatter field on existing posts from clusters.py |
| `scripts/optimize_images.py` | One-time (re-runnable) pass to resize/recompress everything under static/images/ |
| `scripts/backfill_legacy_posts.py` | One-time pass to expand thin legacy posts and add a Common Questions/FAQ section site-wide |

### Content Clusters

Every post is assigned a cluster (see `scripts/clusters.py`) via the `clusters:` frontmatter field. Hugo turns this into taxonomy hub pages at `/clusters/<slug>/` (content in `content/clusters/<slug>/_index.md`), and `layouts/posts/single.html`'s "Related Guides" box links every post to its cluster-mates plus the hub page — this is the site's main internal-linking mechanism and needs no API calls to maintain. When adding a new cluster, update `clusters.py` and re-run `assign_clusters.py`.

**Hugo layout gotcha:** this project has its own root-level `layouts/` directory that overrides the theme (`themes/twtf/layouts/`) for taxonomy pages and the posts section. `layouts/_default/taxonomy.html` handles *both* the taxonomy list page (`/clusters/`) and individual term pages (`/clusters/<slug>/`) — `layouts/_default/term.html` is not used by this Hugo setup and should not be re-added without re-verifying. `layouts/posts/single.html` (not the theme's `_default/single.html`) is what actually renders every post.

### FAQ Schema

Posts can carry a `faq:` frontmatter field (list of `{q, a}`) sourced from a "## Common Questions" section in the body (see `generate_post.py`'s `extract_faq_pairs`/`build_faq_yaml`). The theme (`themes/twtf/layouts/partials/head.html`) emits `FAQPage` JSON-LD from it automatically when present. Not every post has one — it's optional structured data, not a hard requirement.

### Platforms Syndicated To
1. Dev.to (split across two accounts — see below)
2. Tumblr
3. Blogger
4. WordPress
5. Feeder (internal blog)

### Tracking Files
- `scripts/synced-posts.txt` — all syndicated post slugs
- `scripts/syndication_log.txt` — per-platform result log (parsed by dashboard)
- `scripts/wordpress-synced-posts.txt`
- `scripts/blogger-synced-posts.txt`
- `scripts/feeder-synced.txt`

---

## Dev.to Account Split

Dev.to rate-limits aggressively. Two accounts are used:

| Account | Env Var | Used For | Frequency |
|---------|---------|---------|-----------|
| TWTF1 | `DevTO_TWTF1_API_Key` | Backlog (old posts) | 1/day at 14:30 UTC |
| TWTF2 | `DevTO_TWTF2_API_Key` | New posts (blog engine) | 2/day at 10:30 & 12:30 UTC |

- Set `DEVTO_ENABLED=false` to disable Dev.to cleanly without removing keys.
- Dev.to logs include `DEVTO_ACCOUNT_LABEL` so runs show whether TWTF1, TWTF2, legacy, or no account was selected.
- `DEVTO_API_KEY` is legacy fallback only; new work should use the TWTF1/TWTF2 split above.

### Feeder Generation

Feeder content is generated during syndication, not by a separate daily generation job.

---

## GitHub Actions Workflow

File: `.github/workflows/daily-post.yml`

| Job | Cron (UTC) | What it does |
|-----|-----------|-------------|
| `generate-general` | 09:00 | Generate general post via Claude |
| `generate-local` | 09:30 | Generate local/city post |
| `syndicate-new-1` | 10:30 | Syndicate general post (TWTF2 for Dev.to) |
| `syndicate-new-2` | 12:30 | Syndicate local post (TWTF2 for Dev.to) |
| `syndicate-backlog` | 14:30 | Syndicate 1 oldest backlog post (TWTF1 for Dev.to) |
| `syndicate-wordpress-backlog` | 14:35 | WordPress-specific backlog |
| `syndicate-blogger-backlog` | 14:40 | Blogger-specific backlog |

---

## Syndication Dashboard

- Template: `scripts/dashboard_template.html`
- Build script: `scripts/build_dashboard.py`
- Output: `static/dashboard/index.html`
- After changing the template or build_dashboard.py, run `python scripts/build_dashboard.py` and commit the output.
- Dashboard is password-protected (SHA256 of `DASHBOARD_PASSWORD`).
- Reads `syndication_log.txt` from GitHub raw for live status display.
