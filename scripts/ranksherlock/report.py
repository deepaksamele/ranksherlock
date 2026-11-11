"""Client-facing HTML report (print-ready, self-contained) and PDF via Playwright.

Structure: cover, contents, how to read, executive summary, crawl overview, one chapter per category
(intro, score, every check performed, detailed finding cards), AI visibility detail, performance detail,
page inventory, 90-day roadmap, glossary, methodology.
"""

from __future__ import annotations

import html
import math
import re
from collections import Counter
from datetime import date

SEV_COLORS = {"critical": "#b91c1c", "high": "#c2410c", "medium": "#b45309", "low": "#1d4ed8", "info": "#4b5563"}
SEV_LABEL = {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low", "info": "Info"}
CAT_ORDER = ["technical", "content", "schema", "geo", "local", "ecommerce", "performance"]
CAT_LABELS = {"technical": "Technical SEO", "content": "Content, On-page and Answer Readiness", "schema": "Structured Data", "performance": "Performance and Core Web Vitals", "geo": "AI Visibility (GEO)", "local": "Local SEO", "ecommerce": "E-commerce"}
CAT_SHORT = {"technical": "Technical", "content": "Content and AEO", "schema": "Schema", "performance": "Performance", "geo": "AI Visibility", "local": "Local", "ecommerce": "E-commerce"}
CAT_INTRO = {
    "technical": "Technical SEO is the plumbing. It decides whether search engines and AI crawlers can reach every page, understand which version of a URL is the real one, and trust the site enough to index it. Problems here silently cap everything else: a brilliant article on a page that returns the wrong status code, or that is blocked in robots.txt, earns nothing. This chapter covers crawlability, indexability, redirects, canonical tags, duplicate pages, sitemap quality, security headers, mobile readiness and JavaScript rendering.",
    "content": "Content is what actually ranks and gets quoted. Google judges pages on experience, expertise, authoritativeness and trust (E-E-A-T), and answer engines such as ChatGPT, Perplexity and Google AI Overviews lift short, self-contained passages that answer a question directly. This chapter looks at titles, descriptions, headings, depth, readability, author and date signals, trust pages, images, internal links, and how answer-ready each page is.",
    "schema": "Structured data (schema.org JSON-LD) is a machine-readable summary of what each page is about: the organisation, its products, articles, FAQs, reviews and breadcrumbs. Search engines use it for rich results (stars, prices, FAQs, sitelinks) and AI systems use it to confirm facts about the business. Wrong or missing schema is a missed opportunity; self-serving or fake schema is a policy risk.",
    "geo": "AI visibility (often called GEO, generative engine optimisation) measures whether AI answer engines can fetch, understand and quote the site. Three layers matter: access (robots.txt, firewall rules and JavaScript rendering decide whether AI crawlers see anything), understanding (a consistent brand entity with Organization schema and profile links) and quotability (passages written as direct, factual, sourced answers). Training bots and retrieval bots are different: blocking training bots is a policy choice, blocking retrieval bots removes the site from AI answers.",
    "local": "Local SEO decides whether the business shows up when someone nearby searches for the service, including map results and 'near me' answers from AI assistants. It depends on a consistent name, address and phone number, LocalBusiness schema that matches the Google Business Profile, genuinely local pages for each service area, and visible reviews.",
    "ecommerce": "Online shops win or lose on category and product pages. This chapter checks whether those pages carry enough unique copy to rank, whether prices, reviews and buyer questions are visible to crawlers and AI shopping assistants, whether the catalogue is free of duplicate and demo listings, and whether the trust pages shoppers and Google Merchant Center expect (shipping, returns, secure payment) exist and are linked.",
    "performance": "Performance is user experience measured in numbers. Google's Core Web Vitals (how fast the main content appears, how quickly the page responds to taps, and how much the layout jumps around) are a ranking signal and a conversion driver. This chapter uses real-user data from Google when available, plus lab measurements and HTML-level checks that apply to every page crawled.",
}
LANE_LABEL = {"auto": "Developer can apply directly", "assisted": "Apply with review", "human": "Needs content or business input"}
OWNER_DEFAULT = {"technical": "Developer / hosting", "content": "Content team", "schema": "Developer", "geo": "Developer + content", "local": "Marketing", "performance": "Developer / hosting", "ecommerce": "Store team"}

GLOSSARY = [
    ("AEO (Answer Engine Optimisation)", "Writing and structuring pages so that search engines and AI assistants can lift a direct answer from them (featured snippets, People Also Ask, AI answers)."),
    ("AI Overviews / AI Mode", "Google's AI-generated answers shown above the classic results. They quote pages Googlebot can crawl and that allow snippets."),
    ("Canonical tag", "A line in the page's HTML that names the preferred URL when several URLs show the same content. Stops duplicate versions competing with each other."),
    ("Citability", "A 0 to 100 score RankSherlock assigns to a passage based on how self-contained, factual, structured and sourced it is. Higher means more likely to be quoted by an AI engine."),
    ("Core Web Vitals (CWV)", "Google's three user-experience metrics: LCP (loading), INP (responsiveness) and CLS (visual stability). Measured on real Chrome users over 28 days."),
    ("Crawl budget", "How many pages a search engine is willing to fetch from a site in a given period. Wasted on redirects, errors and duplicates."),
    ("Crawlability", "Whether a bot can reach a page: not blocked by robots.txt or a firewall, linked from somewhere, and returning a normal status code."),
    ("E-E-A-T", "Experience, Expertise, Authoritativeness and Trust: the qualities Google's quality raters look for. Shown through authors, credentials, sources, contact details and reviews."),
    ("GEO (Generative Engine Optimisation)", "Making a site visible and quotable inside AI answer engines such as ChatGPT, Perplexity, Claude and Google AI Overviews."),
    ("H1 / H2 / H3", "Heading levels in the page. The H1 is the page's headline; H2 and H3 structure the sections underneath. Answer engines use them to find the relevant passage."),
    ("hreflang", "Tags that tell search engines which language or country version of a page to show to which users."),
    ("Indexability", "Whether a crawled page is allowed into the search index: not noindex, not canonicalised elsewhere, returning 200."),
    ("JSON-LD", "The recommended format for structured data: a small block of JSON inside a script tag in the page."),
    ("LCP (Largest Contentful Paint)", "Time until the biggest visible element (usually the hero image or headline) is rendered. Good is under 2.5 seconds."),
    ("INP (Interaction to Next Paint)", "How long the page takes to respond visually after a tap or click. Good is under 200 ms."),
    ("CLS (Cumulative Layout Shift)", "How much the layout jumps while loading. Good is under 0.1."),
    ("llms.txt", "An emerging convention: a Markdown file at /llms.txt that gives AI agents a curated map of the most important pages. Cheap to add; no confirmed ranking weight yet."),
    ("Meta description", "The short summary under the title in search results. Google rewrites weak ones; a good one lifts click-through rate."),
    ("NAP", "Name, Address, Phone. Must be identical across the website, Google Business Profile and directories for local rankings."),
    ("noindex", "A directive (meta tag or HTTP header) that tells search engines not to list a page."),
    ("Orphan page", "A page that exists (often in the sitemap) but that no other page links to. Rarely crawled, rarely ranked, and unreachable by browsing."),
    ("PageSpeed Insights", "Google's free tool and API that reports Core Web Vitals field data and Lighthouse lab scores for a URL."),
    ("Retrieval bot vs training bot", "Retrieval bots (OAI-SearchBot, PerplexityBot, Claude-SearchBot, Googlebot, Bingbot) fetch pages to cite them in answers. Training bots (GPTBot, ClaudeBot, CCBot) collect data for future models. Blocking the first removes the site from AI answers; blocking the second is a policy choice."),
    ("Rich results", "Enhanced search listings (star ratings, prices, FAQs, breadcrumbs, sitelinks) that depend on valid structured data."),
    ("robots.txt", "A text file at the site root that tells crawlers which paths they may fetch. One wrong line can hide the whole site."),
    ("Schema.org", "The shared vocabulary for structured data types such as Organization, Product, Article, FAQPage and LocalBusiness."),
    ("Sitemap (XML)", "A file listing the URLs a site wants indexed, with optional last-modified dates. Should contain only final, 200-status, indexable URLs."),
    ("Soft 404", "A page that says 'not found' but returns status 200, so search engines index it as a real (thin) page."),
    ("Title tag", "The page title shown in the browser tab and as the blue link in search results. The strongest on-page ranking signal."),
    ("TTFB (Time to First Byte)", "How long the server takes to start sending the page. High TTFB caps every other speed metric."),
]


def e(s) -> str:
    return html.escape(str(s if s is not None else ""))


def grade_color(score) -> str:
    if score is None:
        return "#6b7280"
    return "#15803d" if score >= 80 else "#65a30d" if score >= 70 else "#ca8a04" if score >= 60 else "#dc2626"


def grade_word(score) -> str:
    if score is None:
        return "not measured"
    return "excellent" if score >= 90 else "good" if score >= 80 else "fair" if score >= 70 else "weak" if score >= 60 else "poor"


def ring(score, grade, size=150, stroke=14, label="") -> str:
    """SVG score ring."""
    r = (size - stroke) / 2
    circ = 2 * math.pi * r
    val = 0 if score is None else max(0, min(100, score))
    dash = circ * val / 100
    color = grade_color(score)
    txt = "n/a" if score is None else str(score)
    return f"""<svg class="ring" width="{size}" height="{size}" viewBox="0 0 {size} {size}" role="img" aria-label="{e(label)} {txt}">
<circle cx="{size/2}" cy="{size/2}" r="{r}" fill="none" stroke="#e5e7eb" stroke-width="{stroke}"/>
<circle cx="{size/2}" cy="{size/2}" r="{r}" fill="none" stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" stroke-dasharray="{dash:.1f} {circ:.1f}" transform="rotate(-90 {size/2} {size/2})"/>
<text x="50%" y="50%" text-anchor="middle" dominant-baseline="central" font-size="{size*0.27:.0f}" font-weight="800" fill="{color}">{txt}</text>
<text x="50%" y="{size*0.72:.0f}" text-anchor="middle" font-size="{size*0.1:.0f}" font-weight="700" fill="#6b7280">{e(grade)}</text>
</svg>"""


def bar(score, width=220, height=12) -> str:
    val = 0 if score is None else max(0, min(100, score))
    return f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}"><rect width="{width}" height="{height}" rx="6" fill="#e5e7eb"/><rect width="{width*val/100:.1f}" height="{height}" rx="6" fill="{grade_color(score)}"/></svg>"""


