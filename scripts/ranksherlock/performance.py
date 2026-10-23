"""Performance: PageSpeed Insights (field + lab) when reachable, HTML-level heuristics always."""

from __future__ import annotations

import os
import re
from typing import Optional

import requests

from .findings import Collector

PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
THRESHOLDS = {"LCP": (2500, 4000), "CLS": (0.1, 0.25), "INP": (200, 500), "FCP": (1800, 3000), "TTFB": (800, 1800)}


def _rate(metric: str, value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    good, poor = THRESHOLDS[metric]
    return "good" if value <= good else "needs-improvement" if value <= poor else "poor"


def run_psi(url: str, strategy: str = "mobile", api_key: Optional[str] = None, timeout: int = 90) -> dict:
    params = {"url": url, "strategy": strategy, "category": "performance"}
    if api_key:
        params["key"] = api_key
    try:
        r = requests.get(PSI_ENDPOINT, params=params, timeout=timeout)
    except requests.RequestException as exc:
        return {"ok": False, "error": exc.__class__.__name__}
    if r.status_code != 200:
        msg = ""
        try:
            msg = r.json().get("error", {}).get("message", "")[:200]
        except Exception:
            pass
        return {"ok": False, "error": f"HTTP {r.status_code} {msg}"}
    data = r.json()
    lh = data.get("lighthouseResult", {})
    audits = lh.get("audits", {})
    field = data.get("loadingExperience", {}).get("metrics", {})
    origin_field = data.get("originLoadingExperience", {}).get("metrics", {})

    def f(metric_key):
        m = field.get(metric_key) or origin_field.get(metric_key)
        return (m or {}).get("percentile")

    def lab(key):
        return (audits.get(key) or {}).get("numericValue")

    opportunities = []
    for key, a in audits.items():
        if a.get("details", {}).get("type") == "opportunity" and (a.get("details", {}).get("overallSavingsMs") or 0) > 150:
            opportunities.append({"id": key, "title": a.get("title"), "savings_ms": round(a["details"]["overallSavingsMs"])})
    opportunities.sort(key=lambda x: -x["savings_ms"])
    diagnostics = []
    for key in ("render-blocking-resources", "unused-javascript", "unused-css-rules", "modern-image-formats", "uses-optimized-images", "uses-responsive-images", "offscreen-images", "server-response-time", "uses-text-compression", "uses-long-cache-ttl", "total-byte-weight", "dom-size", "third-party-summary", "largest-contentful-paint-element", "mainthread-work-breakdown", "font-display"):
        a = audits.get(key)
        if a and a.get("score") is not None and a["score"] < 0.9:
            diagnostics.append({"id": key, "title": a.get("title"), "score": a.get("score"), "display": (a.get("displayValue") or "")[:80]})
    return {
        "ok": True,
        "strategy": strategy,
        "performance_score": round((lh.get("categories", {}).get("performance", {}).get("score") or 0) * 100),
        "field": {
            "LCP": f("LARGEST_CONTENTFUL_PAINT_MS"),
            "CLS": (f("CUMULATIVE_LAYOUT_SHIFT_SCORE") or 0) / 100 if f("CUMULATIVE_LAYOUT_SHIFT_SCORE") is not None else None,
            "INP": f("INTERACTION_TO_NEXT_PAINT"),
            "FCP": f("FIRST_CONTENTFUL_PAINT_MS"),
            "TTFB": f("EXPERIMENTAL_TIME_TO_FIRST_BYTE"),
            "source": "page" if field else ("origin" if origin_field else "none"),
            "overall": data.get("loadingExperience", {}).get("overall_category") or data.get("originLoadingExperience", {}).get("overall_category"),
        },
        "lab": {
            "LCP": lab("largest-contentful-paint"),
            "CLS": lab("cumulative-layout-shift"),
            "TBT": lab("total-blocking-time"),
            "FCP": lab("first-contentful-paint"),
            "SI": lab("speed-index"),
            "TTFB": lab("server-response-time"),
            "total_bytes": lab("total-byte-weight"),
            "dom_size": lab("dom-size"),
        },
        "opportunities": opportunities[:8],
        "diagnostics": diagnostics[:10],
        "lighthouse_version": lh.get("lighthouseVersion"),
    }


def analyze_performance(pages: list, home_url: str, sample_urls: list[str], api_key: Optional[str] = None, skip_psi: bool = False, log=print) -> dict:
    c = Collector("performance")
    html_pages = [p for p in pages if p.status == 200 and "text/html" in (p.content_type or "")]
    api_key = api_key or os.environ.get("PSI_API_KEY") or os.environ.get("PAGESPEED_API_KEY")
    psi_results = {}
    measured = False
    if not skip_psi:
        targets = [home_url] + [u for u in sample_urls if u != home_url][:2]
        for i, u in enumerate(targets):
            log(f"  PageSpeed Insights (mobile) {i + 1}/{len(targets)}: {u}")
            res = run_psi(u, "mobile", api_key)
            psi_results[u] = res
            if res.get("ok"):
                measured = True
            elif "429" in str(res.get("error")) or "quota" in str(res.get("error")).lower():
                log("  PSI quota hit; stopping further PSI calls")
                break
        if measured and home_url in psi_results and psi_results[home_url].get("ok"):
            d = run_psi(home_url, "desktop", api_key)
            psi_results[home_url + "#desktop"] = d

    home_psi = psi_results.get(home_url, {})
    if measured and home_psi.get("ok"):
        fld = home_psi["field"]
        lab = home_psi["lab"]
        score = home_psi["performance_score"]
        src = fld.get("source")
        if src != "none":
            ratings = {m: _rate(m, fld.get(m)) for m in ("LCP", "CLS", "INP")}
            poor = [m for m, r in ratings.items() if r == "poor"]
            ni = [m for m, r in ratings.items() if r == "needs-improvement"]
            if poor:
                c.add("cwv-field-poor", "high", f"Core Web Vitals fail in real-user data: {', '.join(poor)}", "Google uses field CWV as a ranking signal and a page-experience tiebreaker. 'Poor' means most real visitors have a bad experience.", "Fix the failing metric first: LCP (server speed, hero image preload, render-blocking CSS), INP (long JS tasks, third-party scripts), CLS (image dimensions, ads/embeds reserved space, late fonts).", evidence=[f"{m}: {fld.get(m)} ({ratings[m]})" for m in ("LCP", "CLS", "INP")] + [f"source: {src} data, 28-day p75"], effort="high")
            elif ni:
                c.add("cwv-field-needs-improvement", "medium", f"Core Web Vitals need improvement: {', '.join(ni)}", "Not failing, but short of the 'good' threshold Google rewards.", "Tune the named metrics; see PSI opportunities in the evidence.", evidence=[f"{m}: {fld.get(m)} ({ratings[m]})" for m in ("LCP", "CLS", "INP")], effort="medium")
            else:
                c.passed("cwv-field", f"Core Web Vitals pass in field data (LCP {fld.get('LCP')} ms, CLS {fld.get('CLS')}, INP {fld.get('INP')} ms)")
        else:
            c.add("cwv-no-field-data", "info", "No real-user (CrUX) data for this site", "Traffic is below the threshold Google needs to publish field metrics. Lab scores are used instead.", "No action; grow traffic. Treat the lab numbers below as the guide.", effort="low")
        if score < 50:
            c.add("psi-mobile-poor", "high", f"Mobile Lighthouse performance score is {score}/100", "Lab performance this low almost always means slow real-world loads and lost conversions.", "Work through the top opportunities in the evidence list, biggest savings first.", evidence=[f"{o['title']} (save ~{o['savings_ms']} ms)" for o in home_psi["opportunities"][:5]] + [f"LCP lab {round((lab.get('LCP') or 0) / 1000, 1)} s, TBT {round(lab.get('TBT') or 0)} ms, total {round((lab.get('total_bytes') or 0) / 1024)} KB"], effort="high")
        elif score < 80:
            c.add("psi-mobile-average", "medium", f"Mobile Lighthouse performance score is {score}/100", "Room to improve before it costs rankings or conversions.", "Address the top opportunities listed.", evidence=[f"{o['title']} (save ~{o['savings_ms']} ms)" for o in home_psi["opportunities"][:4]], effort="medium")
        else:
            c.passed("psi-mobile", f"Mobile Lighthouse performance {score}/100")
        if (lab.get("total_bytes") or 0) > 3_000_000:
            c.add("page-weight", "medium", f"Homepage weighs {round(lab['total_bytes'] / 1024 / 1024, 1)} MB", "Heavy pages are slow on mobile networks and expensive to crawl.", "Compress images, defer non-critical JS, remove unused CSS and third-party tags.", effort="medium")
        if (lab.get("dom_size") or 0) > 1500:
            c.add("dom-size", "low", f"Homepage DOM has {int(lab['dom_size'])} nodes", "Very large DOMs slow style calculation and interaction.", "Simplify markup; avoid deeply nested builder wrappers.", effort="medium")
        for d in home_psi["diagnostics"]:
            if d["id"] in ("render-blocking-resources", "uses-text-compression", "modern-image-formats", "server-response-time", "unused-javascript"):
                sev = "medium" if d["score"] < 0.5 else "low"
                c.add(f"psi-{d['id']}", sev, d["title"], "Flagged by Lighthouse on the homepage.", "See PageSpeed Insights for the exact resources.", evidence=[d["display"]] if d["display"] else [], effort="medium")
    else:
        reason = home_psi.get("error") if home_psi else ("skipped by flag" if skip_psi else "not attempted")
        c.skipped("cwv", f"Core Web Vitals not measured ({reason}). Set PSI_API_KEY for reliable access.")

    # Always-on HTML heuristics (never claim CWV from these)
    heavy_js = [p for p in html_pages if p.external_scripts > 25]
    if heavy_js and len(heavy_js) > len(html_pages) * 0.3:
        c.add("many-scripts", "low", "Pages load 25+ external scripts", "Each script competes for the main thread and delays interactivity.", "Audit tags: remove unused plugins and trackers, defer the rest.", evidence=[f"{p.url} ({p.external_scripts} scripts)" for p in heavy_js[:4]], affected_count=len(heavy_js), effort="medium")
    no_lazy = [p for p in html_pages if p.images_total > 10 and p.images_lazy == 0]
    if no_lazy and len(no_lazy) > len(html_pages) * 0.4:
        c.add("no-lazy-loading", "low", "Image-heavy pages without lazy loading", "Loading every image up front delays LCP and wastes bandwidth.", "Add loading=\"lazy\" to below-the-fold images (never to the hero image).", affected_count=len(no_lazy), effort="low")
    big_inline_css = [p for p in html_pages if p.inline_css_bytes > 150_000]
    if big_inline_css:
        c.add("huge-inline-css", "low", "Pages with over 150 KB of inline CSS", "Typical of page builders; it bloats every HTML response and blocks rendering.", "Enable the builder's CSS optimisation or move CSS to cached external files.", evidence=[f"{p.url} ({p.inline_css_bytes // 1024} KB)" for p in big_inline_css[:4]], affected_count=len(big_inline_css), effort="medium")
    avg_ms = round(sum(p.elapsed_ms for p in html_pages) / max(len(html_pages), 1))

    out = c.to_dict()
    out["measured"] = measured
    out["psi"] = {k: v for k, v in psi_results.items()}
    out["avg_html_response_ms"] = avg_ms
    out["avg_html_kb"] = round(sum(p.size_bytes for p in html_pages) / max(len(html_pages), 1) / 1024)
    return out
