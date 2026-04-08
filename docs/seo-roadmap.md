# SEO Roadmap

This roadmap is built around the current keyword scoring logic in [`scripts/keyword_research.py`](/Users/matt/Repos/TowWithTheFlow/scripts/keyword_research.py) and the publish-order logic in [`scripts/generate_post.py`](/Users/matt/Repos/TowWithTheFlow/scripts/generate_post.py).

Ranking method:
- Prioritize keywords with the best blend of search demand, urgency, lower competition, and monetization.
- Favor scenarios where a stressed driver needs an answer fast.
- De-prioritize weak modifier clones that only add a season, time of day, or random city unless the modifier changes the answer meaningfully.

These rankings are inferred from the current backlog, live SERP makeup, Google suggestion depth, and competition patterns. They are not exact Google Ads search-volume numbers.

## Main Site First

Priority 1. Publish these first on the main site.

1. `[9] car wont shift into drive need tow truck`
2. `[9] car leaking fluid underneath emergency tow`
3. `[9] car shaking violently while driving tow needed`
4. `[9] tire blowout on highway emergency tow cost`
5. `[8] car overheating red light on dashboard what to do`
6. `[8] roadside assistance vs calling tow truck direct`
7. `[8] car key broke in ignition need tow truck`
8. `[8] car breaks down on bridge who to call`
9. `[8] locked keys in car with engine running cost`
10. `[8] car slides off road in ice who pays towing`
11. `[7] does geico cover towing after breakdown`
12. `[7] does state farm pay for towing after accident`
13. `[7] does usaa cover emergency roadside towing costs`
14. `[7] how much to tow car 100 miles interstate`
15. `[7] flat tire on freeway no spare tire options`

Priority 2. Publish after the first cluster is live and internally linked.

1. `[7] how long can you drive with bad alternator`
2. `[7] coolant leak emergency can i drive home`
3. `[7] car wont shift out of park roadside help`
4. `[7] car hydroplaned into ditch towing options`
5. `[6] brake pedal goes to floor while driving`
6. `[6] car shaking when braking at highway speeds`
7. `[6] strange smell from car vents while driving`
8. `tire blowout on highway what to do`
9. `dead battery no jumper cables options`
10. `who pays towing costs after not at fault accident`

Priority 3. Hold these until stronger core pages exist.

1. `how long does a tow truck take to arrive`
2. `roadside assistance response time average`
3. `car breaks down no cell service what to do`
4. `car breaks down in bad neighborhood what to do`
5. `smoke coming from hood what to do`
6. `car wont move in drive or reverse`
7. `can i tow my car with a rope`
8. `how to push a car safely`
9. `towing a car without keys how to`
10. Modifier clones like `in winter`, `at night`, and random city variants

## Feeder Role

The feeder is a support asset, not the primary authority site. Use it to reinforce the main site around cost and comparison intent.

Best feeder targets next:

1. `[8] towing cost after accident`
2. `[8] towing cost without insurance`
3. `[8] towing cost for long distance`
4. `[8] towing cost broken down on highway`
5. `[8] towing cost AAA vs no membership`
6. `[7] emergency towing cost at night`
7. `[7] towing cost per mile national average`
8. `[7] flatbed towing cost vs wheel lift`
9. `[7] towing cost highway vs city`
10. `[7] towing cost electric vehicle`
11. `[6] towing cost luxury car`
12. `[6] towing cost pickup truck`

Use the feeder mostly for:
- cost breakdowns
- comparison pages
- vehicle-specific price modifiers
- after-hours and distance modifiers

Avoid using the feeder for:
- the main emergency troubleshooting topics
- your strongest “what should I do right now” topics
- brand-defining cornerstone pages

## Publishing Cadence

Recommended cadence:

1. Publish 3 to 5 main-site articles for every 1 feeder article.
2. Complete the top 10 main-site pages before expanding into many modifiers.
3. Add feeder posts only when they naturally support a published main-site article.
4. Refresh the top winners every 30 to 60 days with tighter intros, FAQs, and better internal links.

## Linking Rules

For every new main-site article:

1. Link to 3 to 5 closely related main-site articles.
2. Link to 1 cost or insurance explainer when relevant.
3. Add 1 short FAQ section only if it answers a real follow-up query.

For every new feeder article:

1. Canonical to the main site where appropriate.
2. Include a contextual backlink to the strongest matching main-site page.
3. Do not create feeder content that competes head-on with your best main page.
