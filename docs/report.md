# The client report

`report.html` is self-contained (inline CSS and SVG, no external requests) and prints to A4. `report.pdf` is rendered from it with Playwright Chromium, with a running header (client, brand) and page numbers.

## Sections

1. **Cover**: brand, client, URL, three score rings (overall, Search SEO, AI Visibility), one-paragraph verdict, prepared for / by, date, pages analysed.
2. **Contents** and **How to read this report**: scoring in plain words, severity legend, lanes.
3. **Executive summary**: narrative paragraphs generated from the data (score, biggest problems, strongest and weakest areas, AI access, projection, unmeasured areas), score rings, severity donut, scores-by-area table, "Do this week" (top 3), top priorities, what is already working.
4. **Crawl overview**: pages crawled, unique sitemap URLs, URLs discovered, completeness, indexable pages, server response, documents, platform, HTTP status chart, scores chart.
5. **Priority action list**: every issue with severity, area, affected count, effort and owner, linked to its detail card.
6. **One chapter per category** (Technical, Content and AEO, Structured Data, AI Visibility, Local, E-commerce, Performance): intro in client language, score ring, counts, the full table of checks performed (issue / note / pass / not measured), then a detail card per finding with What we checked, What we found (evidence), Why it matters (plus business impact), How to fix (numbered steps), How to verify, owner, lane, effort, reference link.
7. **AI crawler access in detail**: robots.txt status per bot with roles, live server response per bot (homepage), discovery files (llms.txt, llms-full.txt, feed, markdown negotiation), brand entity names and sameAs, least and most quotable pages with citability breakdown.
8. **Performance detail**: real-user Core Web Vitals with thresholds, lab metrics, biggest savings, diagnostics (or an honest "not measured" page).
9. **Key page scorecards**: one representative page per template with title and description lengths, H1, words, links, schema, citability and flags.
10. **Page inventory**: first 300 pages with flags; the full inventory is in `pages.csv`.
11. **90-day roadmap**: projected scores after each phase, then phase 1 (unblock and quick wins), phase 2 (structural), phase 3 (content, authority, polish) with owner and lane.
12. **Glossary**: 30 terms in plain English.
13. **Methodology and limits**, including "What this audit did not check".

## Branding

`run_audit.py ... --client "Name" --prepared-by "Person, Agency" --brand "Agency" --accent "#hex" --logo URL`, or re-render an existing audit without crawling: `rerender.py OUT_DIR --pdf --client ... --brand ...`.

## Companion files

- `findings.csv`: one row per finding, ticket-ready (severity, category, id, title, affected, effort, lane, owner, why, fix, evidence, pages).
- `pages.csv`: one row per crawled page with every measured field.
- `pages.jsonl`: full parsed page records; `crawl.db`: SQLite with pages and sitemap URLs for ad-hoc queries and `--resume`.
- `summary.md`: short Markdown summary for chat or email.
