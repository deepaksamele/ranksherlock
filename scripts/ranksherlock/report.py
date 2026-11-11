"""Client-facing report: self-contained HTML (screen layout with side navigation) that prints to a clean A4 PDF.

Design system: one navy ink, one accent colour, muted status colours, small-caps labels, hairline tables.
Print layout uses CSS paged media (full-bleed cover, running header and page numbers via @page margin boxes),
so the PDF is produced by Chromium straight from the same HTML.
"""

from __future__ import annotations

import html
import math
import re
from datetime import date

from .report_text import CAT_INTRO, CAT_LABELS, CAT_ORDER, CAT_SHORT, GLOSSARY, LANE_LABEL, OWNER_DEFAULT, SEV_LABEL

SEV_ORDER = ["critical", "high", "medium", "low", "info"]
SEV_SOLID = {"critical": "#d92d20", "high": "#e0621a", "medium": "#d08a00", "low": "#3b6fe0", "info": "#98a2b3"}
SEV_MEANING = {
    "critical": "Blocks indexing, ranking or AI access. Fix immediately.",
    "high": "Materially suppresses rankings, rich results or citations.",
    "medium": "Measurable loss of visibility or trust. Schedule this quarter.",
    "low": "Hygiene and polish; fix when touching the template.",
    "info": "Context only; no action required.",
}
ST_LABEL = {"allowed": "Allowed", "allowed-by-wildcard": "Allowed", "not-mentioned": "Allowed (no rule)", "no-robots": "Allowed (no robots.txt)", "partial": "Partly restricted", "blocked": "Blocked", "blocked-by-wildcard": "Blocked (wildcard)"}


# --------------------------------------------------------------------------- helpers
def e(s) -> str:
    return html.escape(str(s if s is not None else ""))


def css_str(s) -> str:
    return str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def resolve_logo(value: str) -> str:
    """Accept a URL, a data URI or a local image path. Local files are embedded so the report stays self-contained."""
    value = (value or "").strip().strip('"')
    if not value or value.startswith(("http://", "https://", "data:")):
        return value
    import base64
    from pathlib import Path

    p = Path(value).expanduser()
    if not p.is_file() or p.stat().st_size > 3_000_000:
        return ""
    mime = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}.get(p.suffix.lower())
    if not mime:
        return ""
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode("ascii")


def score_color(score) -> str:
    if score is None:
        return "#98a2b3"
    if score >= 90:
        return "#0f8a4f"
    if score >= 80:
        return "#2e9e5b"
    if score >= 70:
        return "#d08a00"
    if score >= 60:
        return "#e0621a"
    return "#d92d20"


grade_color = score_color  # backwards-compatible name


def grade_word(score) -> str:
    if score is None:
        return "not measured"
    return "excellent" if score >= 90 else "good" if score >= 80 else "fair" if score >= 70 else "weak" if score >= 60 else "poor"


def num(n) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return e(n)


def chip(sev: str) -> str:
    return '<span class="chip sev-' + sev + '">' + SEV_LABEL.get(sev, sev) + "</span>"


def gauge(score, grade: str = "", size: int = 150, dark: bool = False) -> str:
    """270-degree arc gauge with the score in the middle and the grade in the gap."""
    stroke = max(8, round(size * 0.085))
    r = (size - stroke) / 2
    c = 2 * math.pi * r
    arc = c * 0.75
    val = 0 if score is None else max(0, min(100, score))
    color = score_color(score)
    track = "rgba(255,255,255,.16)" if dark else "#e6eaf0"
    txt = "#ffffff" if dark else "#0f172a"
    sub = "rgba(255,255,255,.72)" if dark else "#64748b"
    label = "n/a" if score is None else str(score)
    cx = size / 2
    return (
        f'<svg class="gauge" width="{size}" height="{size}" viewBox="0 0 {size} {size}" role="img" aria-label="score {label}">'
        f'<circle cx="{cx}" cy="{cx}" r="{r:.1f}" fill="none" stroke="{track}" stroke-width="{stroke}" stroke-linecap="round" stroke-dasharray="{arc:.1f} {c:.1f}" transform="rotate(135 {cx} {cx})"/>'
        + (f'<circle cx="{cx}" cy="{cx}" r="{r:.1f}" fill="none" stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" stroke-dasharray="{arc * val / 100:.1f} {c:.1f}" transform="rotate(135 {cx} {cx})"/>' if val > 0 else "")
        + f'<text x="50%" y="{size * 0.5:.0f}" text-anchor="middle" dominant-baseline="central" font-size="{size * 0.31:.0f}" font-weight="700" fill="{txt}" letter-spacing="-1">{label}</text>'
        f'<text x="50%" y="{size * 0.88:.0f}" text-anchor="middle" font-size="{max(9, size * 0.085):.0f}" font-weight="700" fill="{sub}" letter-spacing="1.2">{e(grade)}</text>'
        "</svg>"
    )


def hbar(label: str, value, max_value: float = 100, color: str = "", right: str = "", href: str = "", compact: bool = False) -> str:
    pct = 0 if not max_value or value is None else max(0.0, min(100.0, 100.0 * float(value) / float(max_value)))
    color = color or "var(--accent)"
    tag = "a" if href else "div"
    attr = f' href="{e(href)}"' if href else ""
    val = "n/a" if value is None else num(value)
    cls = "hbar" + (" c" if compact else "") + (" na" if value is None else "")
    tail = "" if compact else f'<span class="hbar-g">{e(right)}</span>'
    return (
        f'<{tag} class="{cls}"{attr}><span class="hbar-l">{e(label)}</span>'
        f'<span class="hbar-t"><i class="hbar-f" style="width:{pct:.1f}%;background:{color}"></i></span>'
        f'<span class="hbar-v">{val}</span>{tail}</{tag}>'
    )


def trajectory(points: list) -> str:
    """Small line chart: projected overall score per roadmap phase. points = [(label, score)]."""
    pts = [(l, sc) for l, sc in points if sc is not None]
    if len(pts) < 2:
        return ""
    w, h, pad = 720, 150, 56
    lo = max(0, min(sc for _, sc in pts) - 15)
    hi = 100
    step = (w - 2 * pad) / (len(pts) - 1)
    xy = []
    for i, (_, sc) in enumerate(pts):
        x = pad + i * step
        y = 28 + (h - 70) * (1 - (sc - lo) / max(hi - lo, 1))
        xy.append((x, y))
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in xy)
    area = f"{xy[0][0]:.1f},{h - 34} " + line + f" {xy[-1][0]:.1f},{h - 34}"
    out = [f'<svg class="traj" viewBox="0 0 {w} {h}" role="img" aria-label="projected score by phase">']
    out.append(f'<line x1="{pad - 20}" y1="{h - 34}" x2="{w - pad + 20}" y2="{h - 34}" stroke="#e2e8f0"/>')
    out.append(f'<polygon points="{area}" fill="var(--accent)" opacity=".08"/>')
    out.append(f'<polyline points="{line}" fill="none" stroke="var(--accent)" stroke-width="2.5" stroke-linejoin="round"/>')
    for (label, sc), (x, y) in zip(pts, xy):
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5.5" fill="#fff" stroke="{score_color(sc)}" stroke-width="3"/>')
        out.append(f'<text x="{x:.1f}" y="{y - 13:.1f}" text-anchor="middle" font-size="15" font-weight="700" fill="#0f172a">{sc}</text>')
        out.append(f'<text x="{x:.1f}" y="{h - 14}" text-anchor="middle" font-size="11" fill="#64748b" letter-spacing=".6">{e(label.upper())}</text>')
    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------- narrative
def takeaways(audit: dict) -> dict:
    """Plain-language verdict and key points built only from measured data."""
    s = audit["scores"]
    site = audit["site"]
    cats = s["categories"]
    findings = s["findings"]
    crawl = audit["crawl"]
    host = site["host"]
    overall = s["overall"]
    crit = [f for f in findings if f["severity"] == "critical"]
    high = [f for f in findings if f["severity"] == "high"]
    checks = sum(len(c.get("checks", [])) for c in audit["categories"].values() if c)
    measured = [(k, v) for k, v in cats.items() if v.get("measured", True)]

    if crit:
        second = f"{len(crit)} critical defect{'s' if len(crit) != 1 else ''} must be fixed before anything else pays off."
    elif high:
        second = f"Nothing is critically broken, but {len(high)} high-severity issue{'s' if len(high) != 1 else ''} hold{'' if len(high) != 1 else 's'} the score back."
    else:
        second = "No critical or high-severity defects were found; the remaining work is refinement that lifts rankings, clicks and AI citations."
    verdict = f"{host} scores {overall}/100 overall (grade {s['grade']}, {grade_word(overall)}): {s['search_seo']['score']} for search engines and {s['ai_visibility']['score']} for AI visibility. {second}"

    points = []
    whole = " (the whole site)" if crawl.get("complete") else ""
    points.append(("Scope", f"{num(crawl['pages_crawled'])} pages crawled{whole}, robots.txt and {crawl.get('sitemaps', {}).get('files_fetched', 0)} sitemap files read, AI crawler access tested live, {checks} checks run across {len(measured)} areas. The site runs on {site.get('platform') or 'an unidentified platform'} and reads as a {site.get('business_type', 'business')} site."))
    top = crit[:3] or high[:3] or [f for f in findings if f["severity"] == "medium"][:3]
    if top:
        points.append(("Biggest issues", "; ".join(f["title"] for f in top) + "."))
    if measured:
        strongest = sorted(measured, key=lambda kv: -kv[1]["score"])[:2]
        weakest = sorted(measured, key=lambda kv: kv[1]["score"])[:2]
        st = ", ".join(f"{CAT_SHORT.get(k, k)} ({v['score']})" for k, v in strongest)
        wk = ", ".join(f"{CAT_SHORT.get(k, k)} ({v['score']})" for k, v in weakest)
        points.append(("Strong and weak", f"Strongest: {st}. Weakest: {wk}."))
    geo = audit["categories"].get("geo", {})
    bots = geo.get("bot_status", {})
    blocked = [b for b, i in bots.items() if i["role"] in ("retrieval", "user-fetch") and i["status"] in ("blocked", "blocked-by-wildcard")]
    challenged = [b for b, r in geo.get("ua_probes", {}).items() if r.get("challenged")]
    avg_cit = audit["categories"].get("content", {}).get("avg_citability")
    if blocked or challenged:
        parts = []
        if blocked:
            parts.append("robots.txt blocks " + ", ".join(blocked[:5]))
        if challenged:
            parts.append("the firewall challenges " + ", ".join(challenged[:5]))
        points.append(("AI visibility", "AI answer engines cannot fully reach the site: " + " and ".join(parts) + ". Until that is fixed the brand cannot be cited by those engines."))
    else:
        tail = "which is low: most pages open with preamble instead of a direct answer." if (avg_cit or 0) < 45 else "a reasonable base to build on."
        points.append(("AI visibility", f"AI answer engines can fetch the site. Average passage citability is {avg_cit}/100, {tail}"))
    proj = s.get("projected", {})
    p3 = (proj.get("phase3") or {}).get("overall")
    p1 = (proj.get("phase1") or {}).get("overall")
    if p3 is not None and p3 > (overall or 0):
        target = "the high 90s" if p3 >= 97 else f"about {p3}"
        points.append(("Potential", f"Fixing the phase 1 quick wins lifts the score to roughly {p1}; fixing every actionable finding takes it to {target}. A guide to progress, not a traffic forecast."))
    if s["unmeasured"]:
        points.append(("Not measured", ", ".join(CAT_LABELS.get(u, u) for u in s["unmeasured"]) + ". These areas are excluded from the score rather than guessed."))
    return {"verdict": verdict, "points": points}