def donut(counts: dict, size=140) -> str:
    total = sum(counts.values()) or 1
    r = size / 2 - 14
    circ = 2 * math.pi * r
    offset = 0.0
    arcs = ""
    for sev in ("critical", "high", "medium", "low", "info"):
        n = counts.get(sev, 0)
        if not n:
            continue
        seg = circ * n / total
        arcs += f'<circle cx="{size/2}" cy="{size/2}" r="{r}" fill="none" stroke="{SEV_COLORS[sev]}" stroke-width="22" stroke-dasharray="{seg:.1f} {circ:.1f}" stroke-dashoffset="{-offset:.1f}" transform="rotate(-90 {size/2} {size/2})"/>'
        offset += seg
    return f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">{arcs}<text x="50%" y="50%" text-anchor="middle" dominant-baseline="central" font-size="26" font-weight="800" fill="#111827">{sum(counts.values())}</text><text x="50%" y="{size*0.68:.0f}" text-anchor="middle" font-size="10" fill="#6b7280">findings</text></svg>'


def hbar_chart(rows: list[tuple[str, int, int]], width=520) -> str:
    """rows: (label, value, max)."""
    if not rows:
        return ""
    h = 22 * len(rows) + 6
    out = [f'<svg width="{width}" height="{h}" viewBox="0 0 {width} {h}" font-size="11">']
    for i, (label, val, mx) in enumerate(rows):
        y = i * 22 + 4
        w = (width - 190) * (val / mx if mx else 0)
        out.append(f'<text x="0" y="{y+12}" fill="#374151">{e(label[:28])}</text><rect x="150" y="{y+2}" width="{width-190}" height="14" rx="4" fill="#f3f4f6"/><rect x="150" y="{y+2}" width="{max(w,0):.1f}" height="14" rx="4" fill="#0f766e"/><text x="{width-34}" y="{y+12}" fill="#374151">{val}</text>')
    out.append("</svg>")
    return "".join(out)


def narrative(audit: dict) -> list[str]:
    """Plain-language executive summary paragraphs built from the data, never guessed."""
    s = audit["scores"]
    site = audit["site"]
    cats = s["categories"]
    findings = s["findings"]
    crawl = audit["crawl"]
    host = site["host"]
    btype = site.get("business_type", "business")
    paras = []
    overall = s["overall"]
    paras.append(
        f"{host} scores {overall}/100 overall (grade {s['grade']}, {grade_word(overall)}). Search SEO readiness is {s['search_seo']['score']}/100 and AI visibility is {s['ai_visibility']['score']}/100. "
        f"We crawled {crawl['pages_crawled']:,} pages{' (the whole site)' if crawl.get('complete') else ''}, read the robots.txt and sitemap files, tested how the server treats AI crawlers, and ran {sum(c.get('passes', 0) + c.get('findings', 0) for c in cats.values())} checks across {len([c for c in cats.values() if c.get('measured', True)])} areas. The site runs on {site.get('platform') or 'an unidentified platform'} and reads as a {btype} site, so the recommendations below are weighted for that."
    )
    crit = [f for f in findings if f["severity"] == "critical"]
    high = [f for f in findings if f["severity"] == "high"]
    if crit:
        paras.append("The most urgent problems are " + "; ".join(f"{f['title'].lower()} ({f.get('affected_count', 1)} affected)" for f in crit[:3]) + ". These are the kind of defects that hold back every other improvement and should be fixed first.")
    elif high:
        paras.append("Nothing is critically broken. The biggest issues are " + "; ".join(f"{f['title'].lower()}" for f in high[:3]) + ". Each of these is explained with evidence and a fix in the chapters that follow.")
    else:
        paras.append("No critical or high-severity defects were found. The remaining items are refinements that lift rankings, click-through and AI citations rather than repairs.")
    strongest = sorted([(k, v) for k, v in cats.items() if v.get("measured", True)], key=lambda kv: -kv[1]["score"])[:2]
    weakest = sorted([(k, v) for k, v in cats.items() if v.get("measured", True)], key=lambda kv: kv[1]["score"])[:2]
    if strongest and weakest:
        paras.append(f"Strongest areas: {', '.join(f'{CAT_SHORT[k]} ({v['score']})' for k, v in strongest)}. Weakest areas: {', '.join(f'{CAT_SHORT[k]} ({v['score']})' for k, v in weakest)}. The roadmap at the end sequences the work so the weakest areas move first without disturbing what already works.")
    geo = audit["categories"].get("geo", {})
    bots = geo.get("bot_status", {})
    blocked = [b for b, i in bots.items() if i["role"] in ("retrieval", "user-fetch") and i["status"] in ("blocked", "blocked-by-wildcard")]
    probes = geo.get("ua_probes", {})
    challenged = [b for b, r in probes.items() if r.get("challenged")]
    if blocked or challenged:
        paras.append(f"AI answer engines cannot fully reach the site today: {'robots.txt blocks ' + ', '.join(blocked) if blocked else ''}{' and ' if blocked and challenged else ''}{'the firewall challenges ' + ', '.join(challenged) if challenged else ''}. Until that is fixed the brand cannot be cited by those engines no matter how good the content is.")
    else:
        avg_cit = audit["categories"].get("content", {}).get("avg_citability")
        paras.append(f"AI answer engines can fetch the site. The question is whether they will quote it: the average passage citability is {avg_cit}/100" + (", which is low; most pages open with preamble rather than a direct answer." if (avg_cit or 0) < 45 else ", a reasonable base to build on."))
    proj = s.get("projected", {})
    if proj.get("phase3") and proj["phase3"].get("overall") is not None and proj["phase3"]["overall"] > (overall or 0):
        target = "the high 90s" if proj["phase3"]["overall"] >= 97 else f"about {proj['phase3']['overall']}/100"
        paras.append(f"If every actionable finding in this report is fixed, the same scoring model projects an overall score in {target} (grade {proj['phase3']['grade']}), with roughly {proj['phase1']['overall']} reachable after the phase 1 quick wins alone. Scores are a guide to progress, not a traffic guarantee.")
    if s["unmeasured"]:
        paras.append("Not measured in this run: " + ", ".join(CAT_LABELS.get(u, u) for u in s["unmeasured"]) + ". Scores exclude these areas rather than guessing at them.")
    return paras


