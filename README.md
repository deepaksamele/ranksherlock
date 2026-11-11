# RankSherlock

**Whole-site SEO, AEO and GEO audits with a real crawler, 250+ deterministic checks and a client-ready report. Built for Claude Code.**

RankSherlock crawls the entire site (sitemaps plus every internal link, up to 50,000 pages), runs every check with evidence, scores it on two axes (Search SEO and AI Visibility), probes how AI crawlers are actually treated, and renders a branded HTML/PDF report that explains every finding in plain English: what we checked, what we found, why it matters, how to fix it, how to verify it. No paid APIs. No invented numbers.

```
/ranksherlock:audit https://example.com --pdf --client "Example Ltd"
```

## What makes it different

| | RankSherlock 2.0 | Typical audit skill |
|---|---|---|
| Crawler | Concurrent whole-site crawler: all sitemap files, BFS link depth, orphan detection, SQLite checkpoints, resume, polite back-off | Homepage plus a few pages, or WebFetch one URL at a time |
| Checks | 250+ deterministic checks across technical, content and AEO, schema, AI visibility, local, e-commerce and performance, each with evidence URLs | Prose judgement |
| Scoring | Severity-weighted with soft caps, two axes, business-type weighting, hard caps for blockers (shown as "capped from"), projected score after fixes, "not measured" never counted | Model-estimated number |
| AI visibility | 35 AI bots with roles (retrieval / user-fetch / training), robots.txt 7-state parsing, Content-Signal, live user-agent probes on homepage and inner pages, Cloudflare detection, llms.txt validation, Wikidata entity lookup, platform-by-platform readiness, passage citability | robots.txt only |
| Report | Cover, executive summary, every check (pass and fail), detail card per finding with steps and verification, AI bot tables, Core Web Vitals, key page scorecards, page inventory, 90-day roadmap with projected scores, glossary, methodology; PDF with page numbers; ticket-ready CSVs | Markdown |
| Re-audit | `compare.py` diffs two runs by finding id (resolved / new / persisting) | Manual |

## Install

Inside Claude Code:

```
/plugin marketplace add deepaksamele/ranksherlock
/plugin install ranksherlock@ranksherlock
```

Python 3.10+ is required. Dependencies install once (the `audit` skill runs this for you):

```bash
python -m pip install -r ~/.claude/plugins/marketplaces/ranksherlock/requirements.txt
```

For PDF reports also run `pip install playwright && playwright install chromium`. On Windows, if `python` opens the Microsoft Store, use `py`.

## Skills

| Command | What it does |
|---|---|
| `/ranksherlock:audit <url> [--quick] [--max-pages N] [--pdf] [--client NAME] [--brand NAME]` | Whole-site audit, all categories, two-axis score, HTML/PDF report, narrative and page rewrites |
| `/ranksherlock:page <url>` | Deep review of one page with rewritten title, description, H1 and opening paragraph |
| `/ranksherlock:geo <url>` | AI visibility only: bot access, firewall probes, Content-Signal, llms.txt, entity and Wikidata, citability, platform readiness, 30-day plan |
| `/ranksherlock:compare <a> <b> [--competitor]` | Before/after diff or side-by-side with a competitor |

Three subagents (`technical-auditor`, `content-auditor`, `geo-auditor`) can be fanned out in parallel on large sites.

## What gets checked

Seven categories; the full list with severities is in [docs/checks.md](docs/checks.md).

- **Technical** (100+ checks): robots.txt syntax and traps, sitemaps (index errors, 50k limit, size, duplicates, foreign hosts, http URLs, lastmod truthfulness, non-200, redirected, noindex and non-canonical entries, coverage gaps, orphans), https and www redirects, chains, temporary redirects, loops, meta refresh, broken links with the linking page, server errors, timeouts, soft 404s, 404 handling and custom 404 quality, noindex and nofollow directives, utility pages indexable, pagination and parameter duplicates, canonicals (missing, multiple, to homepage, cross-domain, http, conflicting with noindex, broken targets), duplicate titles, descriptions, H1s and exact-duplicate bodies, trailing-slash and double-slash duplicates, URL hygiene, click depth, security headers, compression, cache headers, mixed content, viewport and zoom lock, html lang, AMP, client-side rendering, hreflang (codes, self, return tags, x-default, protocol, non-canonical), outbound links, HTML size, server response, accessibility basics (empty links, unlabelled inputs, favicon, skip link), analytics and legacy tags.
- **Content, on-page and AEO** (70+): titles (missing, long, short, same as home, brand doubled, CMS defaults), descriptions, H1s, hierarchy, empty and UI-chrome headings, subheadings, page-type word floors, text ratio, placeholder text, template-duplicate copy, readability, filler phrases, table of contents, trust pages, contact and social links, author bylines, dates, stale content, outbound citations, media, YMYL reviewer lines, social proof, images (alt presence and quality, formats, dimensions, srcset, lazy hero, template images), internal links (count, density, generic anchors, mega menus, nofollow), question headings, FAQ, answer-first and definition openings, lists and tables, comparison tables, passage citability (deterministic 0 to 100), Open Graph and Twitter cards.
- **Structured data** (35+): presence and coverage, Microdata-only, JSON syntax, Organization and WebSite on the homepage (sameAs, logo, contactPoint, richness, SearchAction), required and recommended properties for 20+ types including nested offers and ratings, self-serving and unverifiable ratings, placeholders, http context, relative URLs, invalid dates, FAQ text not visible, entity name and url consistency across blocks, breadcrumbs, Article and Product coverage (ProductGroup aware), offers completeness, shipping and returns, VideoObject, deprecated types, FAQPage note, business-type schema opportunities, duplicate Organization blocks.
- **AI visibility** (25+): 35 bots with roles and 7-state robots.txt status, partial restrictions, Content-Signal, Cloudflare managed robots, live probes on homepage and inner pages (block, inconclusive, cloaked), nosnippet, noai, prompt-injection text, llms.txt and llms-full.txt validation with dead-link check, feeds, agents.md, RSL, markdown negotiation, entity name consistency, sameAs knowledge-graph anchors, About-page facts, Wikidata lookup, answer-sized paragraphs, citable facts, platform readiness.
- **Local SEO** (when detected or forced): LocalBusiness schema completeness and subtype, areaServed, Business Profile in sameAs, schema vs visible phone, multiple phones, phone on homepage, visible address, hours, map, location pages (presence, doorway copy, thin, scale gates), reviews, Business Profile link.
- **E-commerce** (for shops): thin and duplicated product copy, visible prices, product reviews and Q&A, duplicate listings, category copy, demo collections, shipping and returns pages, trust signals.
- **Performance**: PageSpeed Insights field (CrUX p75) and lab metrics for the homepage plus one page per template, TTFB, TBT, inner-template scores, opportunities and diagnostics, render-blocking scripts, third-party hosts, lazy loading, inline CSS, DOM size, CDN, preload and fetchpriority hints, image weight sampled with HEAD requests.

