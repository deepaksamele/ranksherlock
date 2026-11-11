"""Performance: PageSpeed Insights (field + lab) on a page-type sample when reachable; HTML-level checks always."""

from __future__ import annotations

import os
import re
from collections import Counter
from typing import Optional

import requests

from .business import page_type
from .findings import Collector

PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
THRESHOLDS = {"LCP": (2500, 4000), "CLS": (0.1, 0.25), "INP": (200, 500), "FCP": (1800, 3000), "TTFB": (800, 1800)}
CDN_HINTS = {"cf-ray": "Cloudflare", "x-vercel-id": "Vercel", "x-amz-cf-id": "CloudFront", "x-cache": "edge cache", "x-fastly-request-id": "Fastly", "x-akamai-transformed": "Akamai", "x-sucuri-id": "Sucuri", "x-cdn": "CDN"}


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
    for key in ("render-blocking-resources", "unused-javascript", "unused-css-rules", "modern-image-formats", "uses-optimized-images", "uses-responsive-images", "offscreen-images", "server-response-time", "uses-text-compression", "uses-long-cache-ttl", "total-byte-weight", "dom-size", "third-party-summary", "largest-contentful-paint-element", "mainthread-work-breakdown", "font-display", "bootup-time", "legacy-javascript"):
        a = audits.get(key)
        if a and a.get("score") is not None and a["score"] < 0.9:
            diagnostics.append({"id": key, "title": a.get("title"), "score": a.get("score"), "display": (a.get("displayValue") or "")[:80]})
    lcp_el = ""
    try:
        items = audits.get("largest-contentful-paint-element", {}).get("details", {}).get("items", [])
        if items and isinstance(items[0], dict):
            node = items[0].get("node") or (items[0].get("items") or [{}])[0].get("node") or {}
            lcp_el = (node.get("snippet") or node.get("nodeLabel") or "")[:160]
    except Exception:
        pass
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
            "js_execution_ms": lab("bootup-time"),
        },
        "lcp_element": lcp_el,
        "opportunities": opportunities[:8],
        "diagnostics": diagnostics[:12],
        "lighthouse_version": lh.get("lighthouseVersion"),
    }


def _sample_urls(pages: list, home_url: str) -> list[str]:
    """Homepage plus the best representative of up to three other page types."""
    html = [p for p in pages if p.status == 200 and "text/html" in (p.content_type or "") and p.depth < 99]
    chosen = [home_url]
    by_type = {}
    for p in sorted(html, key=lambda p: (p.depth, -p.word_count)):
        t = page_type(p.url, p)
        if t in ("home", "cart", "search", "legal", "pagination", "tag") or p.url == home_url:
            continue
        by_type.setdefault(t, p.url)
    for t in ("product", "category", "service", "article", "location", "other", "about"):
        if t in by_type and len(chosen) < 4:
            chosen.append(by_type[t])
    return chosen


