# The client report

`report.html` is self-contained (inline CSS and SVG, no external requests). On screen it shows a side navigation and section cards; printed, the same file becomes an A4 document with a full-bleed cover, a running header and page numbers. `report.pdf` is rendered from it with Playwright Chromium using the report's own CSS page rules.

## Design system

- One ink colour (navy), one accent (`--accent`, default `#2563eb`, set with `--accent`), muted status colours for scores and severities.
- Scores use 270-degree gauges; areas use horizontal bars; severities use tinted chips; labels are small caps; tables use hairlines only.
- Every finding is a card with a severity edge and labelled rows: what we checked, what we found (evidence panel), why it matters, business impact, how to fix (numbered steps), how to verify, reference.
- Print rules live in the CSS: `@page` margins and margin boxes (client and brand in the header, date and "Page X of Y" in the footer), a named `cover` page with zero margins, and break rules that keep headings with their content while letting long cards flow across pages.

## Sections

1. **Cover**: brand, client, URL, overall gauge, Search SEO and AI visibility bars, issue counts, prepared for / by, date, scope.
2. **01 Executive summary**: one-sentence verdict, three gauges, pages / issues / checks tiles, score by area, issues by severity, key takeaways, "do this week", what is already working.
3. **Contents** with area scores, plus a legend: how scores work, severity meanings, who can do the work.
4. **Crawl overview**: eight fact tiles, HTTP status codes, click depth from the homepage, page types.
5. **Priority action list**: every issue with severity, area, affected count, effort and owner, linked to its card.
6. **One numbered chapter per audit area** (Technical, Content and AEO, Structured Data, AI Visibility, Local, E-commerce, Performance): introduction, gauge, four tiles, issues table, passed checks, then the finding cards.
7. **AI crawler access in detail**: readiness per AI platform, answer-engine crawlers and training crawlers (robots.txt status and live test), discovery files, brand entity, least and most quotable pages.
8. **Performance detail**: real-user Core Web Vitals, lab metrics, savings, diagnostics, templates sampled (or an honest "not measured" page).
9. **Key page scorecards**: one representative page per template.
10. **Page inventory**: first 250 pages on one line each; the full list is in `pages.csv`.
11. **90-day roadmap**: three phase cards with projected scores, a score trajectory chart, and an action table per phase.
12. **Glossary** and **Methodology and limits**, including what the audit did not check.

## Branding

`run_audit.py ... --client "Name" --prepared-by "Person, Agency" --brand "Agency" --accent "#hex" --logo URL`, or re-render an existing audit without crawling: `rerender.py OUT_DIR --pdf --client ... --brand ...`.

## Companion files

- `findings.csv`: one row per finding, ticket-ready.
- `pages.csv`: one row per crawled page with every measured field.
- `pages.jsonl`, `crawl.db`: full parsed page records for ad-hoc queries and `--resume`.
- `summary.md`: short Markdown summary for chat or email.

Client-language text lives in `scripts/ranksherlock/report_text.py` (chapter introductions, glossary) and `catalog_*.py` (per-check explanations); layout and CSS live in `report.py`.
