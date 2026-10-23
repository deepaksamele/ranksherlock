"""Scoring: category scores, two axes (Search SEO, AI Visibility), caps, grade, prioritised findings."""

from __future__ import annotations

from .findings import SEVERITY_ORDER

# Category weights per axis. A category that was not measured is dropped and the rest re-normalised.
SEARCH_WEIGHTS = {"technical": 30, "content": 25, "schema": 12, "performance": 18, "local": 10, "geo": 5}
AI_WEIGHTS = {"geo": 35, "content": 30, "schema": 20, "technical": 15}
OVERALL_MIX = {"search": 0.65, "ai": 0.35}

LANE_RULES = [
    (("robots-", "canonical", "redirect", "www-", "http-", "hreflang", "noindex", "sitemap-non-200", "soft-404", "404-returns", "csr-", "geo-csr", "geo-waf", "cwv-", "psi-"), "assisted"),
    (("schema-", "missing-title", "missing-description", "missing-h1", "images-", "aeo-", "geo-no-llms", "geo-llms", "local-no-map", "local-no-gbp", "no-hsts", "no-xcto", "no-xfo", "no-referrer", "generic-anchor", "duplicate-"), "auto"),
    (("thin-content", "no-about", "no-contact", "no-author", "low-citability", "local-no-location", "local-doorway", "deep-pages", "weak-internal", "hard-to-read", "generic-ai"), "human"),
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


def _axis(cats: dict, weights: dict) -> tuple[int | None, dict]:
    total_w = 0
    acc = 0.0
    used = {}
    for cat, w in weights.items():
        info = cats.get(cat)
        if not info or info.get("measured") is False:
            continue
        acc += info["score"] * w
        total_w += w
        used[cat] = w
    if total_w == 0:
        return None, {}
    norm = {k: round(v / total_w, 3) for k, v in used.items()}
    return round(acc / total_w), norm


def apply_caps(findings: list[dict], search: int | None, ai: int | None) -> tuple[int | None, int | None, list[dict]]:
    """Hard ceilings: some single defects make a high score meaningless."""
    caps = []
    ids = {f["id"] for f in findings}
    rules = [
        ("robots-disallow-all", 20, "robots.txt blocks the entire site", "both"),
        ("homepage-noindex", 25, "homepage is noindex", "both"),
        ("canonical-to-homepage", 45, "pages canonicalise to the homepage", "search"),
        ("no-https", 55, "site is not on HTTPS", "search"),
        ("geo-retrieval-bots-blocked", 40, "answer-engine crawlers are blocked", "ai"),
        ("geo-waf-blocks-ai-bots", 45, "firewall challenges AI crawlers", "ai"),
        ("csr-empty-html", 50, "content is not in the HTML", "ai"),
        ("geo-nosnippet", 30, "homepage forbids snippets", "ai"),
        ("schema-none", 70, "no structured data at all", "ai"),
    ]
    for fid, ceiling, reason, axis in rules:
        if fid in ids:
            if axis in ("search", "both") and search is not None and search > ceiling:
                caps.append({"axis": "search", "id": fid, "ceiling": ceiling, "reason": reason, "uncapped": search})
                search = ceiling
            if axis in ("ai", "both") and ai is not None and ai > ceiling:
                caps.append({"axis": "ai", "id": fid, "ceiling": ceiling, "reason": reason, "uncapped": ai})
                ai = ceiling
    return search, ai, caps


def build_scores(categories: dict) -> dict:
    cats = {k: v for k, v in categories.items() if v}
    search, s_norm = _axis(cats, SEARCH_WEIGHTS)
    ai, a_norm = _axis(cats, AI_WEIGHTS)
    all_findings = [f for v in cats.values() for f in v.get("findings", [])]
    search_c, ai_c, caps = apply_caps(all_findings, search, ai)
    if search_c is not None and ai_c is not None:
        overall = round(search_c * OVERALL_MIX["search"] + ai_c * OVERALL_MIX["ai"])
    else:
        overall = search_c if search_c is not None else ai_c
    # Prioritise findings: severity, then impact, then low effort first
    sev_rank = {s: i for i, s in enumerate(SEVERITY_ORDER)}
    effort_rank = {"low": 0, "medium": 1, "high": 2}
    for f in all_findings:
        f["lane"] = lane_for(f["id"])
        f["priority"] = sev_rank.get(f["severity"], 9) * 10 + effort_rank.get(f.get("effort"), 1)
    ordered = sorted(all_findings, key=lambda f: (f["priority"], -f.get("affected_count", 0)))
    quick_wins = [f for f in ordered if f.get("effort") == "low" and f["severity"] in ("critical", "high", "medium")][:8]
    counts = {s: sum(1 for f in all_findings if f["severity"] == s) for s in SEVERITY_ORDER}
    measured = [k for k, v in cats.items() if v.get("measured", True)]
    unmeasured = [k for k, v in categories.items() if not v or v.get("measured") is False]
    return {
        "overall": overall,
        "grade": grade(overall),
        "search_seo": {"score": search_c, "grade": grade(search_c), "uncapped": search, "weights": s_norm},
        "ai_visibility": {"score": ai_c, "grade": grade(ai_c), "uncapped": ai, "weights": a_norm},
        "caps": caps,
        "categories": {k: {"score": v["score"], "grade": grade(v["score"]), "findings": len(v.get("findings", [])), "passes": v.get("pass_count", 0), "measured": v.get("measured", True)} for k, v in cats.items()},
        "measured": measured,
        "unmeasured": unmeasured,
        "counts": counts,
        "findings": ordered,
        "quick_wins": quick_wins,
        "scoring_version": 1,
    }