def analyze_performance(pages: list, home_url: str, sample_urls: list[str] | None = None, api_key: Optional[str] = None, skip_psi: bool = False, log=print, fetcher=None) -> dict:
    c = Collector("performance")
    html_pages = [p for p in pages if p.status == 200 and "text/html" in (p.content_type or "")]
    n = max(len(html_pages), 1)
    api_key = api_key or os.environ.get("PSI_API_KEY") or os.environ.get("PAGESPEED_API_KEY")
    psi_results = {}
    measured = False
    targets = sample_urls or _sample_urls(pages, home_url)
    if not skip_psi:
        for i, u in enumerate(targets):
            log(f"  PageSpeed Insights (mobile) {i + 1}/{len(targets)}: {u}")
            res = run_psi(u, "mobile", api_key)
            psi_results[u] = res
            if res.get("ok"):
                measured = True
            elif "429" in str(res.get("error")) or "quota" in str(res.get("error")).lower():
                log("  PSI quota hit; stopping further PSI calls (set PSI_API_KEY for your own quota)")
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
            if fld.get("TTFB") and fld["TTFB"] > 1800:
                c.add("ttfb-field-poor", "medium", f"Real-user time to first byte is {fld['TTFB']} ms", "A slow server response caps every other speed metric; Google's good threshold is 800 ms.", "Add full-page caching, a CDN in front of the origin, or faster hosting.", effort="medium")
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
        if (lab.get("TBT") or 0) > 600:
            c.add("tbt-high", "medium", f"Total blocking time is {round(lab['TBT'])} ms", "Long JavaScript tasks freeze the page after it appears; this is the lab proxy for a poor INP.", "Split or defer heavy scripts, remove unused third-party tags, lazy-load widgets.", effort="high")
        for d in home_psi["diagnostics"]:
            if d["id"] in ("render-blocking-resources", "uses-text-compression", "modern-image-formats", "server-response-time", "unused-javascript", "uses-long-cache-ttl", "third-party-summary", "legacy-javascript"):
                sev = "medium" if d["score"] < 0.5 else "low"
                c.add(f"psi-{d['id']}", sev, d["title"], "Flagged by Lighthouse on the homepage.", "See PageSpeed Insights for the exact resources.", evidence=[d["display"]] if d["display"] else [], effort="medium")
        other = [(u, r) for u, r in psi_results.items() if r.get("ok") and u != home_url and "#desktop" not in u]
        slow_inner = [(u, r["performance_score"]) for u, r in other if r["performance_score"] < 50]
        if slow_inner:
            c.add("psi-inner-pages-poor", "medium", f"{len(slow_inner)} sampled inner page templates score under 50 on mobile", "The homepage is often optimised while product, category or article templates are not; those templates carry most of the traffic.", "Apply the same optimisations to every template, starting with the ones listed.", evidence=[f"{u}: {s}/100" for u, s in slow_inner], affected_count=len(slow_inner), effort="high")
    else:
        reason = home_psi.get("error") if home_psi else ("skipped by flag" if skip_psi else "not attempted")
        c.skipped("cwv", f"Core Web Vitals not measured ({reason}). Set PSI_API_KEY for reliable access.")

    # ------------------------------------------- Always-on HTML heuristics
    heavy_js = [p for p in html_pages if p.external_scripts > 25]
    if heavy_js and len(heavy_js) > n * 0.3:
        c.add("many-scripts", "low", f"Pages load {round(sum(p.external_scripts for p in heavy_js) / len(heavy_js))} external scripts on average", "Each script competes for the main thread and delays interactivity.", "Audit tags: remove unused plugins and trackers, defer the rest.", evidence=[f"{p.url} ({p.external_scripts} scripts)" for p in heavy_js[:4]], affected_count=len(heavy_js), effort="medium")
    blocking = [p for p in html_pages if p.blocking_scripts >= 3]
    if blocking and len(blocking) > n * 0.3:
        c.add("render-blocking-scripts", "medium", f"{round(sum(p.blocking_scripts for p in blocking) / len(blocking))} render-blocking scripts in <head> on most pages", "Scripts in the head without async or defer stop the browser from painting anything until they download and run.", "Add defer (or async) to head scripts, or move them before </body>.", evidence=[f"{p.url} ({p.blocking_scripts} blocking)" for p in blocking[:4]], affected_count=len(blocking), effort="low")
    else:
        c.passed("render-blocking-scripts", "Few or no render-blocking scripts in <head>")
    tp = Counter(h for p in html_pages[:200] for h in p.third_party_script_hosts)
    home = next((p for p in html_pages if p.url == home_url), None)
    if home is not None:
        if len(home.third_party_script_hosts) > 12:
            c.add("third-party-scripts", "low", f"Homepage loads scripts from {len(home.third_party_script_hosts)} third-party hosts", "Every third-party host adds DNS, connection and execution cost you do not control.", "Remove unused tags; load the rest through a tag manager with consent and delay.", evidence=home.third_party_script_hosts[:8], affected_count=len(home.third_party_script_hosts), effort="medium")
    no_lazy = [p for p in html_pages if p.images_total > 10 and p.images_lazy == 0]
    if no_lazy and len(no_lazy) > n * 0.4:
        c.add("no-lazy-loading", "low", f"{len(no_lazy):,} image-heavy pages do not lazy-load images", "Loading every image up front delays LCP and wastes bandwidth.", "Add loading=\"lazy\" to below-the-fold images (never to the hero image).", affected_count=len(no_lazy), effort="low")
    big_inline_css = [p for p in html_pages if p.inline_css_bytes > 150_000]
    if big_inline_css:
        c.add("huge-inline-css", "low", f"{len(big_inline_css):,} pages carry over 150 KB of inline CSS", "Typical of page builders; it bloats every HTML response and blocks rendering.", "Enable the builder's CSS optimisation or move CSS to cached external files.", evidence=[f"{p.url} ({p.inline_css_bytes // 1024} KB)" for p in big_inline_css[:4]], affected_count=len(big_inline_css), effort="medium")
    big_dom = [p for p in html_pages if p.dom_nodes > 2500]
    if big_dom and len(big_dom) > n * 0.3 and not (measured and home_psi.get("ok")):
        c.add("dom-size-html", "low", f"{len(big_dom):,} pages have more than 2,500 HTML elements", "Very large DOMs slow style calculation, layout and interaction on phones.", "Simplify templates; avoid nested builder wrappers and mega menus.", evidence=[f"{p.url} ({p.dom_nodes} elements)" for p in big_dom[:4]], affected_count=len(big_dom), effort="medium")
    if home is not None:
        cdn = [name for h, name in CDN_HINTS.items() if h in home.headers] or (["Cloudflare"] if "cloudflare" in (home.headers.get("server") or "").lower() else [])
        if cdn:
            c.passed("cdn", f"Served through a CDN/edge ({cdn[0]})")
        else:
            c.add("no-cdn", "info", "No CDN or edge cache detected on HTML responses", "A CDN cuts latency for distant visitors and absorbs crawler load.", "Put Cloudflare, CloudFront or Fastly in front of the origin, or enable the host's CDN.", effort="low")
        if home.preload_hints == 0 and home.images_total > 3:
            c.add("no-preload-hints", "info", "No preload or preconnect hints on the homepage", "Preconnecting to font/CDN hosts and preloading the hero image shaves hundreds of milliseconds off LCP.", "Add <link rel=preconnect> for third-party hosts and <link rel=preload as=image> for the LCP image.", effort="low")
        if home.images_fetchpriority == 0 and home.images_total > 3:
            c.add("no-fetchpriority", "info", "Hero image is not marked fetchpriority=high", "Browsers download images in document order; the hero image should jump the queue.", "Add fetchpriority=\"high\" to the above-the-fold hero image.", effort="low")

    # Image weight sample via HEAD requests
    img_sizes = []
    if fetcher is not None:
        seen = set()
        sample_pages = [p for p in html_pages if p.url in targets] or html_pages[:3]
        for p in sample_pages:
            for src in p.image_srcs[:20]:
                if src in seen or len(seen) >= 40:
                    continue
                seen.add(src)
                try:
                    s = fetcher._session()
                    r = s.head(src, timeout=10, allow_redirects=True)
                    size = int(r.headers.get("content-length") or 0)
                    ctype = r.headers.get("content-type", "")
                    if size:
                        img_sizes.append((src, size, ctype))
                except Exception:
                    continue
        big = [(s, b) for s, b, _ in img_sizes if b > 300_000]
        if big:
            total_kb = sum(b for _, b in big) // 1024
            c.add("images-oversized", "medium" if len(big) >= 3 else "low", f"{len(big)} sampled images are over 300 KB ({total_kb:,} KB total)", "Oversized images are the most common cause of slow LCP on mobile.", "Resize to the displayed dimensions, compress to WebP/AVIF at quality 75 to 80, and serve responsive sizes.", evidence=[f"{s[:90]} ({b // 1024} KB)" for s, b in sorted(big, key=lambda x: -x[1])[:5]], affected_count=len(big), effort="low")
        elif img_sizes:
            c.passed("image-weight", f"Sampled {len(img_sizes)} images; none over 300 KB")

    avg_ms = round(sum(p.elapsed_ms for p in html_pages) / n)
    out = c.to_dict()
    out["measured"] = measured
    out["psi"] = {k: v for k, v in psi_results.items()}
    out["psi_sample"] = targets
    out["avg_html_response_ms"] = avg_ms
    out["avg_html_kb"] = round(sum(p.size_bytes for p in html_pages) / n / 1024)
    out["third_party_hosts"] = dict(tp.most_common(15))
    out["image_sample"] = [{"src": s, "kb": b // 1024, "type": t} for s, b, t in sorted(img_sizes, key=lambda x: -x[1])[:15]]
    return out
