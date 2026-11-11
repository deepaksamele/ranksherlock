"""Scoring: category scores, two axes (Search SEO, AI Visibility), caps, grade, prioritised findings,
business-type weighting and a projected score after the roadmap."""

from __future__ import annotations

from .findings import SEVERITY_ORDER, SEVERITY_WEIGHT, weighted_penalty, score_from_penalty

SCORING_VERSION = 2

# Category weights per axis. A category that was not measured is dropped and the rest re-normalised.
SEARCH_WEIGHTS = {"technical": 28, "content": 24, "schema": 10, "performance": 16, "local": 10, "ecommerce": 7, "geo": 5}
AI_WEIGHTS = {"geo": 35, "content": 30, "schema": 20, "technical": 15}
OVERALL_MIX = {"search": 0.65, "ai": 0.35}

# Business-type adjustments (multipliers on the search axis before normalisation).
TYPE_ADJUST = {
    "local business": {"local": 1.6, "schema": 1.2},
    "home services / construction": {"local": 1.5, "schema": 1.2},
    "restaurant / food": {"local": 1.6, "schema": 1.2},
    "legal": {"local": 1.4, "content": 1.2},
    "real estate": {"local": 1.3, "schema": 1.2},
    "e-commerce": {"ecommerce": 1.6, "schema": 1.4, "performance": 1.2},
    "publisher / media": {"content": 1.4, "geo": 1.4},
    "SaaS / software": {"content": 1.2, "geo": 1.3},
    "finance": {"content": 1.3, "schema": 1.2},
    "healthcare": {"content": 1.3, "local": 1.3},
}

LANE_RULES = [
    (("robots-", "canonical", "redirect", "www-", "http-", "https-", "hreflang", "noindex", "sitemap-non-200", "sitemap-redirected", "soft-404", "404-returns", "csr-", "geo-csr", "geo-waf", "geo-bots-get", "cwv-", "psi-", "ttfb", "tbt-", "server-errors", "timeouts", "parameter-url", "low-value", "pagination", "meta-refresh", "meta-nofollow", "ssl-", "duplicate-content", "many-noindex"), "assisted"),
    (("schema-", "missing-title", "missing-description", "missing-h1", "images-", "aeo-no-faq", "geo-no-llms", "geo-llms", "local-no-map", "local-no-gbp", "no-hsts", "no-xcto", "no-xfo", "no-csp", "no-referrer", "generic-anchor", "duplicate-titles", "duplicate-descriptions", "duplicate-h1", "long-", "short-", "title-", "og-", "missing-og", "missing-twitter", "no-favicon", "no-skip", "empty-", "unlabeled", "viewport", "no-viewport", "no-html-lang", "invalid-html", "render-blocking", "no-lazy", "hero-image", "no-preload", "no-fetchpriority", "no-cdn", "no-compression", "no-cache", "x-powered", "unsafe-target", "nofollow-internal", "legacy-ua", "no-analytics", "heading-", "url-", "mega-menu", "geo-nosnippet", "geo-retrieval", "geo-training", "geo-no-feed", "sitemap-", "orphan", "crawl-", "amp-", "custom-404", "mixed-content", "robots-no-sitemap", "robots-crawl", "broken-", "deep-pages", "huge-inline", "many-scripts", "third-party", "dom-size", "page-weight", "local-schema", "local-no-areaserved", "local-nap", "local-multiple", "ecom-demo", "ecom-duplicate-listings", "ecom-no-visible-price"), "auto"),
    (("thin-content", "no-about", "no-contact", "no-author", "no-dates", "stale-", "low-citability", "local-no-location", "local-doorway", "local-thin", "local-location-page", "local-no-reviews", "local-no-address", "local-no-hours", "local-no-phone", "weak-internal", "low-link", "hard-to-read", "long-sentences", "generic-ai", "placeholder", "template-duplicate", "no-outbound", "articles-no", "ymyl-", "no-social", "aeo-", "geo-entity", "geo-no-wikidata", "geo-wikidata", "geo-no-kg", "geo-no-answer", "geo-few", "no-subheadings", "no-table", "no-terms", "no-privacy", "ui-chrome", "excessive-external", "ecom-thin", "ecom-duplicate-product", "ecom-category", "ecom-no-product", "ecom-no-policy", "ecom-no-trust", "no-terms", "no-privacy"), "human"),
]


def lane_for(finding_id: str) -> str:
    for prefixes, lane in LANE_RULES:
        if finding_id.startswith(prefixes):
            return lane
    return "assisted"


def grade(score) -> str:
    if score is None:
        return "N/A"
    return "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D" if score >= 60 else "F"


def _axis(cats: dict, weights: dict, adjust: dict | None = None) -> tuple[int | None, dict]:
    total_w = 0.0
    acc = 0.0
    used = {}
    for cat, w in weights.items():
        info = cats.get(cat)
        if not info or info.get("measured") is False:
            continue
        w = w * (adjust or {}).get(cat, 1.0)
        acc += info["score"] * w
        total_w += w
        used[cat] = w
    if total_w == 0:
        return None, {}
    norm = {k: round(v / total_w, 3) for k, v in used.items()}
    return round(acc / total_w), norm


CAP_RULES = [
    ("robots-disallow-all", 20, "robots.txt blocks the entire site", "both"),
    ("homepage-noindex", 25, "homepage is noindex", "both"),
    ("ssl-error", 40, "TLS certificate errors", "both"),
    ("canonical-to-homepage", 45, "pages canonicalise to the homepage", "search"),
    ("no-https", 55, "site is not on HTTPS", "search"),
    ("geo-retrieval-bots-blocked", 40, "answer-engine crawlers are blocked", "ai"),
    ("geo-waf-blocks-ai-bots", 45, "firewall challenges AI crawlers", "ai"),
    ("csr-empty-html", 50, "content is not in the HTML", "ai"),
    ("geo-nosnippet", 30, "homepage forbids snippets", "ai"),
    ("schema-none", 70, "no structured data at all", "ai"),
]


