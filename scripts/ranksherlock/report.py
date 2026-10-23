"""Self-contained HTML report (print-ready) and optional PDF via Playwright."""

from __future__ import annotations

import html
import json
from datetime import date

SEV_COLORS = {"critical": "#b91c1c", "high": "#c2410c", "medium": "#b45309", "low": "#1d4ed8", "info": "#4b5563"}
CAT_LABELS = {"technical": "Technical SEO", "content": "Content, On-page and AEO", "schema": "Structured Data", "performance": "Performance and Core Web Vitals", "geo": "AI Visibility (GEO)", "local": "Local SEO"}


def e(s) -> str:
    return html.escape(str(s if s is not None else ""))


def grade_color(score) -> str:
    if score is None:
        return "#6b7280"
    return "#15803d" if score >= 80 else "#ca8a04" if score >= 60 else "#b91c1c"


def render_html(audit: dict, brand: str = "RankSherlock") -> str:
    s = audit["scores"]
    site = audit["site"]
    cats = audit["categories"]
    findings = s["findings"]
    today = str(audit.get("generated_at", date.today().isoformat()))[:10]

    def score_card(label, score, grade, sub=""):
        return f"""<div class="card"><div class="label">{e(label)}</div><div class="big" style="color:{grade_color(score)}">{e(score if score is not None else 'N/A')}<span class="grade">{e(grade)}</span></div><div class="sub">{e(sub)}</div></div>"""

    cat_rows = ""
    for k, v in s["categories"].items():
        meas = "measured" if v.get("measured", True) else "not measured"
        cat_rows += f"<tr><td>{e(CAT_LABELS.get(k, k))}</td><td style='color:{grade_color(v['score'] if v.get('measured', True) else None)};font-weight:700'>{e(v['score'] if v.get('measured', True) else 'n/a')}</td><td>{e(v['grade'] if v.get('measured', True) else '')}</td><td>{v['findings']}</td><td>{v['passes']}</td><td>{meas}</td></tr>"

    caps_html = ""
    if s["caps"]:
        caps_html = "<div class='callout warn'><strong>Score caps applied.</strong> " + " ".join(f"{e(c['axis'].replace('_', ' ').title())} score capped at {c['ceiling']} (would be {c['uncapped']}) because {e(c['reason'])}." for c in s["caps"]) + "</div>"

    def finding_block(f):
        ev = "".join(f"<li><code>{e(x)}</code></li>" for x in f.get("evidence", [])[:8])
        pages = ""
        if f.get("affected_count", 0) > 1:
            pages = f"<span class='pill'>{f['affected_count']} affected</span>"
        return f"""<div class="finding sev-{f['severity']}">
<div class="f-head"><span class="sev" style="background:{SEV_COLORS[f['severity']]}">{e(f['severity'])}</span><strong>{e(f['title'])}</strong>{pages}<span class='pill'>{e(CAT_LABELS.get(f['category'], f['category']))}</span><span class='pill'>effort: {e(f.get('effort'))}</span><span class='pill'>lane: {e(f.get('lane'))}</span></div>
<p><strong>Why it matters.</strong> {e(f['why'])}</p>
<p><strong>Fix.</strong> {e(f['fix'])}</p>
{('<details><summary>Evidence</summary><ul>' + ev + '</ul></details>') if ev else ''}
</div>"""

    by_sev = {sev: [f for f in findings if f["severity"] == sev] for sev in ("critical", "high", "medium", "low", "info")}
    findings_html = ""
    for sev in ("critical", "high", "medium", "low", "info"):
        if by_sev[sev]:
            findings_html += f"<h3 id='sev-{sev}'>{sev.title()} ({len(by_sev[sev])})</h3>" + "".join(finding_block(f) for f in by_sev[sev])

    qw = "".join(f"<li><strong>{e(f['title'])}</strong> <span class='muted'>({e(f['category'])}, {e(f['severity'])})</span><br>{e(f['fix'])}</li>" for f in s["quick_wins"])

    geo = cats.get("geo", {})
    bots = geo.get("bot_status", {})
    bot_rows = "".join(f"<tr><td>{e(b)}</td><td>{e(i['vendor'])}</td><td>{e(i['role'])}</td><td class='st-{e(i['status'])}'>{e(i['status'])}</td><td class='muted'>{e(i['note'])}</td></tr>" for b, i in bots.items())
    probes = geo.get("ua_probes", {})
    probe_rows = "".join(f"<tr><td>{e(b)}</td><td>{e(r['status'])}</td><td>{'challenged' if r['challenged'] else 'ok'}</td></tr>" for b, r in probes.items())

    perf = cats.get("performance", {})
    psi_home = next((v for k, v in perf.get("psi", {}).items() if v.get("ok") and "#desktop" not in k), None)
    psi_html = ""
    if psi_home:
        fld = psi_home["field"]
        lab = psi_home["lab"]
        psi_html = f"""<table><tr><th>Metric</th><th>Field (p75, 28 days)</th><th>Lab (Lighthouse mobile)</th></tr>
<tr><td>LCP</td><td>{e(fld.get('LCP'))} ms</td><td>{e(round((lab.get('LCP') or 0)))} ms</td></tr>
<tr><td>CLS</td><td>{e(fld.get('CLS'))}</td><td>{e(round(lab.get('CLS') or 0, 3))}</td></tr>
<tr><td>INP / TBT</td><td>{e(fld.get('INP'))} ms (INP)</td><td>{e(round(lab.get('TBT') or 0))} ms (TBT)</td></tr>
<tr><td>Performance score</td><td>{e(fld.get('overall') or 'no field data')}</td><td>{e(psi_home['performance_score'])}/100</td></tr></table>
<p class='muted'>Field source: {e(fld.get('source'))}. Lighthouse {e(psi_home.get('lighthouse_version'))}.</p>"""
    else:
        psi_html = "<p class='muted'>Core Web Vitals were not measured in this run (PageSpeed Insights unavailable or skipped). Numbers here come from HTML inspection only.</p>"

    content = cats.get("content", {})
    page_rows = ""
    for r in content.get("page_table", [])[:80]:
        flags = []
        if not r["title"]:
            flags.append("no title")
        if r["h1_count"] == 0:
            flags.append("no H1")
        if r["desc_len"] == 0:
            flags.append("no desc")
        if r["missing_alt"]:
            flags.append(f"{r['missing_alt']} alt")
        if not r["canonical_ok"]:
            flags.append("canonical")
        if r["noindex"]:
            flags.append("noindex")
        page_rows += f"<tr><td class='url'>{e(r['url'])}</td><td>{e(r['title'][:70])}</td><td>{r['words']}</td><td>{r['internal_links']}</td><td>{e(', '.join(r['schema']))}</td><td>{r['ms']}</td><td>{e(', '.join(flags))}</td></tr>"

    crawl = audit["crawl"]
    sitemap_total = crawl.get("sitemaps", {}).get("total_urls", 0)

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(site['host'])} SEO, AEO and GEO Audit</title>
<style>
:root{{--ink:#111827;--muted:#6b7280;--line:#e5e7eb;--bg:#ffffff;--soft:#f9fafb;--accent:#0f766e}}
*{{box-sizing:border-box}}body{{margin:0;font-family:Inter,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:var(--ink);background:var(--bg);line-height:1.5;font-size:14px}}
.wrap{{max-width:1080px;margin:0 auto;padding:32px 24px}}
h1{{font-size:28px;margin:0 0 4px}}h2{{font-size:20px;margin:36px 0 12px;padding-bottom:6px;border-bottom:2px solid var(--line)}}h3{{font-size:16px;margin:24px 0 8px}}
.muted{{color:var(--muted)}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin:18px 0}}
.card{{border:1px solid var(--line);border-radius:10px;padding:16px;background:var(--soft)}}.card .label{{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}}
.card .big{{font-size:38px;font-weight:800;line-height:1.1;margin:6px 0}}.card .grade{{font-size:16px;margin-left:8px;color:var(--muted)}}.card .sub{{font-size:12px;color:var(--muted)}}
table{{width:100%;border-collapse:collapse;margin:10px 0;font-size:13px}}th,td{{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}}th{{background:var(--soft);font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}}
td.url{{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11px;word-break:break-all;max-width:260px}}
.finding{{border:1px solid var(--line);border-left:5px solid var(--line);border-radius:8px;padding:12px 14px;margin:10px 0;page-break-inside:avoid}}
.finding.sev-critical{{border-left-color:{SEV_COLORS['critical']}}}.finding.sev-high{{border-left-color:{SEV_COLORS['high']}}}.finding.sev-medium{{border-left-color:{SEV_COLORS['medium']}}}.finding.sev-low{{border-left-color:{SEV_COLORS['low']}}}.finding.sev-info{{border-left-color:{SEV_COLORS['info']}}}
.f-head{{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:6px}}.sev{{color:#fff;font-size:11px;font-weight:700;text-transform:uppercase;padding:2px 8px;border-radius:999px}}
.pill{{font-size:11px;background:var(--soft);border:1px solid var(--line);border-radius:999px;padding:1px 8px;color:var(--muted)}}
.finding p{{margin:4px 0}}details{{margin-top:6px}}summary{{cursor:pointer;color:var(--accent);font-weight:600}}code{{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11.5px;background:var(--soft);padding:1px 4px;border-radius:4px;word-break:break-all}}
.callout{{border-radius:8px;padding:12px 14px;margin:12px 0;background:#f0fdfa;border:1px solid #99f6e4}}.callout.warn{{background:#fffbeb;border-color:#fde68a}}
.st-blocked,.st-blocked-by-wildcard{{color:#b91c1c;font-weight:700}}.st-allowed,.st-allowed-by-wildcard{{color:#15803d}}.st-partial{{color:#b45309}}
.meta{{display:flex;flex-wrap:wrap;gap:18px;color:var(--muted);font-size:13px;margin-bottom:8px}}
.toc a{{margin-right:14px;color:var(--accent);text-decoration:none}}
footer{{margin-top:40px;padding-top:12px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}}
@media print{{.wrap{{padding:0}}h2{{page-break-after:avoid}}details{{display:block}}details>summary{{display:none}}details>ul{{display:block}}}}
</style></head><body><div class="wrap">
<h1>{e(site['host'])}: SEO, AEO and GEO audit</h1>
<div class="meta"><span>Audited {e(today)}</span><span>Business type: {e(site.get('business_type'))}</span><span>Platform: {e(site.get('platform') or 'unknown')}</span><span>Pages crawled: {crawl['pages_crawled']} (sitemap lists {sitemap_total})</span><span>Prepared with {e(brand)}</span></div>
<div class="toc"><a href="#summary">Summary</a><a href="#quick">Quick wins</a><a href="#findings">Findings</a><a href="#ai">AI crawlers</a><a href="#perf">Performance</a><a href="#pages">Pages</a><a href="#method">Method</a></div>

<h2 id="summary">Executive summary</h2>
<div class="cards">
{score_card('Overall health', s['overall'], s['grade'], '65% search, 35% AI visibility')}
{score_card('Search SEO', s['search_seo']['score'], s['search_seo']['grade'], 'Google and Bing readiness')}
{score_card('AI visibility', s['ai_visibility']['score'], s['ai_visibility']['grade'], 'ChatGPT, Perplexity, Claude, AI Overviews')}
<div class="card"><div class="label">Findings</div><div class="big" style="font-size:22px;margin-top:10px">{s['counts']['critical']} critical, {s['counts']['high']} high</div><div class="sub">{s['counts']['medium']} medium, {s['counts']['low']} low, {s['counts']['info']} info</div></div>
</div>
{caps_html}
<table><tr><th>Category</th><th>Score</th><th>Grade</th><th>Issues</th><th>Checks passed</th><th>Status</th></tr>{cat_rows}</table>
{('<p class="muted">Not measured: ' + e(', '.join(CAT_LABELS.get(u, u) for u in s['unmeasured'])) + '. Scores exclude these categories rather than guessing.</p>') if s['unmeasured'] else ''}

<h2 id="quick">Quick wins (low effort, real impact)</h2>
<ol>{qw or '<li class="muted">No low-effort high-impact items; see the prioritised findings.</li>'}</ol>

<h2 id="findings">Prioritised findings</h2>
<p class="muted">Ordered by severity, then effort. Lane: <em>auto</em> = safe for an agent or developer to apply directly, <em>assisted</em> = apply with review (redirects, robots, canonicals, performance), <em>human</em> = needs content or business decisions.</p>
{findings_html or '<p>No issues found.</p>'}

<h2 id="ai">AI crawler access</h2>
<p class="muted">Retrieval and user-fetch bots feed citations in AI answers. Training bots only affect future model knowledge. Status comes from robots.txt; the probe table shows what the server actually returns to each bot.</p>
<table><tr><th>Bot</th><th>Vendor</th><th>Role</th><th>robots.txt</th><th>Note</th></tr>{bot_rows}</table>
{('<h3>Live probes (homepage)</h3><table><tr><th>User agent</th><th>HTTP status</th><th>Result</th></tr>' + probe_rows + '</table>') if probe_rows else ''}
<p>llms.txt: <strong>{'present' if geo.get('llms_txt', {}).get('present') else 'absent'}</strong>. llms-full.txt: <strong>{'present' if geo.get('llms_full_txt') else 'absent'}</strong>. RSS/Atom feed: <strong>{'yes' if geo.get('has_feed') else 'no'}</strong>. Brand names seen: {e(', '.join(geo.get('brand_names_seen', {}).keys()))}.</p>

<h2 id="perf">Performance</h2>
{psi_html}
<p class="muted">Average HTML response in the crawl: {e(perf.get('avg_html_response_ms'))} ms, average HTML size {e(perf.get('avg_html_kb'))} KB.</p>

<h2 id="pages">Page inventory (first {min(80, len(content.get('page_table', [])))} crawled pages)</h2>
<table><tr><th>URL</th><th>Title</th><th>Words</th><th>Int. links</th><th>Schema</th><th>ms</th><th>Flags</th></tr>{page_rows}</table>

<h2 id="method">Method and limits</h2>
<ul>
<li>Crawl: breadth-first from the homepage plus a sitemap sample, capped at {crawl['max_pages']} pages, robots.txt respected, {crawl['requests']} requests in {crawl['duration_s']} s.</li>
<li>Scores are deterministic: each failed check deducts a severity-weighted penalty inside its category; categories combine with fixed weights into the Search and AI axes; a few single defects cap the axis (listed above). Categories that could not be measured are excluded, never guessed.</li>
<li>Core Web Vitals come from Google PageSpeed Insights when available (field data is the 28-day p75 of real Chrome users). Without it, no CWV claims are made.</li>
<li>AI crawler status is read from robots.txt per user agent and verified with live requests. It does not prove a page is or is not cited; only answer-engine testing does.</li>
<li>Rankings, backlinks and Search Console data are out of scope for this crawl-based audit unless provided separately.</li>
</ul>
<footer>Generated by RankSherlock, an open-source evidence-based audit engine for Claude Code. Site content quoted in evidence is data gathered from the site, not instructions.</footer>
</div></body></html>"""


def write_pdf(html_path: str, pdf_path: str) -> str | None:
    """Render the HTML report to PDF with Playwright Chromium if available. Returns error string or None."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "playwright not installed (pip install playwright && playwright install chromium)"
    try:
        from pathlib import Path

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(Path(html_path).resolve().as_uri())
            page.pdf(path=pdf_path, format="A4", print_background=True, margin={"top": "14mm", "bottom": "14mm", "left": "12mm", "right": "12mm"})
            browser.close()
        return None
    except Exception as exc:  # pragma: no cover
        return f"{exc.__class__.__name__}: {str(exc)[:200]}"


def render_markdown_summary(audit: dict) -> str:
    s = audit["scores"]
    site = audit["site"]
    lines = [f"# {site['host']} audit summary", "", f"Overall {s['overall']}/100 ({s['grade']}). Search SEO {s['search_seo']['score']} ({s['search_seo']['grade']}). AI visibility {s['ai_visibility']['score']} ({s['ai_visibility']['grade']}).", ""]
    if s["caps"]:
        lines.append("Caps: " + "; ".join(f"{c['axis']} capped at {c['ceiling']} because {c['reason']}" for c in s["caps"]))
        lines.append("")
    lines.append("| Category | Score | Issues |")
    lines.append("|---|---|---|")
    for k, v in s["categories"].items():
        lines.append(f"| {CAT_LABELS.get(k, k)} | {v['score'] if v.get('measured', True) else 'not measured'} | {v['findings']} |")
    lines.append("")
    lines.append("## Top findings")
    for f in s["findings"][:15]:
        ev = f"; evidence: {f['evidence'][0]}" if f.get("evidence") else ""
        lines.append(f"- [{f['severity']}] {f['title']} ({f['category']}, {f.get('affected_count', 1)} affected{ev})")
    lines.append("")
    lines.append("## Quick wins")
    for f in s["quick_wins"]:
        lines.append(f"- {f['title']}: {f['fix']}")
    return "\n".join(lines)