def finding_card(f: dict, idx: int) -> str:
    sev = f["severity"]
    ev = "".join(f"<li><code>{e(x)}</code></li>" for x in f.get("evidence", [])[:10])
    pages = f.get("pages", [])
    more_pages = ""
    if len(pages) > 10:
        more_pages = f"<p class='muted small'>Plus {len(pages) - 10} more affected URLs; the full list is in findings.csv.</p>"
    steps = f.get("steps") or []
    if steps:
        fix_html = "<ol>" + "".join(f"<li>{e(st)}</li>" for st in steps) + "</ol>"
    else:
        fix_html = f"<p>{e(f['fix'])}</p>"
    what = f.get("what") or ""
    verify = f.get("verify") or ""
    biz = f.get("business_impact") or ""
    ref = f.get("ref") or ""
    affected = f.get("affected_count", 1)
    return f"""<div class="finding sev-{sev}">
<div class="f-head"><span class="num">{idx}</span><span class="sev" style="background:{SEV_COLORS[sev]}">{SEV_LABEL[sev]}</span><strong>{e(f['title'])}</strong></div>
<div class="f-meta"><span>Affected: <b>{affected:,}</b></span><span>Effort: <b>{e(f.get('effort'))}</b></span><span>Impact: <b>{e(f.get('impact'))}</b></span><span>Owner: <b>{e(f.get('owner') or OWNER_DEFAULT.get(f['category'], ''))}</b></span><span>Lane: <b>{e(LANE_LABEL.get(f.get('lane'), f.get('lane')))}</b></span></div>
{f"<p class='what'><strong>What we checked.</strong> {e(what)}</p>" if what else ''}
<p><strong>What we found.</strong> {e(f['title'].rstrip('.'))}{(' (' + format(affected, ',') + ' affected)') if affected > 1 and not re.search(r'\d', f['title']) else ''}.{' Examples:' if ev else ''}</p>
{('<ul class="evidence">' + ev + '</ul>') if ev else ''}
{more_pages}
<p><strong>Why it matters.</strong> {e(f.get('why_long') or f['why'])}</p>
{f"<p class='biz'><strong>Business impact.</strong> {e(biz)}</p>" if biz else ''}
<div class="fix"><strong>How to fix.</strong>{fix_html}</div>
{f"<p class='verify'><strong>How to verify.</strong> {e(verify)}</p>" if verify else ''}
{f"<p class='small muted'>Reference: <a href='{e(ref)}'>{e(ref)}</a></p>" if ref else ''}
</div>"""


def checks_table(checks: list[dict]) -> str:
    icon = {"pass": "<span class='ok'>&#10003; Pass</span>", "fail": "<span class='bad'>&#10007; Issue</span>", "skip": "<span class='muted'>&#8211; Not measured</span>", "info": "<span class='muted'>&#9432; Note</span>"}
    order = {"fail": 0, "info": 1, "pass": 2, "skip": 3}
    rows = ""
    for c in sorted(checks, key=lambda c: (order.get(c["status"], 9), c.get("title", ""))):
        extra = c.get("note") or (f"{c.get('affected'):,} affected" if c.get("affected") and c.get("status") == "fail" else "")
        rows += f"<tr><td>{icon.get(c['status'], c['status'])}</td><td>{e(c.get('title'))}</td><td class='muted'>{e(c.get('group', ''))}</td><td class='muted'>{e(extra)}</td></tr>"
    return f"<table class='checks'><tr><th>Result</th><th>Check</th><th>Area</th><th>Detail</th></tr>{rows}</table>"


