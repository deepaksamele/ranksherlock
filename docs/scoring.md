# How RankSherlock scores a site

The score is deterministic. Run the same site twice and you get the same number. Every point lost traces to a finding id with evidence.

## 1. Checks and findings

Each analyzer runs checks against the crawl. A failed check produces a finding with:

- `severity`: critical, high, medium, low, info
- `evidence`: the URLs or values that triggered it
- `affected_count`, `pages`
- `effort` (low / medium / high) and `lane` (auto / assisted / human)

Checks that cannot run (no PageSpeed data, not a local business) are recorded as skipped, never scored as failures.

## 2. Category score

Each category starts at 100 and loses a weighted penalty per finding:

| Severity | Penalty |
|---|---|
| critical | 10 |
| high | 6 |
| medium | 3 |
| low | 1 |
| info | 0 |

Category score = 100 minus (penalty / 40) x 100, floored at 0. So four high findings and two mediums (30 points) leave a category at 25.

Categories: technical, content (on-page, E-E-A-T, AEO, images, internal links), schema, performance, geo, local. `local` and `performance` are measured only when applicable or when PageSpeed Insights answered.

## 3. Two axes

Search SEO and AI Visibility weigh the same categories differently. Unmeasured categories are dropped and the remaining weights re-normalised.

| Category | Search SEO | AI Visibility |
|---|---|---|
| technical | 30 | 15 |
| content | 25 | 30 |
| schema | 12 | 20 |
| performance | 18 | 0 |
| local | 10 | 0 |
| geo | 5 | 35 |

Overall health = 65% Search SEO + 35% AI Visibility.

## 4. Caps

A few single defects make a high score misleading, so they cap an axis. The report lists each cap with the uncapped value.

| Finding | Cap | Axis |
|---|---|---|
| robots.txt blocks the whole site | 20 | both |
| homepage noindex | 25 | both |
| pages canonicalise to the homepage | 45 | search |
| no HTTPS | 55 | search |
| answer-engine crawlers blocked in robots.txt | 40 | ai |
| firewall challenges AI crawlers | 45 | ai |
| content not in the HTML (client-side rendering) | 50 | ai |
| homepage nosnippet | 30 | ai |
| no structured data at all | 70 | ai |

## 5. Grades

A 90+, B 80 to 89, C 70 to 79, D 60 to 69, F below 60. An axis with no measured category is N/A, not F.

## 6. What the score does not include

Rankings, traffic, backlinks, Search Console data and actual AI citations are not crawlable from the site, so they are out of scope. The `geo` skill can run a labelled spot check with web search. Treat the AI Visibility axis as readiness, not proof of citations.

## 7. Changing the model

Weights live in `scripts/ranksherlock/score.py` (`SEARCH_WEIGHTS`, `AI_WEIGHTS`, `OVERALL_MIX`, cap rules) and penalties in `scripts/ranksherlock/findings.py`. Bump `scoring_version` in `score.py` when you change them; `compare.py` refuses to treat runs with different versions as comparable.