def narrative(audit: dict) -> list:
    t = takeaways(audit)
    return [t["verdict"]] + [f"{label}: {text}" for label, text in t["points"]]


# --------------------------------------------------------------------------- components
def finding_card(f: dict, idx: int, origin: str = "") -> str:
    sev = f["severity"]

    def short(x) -> str:
        t = str(x)
        if origin:
            t = t.replace(origin + "/", "/")
        return t

    ev_items = "".join("<li>" + e(short(x)) + "</li>" for x in f.get("evidence", [])[:10])
    pages = f.get("pages", [])
    more = ""
    if len(pages) > 10:
        more = f'<p class="muted small">{num(len(pages) - 10)} more affected URLs are listed in findings.csv.</p>'
    steps = f.get("steps") or []
    if steps:
        fix_html = "<ol>" + "".join("<li>" + e(st) + "</li>" for st in steps) + "</ol>"
    else:
        fix_html = "<p>" + e(f["fix"]) + "</p>"
    affected = f.get("affected_count", 1)
    owner = f.get("owner") or OWNER_DEFAULT.get(f["category"], "")
    rows = []
    if f.get("what"):
        rows.append(("What we checked", "", "<p>" + e(f["what"]) + "</p>"))
    found = "<p>" + e(f["title"].rstrip(".")) + ".</p>"
    if ev_items:
        found += '<ul class="ev">' + ev_items + "</ul>" + more
    rows.append(("What we found", " found", found))
    rows.append(("Why it matters", "", "<p>" + e(f.get("why_long") or f["why"]) + "</p>"))
    if f.get("business_impact"):
        rows.append(("Business impact", " impact", "<p>" + e(f["business_impact"]) + "</p>"))
    rows.append(("How to fix", " fix", fix_html))
    if f.get("verify"):
        rows.append(("How to verify", "", "<p>" + e(f["verify"]) + "</p>"))
    if f.get("ref"):
        rows.append(("Reference", " ref", '<p><a href="' + e(f["ref"]) + '">' + e(f["ref"]) + "</a></p>"))
    body = "".join(f'<div class="row{cls}"><div class="k">{label}</div><div class="v">{content}</div></div>' for label, cls, content in rows)
    meta = (
        chip(sev)
        + f"<span>Affected <b>{num(affected)}</b></span>"
        + f"<span>Effort <b>{e(f.get('effort'))}</b></span>"
        + f"<span>Owner <b>{e(owner)}</b></span>"
        + f"<span>{e(LANE_LABEL.get(f.get('lane'), f.get('lane') or ''))}</span>"
    )
    return (
        f'<article class="finding fs-{sev}" id="f-{e(f["id"])}">'
        f'<header class="f-head"><span class="f-num">{idx:02d}</span><div><h4>{e(f["title"])}</h4><div class="f-meta">{meta}</div></div></header>'
        f'<div class="f-body">{body}</div></article>'
    )


def checks_block(checks: list) -> str:
    rank = {s: i for i, s in enumerate(SEV_ORDER)}
    issues = sorted([c for c in checks if c["status"] in ("fail", "info")], key=lambda c: (rank.get(c.get("severity", "info"), 9), c.get("title", "")))
    passes = sorted([c for c in checks if c["status"] == "pass"], key=lambda c: c.get("title", ""))
    skips = [c for c in checks if c["status"] == "skip"]
    out = ""
    if issues:
        rows = ""
        for c in issues:
            aff = num(c.get("affected")) if c.get("affected") else ""
            rows += f"<tr><td>{chip(c.get('severity', 'info'))}</td><td>{e(c.get('title'))}</td><td class='muted'>{e(c.get('group', ''))}</td><td class='num'>{aff}</td></tr>"
        out += f"<h3>Issues found ({len(issues)})</h3><table class='tight'><tr><th style='width:86px'>Severity</th><th>Check</th><th>Area</th><th class='num'>Affected</th></tr>{rows}</table>"
    if passes:
        out += f"<h3>Checks passed ({len(passes)})</h3><ul class='ticks cols'>" + "".join("<li>" + e(c.get("title")) + "</li>" for c in passes) + "</ul>"
    if skips:
        out += "<h3>Not measured</h3><ul class='dashes'>" + "".join("<li>" + e(c.get("title")) + (": " + e(c["note"]) if c.get("note") else "") + "</li>" for c in skips) + "</ul>"
    return out