def render_html(audit: dict, brand: str = "RankSherlock", client: str = "", prepared_by: str = "", accent: str = "#0f766e", logo_url: str = "") -> str:
    s = audit["scores"]
    site = audit["site"]
    cats = audit["categories"]
    findings = s["findings"]
    crawl = audit["crawl"]
    today = str(audit.get("generated_at", date.today().isoformat()))[:10]
    client = client or site["host"]
    prepared_by = prepared_by or brand
    by_cat = {k: [f for f in findings if f["category"] == k] for k in CAT_ORDER}
    counts = s["counts"]
    paras = narrative(audit)

    # ------------------------------------------------------------ cover
    cover = f"""<section class="cover">
<div class="cover-top">{f'<img src="{e(logo_url)}" alt="" class="logo">' if logo_url else ''}<div class="brand">{e(brand)}</div></div>
<div class="cover-mid">
<div class="kicker">SEO, AEO and GEO audit report</div>
<h1>{e(client)}</h1>
<div class="cover-sub">{e(site['url'])}</div>
<div class="cover-scores">
<div class="cs">{ring(s['overall'], 'Grade ' + s['grade'], 170, 16, 'Overall health')}<div class="cs-l">Overall health</div></div>
<div class="cs">{ring(s['search_seo']['score'], s['search_seo']['grade'], 120, 12, 'Search SEO')}<div class="cs-l">Search SEO</div></div>
<div class="cs">{ring(s['ai_visibility']['score'], s['ai_visibility']['grade'], 120, 12, 'AI visibility')}<div class="cs-l">AI visibility</div></div>
</div>
<p class="cover-verdict">{e(paras[0])}</p>
</div>
<div class="cover-bottom"><div>Prepared for <b>{e(client)}</b></div><div>Prepared by <b>{e(prepared_by)}</b></div><div>Date <b>{e(today)}</b></div><div>Pages analysed <b>{crawl['pages_crawled']:,}</b></div></div>
</section>"""

    # --------------------------------------------------------- contents
    toc_items = [("summary", "Executive summary"), ("overview", "Crawl overview"), ("priorities", "Priority action list")]
    for k in CAT_ORDER:
        if k in cats and cats[k]:
            toc_items.append((f"cat-{k}", CAT_LABELS[k]))
    toc_items += [("ai-detail", "AI crawler access in detail"), ("perf-detail", "Performance detail"), ("keypages", "Key page scorecards"), ("pages", "Page inventory"), ("roadmap", "90-day roadmap"), ("glossary", "Glossary"), ("method", "Methodology and limits")]
    toc = "<section class='page'><h2>Contents</h2><ol class='toc'>" + "".join(f"<li><a href='#{a}'>{e(t)}</a></li>" for a, t in toc_items) + "</ol>" + """
<div class="howto"><h3>How to read this report</h3>
<p>Every score is deterministic: the same site audited twice gives the same number. Each category starts at 100 and loses points per failed check according to severity (critical 10, high 6, medium 3, low 1, info 0), so one critical defect costs as much as ten small ones. Categories combine with fixed weights into two axes: <b>Search SEO</b> (how ready the site is for Google and Bing) and <b>AI visibility</b> (how ready it is to be fetched and quoted by ChatGPT, Perplexity, Claude and Google AI Overviews). Overall health is 65% search and 35% AI. A handful of single defects (for example robots.txt blocking the site) cap an axis because a high score would be misleading; any cap is stated explicitly. Areas that could not be measured are excluded, never guessed.</p>
<table class="legend"><tr><th>Severity</th><th>Meaning</th></tr>
<tr><td><span class="sev" style="background:#b91c1c">Critical</span></td><td>Blocks indexing, ranking or AI access for large parts of the site. Fix immediately.</td></tr>
<tr><td><span class="sev" style="background:#c2410c">High</span></td><td>Materially suppresses rankings, rich results or citations. Fix within the first sprint.</td></tr>
<tr><td><span class="sev" style="background:#b45309">Medium</span></td><td>Measurable loss of visibility or trust. Schedule within the quarter.</td></tr>
<tr><td><span class="sev" style="background:#1d4ed8">Low</span></td><td>Hygiene and polish; worthwhile when touching the template anyway.</td></tr>
<tr><td><span class="sev" style="background:#4b5563">Info</span></td><td>Context only; no action required.</td></tr></table>
<p><b>Lanes</b> tell you who can do the work: <em>developer can apply directly</em> (safe, mechanical), <em>apply with review</em> (redirects, robots, canonicals: easy to get wrong), <em>needs content or business input</em> (writing, decisions, outreach).</p>
</div></section>"""

    # -------------------------------------------------------- summary
    cat_rows = ""
    chart_rows = []
    for k in CAT_ORDER:
        v = s["categories"].get(k)
        if not v:
            continue
        meas = v.get("measured", True)
        sc = v["score"] if meas else None
        cat_rows += f"<tr><td><a href='#cat-{k}'>{e(CAT_LABELS[k])}</a></td><td>{bar(sc, 160)}</td><td style='color:{grade_color(sc)};font-weight:800'>{e(sc if meas else 'n/a')}</td><td>{e(v['grade'] if meas else '')}</td><td>{v['findings']}</td><td>{v['passes']}</td><td class='muted'>{'measured' if meas else 'not measured'}</td></tr>"
        if meas:
            chart_rows.append((CAT_SHORT[k], sc, 100))
    caps_html = ""
    if s["caps"]:
        caps_html = "<div class='callout warn'><strong>Score caps applied.</strong> " + " ".join(f"{e(c['axis'].replace('_', ' ').title())} score capped at {c['ceiling']} (it would otherwise be {c['uncapped']}) because {e(c['reason'])}." for c in s["caps"]) + "</div>"
    passes_all = [c for k in CAT_ORDER for c in cats.get(k, {}).get("checks", []) if c["status"] == "pass"]
    good = "".join(f"<li>{e(c['title'])}</li>" for c in passes_all[:12])
    this_week = [f for f in findings if f["severity"] in ("critical", "high", "medium") and f.get("effort") == "low"][:3] or [f for f in findings if f["severity"] != "info"][:3]
    week_html = "".join(f"<li><a href='#f-{e(f['id'])}'><strong>{e(f['title'])}</strong></a><br><span class='muted small'>{e(f['fix'][:160])}</span></li>" for f in this_week)
    skipped_all = [c for k in CAT_ORDER for c in cats.get(k, {}).get("checks", []) if c["status"] == "skip"]
    top5 = "".join(f"<tr><td>{i+1}</td><td><span class='sev' style='background:{SEV_COLORS[f['severity']]}'>{SEV_LABEL[f['severity']]}</span></td><td><a href='#f-{e(f['id'])}'>{e(f['title'])}</a></td><td>{f.get('affected_count', 1):,}</td><td>{e(f.get('effort'))}</td><td>{e(CAT_SHORT.get(f['category'], f['category']))}</td></tr>" for i, f in enumerate(findings[:8]))
    summary = f"""<section class="page" id="summary"><h2>Executive summary</h2>
{''.join(f'<p class="lead">{e(p)}</p>' for p in paras)}
{caps_html}
<div class="dash">
<div class="dash-left">
<div class="rings">
<div class="cs">{ring(s['overall'], 'Grade ' + s['grade'], 150, 14, 'Overall')}<div class="cs-l">Overall health</div></div>
<div class="cs">{ring(s['search_seo']['score'], s['search_seo']['grade'], 110, 11, 'Search SEO')}<div class="cs-l">Search SEO</div></div>
<div class="cs">{ring(s['ai_visibility']['score'], s['ai_visibility']['grade'], 110, 11, 'AI visibility')}<div class="cs-l">AI visibility</div></div>
</div></div>
<div class="dash-right"><div class="cs">{donut(counts)}<div class="cs-l">{counts['critical']} critical, {counts['high']} high, {counts['medium']} medium, {counts['low']} low</div></div></div>
</div>
<h3>Scores by area</h3>
<table><tr><th>Area</th><th></th><th>Score</th><th>Grade</th><th>Issues</th><th>Checks passed</th><th>Status</th></tr>{cat_rows}</table>
<div class="callout"><strong>Do this week.</strong><ol class="week">{week_html}</ol></div>
<div class="two-col">
<div><h3>Top priorities</h3><table><tr><th>#</th><th>Severity</th><th>Finding</th><th>Affected</th><th>Effort</th><th>Area</th></tr>{top5}</table></div>
<div><h3>What is already working</h3><ul class="good">{good or '<li class="muted">No passed checks recorded.</li>'}</ul></div>
</div>
</section>"""

    # --------------------------------------------------------- overview
    status_counts = cats.get("technical", {}).get("status_breakdown", {}) or crawl.get("status_counts", {})
    status_rows = sorted(((str(k), int(v)) for k, v in status_counts.items()), key=lambda kv: -kv[1])[:8]
    depth_counts = Counter()
    for r in cats.get("content", {}).get("page_table", []):
        pass
    sm = crawl.get("sitemaps", {})
    overview = f"""<section class="page" id="overview"><h2>Crawl overview</h2>
<p>This audit is built on a real crawl, not a sample of the homepage. The crawler followed internal links breadth-first from the homepage so every page carries its true click depth, and it also fetched every URL listed in the XML sitemaps so that pages nobody links to (orphans) are still examined.</p>
<div class="stats">
<div class="stat"><div class="v">{crawl['pages_crawled']:,}</div><div class="l">pages crawled</div></div>
<div class="stat"><div class="v">{sm.get('unique_urls', sm.get('total_urls', 0)):,}</div><div class="l">unique sitemap URLs</div></div>
<div class="stat"><div class="v">{crawl.get('pages_discovered', 0):,}</div><div class="l">URLs discovered</div></div>
<div class="stat"><div class="v">{'Yes' if crawl.get('complete') else 'No'}</div><div class="l">crawl complete{'' if crawl.get('complete') else ' (' + e(crawl.get('stopped_reason', '')) + ')'}</div></div>
<div class="stat"><div class="v">{cats.get('technical', {}).get('indexable_pages', 0):,}</div><div class="l">indexable pages</div></div>
<div class="stat"><div class="v">{cats.get('technical', {}).get('avg_response_ms', 0)} ms</div><div class="l">avg server response</div></div>
<div class="stat"><div class="v">{crawl.get('documents_count', 0)}</div><div class="l">PDF documents linked</div></div>
<div class="stat"><div class="v">{e(site.get('platform') or 'unknown')}</div><div class="l">platform</div></div>
</div>
<div class="two-col"><div><h3>HTTP status codes</h3>{hbar_chart([(f'HTTP {k}' if k != '0' else 'No response', v, max(v for _, v in status_rows) if status_rows else 1) for k, v in status_rows], 420)}</div>
<div><h3>Scores by area</h3>{hbar_chart(chart_rows, 420)}</div></div>
<p class="muted small">Robots.txt status {crawl.get('robots_status')}; {len(crawl.get('sitemap_files', []))} sitemap files read; {crawl.get('blocked_by_robots_count', len(crawl.get('blocked_by_robots', [])))} linked URLs blocked by robots.txt; {crawl.get('requests', 0):,} HTTP requests in {crawl.get('duration_s', 0)} s with {crawl.get('workers', 1)} parallel workers.</p>
</section>"""

    # ------------------------------------------------------ priorities
    pr_rows = ""
    for i, f in enumerate(findings):
        if f["severity"] == "info":
            continue
        pr_rows += f"<tr><td>{i+1}</td><td><span class='sev' style='background:{SEV_COLORS[f['severity']]}'>{SEV_LABEL[f['severity']]}</span></td><td><a href='#f-{e(f['id'])}'>{e(f['title'])}</a></td><td>{e(CAT_SHORT.get(f['category'], ''))}</td><td>{f.get('affected_count', 1):,}</td><td>{e(f.get('effort'))}</td><td>{e(f.get('owner') or OWNER_DEFAULT.get(f['category'], ''))}</td></tr>"
    priorities = f"""<section class="page" id="priorities"><h2>Priority action list</h2>
<p>Every issue found, ordered by severity and then by effort (quick fixes first within each severity). Click a row to jump to the full explanation, evidence and fix.</p>
<table class="prio"><tr><th>#</th><th>Severity</th><th>Finding</th><th>Area</th><th>Affected</th><th>Effort</th><th>Owner</th></tr>{pr_rows}</table></section>"""

    # ------------------------------------------------------- chapters
    chapters = ""
    n = 0
    for k in CAT_ORDER:
        cat = cats.get(k)
        if not cat:
            continue
        v = s["categories"].get(k, {})
        meas = v.get("measured", True)
        sc = v["score"] if meas else None
        fl = by_cat.get(k, [])
        cards = ""
        for f in fl:
            n += 1
            cards += f"<a id='f-{e(f['id'])}'></a>" + finding_card(f, n)
        intro = CAT_INTRO.get(k, "")
        extra = ""
        if k == "content":
            extra = f"<p class='muted small'>Average words per page {cat.get('avg_word_count')}; average passage citability {cat.get('avg_citability')}/100; {cat.get('article_pages')} article pages; FAQ content on {cat.get('faq_pages')} pages; question-style headings on {cat.get('question_heading_pages')} pages; {cat.get('images_missing_alt')} of {cat.get('images_total')} images without alt text.</p>"
        elif k == "schema":
            types = cat.get("types_found", {})
            extra = f"<p class='muted small'>Structured data on {cat.get('pages_with_schema')} of {cat.get('pages_total')} pages. Types found: {e(', '.join(f'{t} ({c})' for t, c in list(types.items())[:12])) or 'none'}.</p>"
        elif k == "local" and not meas:
            extra = "<p class='muted'>The site does not read as a local business (no LocalBusiness schema, address and phone pattern or local service language), so local checks are not scored. If it serves a physical area, tell us and we will re-run with local checks forced on.</p>"
        elif k == "ecommerce" and not meas:
            extra = f"<p class='muted'>The site reads as a {e(site.get('business_type'))} site rather than an online shop, so shop-specific checks are not scored.</p>"
        elif k == "ecommerce":
            extra = f"<p class='muted small'>{cat.get('product_pages', 0):,} product pages and {cat.get('category_pages', 0):,} category pages analysed.</p>"
        elif k == "performance" and not cat.get("measured"):
            extra = "<p class='muted'>Core Web Vitals were not measured in this run (Google PageSpeed Insights unavailable or skipped), so only HTML-level performance checks are reported and the category is excluded from the score.</p>"
        chapters += f"""<section class="page chapter" id="cat-{k}">
<div class="ch-head"><div><div class="kicker">Chapter</div><h2>{e(CAT_LABELS[k])}</h2></div><div class="ch-score">{ring(sc, v.get('grade', '') if meas else 'n/a', 110, 11, CAT_LABELS[k])}</div></div>
<p class="lead">{e(intro)}</p>
{extra}
<div class="ch-stats"><span><b>{len([f for f in fl if f['severity'] != 'info'])}</b> issues</span><span><b>{cat.get('pass_count', 0)}</b> checks passed</span><span><b>{len([f for f in fl if f['severity'] in ('critical', 'high')])}</b> critical or high</span></div>
<h3>Checks performed</h3>
{checks_table(cat.get('checks', []))}
<h3>Findings in detail</h3>
{cards or '<p class="muted">No issues in this area.</p>'}
</section>"""

    # ------------------------------------------------------ AI detail
    geo = cats.get("geo", {})
    bots = geo.get("bot_status", {})
    st_label = {"allowed": "Allowed", "allowed-by-wildcard": "Allowed (wildcard rule)", "not-mentioned": "Not mentioned (allowed)", "no-robots": "No robots.txt (allowed)", "partial": "Partly restricted", "blocked": "Blocked", "blocked-by-wildcard": "Blocked (wildcard rule)"}
    bot_rows = "".join(f"<tr><td><b>{e(b)}</b></td><td>{e(i['vendor'])}</td><td>{e(i['role'])}</td><td class='st-{e(i['status'])}'>{e(st_label.get(i['status'], i['status']))}</td><td class='muted'>{e(i['note'])}</td></tr>" for b, i in bots.items())
    probes = geo.get("ua_probes", {})
    probe_rows = "".join(f"<tr><td>{e(b)}</td><td>HTTP {e(r['status'])}</td><td class='{'bad' if r['challenged'] else 'ok'}'>{'Challenged / blocked' if r['challenged'] else 'Served normally'}</td><td class='muted'>{e(r.get('server', ''))}{' (Cloudflare)' if r.get('cf') else ''}</td></tr>" for b, r in probes.items())
    content = cats.get("content", {})
    cit_low = "".join(f"<tr><td class='url'>{e(x['url'])}</td><td style='color:{grade_color(x['score'])};font-weight:700'>{x['score']}</td><td class='muted'>{e(', '.join(f'{a} {b}' for a, b in x.get('parts', {}).items()))}</td></tr>" for x in content.get("citability_lowest", []))
    cit_high = "".join(f"<tr><td class='url'>{e(x['url'])}</td><td style='color:{grade_color(x['score'])};font-weight:700'>{x['score']}</td></tr>" for x in content.get("citability_highest", []))
    llms = geo.get("llms_txt", {})
    ai_detail = f"""<section class="page" id="ai-detail"><h2>AI crawler access in detail</h2>
<p>AI answer engines only cite what their crawlers can fetch. The first table reads the site's robots.txt for every known AI bot and labels each bot's role: <b>retrieval</b> bots fetch pages to cite them in answers, <b>user-fetch</b> bots open a page when a user pastes a link, and <b>training</b> bots collect data for future models. The second table shows what the server actually returned when we requested the homepage pretending to be each bot, which catches firewalls and CDN rules that robots.txt does not reveal.</p>
<h3>Readiness by AI platform</h3>
<table><tr><th>Platform</th><th>Can it fetch the site?</th><th>Blocked by</th></tr>{''.join(f"<tr><td><b>{e(name)}</b></td><td class='{'ok' if v.get('ready') else 'bad'}'>{'Yes' if v.get('ready') else 'No'}</td><td class='muted'>{e(', '.join(v.get('blocked', [])) or 'nothing')}</td></tr>" for name, v in geo.get('platform_readiness', {}).items())}</table>
<p class="muted small">Ready means the platform's crawlers are allowed in robots.txt and were served the page in our live test. It does not mean the platform already cites the site.</p>
<h3>robots.txt rules per AI bot</h3>
<table><tr><th>Bot</th><th>Vendor</th><th>Role</th><th>robots.txt</th><th>What it does</th></tr>{bot_rows}</table>
{('<h3>Live server response per bot (homepage)</h3><table><tr><th>User agent</th><th>Status</th><th>Result</th><th>Server</th></tr>' + probe_rows + '</table>') if probe_rows else ''}
<h3>AI discovery files</h3>
<table><tr><th>File</th><th>Status</th><th>Note</th></tr>
<tr><td>/llms.txt</td><td>{'Present' if llms.get('present') else 'Absent'}</td><td class='muted'>{e(('H1 ' + ('yes' if llms.get('has_h1') else 'no') + ', description ' + ('yes' if llms.get('has_description') else 'no') + ', ' + str(llms.get('links', 0)) + ' links, ' + str(llms.get('sections', 0)) + ' sections') if llms.get('present') else 'Optional convention; cheap to add')}</td></tr>
<tr><td>/llms-full.txt</td><td>{'Present' if geo.get('llms_full_txt') else 'Absent'}</td><td class='muted'>Full-text companion to llms.txt</td></tr>
<tr><td>RSS / Atom feed</td><td>{'Present' if geo.get('has_feed') else 'Absent'}</td><td class='muted'>Feeds help crawlers and aggregators notice new content quickly</td></tr>
<tr><td>Markdown content negotiation</td><td>{'Supported' if geo.get('markdown_negotiation') else 'Not supported'}</td><td class='muted'>Serving text/markdown on request is an emerging agent-friendly feature</td></tr></table>
<h3>Brand entity</h3>
<p>Names seen for the organisation across schema, og:site_name and title suffixes: {e(', '.join(f'{n} ({c})' for n, c in geo.get('brand_names_seen', {}).items())) or 'none detected'}. sameAs profile links in schema: {e(', '.join(geo.get('same_as', [])[:8])) or 'none'}.</p>
<div class="two-col"><div><h3>Least quotable pages</h3><table><tr><th>URL</th><th>Citability</th><th>Breakdown</th></tr>{cit_low or '<tr><td colspan=3 class=muted>n/a</td></tr>'}</table></div>
<div><h3>Most quotable pages</h3><table><tr><th>URL</th><th>Citability</th></tr>{cit_high or '<tr><td colspan=2 class=muted>n/a</td></tr>'}</table></div></div>
<p class="muted small">Citability scores passages on answer quality (30), self-containment (25), structure (20), statistics and sourcing (15) and uniqueness (10). It predicts quotability; it does not prove that any engine currently cites the page.</p>
</section>"""

    # ------------------------------------------------------ perf detail
    perf = cats.get("performance", {})
    psi_home = next((v for k, v in perf.get("psi", {}).items() if v.get("ok") and "#desktop" not in k), None)
    psi_desk = next((v for k, v in perf.get("psi", {}).items() if v.get("ok") and "#desktop" in k), None)
    if psi_home:
        fld = psi_home["field"]
        lab = psi_home["lab"]
        th = {"LCP": "under 2.5 s is good, over 4 s is poor", "INP": "under 200 ms is good, over 500 ms is poor", "CLS": "under 0.1 is good, over 0.25 is poor"}

        def metric_card(name, val, unit, desc):
            return f"<div class='stat'><div class='v'>{e(val if val is not None else 'n/a')}{unit if val is not None else ''}</div><div class='l'>{name}</div><div class='l muted'>{desc}</div></div>"

        opp = "".join(f"<tr><td>{e(o['title'])}</td><td>~{o['savings_ms']:,} ms</td></tr>" for o in psi_home.get("opportunities", []))
        diag = "".join(f"<tr><td>{e(d['title'])}</td><td>{e(d.get('display', ''))}</td></tr>" for d in psi_home.get("diagnostics", []))
        perf_detail = f"""<section class="page" id="perf-detail"><h2>Performance detail</h2>
<p>Field data is what real Chrome users experienced over the last 28 days (the 75th percentile), which is what Google ranks on. Lab data is a single simulated mobile load by Lighthouse, useful for diagnosis.</p>
<h3>Core Web Vitals, real users (mobile)</h3>
<div class="stats">{metric_card('LCP (loading)', fld.get('LCP'), ' ms', th['LCP'])}{metric_card('INP (responsiveness)', fld.get('INP'), ' ms', th['INP'])}{metric_card('CLS (stability)', fld.get('CLS'), '', th['CLS'])}{metric_card('TTFB (server)', fld.get('TTFB'), ' ms', 'under 800 ms is good')}</div>
<p class="muted small">Field data source: {e(fld.get('source'))} ({'page-level' if fld.get('source') == 'page' else 'origin-level' if fld.get('source') == 'origin' else 'no real-user data available'}). Overall field assessment: {e(fld.get('overall') or 'n/a')}.</p>
<h3>Lab measurements (Lighthouse mobile{(' / desktop ' + str(psi_desk['performance_score']) + '/100') if psi_desk else ''})</h3>
<div class="stats"><div class='stat'><div class='v' style='color:{grade_color(psi_home['performance_score'])}'>{psi_home['performance_score']}</div><div class='l'>performance score /100</div></div>{metric_card('LCP', round((lab.get('LCP') or 0)), ' ms', '')}{metric_card('Total blocking time', round(lab.get('TBT') or 0), ' ms', '')}{metric_card('Speed index', round(lab.get('SI') or 0), ' ms', '')}{metric_card('Page weight', round((lab.get('total_bytes') or 0) / 1024), ' KB', '')}{metric_card('DOM nodes', int(lab.get('dom_size') or 0), '', '')}</div>
<div class="two-col"><div><h3>Biggest savings</h3><table><tr><th>Opportunity</th><th>Estimated saving</th></tr>{opp or '<tr><td colspan=2 class=muted>None over 150 ms</td></tr>'}</table></div>
<div><h3>Diagnostics</h3><table><tr><th>Audit</th><th>Value</th></tr>{diag or '<tr><td colspan=2 class=muted>None flagged</td></tr>'}</table></div></div>
<p class="muted small">Average HTML response in the crawl: {e(perf.get('avg_html_response_ms'))} ms; average HTML size {e(perf.get('avg_html_kb'))} KB. Lighthouse {e(psi_home.get('lighthouse_version'))}.</p>
</section>"""
    else:
        perf_detail = f"""<section class="page" id="perf-detail"><h2>Performance detail</h2>
<p class="muted">Core Web Vitals were not measured in this run (Google PageSpeed Insights was unavailable, rate-limited or skipped). The performance chapter reports only what can be read from the HTML: script counts, lazy loading, inline CSS size and server response time. Average HTML response in the crawl: {e(perf.get('avg_html_response_ms'))} ms; average HTML size {e(perf.get('avg_html_kb'))} KB.</p>
<p>To add real-user Core Web Vitals, re-run the audit with a PageSpeed Insights API key, or open <a href="https://pagespeed.web.dev/">pagespeed.web.dev</a> for the homepage and two key inner pages.</p></section>"""

    # ------------------------------------------------------ key page cards
    table = content.get("page_table", [])
    cit_map = {x["url"]: x["score"] for x in content.get("citability_lowest", []) + content.get("citability_highest", [])}
    key_rows = []
    seen_types = set()
    for r in table:
        t = r.get("type", "other")
        if t in ("cart", "search", "pagination", "tag", "legal", "author") or t in seen_types:
            continue
        seen_types.add(t)
        key_rows.append(r)
        if len(key_rows) >= 6:
            break

    def key_card(r):
        tl, dl = r["title_len"], r["desc_len"]
        t_ok = 30 <= tl <= 65
        d_ok = 70 <= dl <= 170
        flags = []
        if r["h1_count"] != 1:
            flags.append(f"{r['h1_count']} H1 tags")
        if r["words"] < 150:
            flags.append("thin copy")
        if r["missing_alt"]:
            flags.append(f"{r['missing_alt']} images without alt")
        if not r["canonical_ok"]:
            flags.append("canonical points elsewhere")
        return f"""<div class="keycard">
<div class="kc-head"><span class="pill">{e(r.get('type', 'page'))}</span><span class="url">{e(r['url'])}</span></div>
<table class="kc">
<tr><th>Title</th><td>{e(r['title']) or '<span class=bad>missing</span>'} <span class="{'ok' if t_ok else 'bad'}">({tl} chars{'' if t_ok else ', aim for 30 to 60'})</span></td></tr>
<tr><th>Description</th><td><span class="{'ok' if d_ok else 'bad'}">{dl} chars{'' if d_ok else (', missing: write 140 to 160' if dl == 0 else ', aim for 140 to 160')}</span></td></tr>
<tr><th>H1</th><td>{e(r['h1']) or '<span class=bad>missing</span>'}</td></tr>
<tr><th>Words</th><td>{r['words']:,} <span class="muted">(main content)</span></td><th>Internal links</th><td>{r['internal_links']}</td></tr>
<tr><th>Opening</th><td colspan="3" class="muted">{e(r.get('first_paragraph') or 'no paragraph found')}{'...' if len(r.get('first_paragraph') or '') >= 220 else ''}</td></tr>
<tr><th>Schema</th><td>{e(', '.join(r['schema'])) or '<span class=muted>none</span>'}</td><th>Citability</th><td>{e(r.get('citability') if r.get('citability') is not None else cit_map.get(r['url'], 'n/a'))}{' /100' if r.get('citability') is not None else ''}</td></tr>
<tr><th>Flags</th><td colspan="3" class="{'bad' if flags else 'ok'}">{e(', '.join(flags)) or 'no page-level issues'}</td></tr>
</table></div>"""

    key_pages_sec = f"""<section class="page" id="keypages"><h2>Key page scorecards</h2>
<p>One representative page per template (homepage, service, product, category, article, location). These are the pages that carry most of the traffic, so template-level fixes here apply everywhere.</p>
{''.join(key_card(r) for r in key_rows)}
</section>"""

    # ----------------------------------------------------------- pages
    page_rows = ""
    for r in table[:300]:
        flags = []
        if not r["title"]:
            flags.append("no title")
        if r["h1_count"] == 0:
            flags.append("no H1")
        if r["h1_count"] > 1:
            flags.append("multiple H1")
        if r["desc_len"] == 0:
            flags.append("no description")
        if r["title_len"] > 65:
            flags.append("long title")
        if r["missing_alt"]:
            flags.append(f"{r['missing_alt']} alt missing")
        if not r["canonical_ok"]:
            flags.append("canonical elsewhere")
        if r["noindex"]:
            flags.append("noindex")
        if r["words"] < 150:
            flags.append("thin")
        page_rows += f"<tr><td class='url'>{e(r['url'])}</td><td>{e(r['title'][:70])}</td><td>{r['words']:,}</td><td>{r['internal_links']}</td><td>{e(', '.join(r['schema']))}</td><td>{r['ms']}</td><td class='{'bad' if flags else 'ok'}'>{e(', '.join(flags)) or 'ok'}</td></tr>"
    pages_sec = f"""<section class="page" id="pages"><h2>Page inventory</h2>
<p>The first {min(300, len(table))} crawled pages, ordered by click depth. The complete inventory of all {crawl['pages_crawled']:,} pages with every measured field is in <code>pages.csv</code> next to this report.</p>
<table class="inv"><tr><th>URL</th><th>Title</th><th>Words</th><th>Links out</th><th>Schema</th><th>ms</th><th>Flags</th></tr>{page_rows}</table></section>"""

    # --------------------------------------------------------- roadmap
    def phase(title, when, items, note):
        rows = "".join(f"<tr><td><span class='sev' style='background:{SEV_COLORS[f['severity']]}'>{SEV_LABEL[f['severity']]}</span></td><td><a href='#f-{e(f['id'])}'>{e(f['title'])}</a></td><td>{e(f.get('effort'))}</td><td>{e(f.get('owner') or OWNER_DEFAULT.get(f['category'], ''))}</td><td>{e(LANE_LABEL.get(f.get('lane'), ''))}</td></tr>" for f in items)
        return f"<h3>{e(title)} <span class='muted'>({e(when)})</span></h3><p class='muted small'>{e(note)}</p><table><tr><th>Severity</th><th>Action</th><th>Effort</th><th>Owner</th><th>Lane</th></tr>{rows or '<tr><td colspan=5 class=muted>Nothing scheduled in this phase.</td></tr>'}</table>"

    actionable = [f for f in findings if f["severity"] != "info"]
    p1 = [f for f in actionable if f["severity"] == "critical" or (f["severity"] in ("high", "medium") and f.get("effort") == "low")]
    p2 = [f for f in actionable if f not in p1 and f["severity"] in ("high", "medium") and f.get("lane") != "human"]
    p3 = [f for f in actionable if f not in p1 and f not in p2]
    proj = s.get("projected", {})

    def proj_cell(key):
        p = proj.get(key) or {}
        return f"<div class='stat'><div class='v' style='color:{grade_color(p.get('overall'))}'>{e(p.get('overall', 'n/a'))} <span class='muted' style='font-size:14px'>{e(p.get('grade', ''))}</span></div><div class='l'>{ {'phase1': 'after phase 1', 'phase2': 'after phase 2', 'phase3': 'after phase 3'}[key]} ({p.get('fixes', 0)} fixes)</div></div>"

    roadmap = f"""<section class="page" id="roadmap"><h2>90-day roadmap</h2>
<p>The same findings, sequenced. Phase 1 removes blockers and banks the quick wins; phase 2 fixes the structural issues a developer can own; phase 3 is the content and entity work that compounds over time. Re-audit after each phase: the compare tool lists exactly which findings were resolved.</p>
<h3>Projected scores</h3>
<p class="muted small">Recomputed with the same deterministic model as if the listed findings were fixed. A guide to progress, not a traffic forecast.</p>
<div class="stats"><div class='stat'><div class='v' style='color:{grade_color(s['overall'])}'>{s['overall']} <span class='muted' style='font-size:14px'>{e(s['grade'])}</span></div><div class='l'>today</div></div>{proj_cell('phase1')}{proj_cell('phase2')}{proj_cell('phase3')}</div>
{phase('Phase 1: unblock and quick wins', 'weeks 1 to 2', p1, 'Critical defects plus every high or medium issue that takes low effort.')}
{phase('Phase 2: structural fixes', 'weeks 3 to 6', p2, 'High and medium issues that need developer time or careful review.')}
{phase('Phase 3: content, authority and polish', 'weeks 7 to 12', p3, 'Content rewrites, trust signals, entity work and low-severity hygiene.')}
</section>"""

    # ---------------------------------------------------------- glossary
    glossary = "<section class='page' id='glossary'><h2>Glossary</h2><dl class='gloss'>" + "".join(f"<dt>{e(t)}</dt><dd>{e(d)}</dd>" for t, d in GLOSSARY) + "</dl></section>"

    method = f"""<section class="page" id="method"><h2>Methodology and limits</h2>
<ul>
<li><b>Crawl.</b> Breadth-first from the homepage over internal links, plus every URL in every sitemap file ({crawl.get('sitemaps', {}).get('files_fetched', 0)} files). Cap {crawl['max_pages']:,} pages, robots.txt respected for the generic and Googlebot rules, {crawl.get('workers', 1)} parallel workers at a polite rate. {crawl['requests']:,} requests in {crawl['duration_s']} s. Crawl status: {'complete' if crawl.get('complete') else 'stopped early (' + e(crawl.get('stopped_reason', '')) + ')'}.</li>
<li><b>Checks.</b> Each analyzer runs deterministic checks against the parsed HTML, HTTP headers, robots.txt, sitemaps, live probes with AI-bot user agents, and Google PageSpeed Insights when reachable. Every finding carries the evidence that triggered it.</li>
<li><b>Scoring.</b> Category score = 100 minus severity-weighted penalties (critical 10, high 6, medium 3, low 1) on a 50-point scale, with diminishing returns once many findings of one severity pile up. Search SEO weights: technical 28, content 24, performance 16, schema 10, local 10, e-commerce 7, AI 5, adjusted for the detected business type ({e(s.get('business_type') or 'general')}). AI visibility weights: AI 35, content 30, schema 20, technical 15. Overall = 65% search + 35% AI. Caps: robots blocking the site, homepage noindex, certificate errors, pages canonicalised to the homepage, no HTTPS, answer-engine bots blocked, firewall challenges, content absent from HTML, nosnippet, no structured data. Unmeasured categories are excluded and the remaining weights re-normalised.</li>
<li><b>Word counts</b> are for the main content of each page (navigation, header, footer and sidebars removed), so a page with a large menu is not mistaken for a long page.</li>
<li><b>AI visibility</b> measures readiness (access, entity clarity, quotability). It does not prove that any engine cites the site today; only answer-engine testing does.</li>
<li><b>Out of scope</b> for a crawl-based audit: rankings, traffic, backlinks, Search Console and analytics data. These can be layered on separately.</li>
<li><b>JavaScript.</b> The crawler does not execute JavaScript, which is also how most AI crawlers see the site. Content that only appears after JS runs is reported as such.</li>
<li>Text quoted as evidence was gathered from the audited site and is reproduced as data.</li>
</ul>
<h3>What this audit did not check</h3>
<ul>
{''.join(f'<li>{e(c["title"])}{(": " + e(c["note"])) if c.get("note") else ""}</li>' for c in skipped_all) or '<li class="muted">Every planned check ran.</li>'}
<li>Rankings, search impressions and clicks (needs Search Console access).</li>
<li>Backlinks and referring domains (needs a link index).</li>
<li>Live AI answer citations (needs prompt testing across ChatGPT, Perplexity, Gemini and Claude; available as an add-on).</li>
<li>Rendered-page layout, tap targets and visual overlap (needs a headless browser pass).</li>
</ul>
<p class="muted small">Generated by {e(brand)} using RankSherlock, an open-source evidence-based audit engine. Scoring version {s.get('scoring_version')}.</p>
</section>"""

    css = f"""
:root{{--ink:#111827;--muted:#6b7280;--line:#e5e7eb;--bg:#fff;--soft:#f9fafb;--accent:{accent};--accent-ink:#ffffff}}
*{{box-sizing:border-box}}html{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
body{{margin:0;font-family:Inter,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:var(--ink);background:#eef0f3;line-height:1.55;font-size:13.5px}}
.wrap{{max-width:1000px;margin:0 auto;padding:24px}}
section.page,section.cover{{background:var(--bg);padding:40px 44px;margin:0 0 24px;border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,.08);page-break-after:always;break-after:page}}
h1{{font-size:38px;margin:6px 0 4px;letter-spacing:-.02em}}h2{{font-size:26px;margin:0 0 14px;letter-spacing:-.01em;color:var(--ink)}}h3{{font-size:16px;margin:26px 0 8px;color:var(--accent)}}
.kicker{{text-transform:uppercase;letter-spacing:.14em;font-size:11px;font-weight:700;color:var(--accent)}}
.lead{{font-size:14.5px}}.muted{{color:var(--muted)}}.small{{font-size:12px}}.ok{{color:#15803d;font-weight:700}}.bad{{color:#b91c1c;font-weight:700}}
section.cover{{min-height:1150px;display:flex;flex-direction:column;justify-content:space-between;background:linear-gradient(160deg,#0b1220 0%,#111c33 55%,{accent} 140%);color:#fff}}
.cover h1,.cover h2{{color:#fff}}.cover .kicker{{color:#9fd3c7}}.cover-top{{display:flex;align-items:center;gap:14px}}.cover .brand{{font-weight:800;font-size:20px;letter-spacing:.04em}}.logo{{max-height:48px}}
.cover-sub{{color:#c7d2e0;font-size:15px;margin-bottom:28px}}.cover-scores{{display:flex;gap:34px;align-items:flex-end;margin:12px 0 22px}}
.cover .ring circle:first-child{{stroke:rgba(255,255,255,.18)}}.cover .ring text{{fill:#fff}}.cover .ring text:last-child{{fill:#c7d2e0}}
.cover-verdict{{max-width:720px;font-size:15px;color:#e5eaf2}}
.cover-bottom{{display:flex;gap:28px;flex-wrap:wrap;color:#c7d2e0;font-size:13px;border-top:1px solid rgba(255,255,255,.2);padding-top:16px}}.cover-bottom b{{color:#fff;display:block;font-size:14px}}
.cs{{text-align:center}}.cs-l{{font-size:12px;color:var(--muted);margin-top:4px;font-weight:600}}.cover .cs-l{{color:#c7d2e0}}
.toc{{columns:2;font-size:14px;line-height:2}}.toc a{{color:var(--ink);text-decoration:none}}
.howto{{margin-top:28px;background:var(--soft);border:1px solid var(--line);border-radius:10px;padding:16px 20px}}.howto h3{{margin-top:0}}
table{{width:100%;border-collapse:collapse;margin:8px 0 14px;font-size:12.5px}}th,td{{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}}th{{background:var(--soft);font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}}
tr{{page-break-inside:avoid}}td.url{{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:10.5px;word-break:break-all;max-width:280px}}
.legend td:first-child{{width:110px}}
.sev{{color:#fff;font-size:10.5px;font-weight:700;text-transform:uppercase;padding:2px 8px;border-radius:999px;white-space:nowrap}}
.dash{{display:flex;gap:30px;align-items:center;justify-content:space-between;margin:14px 0 6px;flex-wrap:wrap}}.rings{{display:flex;gap:26px;align-items:flex-end}}
.two-col{{display:grid;grid-template-columns:1fr 1fr;gap:24px}}@media (max-width:760px){{.two-col{{grid-template-columns:1fr}}.toc{{columns:1}}}}
.good li{{margin:3px 0}}
.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:14px 0}}.stat{{background:var(--soft);border:1px solid var(--line);border-radius:10px;padding:12px 14px}}.stat .v{{font-size:22px;font-weight:800;color:var(--ink)}}.stat .l{{font-size:11.5px;color:var(--muted)}}
.ch-head{{display:flex;justify-content:space-between;align-items:center;gap:20px;border-bottom:3px solid var(--accent);padding-bottom:10px;margin-bottom:14px}}
.ch-stats{{display:flex;gap:22px;margin:8px 0 6px;color:var(--muted);font-size:13px}}.ch-stats b{{color:var(--ink);font-size:16px}}
.checks td:first-child{{white-space:nowrap;width:110px}}
.finding{{border:1px solid var(--line);border-left:6px solid var(--line);border-radius:10px;padding:14px 18px;margin:14px 0;page-break-inside:avoid;break-inside:avoid;background:#fff}}
.finding.sev-critical{{border-left-color:{SEV_COLORS['critical']}}}.finding.sev-high{{border-left-color:{SEV_COLORS['high']}}}.finding.sev-medium{{border-left-color:{SEV_COLORS['medium']}}}.finding.sev-low{{border-left-color:{SEV_COLORS['low']}}}.finding.sev-info{{border-left-color:{SEV_COLORS['info']}}}
.f-head{{display:flex;gap:10px;align-items:center;margin-bottom:6px;font-size:15px}}.num{{background:var(--ink);color:#fff;border-radius:6px;font-size:11px;font-weight:700;padding:2px 7px}}
.f-meta{{display:flex;flex-wrap:wrap;gap:14px;font-size:11.5px;color:var(--muted);margin-bottom:8px}}.f-meta b{{color:var(--ink)}}
.finding p{{margin:6px 0}}.evidence{{margin:4px 0 8px 18px;padding:0;font-size:12px}}.evidence li{{margin:2px 0}}
code{{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11px;background:var(--soft);padding:1px 4px;border-radius:4px;word-break:break-all}}
.fix{{background:#f0fdfa;border:1px solid #99f6e4;border-radius:8px;padding:8px 12px;margin:8px 0}}.fix ol{{margin:4px 0 0 18px;padding:0}}.fix li{{margin:3px 0}}
.verify{{font-size:12.5px}}.what{{color:#374151}}.biz{{background:#fffbeb;border-left:3px solid #f59e0b;padding:6px 10px;border-radius:4px}}
.callout{{border-radius:8px;padding:12px 14px;margin:12px 0;background:#f0fdfa;border:1px solid #99f6e4}}.callout.warn{{background:#fffbeb;border-color:#fde68a}}
.st-blocked,.st-blocked-by-wildcard{{color:#b91c1c;font-weight:700}}.st-allowed,.st-allowed-by-wildcard,.st-not-mentioned,.st-no-robots{{color:#15803d}}.st-partial{{color:#b45309;font-weight:700}}
.gloss dt{{font-weight:700;margin-top:10px}}.gloss dd{{margin:2px 0 0 0;color:#374151}}
.inv td{{font-size:11.5px}}
.week{{margin:6px 0 0 18px;padding:0}}.week li{{margin:6px 0}}
.keycard{{border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:12px 0;page-break-inside:avoid}}.kc-head{{display:flex;gap:10px;align-items:center;margin-bottom:6px}}.kc-head .url{{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11px;word-break:break-all}}
table.kc th{{width:110px;background:none;text-transform:none;letter-spacing:0;font-size:12px;color:var(--muted)}}table.kc td{{font-size:12.5px}}
@page{{size:A4;margin:16mm 12mm 18mm}}
@media print{{body{{background:#fff}}.wrap{{padding:0;max-width:none}}section.page,section.cover{{box-shadow:none;border-radius:0;margin:0;padding:0 0 10mm}}section.cover{{min-height:250mm;padding:18mm 16mm;border-radius:0}}h3{{page-break-after:avoid}}a{{color:inherit;text-decoration:none}}}}
"""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(client)} SEO, AEO and GEO audit</title>
<style>{css}</style></head><body><div class="wrap">
{cover}
{toc}
{summary}
{overview}
{priorities}
{chapters}
{ai_detail}
{perf_detail}
{key_pages_sec}
{pages_sec}
{roadmap}
{glossary}
{method}
</div></body></html>"""


def write_pdf(html_path: str, pdf_path: str, brand: str = "RankSherlock", client: str = "") -> str | None:
    """Render the HTML report to PDF with Playwright Chromium if available. Returns error string or None."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "playwright not installed (pip install playwright && playwright install chromium)"
    try:
        from pathlib import Path

        header = f"<div style='font-size:8px;color:#9ca3af;width:100%;padding:0 12mm;display:flex;justify-content:space-between'><span>{html.escape(client)} audit</span><span>{html.escape(brand)}</span></div>"
        footer = "<div style='font-size:8px;color:#9ca3af;width:100%;padding:0 12mm;display:flex;justify-content:space-between'><span>Confidential: prepared for the site owner</span><span>Page <span class='pageNumber'></span> of <span class='totalPages'></span></span></div>"
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(Path(html_path).resolve().as_uri())
            page.emulate_media(media="print")
            page.pdf(path=pdf_path, format="A4", print_background=True, display_header_footer=True, header_template=header, footer_template=footer, margin={"top": "14mm", "bottom": "16mm", "left": "11mm", "right": "11mm"})
            browser.close()
        return None
    except Exception as exc:  # pragma: no cover
        return f"{exc.__class__.__name__}: {str(exc)[:200]}"


