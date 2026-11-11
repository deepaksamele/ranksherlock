# How RankSherlock scores a site (scoring version 2)

The score is deterministic. Run the same site twice and you get the same number. Every point lost traces to a finding id with evidence.

## 1. Checks and findings

Each analyzer runs checks against the crawl. A failed check produces a finding with:

- `severity`: critical, high, medium, low, info
- `evidence`, `affected_count`, `pages`
- `effort` (low / medium / high), `lane` (auto / assisted / human), `owner`
- client-facing text from the catalog: `what`, `why`, `business_impact`, `steps`, `verify`, `ref`

Checks that cannot run (no PageSpeed data, not a local business, not a shop) are recorded as skipped and listed under "What this audit did not check", never scored as failures.

## 2. Category score

Each category starts at 100 and loses points per finding:

| Severity | Points | Soft cap |
|---|---|---|
| critical | 10 | 30 |
| high | 6 | 24 |
| medium | 3 | 15 |
| low | 1 | 6 |
| info | 0 | 0 |

Beyond the soft cap for a severity, further findings of that severity count at half weight, so forty low findings cannot zero a category on their own. Category score = 100 minus (penalty / 50) x 100, floored at 0.

Categories: technical, content (on-page, E-E-A-T, AEO, images, internal links), schema, geo, local (only when the site reads as local), ecommerce (only for shops), performance (only when PageSpeed Insights answered).

## 3. Two axes

Search SEO and AI Visibility weigh the categories differently. Unmeasured categories are dropped and the remaining weights re-normalised.

| Category | Search SEO | AI Visibility |
|---|---|---|
| technical | 28 | 15 |
| content | 24 | 30 |
| schema | 10 | 20 |
| performance | 16 | 0 |
| local | 10 | 0 |
| ecommerce | 7 | 0 |
| geo | 5 | 35 |

Business-type multipliers on the search axis (before normalisation): local business (local x1.6, schema x1.2), e-commerce (ecommerce x1.6, schema x1.4, performance x1.2), publisher (content x1.4, geo x1.4), SaaS (content x1.2, geo x1.3), finance (content x1.3, schema x1.2), healthcare (content x1.3, local x1.3).

Overall health = 65% Search SEO + 35% AI Visibility.

## 4. Caps

A few single defects make a high score misleading, so they cap an axis. The report lists each cap with the uncapped value.

| Finding | Cap | Axis |
|---|---|---|
| robots.txt blocks the whole site | 20 | both |
| homepage noindex | 25 | both |
| TLS certificate errors | 40 | both |
| pages canonicalise to the homepage | 45 | search |
| no HTTPS | 55 | search |
| answer-engine crawlers blocked in robots.txt | 40 | ai |
| firewall challenges AI crawlers | 45 | ai |
| content not in the HTML (client-side rendering) | 50 | ai |
| homepage nosnippet | 30 | ai |
| no structured data at all | 70 | ai |

## 5. Grades

A 90+, B 80 to 89, C 70 to 79, D 60 to 69, F below 60. An axis with no measured category is N/A, not F.

## 6. Projections

The roadmap recomputes the scores with the same model as if the findings in each phase were fixed: phase 1 (critical plus low-effort high/medium), phase 2 (plus the remaining high/medium that a developer can own), phase 3 (everything actionable). Projections are a guide to progress, not a traffic forecast.

## 7. What the score does not include

Rankings, traffic, backlinks, Search Console data and actual AI citations are not crawlable from the site, so they are out of scope. The `geo` skill can run a labelled spot check with web search. Treat the AI Visibility axis as readiness, not proof of citations.

## 8. Changing the model

Weights and caps live in `scripts/ranksherlock/score.py`; penalties and soft caps in `scripts/ranksherlock/findings.py`; client-facing text in `scripts/ranksherlock/catalog_*.py`. Bump `SCORING_VERSION` when you change weights; `compare.py` refuses to treat runs with different versions as comparable.