def apply_caps(findings: list[dict], search: int | None, ai: int | None) -> tuple[int | None, int | None, list[dict]]:
    caps = []
    ids = {f["id"] for f in findings}
    for fid, ceiling, reason, axis in CAP_RULES:
        if fid in ids:
            if axis in ("search", "both") and search is not None and search > ceiling:
                caps.append({"axis": "search", "id": fid, "ceiling": ceiling, "reason": reason, "uncapped": search})
                search = ceiling
            if axis in ("ai", "both") and ai is not None and ai > ceiling:
                caps.append({"axis": "ai", "id": fid, "ceiling": ceiling, "reason": reason, "uncapped": ai})
                ai = ceiling
    return search, ai, caps


def _scores_from(categories: dict, business_type: str, drop_ids: set | None = None) -> tuple[int | None, int | None, int | None, list[dict]]:
    """Recompute axis and overall scores, optionally pretending some findings are fixed (for projections)."""
    drop_ids = drop_ids or set()
    cats = {}
    for k, v in categories.items():
        if not v:
            continue
        if drop_ids:
            pen = weighted_penalty([f for f in v.get("findings", []) if f["id"] not in drop_ids])
            score = score_from_penalty(pen)
        else:
            score = v["score"]
        cats[k] = {"score": score, "measured": v.get("measured", True)}
    adjust = TYPE_ADJUST.get(business_type, {})
    search, _ = _axis(cats, SEARCH_WEIGHTS, adjust)
    ai, _ = _axis(cats, AI_WEIGHTS)
    all_findings = [f for v in categories.values() if v for f in v.get("findings", []) if f["id"] not in drop_ids]
    search_c, ai_c, caps = apply_caps(all_findings, search, ai)
    if search_c is not None and ai_c is not None:
        overall = round(search_c * OVERALL_MIX["search"] + ai_c * OVERALL_MIX["ai"])
    else:
        overall = search_c if search_c is not None else ai_c
    return overall, search_c, ai_c, caps


def build_scores(categories: dict, business: dict | None = None) -> dict:
    business = business or {}
    btype = business.get("business_type", "")
    cats = {k: v for k, v in categories.items() if v}
    adjust = TYPE_ADJUST.get(btype, {})
    search, s_norm = _axis(cats, SEARCH_WEIGHTS, adjust)
    ai, a_norm = _axis(cats, AI_WEIGHTS)
    all_findings = [f for v in cats.values() for f in v.get("findings", [])]
    search_c, ai_c, caps = apply_caps(all_findings, search, ai)
    if search_c is not None and ai_c is not None:
        overall = round(search_c * OVERALL_MIX["search"] + ai_c * OVERALL_MIX["ai"])
    else:
        overall = search_c if search_c is not None else ai_c
    sev_rank = {s: i for i, s in enumerate(SEVERITY_ORDER)}
    effort_rank = {"low": 0, "medium": 1, "high": 2}
    for f in all_findings:
        f["lane"] = lane_for(f["id"])
        f["priority"] = sev_rank.get(f["severity"], 9) * 10 + effort_rank.get(f.get("effort"), 1)
        f["points"] = SEVERITY_WEIGHT.get(f["severity"], 0)
    ordered = sorted(all_findings, key=lambda f: (f["priority"], -f.get("affected_count", 0)))
    quick_wins = [f for f in ordered if f.get("effort") == "low" and f["severity"] in ("critical", "high", "medium")][:10]
    counts = {s: sum(1 for f in all_findings if f["severity"] == s) for s in SEVERITY_ORDER}
    measured = [k for k, v in cats.items() if v.get("measured", True)]
    unmeasured = [k for k, v in categories.items() if not v or v.get("measured") is False]
    # Projections: after phase 1 (critical + low-effort high/medium), after everything actionable
    actionable = [f for f in ordered if f["severity"] != "info"]
    p1 = {f["id"] for f in actionable if f["severity"] == "critical" or (f["severity"] in ("high", "medium") and f.get("effort") == "low")}
    p2 = p1 | {f["id"] for f in actionable if f["severity"] in ("high", "medium") and f.get("lane") != "human"}
    p3 = {f["id"] for f in actionable}
    proj = {}
    for name, ids in (("phase1", p1), ("phase2", p2), ("phase3", p3)):
        o, s, a, _ = _scores_from(categories, btype, ids)
        proj[name] = {"overall": o, "search": s, "ai": a, "grade": grade(o), "fixes": len(ids)}
    return {
        "overall": overall,
        "grade": grade(overall),
        "search_seo": {"score": search_c, "grade": grade(search_c), "uncapped": search, "weights": s_norm},
        "ai_visibility": {"score": ai_c, "grade": grade(ai_c), "uncapped": ai, "weights": a_norm},
        "caps": caps,
        "categories": {k: {"score": v["score"], "grade": grade(v["score"]), "findings": len([f for f in v.get("findings", []) if f["severity"] != "info"]), "passes": v.get("pass_count", 0), "measured": v.get("measured", True), "penalty": v.get("penalty", 0)} for k, v in cats.items()},
        "measured": measured,
        "unmeasured": unmeasured,
        "counts": counts,
        "findings": ordered,
        "quick_wins": quick_wins,
        "projected": proj,
        "business_type": btype,
        "type_adjustments": adjust,
        "scoring_version": SCORING_VERSION,
    }
