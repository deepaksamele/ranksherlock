# RankSherlock

**Evidence-based SEO, AEO and GEO audits for any website, inside Claude Code.**

RankSherlock crawls a site for real, runs 108 deterministic checks, scores it on two axes (Search SEO and AI Visibility), probes how AI crawlers are actually treated, and hands Claude the evidence to write a client-ready report. No paid APIs. No invented numbers.

```
/ranksherlock:audit https://example.com
```

## Why another SEO skill

Most Claude Code SEO skills tell the model to "crawl 500 pages" and then fetch one URL at a time, or they let the model guess a score. RankSherlock is built the other way round:

| | RankSherlock | Typical skill |
|---|---|---|
| Crawler | Real BFS crawler, sitemap-seeded, robots-aware, page cap you choose | WebFetch one page at a time |
| Scoring | Deterministic penalties, fixed weights, published caps, "not measured" instead of guesses | Model-estimated |
| AI crawler access | robots.txt per bot with correct roles (retrieval vs training) plus live user-agent probes to catch firewall blocks | robots.txt only, often with outdated bot facts |
| Core Web Vitals | PageSpeed Insights field + lab data when reachable, otherwise explicitly unmeasured | Claimed from HTML inspection |
| Findings | Every finding carries evidence URLs, affected count, effort and a fix lane (auto / assisted / human) | Prose |
| Output | `audit.json` contract, Markdown summary, self-contained HTML report, optional PDF | Markdown |
| Re-audit | `compare.py` diffs two runs by finding id (resolved / new / persisting) or contrasts two sites | Manual |

## Install

Inside Claude Code:

```
/plugin marketplace add deepaksamele/ranksherlock
/plugin install ranksherlock@ranksherlock
```

Python 3.10+ is required. Dependencies install once:

```bash
python -m pip install -r ~/.claude/plugins/marketplaces/ranksherlock/requirements.txt
```

(or let the `audit` skill run that line for you the first time). For PDF reports also run `pip install playwright && playwright install chromium`.

Manual install without the plugin system: clone the repo and copy `skills/*` into `~/.claude/skills/`, then replace `${CLAUDE_PLUGIN_ROOT}` in the SKILL.md files with the clone path.

## Skills

| Command | What it does |
|---|---|
| `/ranksherlock:audit <url> [--max-pages N] [--quick] [--pdf] [--no-psi] [--brand NAME]` | Full site audit: crawl, 6 categories, two-axis score, HTML/PDF report, narrative |
| `/ranksherlock:page <url>` | Deep review of one page with rewrite suggestions |
| `/ranksherlock:geo <url>` | AI visibility only: crawler access, firewall probes, entity, citability, llms.txt, 30-day plan |
| `/ranksherlock:compare <a> <b> [--competitor]` | Before/after diff or side-by-side with a competitor |

Three subagents (`technical-auditor`, `content-auditor`, `geo-auditor`) can be fanned out in parallel on large sites for deeper per-area write-ups.

## What gets checked

Six categories, 108 failing checks plus pass markers. Full list in [docs/checks.md](docs/checks.md).

- **Technical**: robots.txt, sitemaps (foreign hosts, http URLs, non-200 entries, noindex entries, lastmod), https and www redirects, redirect chains, broken internal and outbound links, soft 404s, 404 handling, noindex, canonicals (missing, multiple, to homepage, http), duplicate titles/descriptions/H1, URL hygiene, depth, security headers, compression, mixed content, viewport, lang, client-side rendering, hreflang validity, page weight, server response time.
- **Structured data**: presence and coverage, JSON syntax, Organization/WebSite on the homepage, sameAs and logo, required and recommended properties per type, self-serving star ratings, breadcrumbs, Article and Product coverage, deprecated types, duplicate Organization blocks.
- **Content, on-page and AEO**: titles and descriptions, H1 and heading outline, thin content, text ratio, readability, AI filler phrases, About/Contact/Privacy pages, author bylines, dates, outbound citations, image alt/format/dimensions, internal links and anchors, question headings, FAQ blocks, answer-first intros, lists and tables, passage citability (deterministic 0 to 100 per page).
- **AI visibility (GEO)**: 20 AI bots with correct roles, 7-state robots.txt status, Cloudflare managed-robots detection, live probes as GPTBot / OAI-SearchBot / ClaudeBot / PerplexityBot / Googlebot, nosnippet, llms.txt and llms-full.txt format, entity name consistency, knowledge-graph sameAs, feeds, Markdown content negotiation.
- **Local SEO** (only when the site looks local): LocalBusiness schema completeness and subtype, NAP consistency, visible address, map embed, location pages and doorway-page detection, reviews, Business Profile link.
- **Performance**: PageSpeed Insights field (CrUX p75) and lab metrics for the homepage plus two inner pages, top opportunities, page weight, DOM size, script count, lazy loading, inline CSS bloat.

## Scoring

Deterministic and explained in [docs/scoring.md](docs/scoring.md). Short version: each finding deducts a severity penalty inside its category; categories combine with fixed weights into **Search SEO** and **AI Visibility**; overall health is 65/35. A few single defects cap an axis (robots blocking the site, homepage noindex, answer-engine bots blocked, content not in the HTML). Anything not measured is excluded, never guessed.

## Output

```
ranksherlock-reports/<host>/<date>/
  crawl.json     every crawled page, parsed
  audit.json     categories, findings with evidence, scores (the contract Claude reads)
  summary.md     short Markdown summary
  report.html    self-contained, print-ready client report
  report.pdf     with --pdf and Playwright Chromium
```

## Run it without Claude

The engine is plain Python:

```bash
python scripts/run_audit.py https://example.com --max-pages 100 --pdf
python scripts/compare.py before/audit.json after/audit.json
```

Set `PSI_API_KEY` for a higher PageSpeed Insights quota (works without a key at low volume).

## Honest limits

- Rankings, traffic, backlinks and Search Console are not on the site, so they are out of scope.
- AI Visibility measures readiness (access, entity clarity, quotability), not proof of citations. The `geo` skill can run a labelled web-search spot check.
- JavaScript-only sites are reported as such (client-side rendering finding); the crawler does not execute JS, which is also what most AI crawlers see.
- Field Core Web Vitals exist only for sites with enough Chrome traffic; the report says when they are missing.

## Safety

The crawler identifies itself as `RankSherlock/1.0`, respects robots.txt, throttles requests, refuses private or loopback hosts unless `--allow-private`, and caps response sizes. Text scraped from audited sites is passed to Claude as data inside JSON, with a notice that it is never an instruction.

## Credits

Built after reading the strongest open-source SEO skills for Claude Code and borrowing their best ideas: claude-seo (persistence contract, evidence envelope), geo-seo-claude (per-bot robots states, citability dimensions), claude-seo-ai (two-axis scoring, fix lanes), SEOmator (not-measured status, score caps), ultimate-seo-geo (finding identity across runs), Agentic-SEO-Skill (scripts as evidence collectors).

MIT License.