CSS = r"""
:root{--ink:#0f172a;--ink2:#334155;--muted:#64748b;--faint:#94a3b8;--line:#e2e8f0;--soft:#f8fafc;--navy:#0b1b33;--accent:__ACCENT__;--accent-soft:color-mix(in srgb,__ACCENT__ 8%,#fff);--accent-mid:color-mix(in srgb,__ACCENT__ 50%,#fff);--good:#0f8a4f;--warn:#b7791f;--bad:#c4320a;--mono:"JetBrains Mono","Cascadia Mono",ui-monospace,Menlo,Consolas,monospace}
*{box-sizing:border-box}
html{-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{margin:0;background:#eef1f5;color:var(--ink);font:14px/1.6 "Inter","Segoe UI Variable Text","Segoe UI",system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif;font-variant-numeric:tabular-nums;-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none;border-bottom:1px solid color-mix(in srgb,var(--accent) 40%,transparent)}
a:hover{color:var(--accent)}
h1,h2,h3,h4{margin:0;letter-spacing:-.015em;color:var(--ink)}
p{margin:0 0 10px}
.muted{color:var(--muted)}.small{font-size:12px}.num{text-align:right}
.layout{display:grid;grid-template-columns:232px minmax(0,940px);gap:28px;justify-content:center;padding:28px 20px 64px}
.nav{position:sticky;top:24px;align-self:start;font-size:12.5px;max-height:calc(100vh - 48px);overflow:auto;padding-right:4px}
.nav .nb{font-weight:800;font-size:15px;letter-spacing:.01em}
.nav .nc{color:var(--muted);margin:0 0 16px;font-size:12px}
.nav a{display:grid;grid-template-columns:22px 1fr;gap:6px;padding:5px 10px;border:0;border-radius:7px;color:var(--ink2);line-height:1.35}
.nav a:hover{background:#dfe5ee;color:var(--ink)}
.nav a span{color:var(--faint);font-size:11px;padding-top:1px}
.nav .ns{height:1px;background:#d8dee8;margin:8px 10px}
main{min-width:0}
.sheet{background:#fff;border:1px solid var(--line);border-radius:14px;padding:44px 48px 40px;margin-bottom:24px;box-shadow:0 1px 2px rgba(15,23,42,.04)}
.sh{display:flex;align-items:baseline;gap:14px;padding-bottom:14px;margin-bottom:22px;border-bottom:1px solid var(--line)}
.sh-num{font-size:13px;font-weight:700;color:var(--accent);letter-spacing:.1em}
.sh h2{font-size:26px;font-weight:700}
h3{font-size:11.5px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);font-weight:700;margin:26px 0 10px}
.lead{font-size:14.5px;color:var(--ink2);max-width:820px}

/* cover */
.cover{position:relative;overflow:hidden;color:#fff;background:linear-gradient(140deg,#071326 0%,#0b1b33 46%,#10294d 100%);border-radius:14px;padding:56px 60px 44px;margin-bottom:24px;min-height:1180px;display:flex;flex-direction:column;justify-content:space-between}
.cover:before{content:"";position:absolute;right:-190px;top:-190px;width:560px;height:560px;border-radius:50%;border:1px solid rgba(255,255,255,.09);box-shadow:0 0 0 70px rgba(255,255,255,.028),0 0 0 150px rgba(255,255,255,.02),0 0 0 240px rgba(255,255,255,.012)}
.cover:after{content:"";position:absolute;left:0;bottom:0;height:7px;width:100%;background:linear-gradient(90deg,var(--accent),var(--accent-mid))}
.cv-top{position:relative;display:flex;justify-content:space-between;align-items:center}
.cv-brand{font-weight:800;font-size:19px;letter-spacing:.01em;display:flex;align-items:center;gap:12px}
.cv-brand img{height:64px;width:auto;max-width:340px;display:block}
.back{min-height:900px}
.back h1{font-size:50px}
.bk-steps{display:grid;gap:22px;max-width:640px}
.bk-step{display:grid;grid-template-columns:44px 1fr;gap:18px;align-items:start}
.bk-step span{width:40px;height:40px;border-radius:50%;border:2px solid var(--accent-mid);color:#fff;font-weight:700;font-size:16px;display:grid;place-items:center}
.bk-step b{display:block;font-size:18px;color:#fff;margin-bottom:3px}
.bk-step p{margin:0;color:rgba(255,255,255,.75);font-size:14.5px}
.bk-meta{grid-template-columns:auto 1fr;gap:56px}
.bk-meta b{white-space:nowrap}
.cv-conf{color:rgba(255,255,255,.55);text-transform:uppercase;font-size:10.5px;letter-spacing:.2em}
.cv-mid{position:relative}
.cv-kicker{font-size:12px;letter-spacing:.26em;text-transform:uppercase;color:var(--accent-mid);font-weight:700;margin-bottom:18px}
.cover h1{color:#fff;font-size:60px;line-height:1.03;font-weight:800;letter-spacing:-.035em;margin-bottom:14px;max-width:780px}
.cv-url{color:rgba(255,255,255,.72);font-size:16px}
.cv-rule{width:72px;height:4px;background:var(--accent-mid);border-radius:2px;margin:34px 0 30px}
.cv-scores{display:grid;grid-template-columns:auto minmax(0,400px);gap:52px;align-items:center}
.cv-g{text-align:center}
.cv-g .l{font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:rgba(255,255,255,.62);margin-top:2px;font-weight:600}
.cv-side{display:grid;gap:22px}
.cv-metric{display:grid;grid-template-columns:1fr auto;align-items:end;gap:8px 14px}
.cv-metric .l{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:rgba(255,255,255,.62);font-weight:600}
.cv-metric .v{font-size:34px;font-weight:700;line-height:1;letter-spacing:-.02em}
.cv-metric .v small{font-size:13px;color:rgba(255,255,255,.62);font-weight:600;margin-left:8px;letter-spacing:.08em}
.cv-metric .t{grid-column:1/-1;height:6px;border-radius:3px;background:rgba(255,255,255,.14);overflow:hidden}
.cv-metric .t i{display:block;height:100%;border-radius:3px}
.cv-find{font-size:13px;color:rgba(255,255,255,.75)}
.cv-find b{color:#fff}
.cv-verdict{margin-top:34px;max-width:660px;font-size:16px;line-height:1.55;color:rgba(255,255,255,.88)}
.cv-meta{position:relative;display:grid;grid-template-columns:repeat(4,1fr);gap:20px;border-top:1px solid rgba(255,255,255,.16);padding-top:20px;font-size:10.5px;color:rgba(255,255,255,.58);text-transform:uppercase;letter-spacing:.14em}
.cv-meta b{display:block;color:#fff;font-size:15px;text-transform:none;letter-spacing:0;margin-top:5px;font-weight:600}

/* dashboard */
.verdict{font-size:19px;line-height:1.5;font-weight:500;margin-bottom:24px;max-width:800px;letter-spacing:-.01em}
.kpis{display:grid;grid-template-columns:1.2fr 1fr 1fr 1.15fr;gap:14px}
.kpi{border:1px solid var(--line);border-radius:12px;padding:16px 12px 14px;text-align:center;display:flex;flex-direction:column;justify-content:center;align-items:center}
.kpi-main{background:var(--soft)}
.kpi-l{font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);font-weight:700;margin-top:4px}
.kpi-stats{display:grid;gap:10px}
.stat{border:1px solid var(--line);border-radius:12px;padding:12px 16px}
.stat .v{font-size:24px;font-weight:700;line-height:1.2;letter-spacing:-.02em}
.stat .l{font-size:10.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.1em;font-weight:700}
.stat .n{font-size:11.5px;color:var(--muted);line-height:1.4;margin-top:2px}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:14px 0}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:18px}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin-top:18px}
.panel{border:1px solid var(--line);border-radius:12px;padding:18px 20px;min-width:0}
.panel h3{margin-top:0}
.panel.tint{background:var(--accent-soft);border-color:color-mix(in srgb,var(--accent) 22%,#fff)}
.hbar{display:grid;grid-template-columns:118px 1fr 40px 46px;gap:10px;align-items:center;margin:10px 0;font-size:12.5px;border:0}
.hbar-t{height:8px;background:#edf0f4;border-radius:4px;overflow:hidden}
.hbar-f{display:block;height:100%;border-radius:4px}
.hbar-v{font-weight:700;text-align:right}
.hbar-g{font-size:11px;color:var(--muted)}
.hbar.na{color:var(--faint)}
.hbar.c{grid-template-columns:minmax(64px,38%) 1fr auto;gap:10px}
.hbar.c .hbar-v{min-width:34px}
.stack{display:flex;height:12px;border-radius:6px;overflow:hidden;background:#edf0f4;margin:4px 0 14px}
.stack i{display:block;height:100%}
.sevrow{display:grid;grid-template-columns:82px 34px 1fr;gap:10px;align-items:center;font-size:12px;margin:8px 0;color:var(--ink2)}
.sevrow b{text-align:right;font-size:15px;color:var(--ink)}
.take2{display:grid;grid-template-columns:1fr 1fr;gap:14px 36px;font-size:13px}
.take2 div{break-inside:avoid}
.take2 b{display:block;font-size:10.5px;text-transform:uppercase;letter-spacing:.08em;color:var(--accent);font-weight:700;margin-bottom:2px}
.take2 span{color:var(--ink2)}
.split{display:grid;grid-template-columns:1.15fr 1fr;gap:28px}
.nw{white-space:nowrap}
.stat .v.t{font-size:16px;line-height:1.3;letter-spacing:-.01em;padding:3px 0}
.take{display:grid;grid-template-columns:104px 1fr;gap:8px 14px;font-size:13px;margin:0}
.take dt{font-size:10.5px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:700;padding-top:3px}
.take dd{margin:0;color:var(--ink2)}
.week{margin:0 0 4px;padding:0;list-style:none;counter-reset:w}
.week li{counter-increment:w;display:grid;grid-template-columns:26px 1fr;gap:10px;margin:0 0 12px;font-size:13px}
.week li:before{content:counter(w);width:24px;height:24px;border-radius:50%;background:var(--accent);color:#fff;font-weight:700;font-size:12px;display:grid;place-items:center;margin-top:1px}
.week a{font-weight:600;border:0}
.week span{display:block;color:var(--muted);font-size:12px;line-height:1.45}
.ticks,.dashes{list-style:none;margin:0;padding:0;font-size:12.5px}
.ticks li,.dashes li{padding-left:22px;position:relative;margin:6px 0;line-height:1.45;break-inside:avoid}
.ticks li:before{content:"";position:absolute;left:3px;top:5px;width:9px;height:5px;border-left:2px solid var(--good);border-bottom:2px solid var(--good);transform:rotate(-45deg)}
.dashes li:before{content:"";position:absolute;left:3px;top:9px;width:9px;height:2px;background:var(--faint)}
.ticks.cols{columns:2;column-gap:32px}
.callout{border-left:4px solid var(--warn);background:#fffaeb;border-radius:8px;padding:12px 16px;margin:16px 0;font-size:13px}

/* chips, tags, status */
.chip{display:inline-block;font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;padding:2px 8px;border-radius:5px;white-space:nowrap;line-height:1.6}
.sev-critical{background:#fee4e2;color:#b42318}.sev-high{background:#ffead5;color:#c4320a}.sev-medium{background:#fef0c7;color:#b54708}.sev-low{background:#e0eaff;color:#1d4ed8}.sev-info{background:#eef2f6;color:#475467}
.tag{display:inline-block;font-size:10.5px;padding:1px 8px;border-radius:5px;background:#eef2f6;color:var(--ink2);font-weight:700;text-transform:uppercase;letter-spacing:.06em}
.st{font-weight:600}.st.ok{color:var(--good)}.st.bad{color:#b42318}.st.warn{color:var(--warn)}
.gradebox{display:inline-grid;place-items:center;min-width:26px;height:22px;border-radius:5px;font-size:11.5px;font-weight:700;color:#fff;padding:0 6px}

/* tables */
table{width:100%;border-collapse:collapse;font-size:12.5px;margin:6px 0 14px}
th{font-size:10px;text-transform:uppercase;letter-spacing:.09em;color:var(--muted);font-weight:700;text-align:left;padding:8px 10px;border-bottom:1.5px solid var(--ink)}
td{padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}
tr{break-inside:avoid}
table.tight td{padding:7px 10px}
td a{border:0}td a:hover{border-bottom:1px solid var(--accent)}
td.url,.mono{font-family:var(--mono);font-size:11px;overflow-wrap:anywhere;color:var(--ink2)}
th.num{text-align:right}
table.inv{table-layout:fixed}
td.el{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
table.bots td{padding:6px 10px}

/* contents */
.toc{list-style:none;margin:0;padding:0;columns:2;column-gap:44px}
.toc li{break-inside:avoid;border-bottom:1px solid var(--line)}
.toc a{display:grid;grid-template-columns:30px 1fr auto;gap:8px;padding:10px 2px;border:0;align-items:center;font-size:13.5px}
.toc a>span:first-child{color:var(--accent);font-weight:700;font-size:12px;letter-spacing:.06em}
.legend3{display:grid;grid-template-columns:1fr 1.35fr 1fr;gap:18px;margin-top:30px}
.legend3 .panel{font-size:12.5px;color:var(--ink2)}
.legend3 p{margin:0 0 6px}
.lg{display:grid;grid-template-columns:70px 1fr;gap:8px 10px;align-items:start;font-size:12px;line-height:1.4}

/* chapters and findings */
.ch{display:grid;grid-template-columns:auto 1fr auto;gap:22px;align-items:center;padding-bottom:18px;margin-bottom:18px;border-bottom:1px solid var(--line)}
.ch-num{font-size:56px;font-weight:800;line-height:1;color:var(--accent);letter-spacing:-.04em}
.ch .kicker{font-size:10.5px;letter-spacing:.18em;text-transform:uppercase;color:var(--muted);font-weight:700}
.ch h2{font-size:28px;font-weight:700;line-height:1.2}
.intro{color:var(--ink2);font-size:13.5px;max-width:820px}
.finding{border:1px solid var(--line);border-left:4px solid var(--faint);border-radius:10px;margin:16px 0;background:#fff}
.fs-critical{border-left-color:#d92d20}.fs-high{border-left-color:#e0621a}.fs-medium{border-left-color:#d08a00}.fs-low{border-left-color:#3b6fe0}.fs-info{border-left-color:#98a2b3}
.f-head{display:grid;grid-template-columns:auto 1fr;gap:14px;padding:16px 20px 13px;border-bottom:1px solid var(--line);break-after:avoid;break-inside:avoid}
.f-num{font-size:11.5px;font-weight:700;color:var(--muted);border:1px solid var(--line);border-radius:6px;padding:1px 7px;height:fit-content;margin-top:2px}
.f-head h4{font-size:15.5px;font-weight:700;line-height:1.35;margin-bottom:7px}
.f-meta{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:11.5px;color:var(--muted);align-items:center}
.f-meta b{color:var(--ink);font-weight:600}
.f-body{padding:4px 20px 10px}
.row{display:block;padding:10px 0;border-bottom:1px solid #eef1f5}
.row:after{content:"";display:block;clear:both}
.row:last-child{border-bottom:0}
.row .k{float:left;width:126px;font-size:10px;text-transform:uppercase;letter-spacing:.09em;color:var(--muted);font-weight:700;padding-top:3px}
.row .v{margin-left:144px;font-size:13px;min-width:0;color:var(--ink2)}
.row .v p{margin:0 0 6px}.row .v p:last-child{margin-bottom:0}
.row.impact .k{color:var(--warn)}.row.impact .v{color:var(--ink);font-weight:500}
.row.fix .k{color:var(--accent)}
.row.fix ol{margin:0;padding-left:18px}.row.fix li{margin:4px 0;padding-left:3px}
.row.ref .v{font-size:11.5px;overflow-wrap:anywhere}
.ev{list-style:none;margin:8px 0 2px;padding:9px 13px;background:var(--soft);border:1px solid var(--line);border-radius:8px;font-family:var(--mono);font-size:11px;color:var(--ink2)}
.ev li{padding:2px 0;overflow-wrap:anywhere;break-inside:avoid}

/* misc blocks */
.plat{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:8px 0 6px}
.plat div{border:1px solid var(--line);border-radius:10px;padding:12px 14px;display:grid;grid-template-columns:24px 1fr;gap:10px;align-items:center;font-size:12.5px}
.plat small{display:block;color:var(--muted);font-size:11px}
.dot{width:22px;height:22px;border-radius:50%;display:grid;place-items:center;color:#fff;font-size:12px;font-weight:700}
.dot.ok{background:var(--good)}.dot.no{background:#d92d20}
.keycard{border:1px solid var(--line);border-radius:10px;padding:14px 18px;margin:12px 0;break-inside:avoid}
.kc-head{display:flex;gap:10px;align-items:center;margin-bottom:10px}
.kc-grid{display:grid;grid-template-columns:104px 1fr;gap:7px 16px;font-size:12.5px}
.kc-grid .k{font-size:10px;text-transform:uppercase;letter-spacing:.09em;color:var(--muted);font-weight:700;padding-top:3px}
.kc-grid .v{min-width:0;color:var(--ink2)}
.kc-stats{display:flex;gap:20px;flex-wrap:wrap}
.kc-stats b{color:var(--ink)}
.phases{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:8px 0 6px}
.phase{border:1px solid var(--line);border-top:4px solid var(--accent);border-radius:12px;padding:16px 18px}
.phase .when{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);font-weight:700}
.phase h4{font-size:15px;margin:2px 0 6px}
.phase p{font-size:12px;color:var(--muted);margin:0 0 8px}
.phase .proj{font-size:28px;font-weight:700;line-height:1.1;letter-spacing:-.02em}
.phase .proj small{font-size:12px;color:var(--muted);font-weight:600;margin-left:6px}
.traj{width:100%;height:auto;display:block;margin:6px 0 2px}
.gloss{columns:2;column-gap:40px;font-size:12.5px}
.gloss div{break-inside:avoid;margin-bottom:13px}
.gloss b{display:block;color:var(--ink)}
.gloss span{color:var(--ink2)}
.method li{margin:7px 0;color:var(--ink2);font-size:13px}
.foot{color:var(--faint);font-size:11.5px;margin-top:22px}

@media (max-width:1180px){.layout{display:block;padding:16px}.nav{display:none}}
@media (max-width:760px){.sheet{padding:26px 20px}.kpis,.grid2,.grid3,.tiles,.plat,.phases,.legend3{grid-template-columns:1fr}.toc,.gloss,.ticks.cols{columns:1}.take2,.split{grid-template-columns:1fr}.row .k{float:none;width:auto;margin-bottom:4px}.row .v{margin-left:0}.cover{padding:36px 26px;min-height:0}.cover h1{font-size:40px}.cv-scores{grid-template-columns:1fr}.cv-meta{grid-template-columns:1fr 1fr}}

@page{size:A4;margin:17mm 15mm 16mm;
  @top-left{content:"__HDR_L__";font-family:"Segoe UI",Arial,sans-serif;font-size:7.5pt;color:#94a3b8}
  @top-right{content:"__HDR_R__";font-family:"Segoe UI",Arial,sans-serif;font-size:7.5pt;color:#94a3b8}
  @bottom-left{content:"__FTR_L__";font-family:"Segoe UI",Arial,sans-serif;font-size:7.5pt;color:#94a3b8}
  @bottom-right{content:"Page " counter(page) " of " counter(pages);font-family:"Segoe UI",Arial,sans-serif;font-size:7.5pt;color:#94a3b8}}
@page cover{margin:0;@top-left{content:none}@top-right{content:none}@bottom-left{content:none}@bottom-right{content:none}}
@media print{
  body{background:#fff;font-size:9.4pt;line-height:1.5}
  .layout{display:block;padding:0}.nav{display:none}
  .sheet{border:0;border-radius:0;box-shadow:none;padding:0;margin:0;break-before:page}
  .cover{page:cover;border-radius:0;margin:0;width:210mm;height:297mm;min-height:0;padding:22mm 20mm 16mm;break-after:page}
  .cover h1{font-size:44pt}
  .cv-brand img{height:18mm;max-width:90mm}
  .back{break-before:page;break-after:auto}.back h1{font-size:34pt}
  a{border:0}
  h3,.sh,.ch{break-after:avoid}
  .panel,.kpi,.stat,.phase,.kpis,.plat div{break-inside:avoid}
  .panel.flow{break-inside:auto}
  .row{break-inside:avoid;orphans:3;widows:3}
  .row.fix,.row.found{break-inside:auto}
  .row.fix li{break-inside:avoid}
  .sh h2{font-size:19pt}.ch h2{font-size:20pt}.ch-num{font-size:40pt}
  .verdict{font-size:12.5pt;margin-bottom:14pt}
  .kpi-main .gauge{width:128px;height:128px}.kpi .gauge{width:104px;height:104px}.kpi-main .gauge{width:128px;height:128px}
  .kpi{padding:10px 8px}.stat{padding:8px 12px}.stat .v{font-size:15pt}.stat .v.t{font-size:10.5pt}
  .panel{padding:12px 14px}.grid2,.grid3{gap:12px;margin-top:12px}
  .hbar{margin:7px 0;font-size:8.8pt;grid-template-columns:96px 1fr 30px 60px}.sevrow{font-size:8.4pt;margin:5px 0;grid-template-columns:70px 24px 1fr}
  .take2{font-size:9pt}.week li{font-size:9pt;margin-bottom:8px}.ticks{font-size:8.8pt}
  table{font-size:8.6pt}.row .v{font-size:9.2pt}.f-head h4{font-size:11pt}
  td{padding:6px 8px}table.tight td{padding:5px 8px}
  .finding{margin:10pt 0}
  .lg{font-size:8.4pt}.legend3 .panel{font-size:8.8pt}
}
"""