## Scoring

Deterministic and explained in [docs/scoring.md](docs/scoring.md). Each finding deducts severity points inside its category (with soft caps so many small issues cannot zero a category); categories combine with business-type-aware weights into **Search SEO** and **AI Visibility**; overall health is 65/35. A few single defects cap an axis and the report says so. Unmeasured areas are excluded, never guessed. The roadmap shows projected scores after each phase.

## Output

```
ranksherlock-reports/<host>/<date>/
  report.html    self-contained client report (see docs/report.md)
  report.pdf     with --pdf and Playwright Chromium
  audit.json     categories, findings with evidence and explanations, scores (the contract Claude reads)
  findings.csv   ticket-ready list of every finding
  pages.csv      one row per crawled page
  pages.jsonl    full parsed page records
  crawl.json     crawl summary (+ first 200 pages)
  crawl.db       SQLite: pages and sitemap URLs (enables --resume)
  summary.md     short Markdown summary
```

## Run it without Claude

```bash
python scripts/run_audit.py https://example.com --pdf --client "Example Ltd" --brand "My Agency"
python scripts/run_audit.py https://big-site.com --max-pages 50000 --workers 12 --rate 12 --max-minutes 240
python scripts/run_audit.py https://big-site.com --resume --out ranksherlock-reports/big-site.com/2026-10-29
python scripts/rerender.py ranksherlock-reports/example.com/2026-10-29 --pdf --accent "#1d4ed8"
python scripts/compare.py before/audit.json after/audit.json
```

Set `PSI_API_KEY` for a private PageSpeed Insights quota (the shared quota is exhausted quickly).

## Large sites

- Speed is about 5 to 10 pages per second depending on `--workers` / `--rate` and the host. 2,000 pages take 4 to 6 minutes; 50,000 pages take 1.5 to 3 hours.
- Every parsed page is written to `crawl.db` as it arrives, so an interrupted crawl continues with `--resume`.
- Memory stays bounded: full detail is kept for the first 500 pages (template analysis) and bulky per-page lists are trimmed for the rest; the full records stay in `crawl.db`.
- The crawler backs off automatically on 429/503 and returns to full speed when the host recovers.
- Word counts and readability are measured on the main content (navigation, header, footer and sidebars removed), while contact, address, hours and review signals are read from the full page.

## Honest limits

- Rankings, traffic, backlinks and Search Console are not on the site, so they are out of scope.
- AI Visibility measures readiness (access, entity clarity, quotability), not proof of citations. The `geo` skill can run a labelled web-search spot check.
- JavaScript-only sites are reported as such; the crawler does not execute JS, which is also what most AI crawlers see.
- Field Core Web Vitals exist only for sites with enough Chrome traffic; the report says when they are missing.

## Safety

The crawler identifies itself as `RankSherlock/2.0`, respects robots.txt, rate-limits and backs off on 429/503, refuses private or loopback hosts unless `--allow-private`, caps response sizes and persists to SQLite. Text scraped from audited sites is passed to Claude as data inside JSON, with a notice that it is never an instruction.

## Credits

Built after reading 45+ open-source SEO skills and auditors for Claude Code and borrowing their best ideas: claude-seo, geo-seo-claude, claude-seo-ai, SEOmator, ultimate-seo-geo, Agentic-SEO-Skill, Snippet tech-seo-audit, seranking seo-skills, lhitches claude-seo-skills, siteone-crawler, AndacGuven technical-seo-skill, do-audit, wonfull888 seo-audit and others.

MIT License.
