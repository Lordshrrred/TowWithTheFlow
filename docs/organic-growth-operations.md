# Organic Growth Operations

## Publishing guardrails

- Publish only one page per defined keyword intent. A duplicate or near-duplicate is a reason to expand the existing guide, not create another URL.
- `scripts/consolidate_articles.py` previews repeated titles and identical bodies; `--execute` archives extra markdown privately, preserves the established complete original, rewrites internal links and installs permanent Vercel redirects. The generator rejects repeated returned titles or existing slugs instead of inventing a numbered duplicate.
- Keep the current four-post daily ceiling until Search Console produces enough impressions and clicks to rank opportunities by evidence.
- Every generated post must pass the cluster-health check and Hugo build before it is committed. Clusters provide the hub and related-guide links without additional API calls.

## Keyword and research loop

- Article writing uses Sonnet 5.5; keyword planning, variations, tool companions and repair suggestions use Haiku 5.5. The shared client removes unsupported sampling settings, bounds effort, and turns off up-front thinking for routine work. Text extraction rejects truncated output.

- Keep 45 to 90 publishing days of scored keyword inventory. Below 45 days, the research job resumes; above 90, it pauses. This avoids paid research churn.
- Use Search Console and GA4 daily for evidence. The normal report makes two requests to each service and makes no paid model, web-search, or rank-tracking calls.
- Use paid competitor research only for a specific decision with a defined cost cap, then turn validated findings into a curated keyword list or an existing-page improvement.

## Backlink safety plan

- Daily: audit the newest 40 syndicated articles and 40 WordPress pages.
- Weekly: run a complete, paced inventory audit. Blogger requests are limited to one per second to avoid rate limits.
- Treat rate limits and temporary server errors as unknown, never as missing backlinks. Repair only confirmed missing or wrong links.
- Missing platform records count toward the backlog. Inaccessible Blogger probes and incomplete verification are separate gaps, not proof that existing articles need republishing. Unavailable audit data never means a clear backlog.
- The audit accepts a direct link to the original Tow With The Flow article even when WordPress changed its own duplicate URL suffix.
- WordPress homepage/navigation links do not verify a specific article; its original article slug must match. Temporary WordPress HTTP failures remain unknown.
- Do not bulk republish old content. Repair only the affected destination post, preserve its publication date, and use small batches after confirmed failures.

## Success measures

- Zero confirmed missing backlinks on newly syndicated posts.
- A shrinking backlog before increasing publishing volume.
- More Search Console impressions, then click-through rate and page-one opportunities, rather than raw post count.
- Shared Claude calls log actual model/token/cache usage for future cost attribution without logging content or credentials.