# --------------------------------------------------------------------------- main renderer
def render_html(audit: dict, brand: str = "RankSherlock", client: str = "", prepared_by: str = "", accent: str = "#2563eb", logo_url: str = "", contact: str = "") -> str:
    s = audit["scores"]
    site = audit["site"]
    cats = audit["categories"]
    findings = s["findings"]
    crawl = audit["crawl"]
    counts = s["counts"]
    today = str(audit.get("generated_at", date.today().isoformat()))[:10]
    client = client or site["host"]
    prepared_by = prepared_by or brand
    origin = (site.get("origin") or "").rstrip("/")
    tk = takeaways(audit)
    geo = cats.get("geo", {}) or {}
    content = cats.get("content", {}) or {}
    perf = cats.get("performance", {}) or {}
    tech = cats.get("technical", {}) or {}
    sm = crawl.get("sitemaps", {}) or {}
    checks_run = sum(len(c.get("checks", [])) for c in cats.values() if c)
    issues_total = sum(counts.get(k, 0) for k in ("critical", "high", "medium", "low"))
    by_cat = {k: [f for f in findings if f["category"] == k] for k in CAT_ORDER}
    actionable = [f for f in findings if f["severity"] != "info"]

    def short(x) -> str:
        t = str(x)
        if origin:
            t = t.replace(origin + "/", "/")
            if t == origin:
                t = "/"
        return t

    secs: list = []

    def reg(sec_id: str, title: str) -> str:
        secs.append((sec_id, title))
        return f"{len(secs):02d}"

    def sec_head(n: str, title: str) -> str:
        return f'<header class="sh"><span class="sh-num">{n}</span><h2>{e(title)}</h2></header>'

    def grade_box(score, grade) -> str:
        if score is None:
            return '<span class="gradebox" style="background:#98a2b3">n/a</span>'
        return f'<span class="gradebox" style="background:{score_color(score)}">{e(grade)}</span>'

    def cv_metric(label: str, block: dict) -> str:
        sc = block.get("score")
        width = 0 if sc is None else sc
        val = "n/a" if sc is None else str(sc)
        return (
            f'<div class="cv-metric"><div class="l">{e(label)}</div><div class="v">{val}<small>GRADE {e(block.get("grade", ""))}</small></div>'
            f'<div class="t"><i style="width:{width}%;background:{score_color(sc)}"></i></div></div>'
        )

    # ---------------------------------------------------------------- cover
    logo_src = resolve_logo(logo_url)
    brand_html = f'<img src="{e(logo_src)}" alt="{e(brand)}">' if logo_src else e(brand)
    cover = f"""<section class="cover" id="top">
<div class="cv-top"><div class="cv-brand">{brand_html}</div><div class="cv-conf">Confidential</div></div>
<div class="cv-mid">
<div class="cv-kicker">SEO &middot; AEO &middot; GEO audit report</div>
<h1>{e(client)}</h1>
<div class="cv-url">{e(site['url'])}</div>
<div class="cv-rule"></div>
<div class="cv-scores">
<div class="cv-g">{gauge(s['overall'], 'GRADE ' + str(s['grade']), 210, dark=True)}<div class="l">Overall health</div></div>
<div class="cv-side">
{cv_metric('Search SEO', s['search_seo'])}
{cv_metric('AI visibility', s['ai_visibility'])}
<div class="cv-find"><b>{num(issues_total)}</b> issues found across <b>{num(crawl['pages_crawled'])}</b> pages: <b>{counts.get('critical', 0)}</b> critical, <b>{counts.get('high', 0)}</b> high, <b>{counts.get('medium', 0)}</b> medium, <b>{counts.get('low', 0)}</b> low</div>
</div>
</div>
</div>
<div class="cv-meta"><div>Prepared for<b>{e(client)}</b></div><div>Prepared by<b>{e(prepared_by)}</b></div><div>Date<b>{e(today)}</b></div><div>Scope<b>{num(crawl['pages_crawled'])} pages, {checks_run} checks</b></div></div>
</section>"""

    # ---------------------------------------------------- executive summary
    n_sum = reg("summary", "Executive summary")
    cat_bars = ""
    for k in CAT_ORDER:
        v = s["categories"].get(k)
        if not v:
            continue
        if v.get("measured", True):
            issues_n = v["findings"]
            cat_bars += hbar(CAT_SHORT[k], v["score"], 100, score_color(v["score"]), right=f"{issues_n} issue{'s' if issues_n != 1 else ''}", href=f"#cat-{k}")
        else:
            cat_bars += hbar(CAT_SHORT[k], None, 100, "#cbd5e1", right="not measured")
    total_f = max(sum(counts.get(k, 0) for k in SEV_ORDER), 1)
    stack = "".join(f'<i style="width:{100 * counts.get(k, 0) / total_f:.2f}%;background:{SEV_SOLID[k]}"></i>' for k in SEV_ORDER if counts.get(k))
    sev_rows = "".join(f'<div class="sevrow">{chip(k)}<b>{counts.get(k, 0)}</b><span>{SEV_MEANING[k]}</span></div>' for k in SEV_ORDER)
    caps_html = ""
    if s["caps"]:
        caps_html = '<div class="callout"><b>Score caps applied.</b> ' + " ".join(f"{e(c['axis'].title())} axis capped at {c['ceiling']} (uncapped {c['uncapped']}) because {e(c['reason'])}." for c in s["caps"]) + "</div>"
    this_week = [f for f in findings if f["severity"] in ("critical", "high", "medium") and f.get("effort") == "low"][:3] or actionable[:3]
    week_html = "".join(f'<li><div><a href="#f-{e(f["id"])}">{e(f["title"])}</a><span>{e(f["fix"][:170])}</span></div></li>' for f in this_week)
    passes_all = [c for k in CAT_ORDER for c in (cats.get(k) or {}).get("checks", []) if c["status"] == "pass"]
    good = "".join("<li>" + e(c["title"]) + "</li>" for c in passes_all[:7])
    take_html = "".join(f"<div><b>{e(label)}</b><span>{e(text)}</span></div>" for label, text in tk["points"])
    summary = f"""<section class="sheet" id="summary">{sec_head(n_sum, 'Executive summary')}
<p class="verdict">{e(tk['verdict'])}</p>
<div class="kpis">
<div class="kpi kpi-main">{gauge(s['overall'], 'GRADE ' + str(s['grade']), 164)}<div class="kpi-l">Overall health</div></div>
<div class="kpi">{gauge(s['search_seo']['score'], 'GRADE ' + str(s['search_seo']['grade']), 132)}<div class="kpi-l">Search SEO</div></div>
<div class="kpi">{gauge(s['ai_visibility']['score'], 'GRADE ' + str(s['ai_visibility']['grade']), 132)}<div class="kpi-l">AI visibility</div></div>
<div class="kpi-stats">
<div class="stat"><div class="l">Pages analysed</div><div class="v">{num(crawl['pages_crawled'])}</div><div class="n">{'Whole site crawled' if crawl.get('complete') else 'Crawl stopped at ' + e(crawl.get('stopped_reason', 'cap'))}</div></div>
<div class="stat"><div class="l">Issues found</div><div class="v">{num(issues_total)}</div><div class="n">{counts.get('critical', 0)} critical, {counts.get('high', 0)} high, {counts.get('medium', 0)} medium</div></div>
<div class="stat"><div class="l">Checks run</div><div class="v">{checks_run}</div><div class="n">{len(passes_all)} passed</div></div>
</div>
</div>
{caps_html}
<div class="grid2">
<div class="panel"><h3>Score by area</h3>{cat_bars}</div>
<div class="panel"><h3>Issues by severity</h3><div class="stack">{stack}</div>{sev_rows}</div>
</div>
<div class="panel flow" style="margin-top:18px"><h3>Key takeaways</h3><div class="take2">{take_html}</div></div>
<div class="panel tint split" style="margin-top:18px"><div><h3>Do this week</h3><ol class="week">{week_html}</ol></div><div><h3>Already working</h3><ul class="ticks">{good or '<li>No passed checks recorded.</li>'}</ul></div></div>
</section>"""

    # ------------------------------------------------------- crawl overview
    n_over = reg("overview", "Crawl overview")
    status_counts = tech.get("status_breakdown") or {}
    st_rows = sorted(((str(k), int(v)) for k, v in status_counts.items()), key=lambda kv: -kv[1])[:6]
    st_max = max([v for _, v in st_rows] or [1])
    st_html = "".join(hbar(("HTTP " + k) if k != "0" else "No response", v, st_max, "#2e9e5b" if k == "200" else "#d08a00" if k.startswith("3") else "#d92d20", compact=True) for k, v in st_rows)
    depth = tech.get("depth_distribution") or {}
    d_rows = [(str(k), int(v)) for k, v in depth.items()]
    d_rows.sort(key=lambda kv: (kv[0] == "orphan", int(kv[0]) if kv[0].isdigit() else 99))
    d_max = max([v for _, v in d_rows] or [1])
    d_html = "".join(hbar(("Orphan" if k == "orphan" else ("Homepage" if k == "0" else f"{k} click{'s' if k != '1' else ''}")), v, d_max, "#d08a00" if k == "orphan" or (k.isdigit() and int(k) >= 4) else "var(--accent)", compact=True) for k, v in d_rows[:9])
    ptypes = list((content.get("page_types") or {}).items())[:8]
    pt_max = max([v for _, v in ptypes] or [1])
    pt_html = "".join(hbar(str(k).replace("-", " ").capitalize(), v, pt_max, compact=True) for k, v in ptypes)

    def tile(value, label, note="") -> str:
        plain = re.sub(r"<[^>]+>", "", str(value))
        cls = "v t" if (len(plain) > 9 and not plain[:1].isdigit()) else "v"
        return f'<div class="stat"><div class="l">{e(label)}</div><div class="{cls}">{value}</div><div class="n">{e(note)}</div></div>'

    lane_short = {"auto": "Developer", "assisted": "Developer, with review", "human": "Content or business"}

    overview = f"""<section class="sheet" id="overview">{sec_head(n_over, 'Crawl overview')}
<p class="lead">This audit is built on a real crawl of the site, not a sample of the homepage. The crawler followed internal links from the homepage so every page carries its true click depth, and it also fetched every URL listed in the XML sitemaps so that pages nobody links to are still examined.</p>
<div class="tiles">
{tile(num(crawl['pages_crawled']), 'Pages crawled', 'complete crawl' if crawl.get('complete') else 'stopped: ' + str(crawl.get('stopped_reason', '')))}
{tile(num(tech.get('indexable_pages', 0)), 'Indexable pages', num(tech.get('noindex_pages', 0)) + ' set to noindex')}
{tile(num(sm.get('unique_urls', sm.get('total_urls', 0))), 'Sitemap URLs', str(sm.get('files_fetched', 0)) + ' sitemap files read')}
{tile(str(tech.get('avg_response_ms', 0)) + ' ms', 'Avg server response', 'HTML documents only')}
{tile(e(site.get('platform') or 'Unknown'), 'Platform', e(tech.get('generator', '')))}
{tile(e(str(site.get('business_type', '')).capitalize()), 'Business type', 'drives thresholds and weights')}
{tile(num(crawl.get('blocked_by_robots_count', 0)), 'Blocked by robots.txt', 'linked URLs crawlers may not fetch')}
{tile(num(crawl.get('documents_count', 0)), 'PDF documents', 'linked from pages')}
</div>
<div class="grid3">
<div class="panel"><h3>HTTP status codes</h3>{st_html or '<p class="muted small">No data.</p>'}</div>
<div class="panel"><h3>Click depth from homepage</h3>{d_html or '<p class="muted small">No data.</p>'}</div>
<div class="panel"><h3>Page types</h3>{pt_html or '<p class="muted small">No data.</p>'}</div>
</div>
</section>"""

    # ---------------------------------------------------- priority actions
    n_prio = reg("priorities", "Priority action list")
    pr_rows = ""
    for i, f in enumerate(actionable, 1):
        owner = f.get("owner") or OWNER_DEFAULT.get(f["category"], "")
        pr_rows += (
            f"<tr><td class='muted'>{i:02d}</td><td><a href='#f-{e(f['id'])}'>{e(f['title'])}</a></td><td>{chip(f['severity'])}</td>"
            f"<td class='muted nw'>{e(CAT_SHORT.get(f['category'], ''))}</td><td class='num'>{num(f.get('affected_count', 1))}</td><td>{e(f.get('effort'))}</td><td class='muted nw'>{e(owner)}</td></tr>"
        )
    priorities = f"""<section class="sheet" id="priorities">{sec_head(n_prio, 'Priority action list')}
<p class="lead">Every issue found, ordered by severity and then by effort, so quick fixes come first within each severity. Each row links to the full explanation, evidence and fix.</p>
<table class="tight"><tr><th style="width:30px">#</th><th>Finding</th><th style="width:78px">Severity</th><th>Area</th><th class="num">Affected</th><th>Effort</th><th>Owner</th></tr>{pr_rows or '<tr><td colspan="7" class="muted">No actionable issues found.</td></tr>'}</table>
</section>"""

    # ------------------------------------------------------------ chapters
    chapters = ""
    card_no = 0
    chapter_meta = {}
    for k in CAT_ORDER:
        cat = cats.get(k)
        if not cat:
            continue
        v = s["categories"].get(k, {})
        meas = v.get("measured", True)
        sc = v.get("score") if meas else None
        n_ch = reg(f"cat-{k}", CAT_LABELS[k])
        chapter_meta[f"cat-{k}"] = (sc, v.get("grade", "") if meas else "")
        fl = by_cat.get(k, [])
        cards = ""
        for f in fl:
            card_no += 1
            cards += finding_card(f, card_no, origin)
        extra = ""
        if k == "content":
            extra = f"<p class='muted small'>Average {num(content.get('avg_word_count', 0))} words of main content per page; average passage citability {content.get('avg_citability')}/100; {num(content.get('article_pages', 0))} articles; FAQ content on {num(content.get('faq_pages', 0))} pages; {num(content.get('images_missing_alt', 0))} of {num(content.get('images_total', 0))} images without alt text.</p>"
        elif k == "schema":
            types = ", ".join(f"{t} ({c})" for t, c in list((cat.get("types_found") or {}).items())[:12])
            extra = f"<p class='muted small'>Structured data on {num(cat.get('pages_with_schema', 0))} of {num(cat.get('pages_total', 0))} pages. Types found: {e(types) or 'none'}.</p>"
        elif k == "local" and not meas:
            extra = "<p class='muted'>The site does not read as a local business (no LocalBusiness schema, address and phone pattern or local service language), so local checks are not scored. If it serves a physical area, re-run with local checks forced on.</p>"
        elif k == "ecommerce" and not meas:
            extra = f"<p class='muted'>The site reads as a {e(site.get('business_type'))} site rather than an online shop, so shop-specific checks are not scored.</p>"
        elif k == "ecommerce":
            extra = f"<p class='muted small'>{num(cat.get('product_pages', 0))} product pages and {num(cat.get('category_pages', 0))} category pages analysed.</p>"
        elif k == "performance" and not cat.get("measured"):
            extra = "<p class='muted'>Core Web Vitals were not measured in this run (Google PageSpeed Insights unavailable or skipped), so only HTML-level performance checks are reported and the area is excluded from the score.</p>"
        n_issues = len([f for f in fl if f["severity"] != "info"])
        n_ch_hi = len([f for f in fl if f["severity"] in ("critical", "high")])
        chapters += f"""<section class="sheet chapter" id="cat-{k}">
<header class="ch"><div class="ch-num">{n_ch}</div><div><div class="kicker">Audit area</div><h2>{e(CAT_LABELS[k])}</h2></div><div>{gauge(sc, ('GRADE ' + str(v.get('grade', ''))) if meas else '', 118)}</div></header>
<p class="intro">{e(CAT_INTRO.get(k, ''))}</p>
{extra}
<div class="tiles">
{tile(str(n_issues), 'Issues', 'excluding notes')}
{tile(str(n_ch_hi), 'Critical or high', 'fix first')}
{tile(str(cat.get('pass_count', 0)), 'Checks passed', '')}
{tile(str(sc) if sc is not None else 'n/a', 'Area score', grade_word(sc))}
</div>
{checks_block(cat.get('checks', []))}
{('<h3>Findings in detail</h3>' + cards) if cards else ''}
</section>"""

    # ------------------------------------------------------- AI visibility
    n_ai = reg("ai-detail", "AI crawler access in detail")
    plat_html = ""
    for name, pv in (geo.get("platform_readiness") or {}).items():
        ok = pv.get("ready")
        note = "Crawlers allowed and served" if ok else "Blocked by " + ", ".join(pv.get("blocked", []))
        plat_html += f'<div><span class="dot {"ok" if ok else "no"}">{"&#10003;" if ok else "&#10005;"}</span><span><b>{e(name)}</b><small>{e(note)}</small></span></div>'
    probes = geo.get("ua_probes") or {}
    bot_rows = ""
    train_rows = ""
    for b, i in (geo.get("bot_status") or {}).items():
        stt = i["status"]
        cls = "bad" if stt.startswith("blocked") else "warn" if stt == "partial" else "ok"
        pr = probes.get(b)
        if pr:
            if pr.get("challenged"):
                live = f"<span class='st bad'>Blocked (HTTP {e(pr['status'])})</span>"
            elif pr.get("inconclusive"):
                live = f"<span class='st warn'>Inconclusive (HTTP {e(pr['status'])})</span>"
            else:
                live = f"<span class='st ok'>Served (HTTP {e(pr['status'])})</span>"
        else:
            live = "<span class='muted'>not tested</span>"
        who = e(i["vendor"]) + ("" if i["role"] == "training" else " &middot; " + e(i["role"]))
        row = f"<tr><td class='nw'><b>{e(b)}</b> <span class='muted small'>{who}</span></td><td class='nw'><span class='st {cls}'>{e(ST_LABEL.get(stt, stt))}</span></td><td class='nw'>{live}</td><td class='muted'>{e(i['note'])}</td></tr>"
        if i["role"] == "training":
            train_rows += row
        else:
            bot_rows += row
    llms = geo.get("llms_txt") or {}
    llms_note = (f"H1 {'yes' if llms.get('has_h1') else 'no'}, summary {'yes' if llms.get('has_description') else 'no'}, {llms.get('links', 0)} links, {llms.get('sections', 0)} sections") if llms.get("present") else "Optional convention; cheap to add"

    def yn(flag, yes="Present", no="Absent") -> str:
        return f"<span class='st {'ok' if flag else 'muted'}'>{yes if flag else no}</span>"

    def cit_rows(rows, with_parts) -> str:
        out = ""
        for x in rows:
            parts = ", ".join(f"{a.replace('_', ' ')} {b}" for a, b in (x.get("parts") or {}).items()) if with_parts else ""
            out += f"<tr><td class='url'>{e(short(x['url']))}</td><td class='num'><b style='color:{score_color(x['score'])}'>{x['score']}</b></td>" + (f"<td class='muted small'>{e(parts)}</td>" if with_parts else "") + "</tr>"
        return out

    wd = geo.get("wikidata") or {}
    wd_txt = "not checked"
    if wd.get("checked"):
        wd_txt = "item found" if wd.get("exact") else "no item found"
    names_seen = ", ".join(f"{n} ({c})" for n, c in (geo.get("brand_names_seen") or {}).items()) or "none detected"
    same_as = ", ".join((geo.get("same_as") or [])[:8]) or "none"
    ai_detail = f"""<section class="sheet" id="ai-detail">{sec_head(n_ai, 'AI crawler access in detail')}
<p class="lead">AI answer engines only cite what their crawlers can fetch. Retrieval bots fetch pages to cite them in answers, user-fetch bots open a page when a user pastes a link, and training bots collect data for future models. Blocking retrieval bots removes the site from AI answers; blocking training bots is a policy choice.</p>
<h3>Readiness by AI platform</h3>
<div class="plat">{plat_html}</div>
<p class="muted small">Ready means the platform's crawlers are allowed in robots.txt and were served the page in our live test. It does not prove the platform already cites the site.</p>
<h3>Answer-engine crawlers (these decide whether the site can be cited)</h3>
<table class="tight bots"><tr><th>Crawler</th><th>robots.txt</th><th>Live test (homepage)</th><th>What it does</th></tr>{bot_rows}</table>
<h3>Training crawlers (a policy choice; no effect on citations)</h3>
<table class="tight bots"><tr><th>Crawler</th><th>robots.txt</th><th>Live test (homepage)</th><th>What it does</th></tr>{train_rows}</table>
<div class="grid2">
<div class="panel"><h3>AI discovery files</h3>
<table class="tight"><tr><td>/llms.txt</td><td>{yn(llms.get('present'))}</td><td class="muted">{e(llms_note)}</td></tr>
<tr><td>/llms-full.txt</td><td>{yn(geo.get('llms_full_txt'))}</td><td class="muted">Full-text companion</td></tr>
<tr><td>RSS / Atom feed</td><td>{yn(geo.get('has_feed'))}</td><td class="muted">Helps crawlers notice new content</td></tr>
<tr><td>Markdown on request</td><td>{yn(geo.get('markdown_negotiation'), 'Supported', 'Not supported')}</td><td class="muted">Emerging agent-friendly feature</td></tr>
<tr><td>Content-Signal</td><td>{yn(bool(geo.get('content_signal')), 'Declared', 'Not declared')}</td><td class="muted">AI usage policy line in robots.txt</td></tr></table></div>
<div class="panel"><h3>Brand entity</h3>
<dl class="take"><dt>Names seen</dt><dd>{e(names_seen)}</dd><dt>Profile links</dt><dd class="mono">{e(same_as)}</dd><dt>Wikidata</dt><dd>{e(wd_txt)}</dd></dl></div>
</div>
<div class="grid2">
<div class="panel"><h3>Least quotable pages</h3><table class="tight"><tr><th>Page</th><th class="num">Score</th><th>Breakdown</th></tr>{cit_rows(content.get('citability_lowest', [])[:6], True) or '<tr><td colspan="3" class="muted">n/a</td></tr>'}</table></div>
<div class="panel"><h3>Most quotable pages</h3><table class="tight"><tr><th>Page</th><th class="num">Score</th></tr>{cit_rows(content.get('citability_highest', [])[:6], False) or '<tr><td colspan="2" class="muted">n/a</td></tr>'}</table></div>
</div>
<p class="muted small">Citability scores a page's opening passage on answer quality (30), self-containment (25), structure (20), statistics and sourcing (15) and uniqueness (10). It predicts quotability; it does not prove citation.</p>
</section>"""

    # --------------------------------------------------------- performance
    n_perf = reg("perf-detail", "Performance detail")
    psi_all = perf.get("psi") or {}
    psi_home = next((pv for pk, pv in psi_all.items() if pv.get("ok") and "#desktop" not in pk), None)
    psi_desk = next((pv for pk, pv in psi_all.items() if pv.get("ok") and "#desktop" in pk), None)
    if psi_home:
        fld = psi_home["field"]
        lab = psi_home["lab"]

        def cwv_tile(label, value, unit, good, poor, note) -> str:
            if value is None:
                return tile("n/a", label, "no real-user data")
            color = "#2e9e5b" if value <= good else "#d08a00" if value <= poor else "#d92d20"
            shown = (f"{value:.2f}" if isinstance(value, float) and value < 10 else num(value)) + unit
            return f'<div class="stat"><div class="l">{e(label)}</div><div class="v" style="color:{color}">{shown}</div><div class="n">{e(note)}</div></div>'

        opp = "".join(f"<tr><td>{e(o['title'])}</td><td class='num'>~{num(o['savings_ms'])} ms</td></tr>" for o in psi_home.get("opportunities", []))
        diag = "".join(f"<tr><td>{e(d['title'])}</td><td class='muted'>{e(d.get('display', ''))}</td></tr>" for d in psi_home.get("diagnostics", []))
        inner = "".join(f"<tr><td class='url'>{e(short(pk))}</td><td class='num'><b style='color:{score_color(pv['performance_score'])}'>{pv['performance_score']}</b></td><td class='num'>{num(round((pv['lab'].get('LCP') or 0)))} ms</td></tr>" for pk, pv in psi_all.items() if pv.get("ok") and "#desktop" not in pk)
        desk = (" Desktop score: " + str(psi_desk["performance_score"]) + "/100.") if psi_desk else ""
        perf_body = f"""<p class="lead">Field data is what real Chrome users experienced over the last 28 days (75th percentile), which is what Google ranks on. Lab data is one simulated mobile load by Lighthouse, useful for diagnosis.</p>
<h3>Core Web Vitals, real users (mobile)</h3>
<div class="tiles">
{cwv_tile('LCP: loading', fld.get('LCP'), ' ms', 2500, 4000, 'good under 2,500 ms')}
{cwv_tile('INP: responsiveness', fld.get('INP'), ' ms', 200, 500, 'good under 200 ms')}
{cwv_tile('CLS: visual stability', fld.get('CLS'), '', 0.1, 0.25, 'good under 0.1')}
{cwv_tile('TTFB: server', fld.get('TTFB'), ' ms', 800, 1800, 'good under 800 ms')}
</div>
<p class="muted small">Field data source: {e(fld.get('source'))}-level. Overall assessment: {e(fld.get('overall') or 'n/a')}.</p>
<h3>Lab measurements (Lighthouse, mobile)</h3>
<div class="tiles">
<div class="stat"><div class="l">Performance score</div><div class="v" style="color:{score_color(psi_home['performance_score'])}">{psi_home['performance_score']}</div><div class="n">out of 100.{e(desk)}</div></div>
{tile(num(round(lab.get('LCP') or 0)) + ' ms', 'LCP (lab)', '')}
{tile(num(round(lab.get('TBT') or 0)) + ' ms', 'Total blocking time', 'proxy for INP')}
{tile(num(round((lab.get('total_bytes') or 0) / 1024)) + ' KB', 'Page weight', num(int(lab.get('dom_size') or 0)) + ' DOM nodes')}
</div>
<div class="grid2">
<div class="panel"><h3>Biggest savings</h3><table class="tight"><tr><th>Opportunity</th><th class="num">Saving</th></tr>{opp or '<tr><td colspan="2" class="muted">None over 150 ms.</td></tr>'}</table></div>
<div class="panel"><h3>Diagnostics</h3><table class="tight"><tr><th>Audit</th><th>Value</th></tr>{diag or '<tr><td colspan="2" class="muted">None flagged.</td></tr>'}</table></div>
</div>
<h3>Templates sampled</h3>
<table class="tight"><tr><th>Page</th><th class="num">Mobile score</th><th class="num">LCP (lab)</th></tr>{inner}</table>"""
    else:
        perf_body = f"""<p class="lead">Core Web Vitals were not measured in this run because Google PageSpeed Insights was unavailable, rate-limited or skipped. The performance chapter therefore reports only what can be read from the HTML: script counts, lazy loading, inline CSS size and server response time.</p>
<div class="tiles">{tile(str(perf.get('avg_html_response_ms', 'n/a')) + ' ms', 'Avg HTML response', 'across the crawl')}{tile(str(perf.get('avg_html_kb', 'n/a')) + ' KB', 'Avg HTML size', 'uncompressed')}{tile(str(len(perf.get('third_party_hosts') or {})), 'Third-party script hosts', 'seen in the crawl')}{tile('n/a', 'Core Web Vitals', 'needs a PageSpeed API key')}</div>
<p class="muted">To add real-user Core Web Vitals, re-run the audit with a PageSpeed Insights API key, or check the homepage and two key inner pages at pagespeed.web.dev.</p>"""
    perf_detail = f'<section class="sheet" id="perf-detail">{sec_head(n_perf, "Performance detail")}{perf_body}</section>'

    # ----------------------------------------------------------- key pages
    n_key = reg("keypages", "Key page scorecards")
    table = content.get("page_table", []) or []
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

    def key_card(r) -> str:
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
        t_note = f"{tl} characters" + ("" if t_ok else ", aim for 30 to 60")
        d_note = (f"{dl} characters" + ("" if d_ok else ", aim for 140 to 160")) if dl else "missing: write 140 to 160 characters"
        cit = r.get("citability")
        opening = (r.get("first_paragraph") or "no paragraph found")
        if len(opening) >= 220:
            opening += "..."
        title_html = e(r["title"]) if r["title"] else "<span class='st bad'>missing</span>"
        h1_html = e(r["h1"]) if r["h1"] else "<span class='st bad'>missing</span>"
        flags_html = f"<span class='st bad'>{e(', '.join(flags))}</span>" if flags else "<span class='st ok'>No page-level issues</span>"
        return f"""<div class="keycard"><div class="kc-head"><span class="tag">{e(str(r.get('type', 'page')).replace('-', ' '))}</span><span class="mono">{e(short(r['url']))}</span></div>
<div class="kc-grid">
<div class="k">Title</div><div class="v">{title_html} <span class="st {'ok' if t_ok else 'warn'} small">({t_note})</span></div>
<div class="k">Description</div><div class="v">{e(r.get('description') or '')} <span class="st {'ok' if d_ok else 'warn'} small">({d_note})</span></div>
<div class="k">H1</div><div class="v">{h1_html}</div>
<div class="k">Opening</div><div class="v muted">{e(opening)}</div>
<div class="k">Signals</div><div class="v kc-stats"><span><b>{num(r['words'])}</b> words</span><span><b>{r['internal_links']}</b> internal links</span><span>Citability <b>{cit if cit is not None else 'n/a'}</b></span><span>Schema: {e(', '.join(r['schema'])) or 'none'}</span></div>
<div class="k">Status</div><div class="v">{flags_html}</div>
</div></div>"""

    key_pages_sec = f"""<section class="sheet" id="keypages">{sec_head(n_key, 'Key page scorecards')}
<p class="lead">One representative page per template. These templates carry most of the traffic, so a fix made here applies to every page built on the same template.</p>
{''.join(key_card(r) for r in key_rows) or '<p class="muted">No pages to show.</p>'}
</section>"""

    # ------------------------------------------------------ page inventory
    n_inv = reg("pages", "Page inventory")
    page_rows = ""
    for r in table[:250]:
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
        fl_html = f"<span class='st warn'>{e(', '.join(flags))}</span>" if flags else "<span class='st ok'>ok</span>"
        page_rows += f"<tr><td class='url el' title='{e(r['url'])}'>{e(short(r['url']))}</td><td class='muted el'>{e(str(r.get('type', '')).replace('-', ' '))}</td><td class='el'>{e(r['title'])}</td><td class='num'>{num(r['words'])}</td><td class='num'>{r['internal_links']}</td><td class='num'>{e(r.get('depth', ''))}</td><td class='el'>{fl_html}</td></tr>"
    pages_sec = f"""<section class="sheet" id="pages">{sec_head(n_inv, 'Page inventory')}
<p class="lead">The first {min(250, len(table))} crawled pages, ordered by click depth. The complete inventory of all {num(crawl['pages_crawled'])} pages with every measured field is in pages.csv, delivered with this report.</p>
<table class="tight inv"><colgroup><col style="width:29%"><col style="width:9%"><col style="width:33%"><col style="width:7%"><col style="width:6%"><col style="width:6%"><col style="width:10%"></colgroup><tr><th>Page</th><th>Type</th><th>Title</th><th class="num">Words</th><th class="num">Links</th><th class="num">Depth</th><th>Flags</th></tr>{page_rows}</table>
</section>"""

    # ------------------------------------------------------------- roadmap
    n_road = reg("roadmap", "90-day roadmap")
    p1 = [f for f in actionable if f["severity"] == "critical" or (f["severity"] in ("high", "medium") and f.get("effort") == "low")]
    p2 = [f for f in actionable if f not in p1 and f["severity"] in ("high", "medium") and f.get("lane") != "human"]
    p3 = [f for f in actionable if f not in p1 and f not in p2]
    proj = s.get("projected", {}) or {}

    def phase_card(key, title, when, note, items) -> str:
        p = proj.get(key) or {}
        sc = p.get("overall")
        sc_html = f'<div class="proj" style="color:{score_color(sc)}">{sc if sc is not None else "n/a"}<small>projected, grade {e(p.get("grade", ""))}</small></div>'
        return f'<div class="phase"><div class="when">{e(when)}</div><h4>{e(title)}</h4><p>{e(note)}</p>{sc_html}<p style="margin-top:6px">{len(items)} action{"s" if len(items) != 1 else ""}</p></div>'

    def phase_table(title, items) -> str:
        rows = ""
        for f in items:
            owner = f.get("owner") or OWNER_DEFAULT.get(f["category"], "")
            rows += f"<tr><td>{chip(f['severity'])}</td><td><a href='#f-{e(f['id'])}'>{e(f['title'])}</a></td><td>{e(f.get('effort'))}</td><td class='muted nw'>{e(owner)}</td><td class='muted nw'>{e(lane_short.get(f.get('lane'), ''))}</td></tr>"
        if not rows:
            rows = '<tr><td colspan="5" class="muted">Nothing scheduled in this phase.</td></tr>'
        return f"<h3>{e(title)}</h3><table class='tight'><tr><th style='width:82px'>Severity</th><th>Action</th><th>Effort</th><th>Owner</th><th>Who can do it</th></tr>{rows}</table>"

    traj = trajectory([("Today", s["overall"]), ("After phase 1", (proj.get("phase1") or {}).get("overall")), ("After phase 2", (proj.get("phase2") or {}).get("overall")), ("After phase 3", (proj.get("phase3") or {}).get("overall"))])
    roadmap = f"""<section class="sheet" id="roadmap">{sec_head(n_road, '90-day roadmap')}
<p class="lead">The same findings, sequenced. Phase 1 removes blockers and banks the quick wins, phase 2 fixes the structural issues a developer can own, and phase 3 is the content and entity work that compounds over time. Re-audit after each phase to confirm which findings were resolved.</p>
<div class="phases">
{phase_card('phase1', 'Unblock and quick wins', 'Phase 1: weeks 1 to 2', 'Critical defects plus every high or medium issue that takes little effort.', p1)}
{phase_card('phase2', 'Structural fixes', 'Phase 2: weeks 3 to 6', 'High and medium issues that need developer time or careful review.', p2)}
{phase_card('phase3', 'Content, authority and polish', 'Phase 3: weeks 7 to 12', 'Content rewrites, trust signals, entity work and low-severity hygiene.', p3)}
</div>
<div class="panel" style="margin-top:14px"><h3>Projected overall score</h3>{traj}<p class="muted small">Recomputed with the same scoring model as if the findings in each phase were fixed. A guide to progress, not a traffic forecast.</p></div>
{phase_table('Phase 1 actions', p1)}
{phase_table('Phase 2 actions', p2)}
{phase_table('Phase 3 actions', p3)}
</section>"""

    # ------------------------------------------------- glossary and method
    n_gl = reg("glossary", "Glossary")
    glossary = f'<section class="sheet" id="glossary">{sec_head(n_gl, "Glossary")}<div class="gloss">' + "".join(f"<div><b>{e(t)}</b><span>{e(d)}</span></div>" for t, d in GLOSSARY) + "</div></section>"

    n_me = reg("method", "Methodology and limits")
    skipped_all = [c for k in CAT_ORDER for c in (cats.get(k) or {}).get("checks", []) if c["status"] == "skip"]
    skipped_html = "".join("<li>" + e(c["title"]) + (": " + e(c["note"]) if c.get("note") else "") + "</li>" for c in skipped_all)
    crawl_state = "complete" if crawl.get("complete") else "stopped early (" + str(crawl.get("stopped_reason", "")) + ")"
    method = f"""<section class="sheet" id="method">{sec_head(n_me, 'Methodology and limits')}
<ul class="method">
<li><b>Crawl.</b> Breadth-first from the homepage over internal links, plus every URL in every sitemap file ({sm.get('files_fetched', 0)} files). Cap {num(crawl['max_pages'])} pages, robots.txt respected, {crawl.get('workers', 1)} parallel workers at a polite rate. Crawl status: {e(crawl_state)}.</li>
<li><b>Checks.</b> Deterministic checks against the parsed HTML, HTTP headers, robots.txt, sitemaps, live requests with AI-crawler user agents, and Google PageSpeed Insights when reachable. Every finding carries the evidence that triggered it.</li>
<li><b>Scoring.</b> Each area starts at 100 and loses points per finding (critical 10, high 6, medium 3, low 1) on a 50-point scale, with diminishing returns once many findings of one severity pile up. Search SEO weights: technical 28, content 24, performance 16, schema 10, local 10, e-commerce 7, AI 5, adjusted for the detected business type ({e(s.get('business_type') or 'general')}). AI visibility weights: AI 35, content 30, schema 20, technical 15. Overall is 65% search and 35% AI. A few single defects cap an axis and are stated when applied. Areas that could not be measured are excluded and the remaining weights re-normalised.</li>
<li><b>Word counts</b> are for the main content of each page, with navigation, header, footer and sidebars removed.</li>
<li><b>AI visibility</b> measures readiness: access, entity clarity and quotability. It does not prove that any engine cites the site today.</li>
<li><b>JavaScript.</b> The crawler does not execute JavaScript, which is also how most AI crawlers see the site. Content that only appears after scripts run is reported as such.</li>
</ul>
<h3>What this audit did not check</h3>
<ul class="dashes">
{skipped_html}
<li>Rankings, search impressions and clicks (needs Search Console access).</li>
<li>Backlinks and referring domains (needs a link index).</li>
<li>Live AI answer citations (needs prompt testing across ChatGPT, Perplexity, Gemini and Claude).</li>
<li>Rendered-page layout, tap targets and visual overlap (needs a headless browser pass).</li>
</ul>
<p class="foot">Prepared by {e(prepared_by)} with RankSherlock, an open-source evidence-based audit engine. Scoring version {s.get('scoring_version')}. Text quoted as evidence was gathered from the audited site and is reproduced as data.</p>
</section>"""

    # -------------------------------------------------- closing page (opt-in)
    closing = ""
    if contact:
        contact_html = " &nbsp;&middot;&nbsp; ".join('<span class="nw">' + e(part.strip()) + "</span>" for part in re.split(r"[|;]", contact) if part.strip())
        p1_score = (proj.get("phase1") or {}).get("overall")
        steps_html = "".join(
            f'<div class="bk-step"><span>{i}</span><div><b>{e(t)}</b><p>{e(d)}</p></div></div>'
            for i, (t, d) in enumerate(
                [
                    ("Walk through the findings", "A 30-minute call to go through the priority list and agree what matters most for the business."),
                    ("Fix phase 1", f"{len(p1)} quick-win action{'s' if len(p1) != 1 else ''}" + (f", projected to lift the score to about {p1_score}." if p1_score is not None else ".")),
                    ("Re-audit and compare", "The same crawl is run again and every finding is marked resolved, new or still open."),
                ],
                1,
            )
        )
        closing = f"""<section class="cover back" id="next">
<div class="cv-top"><div class="cv-brand">{brand_html}</div><div class="cv-conf">Next steps</div></div>
<div class="cv-mid">
<div class="cv-kicker">Where to go from here</div>
<h1>Ready to fix this together?</h1>
<div class="cv-rule"></div>
<div class="bk-steps">{steps_html}</div>
</div>
<div class="cv-meta bk-meta"><div>Prepared by<b>{e(prepared_by)}</b></div><div>Contact<b>{contact_html}</b></div></div>
</section>"""

    # ------------------------------------------------------------ contents
    toc_items = ""
    for i, (sid, title) in enumerate(secs, 1):
        right = ""
        if sid in chapter_meta:
            sc, gr = chapter_meta[sid]
            right = grade_box(sc, f"{sc} {gr}" if sc is not None else "")
        toc_items += f'<li><a href="#{sid}"><span>{i:02d}</span><span>{e(title)}</span><span>{right}</span></a></li>'
    lg_sev = "".join(f"{chip(k)}<span>{SEV_MEANING[k]}</span>" for k in SEV_ORDER)
    contents = f"""<section class="sheet" id="contents"><header class="sh"><span class="sh-num">&nbsp;</span><h2>Contents</h2></header>
<ol class="toc">{toc_items}</ol>
<div class="legend3">
<div class="panel"><h3>How scores work</h3><p>Scores are deterministic: the same site audited twice gives the same number. Each area starts at 100 and loses points for every failed check. Two axes are reported: Search SEO and AI visibility. Overall health is 65% search and 35% AI.</p><p>Grades: A 90+, B 80 to 89, C 70 to 79, D 60 to 69, F below 60.</p></div>
<div class="panel"><h3>Severity</h3><div class="lg">{lg_sev}</div></div>
<div class="panel"><h3>Who can do the work</h3><p><b>Developer can apply directly:</b> safe, mechanical changes.</p><p><b>Apply with review:</b> redirects, robots rules and canonicals, which are easy to get wrong.</p><p><b>Needs content or business input:</b> writing, decisions and outreach.</p></div>
</div>
</section>"""

    nav_links = "".join(f'<a href="#{sid}"><span>{i:02d}</span>{e(title)}</a>' + ('<div class="ns"></div>' if sid in ("priorities", "cat-" + [k for k in CAT_ORDER if cats.get(k)][-1]) else "") for i, (sid, title) in enumerate(secs, 1))
    nav = f'<nav class="nav"><div class="nb">{e(brand)}</div><div class="nc">{e(client)} audit</div><a href="#top"><span>&nbsp;</span>Cover</a>{nav_links}</nav>'

    css = CSS.replace("__ACCENT__", accent if re.match(r"^#[0-9a-fA-F]{3,8}$", accent or "") else "#2563eb")
    css = css.replace("__HDR_L__", css_str(client + " \u00b7 SEO, AEO and GEO audit")).replace("__HDR_R__", css_str(brand)).replace("__FTR_L__", css_str("Confidential \u00b7 " + today))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(client)}: SEO, AEO and GEO audit</title>
