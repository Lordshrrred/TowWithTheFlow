# TWTF SEO Authority Engine Phase 2

This plan applies only to Tow With The Flow and TWTF-specific feeder support.
The existing daily blog publishing pipeline remains separate and should keep
publishing to `content/posts/` exactly as it does today.

## Architecture

Authority assets live outside the blog:

- `/tools/` for decision tools and high-utility interactive resources.
- `/calculators/` for towing, trailer, payload, fuel, stopping-distance, and recovery calculators.
- `/reference/` for legal, consumer, insurance, glossary, and comparison resources.
- `/checklists/` for printable or interactive safety checklists.
- `/data/` for original data resources, cost indexes, statistics, and reports.

Each asset should declare:

- `assetType`
- `description`
- `relatedPosts`
- `relatedAssets`
- `syndicationMode`
- `faq` where useful
- a hub/cluster relationship through `clusters`

## Backlog

The canonical backlog is `data/authority_backlog.json`. Use:

```bash
python3 scripts/authority_backlog.py --next
```

The selector intentionally does not publish anything. It only identifies the
highest-priority unfinished asset so the authority workflow can build correctly
instead of forcing incomplete work into a daily deadline.

## Cannibalization Review

Use:

```bash
python3 scripts/build_intent_map.py
```

Outputs:

- `reports/intent-map.json`
- `reports/intent-map.md`

The intent map flags likely overlap groups, metadata issues, and pages that may
need consolidation, stronger differentiation, canonicalization, or redirects.
It is a review queue, not an automatic merge tool.

## Hub Model

Primary hubs are backed by `content/clusters/*/_index.md` and the taxonomy
rules in `scripts/clusters.py`.

Initial hubs:

- Towing Costs
- Emergency Roadside Assistance
- Vehicle Recovery
- Insurance & Coverage
- State Towing Laws
- Consumer Rights
- Trailer & RV Towing
- Commercial Towing
- Heavy-Duty Recovery
- Emergency Checklists
- Towing Calculators
- Vehicle Safety

## Syndication Defaults

Authority assets should preserve TWTF as the primary source:

- Calculators and decision tools: teaser plus canonical backlink.
- Reference and data resources: summary plus canonical backlink.
- Checklists: summary or excerpt plus canonical backlink.
- Legal resources: summary only unless reviewed.
- Interactive pages should not be duplicated as full articles on external platforms.

## Next Implementation Step

After the foundation is reviewed and committed, build the first reusable asset
template and first asset as a separate work item:

1. Tow Cost Estimator
2. Should I Call a Tow Truck?
3. Dead Battery Troubleshooter
4. Flat Tire Decision Assistant
5. Road Trip Checklist