def render_markdown_summary(audit: dict) -> str:
    s = audit["scores"]
    site = audit["site"]
    lines = [f"# {site['host']} audit summary", ""]
    lines += [p for p in narrative(audit)]
    lines += ["", "| Category | Score | Issues | Passed |", "|---|---|---|---|"]
    for k, v in s["categories"].items():
        lines.append(f"| {CAT_LABELS.get(k, k)} | {v['score'] if v.get('measured', True) else 'not measured'} | {v['findings']} | {v['passes']} |")
    lines += ["", "## Top findings"]
    for f in s["findings"][:15]:
        ev = f"; evidence: {f['evidence'][0]}" if f.get("evidence") else ""
        lines.append(f"- [{f['severity']}] {f['title']} ({f['category']}, {f.get('affected_count', 1)} affected{ev})")
    lines += ["", "## Quick wins"]
    for f in s["quick_wins"]:
        lines.append(f"- {f['title']}: {f['fix']}")
    return "\n".join(lines)


def write_csvs(audit: dict, pages: list, out_dir) -> None:
    import csv
    from pathlib import Path

    out_dir = Path(out_dir)
    with (out_dir / "findings.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["rank", "severity", "category", "id", "title", "affected", "effort", "impact", "lane", "owner", "why", "fix", "evidence", "pages"])
        for i, f in enumerate(audit["scores"]["findings"], 1):
            w.writerow([i, f["severity"], f["category"], f["id"], f["title"], f.get("affected_count", 1), f.get("effort"), f.get("impact"), f.get("lane"), f.get("owner"), f["why"], f["fix"], " | ".join(f.get("evidence", [])), " | ".join(f.get("pages", []))])
    with (out_dir / "pages.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["url", "status", "depth", "title", "title_length", "meta_description_length", "h1", "h1_count", "words", "internal_links", "external_links", "images", "images_missing_alt", "schema_types", "canonical", "meta_robots", "lang", "response_ms", "size_kb", "has_faq", "question_headings", "author_signal", "date_signal", "redirect_hops"])
        for p in pages:
            w.writerow([p.url, p.status, p.depth if p.depth < 99 else "orphan", p.title, len(p.title), len(p.meta_description), (p.h1[0] if p.h1 else ""), len(p.h1), p.word_count, p.internal_link_count or len(p.internal_links), p.external_link_count or len(p.external_links), p.images_total, p.images_missing_alt, ";".join(sorted({str(i.get("@type")) for i in p.json_ld})), p.canonical, p.meta_robots, p.lang, p.elapsed_ms, round(p.size_bytes / 1024), p.has_faq_section, len(p.question_headings), bool(p.author_signals), bool(p.date_signals), len(p.redirect_chain)])