<style>{css}</style></head><body>
<div class="layout">{nav}<main>
{cover}
{summary}
{contents}
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
{closing}
</main></div></body></html>"""


def write_pdf(html_path: str, pdf_path: str, brand: str = "RankSherlock", client: str = "") -> str | None:
    """Render the HTML report to PDF with Playwright Chromium. Page size, margins, running header and page
    numbers come from the report's own CSS (@page rules). Returns an error string, or None on success."""
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
            page.emulate_media(media="print")
            page.pdf(path=pdf_path, print_background=True, prefer_css_page_size=True)
            browser.close()
        return None
    except Exception as exc:  # pragma: no cover
        return f"{exc.__class__.__name__}: {str(exc)[:200]}"


def render_markdown_summary(audit: dict) -> str:
    s = audit["scores"]
    site = audit["site"]
    lines = [f"# {site['host']} audit summary", ""]
    lines += narrative(audit)
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
            w.writerow([i, f["severity"], f["category"], f["id"], f["title"], f.get("affected_count", 1), f.get("effort"), f.get("impact"), f.get("lane"), f.get("owner"), f.get("why_long") or f["why"], f["fix"], " | ".join(f.get("evidence", [])), " | ".join(f.get("pages", []))])
    with (out_dir / "pages.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["url", "status", "depth", "title", "title_length", "meta_description_length", "h1", "h1_count", "words", "internal_links", "external_links", "images", "images_missing_alt", "schema_types", "canonical", "meta_robots", "lang", "response_ms", "size_kb", "has_faq", "question_headings", "author_signal", "date_signal", "redirect_hops"])
        for p in pages:
            w.writerow([p.url, p.status, p.depth if p.depth < 99 else "orphan", p.title, len(p.title), len(p.meta_description), (p.h1[0] if p.h1 else ""), len(p.h1), p.word_count, p.internal_link_count or len(p.internal_links), p.external_link_count or len(p.external_links), p.images_total, p.images_missing_alt, ";".join(p.schema_types), p.canonical, p.meta_robots, p.lang, p.elapsed_ms, round(p.size_bytes / 1024), p.has_faq_section, len(p.question_headings), bool(p.author_signals), bool(p.date_signals), len(p.redirect_chain)])
