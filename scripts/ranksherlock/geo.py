"""GEO: AI crawler access, WAF challenges, llms.txt, entity consistency, AI discovery files."""

from __future__ import annotations

import re
from collections import Counter
from urllib.parse import urlparse

from .fetch import Fetcher
from .findings import Collector

# Roles are deliberately conservative. Training bots do not gate citations; retrieval bots do.
AI_BOTS = [
    # name, role, vendor, why it matters
    ("OAI-SearchBot", "retrieval", "OpenAI", "Powers ChatGPT search results and citations"),
    ("ChatGPT-User", "user-fetch", "OpenAI", "Fetches pages when a ChatGPT user asks about a URL"),
    ("GPTBot", "training", "OpenAI", "Collects training data; blocking does not stop ChatGPT search citations"),
    ("Claude-SearchBot", "retrieval", "Anthropic", "Indexes pages for Claude search answers"),
    ("Claude-User", "user-fetch", "Anthropic", "Fetches pages on a Claude user's request"),
    ("ClaudeBot", "training", "Anthropic", "Training crawler"),
    ("PerplexityBot", "retrieval", "Perplexity", "Indexes pages for Perplexity answers"),
    ("Perplexity-User", "user-fetch", "Perplexity", "Fetches pages on a Perplexity user's request"),
    ("Googlebot", "retrieval", "Google", "Required for Google Search and AI Overviews"),
    ("Google-Extended", "training", "Google", "Controls Gemini training only; does not affect AI Overviews"),
    ("Bingbot", "retrieval", "Microsoft", "Powers Bing and Copilot; ChatGPT search also leans on Bing's index"),
    ("Applebot", "retrieval", "Apple", "Siri and Spotlight; Applebot-Extended is the training opt-out"),
    ("Applebot-Extended", "training", "Apple", "Training opt-out token"),
    ("DuckAssistBot", "retrieval", "DuckDuckGo", "DuckAssist AI answers"),
    ("Amazonbot", "retrieval", "Amazon", "Alexa answers"),
    ("Meta-ExternalAgent", "training", "Meta", "Meta AI training crawler"),
    ("CCBot", "training", "Common Crawl", "Open dataset used by many model trainers"),
    ("Bytespider", "training", "ByteDance", "Known to ignore robots.txt"),
    ("cohere-ai", "training", "Cohere", "Training crawler"),
    ("YouBot", "retrieval", "You.com", "You.com answers"),
]
RETRIEVAL_BOTS = [b for b in AI_BOTS if b[1] in ("retrieval", "user-fetch")]
TRAINING_BOTS = [b for b in AI_BOTS if b[1] == "training"]

PROBE_UAS = {
    "GPTBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.2; +https://openai.com/gptbot",
    "OAI-SearchBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot",
    "ClaudeBot": "Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)",
    "PerplexityBot": "Mozilla/5.0 (compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)",
    "Googlebot": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
}
CHALLENGE_MARKERS = ["cf-challenge", "challenge-platform", "just a moment", "attention required", "access denied", "verify you are human", "ddos-guard", "incapsula", "perimeterx", "px-captcha", "akamai", "captcha"]


def _robots_groups(txt: str) -> list[tuple[list[str], list[str], list[str]]]:
    """Return [(agents, allows, disallows)] groups from robots.txt text."""
    groups = []
    agents: list[str] = []
    allows: list[str] = []
    disallows: list[str] = []
    last_was_agent = False
    for raw in txt.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, val = [x.strip() for x in line.split(":", 1)]
        k = key.lower()
        if k == "user-agent":
            if not last_was_agent and agents:
                groups.append((agents, allows, disallows))
                agents, allows, disallows = [], [], []
            agents.append(val.lower())
            last_was_agent = True
        elif k in ("allow", "disallow"):
            last_was_agent = False
            (allows if k == "allow" else disallows).append(val)
        else:
            last_was_agent = False
    if agents:
        groups.append((agents, allows, disallows))
    return groups


def bot_status(txt: str, bot: str) -> str:
    """7-state status for one bot: no-robots, not-mentioned, allowed, blocked, partial, blocked-by-wildcard, allowed-by-wildcard."""
    if not txt:
        return "no-robots"
    groups = _robots_groups(txt)
    name = bot.lower()
    specific = [g for g in groups if name in g[0]]
    wildcard = [g for g in groups if "*" in g[0]]
    target = specific or wildcard
    if not target:
        return "not-mentioned"
    allows = [a for g in target for a in g[1]]
    disallows = [d for g in target for d in g[2]]
    full_block = any(d.strip() == "/" for d in disallows)
    full_allow = any(a.strip() == "/" for a in allows)
    if full_block and not full_allow:
        return "blocked" if specific else "blocked-by-wildcard"
    if disallows and any(d.strip() not in ("", "/") for d in disallows) and specific:
        return "partial"
    return "allowed" if specific else "allowed-by-wildcard"


def analyze_llms_txt(text: str) -> dict:
    lines = [l.rstrip() for l in text.splitlines()]
    non_empty = [l for l in lines if l.strip()]
    first = non_empty[0] if non_empty else ""
    return {
        "has_h1": first.startswith("# "),
        "has_description": any(l.startswith("> ") for l in non_empty[:6]),
        "sections": len([l for l in lines if l.startswith("## ")]),
        "links": len(re.findall(r"\[[^\]]+\]\((https?://[^)]+)\)", text)),
        "lines": len(lines),
        "words": len(text.split()),
    }


def analyze_geo(pages: list, robots_txt: str, robots_status: int, origin: str, fetcher: Fetcher, home_url: str, brand_name: str = "") -> dict:
    c = Collector("geo")
    html_pages = [p for p in pages if p.status == 200 and "text/html" in (p.content_type or "")]
    home = next((p for p in html_pages if p.url == home_url), html_pages[0] if html_pages else None)

    # ------------------------------------------------------ robots per bot
    statuses = {b[0]: bot_status(robots_txt if robots_status == 200 else "", b[0]) for b in AI_BOTS}
    blocked_retrieval = [b for b in RETRIEVAL_BOTS if statuses[b[0]] in ("blocked", "blocked-by-wildcard")]
    blocked_training = [b for b in TRAINING_BOTS if statuses[b[0]] in ("blocked", "blocked-by-wildcard")]
    cloudflare_managed = "cloudflare managed content" in (robots_txt or "").lower()
    if blocked_retrieval:
        names = ", ".join(b[0] for b in blocked_retrieval)
        sev = "critical" if any(b[0] == "Googlebot" for b in blocked_retrieval) else "high"
        c.add("geo-retrieval-bots-blocked", sev, f"robots.txt blocks answer-engine crawlers: {names}", "These bots fetch pages to cite them in ChatGPT, Perplexity, Claude and Copilot answers. Blocking them removes the site from AI answers entirely.", "Allow the retrieval bots (OAI-SearchBot, PerplexityBot, Claude-SearchBot, Bingbot, Googlebot). You can still block training bots (GPTBot, ClaudeBot, CCBot) if that is the policy.", evidence=[f"{b[0]}: {statuses[b[0]]}" for b in blocked_retrieval] + (["Cloudflare 'managed robots.txt' block detected"] if cloudflare_managed else []), effort="low")
    else:
        c.passed("geo-retrieval-bots", "No answer-engine crawler is blocked in robots.txt")
    if blocked_training and not blocked_retrieval:
        c.add("geo-training-bots-blocked", "info", f"Training crawlers blocked: {', '.join(b[0] for b in blocked_training)}", "A legitimate policy choice. It does not affect citations, but it does reduce the chance the brand is known inside future models.", "Keep if intentional. Consider allowing CCBot/GPTBot if brand recall inside models matters more than content reuse concerns.", effort="low")

    # ------------------------------------------------------- WAF / UA probes
    probe_results = {}
    if home is not None:
        baseline_status = home.status
        for bot, ua in PROBE_UAS.items():
            r = fetcher.get(home_url, user_agent=ua)
            body = (r.text or "")[:4000].lower()
            challenged = r.status in (403, 429, 451, 503) or any(m in body for m in CHALLENGE_MARKERS[:9]) and r.status != 200
            probe_results[bot] = {"status": r.status, "challenged": bool(challenged), "server": r.headers.get("server", ""), "cf": bool(r.headers.get("cf-ray"))}
        blocked = [b for b, r in probe_results.items() if r["challenged"] and baseline_status == 200]
        if blocked:
            c.add("geo-waf-blocks-ai-bots", "high", f"Firewall/CDN challenges AI crawlers: {', '.join(blocked)}", "robots.txt may allow them, but the edge returns a challenge or 403, so answer engines never see the content.", "In Cloudflare (or the WAF in use) disable 'Block AI bots' / bot-fight mode for verified search and AI retrieval bots, or add allow rules for their user agents.", evidence=[f"{b}: HTTP {probe_results[b]['status']} (server: {probe_results[b]['server'] or 'n/a'})" for b in blocked], effort="low")
        else:
            c.passed("geo-waf", "AI bot user agents receive the page without a challenge")

    # ------------------------------------------------------------- llms.txt
    llms = fetcher.get(f"{origin}/llms.txt")
    llms_full = fetcher.get(f"{origin}/llms-full.txt")
    llms_ok = llms.error is None and llms.status == 200 and "text/html" not in llms.content_type and len(llms.text.strip()) > 20
    llms_info = analyze_llms_txt(llms.text) if llms_ok else {}
    if not llms_ok:
        c.add("geo-no-llms-txt", "low", "No /llms.txt file", "An emerging convention (adopted by Anthropic, Stripe, Cloudflare docs and others) that gives LLM agents a curated map of the site. No vendor has confirmed ranking weight, so this is low priority but cheap.", "Publish /llms.txt: an H1 with the brand, a one-line blockquote description, then H2 sections with markdown links to the 10 to 40 most important pages. Optionally /llms-full.txt with full text.", effort="low")
    else:
        issues = []
        if not llms_info["has_h1"]:
            issues.append("missing H1 title on first line")
        if not llms_info["has_description"]:
            issues.append("missing '> description' blockquote")
        if llms_info["links"] == 0:
            issues.append("no markdown links")
        if issues:
            c.add("geo-llms-txt-malformed", "low", "/llms.txt exists but does not follow the spec", "Agents parse the H1, blockquote and link list; a free-form file is ignored.", "Reformat per llmstxt.org: H1, blockquote summary, H2 sections, '- [Title](url): note' links.", evidence=issues, effort="low")
        else:
            c.passed("geo-llms-txt", f"/llms.txt present ({llms_info['links']} links, {llms_info['sections']} sections)")
        if llms_full.error is None and llms_full.status == 200 and "text/html" not in llms_full.content_type:
            c.passed("geo-llms-full", "/llms-full.txt present")

    # ----------------------------------------------------- Google AI gate
    if home is not None:
        robots_meta = (home.meta_robots or "") + " " + (home.x_robots_tag or "")
        if re.search(r"nosnippet|max-snippet:\s*0", robots_meta, re.I):
            c.add("geo-nosnippet", "critical", "Start page forbids snippets (nosnippet / max-snippet:0)", "Google AI Overviews and AI Mode only quote pages that allow snippets. This directive opts the page out entirely.", "Remove nosnippet or raise max-snippet (or drop the directive).", evidence=[robots_meta.strip()], effort="low")
        if statuses.get("Googlebot") in ("blocked", "blocked-by-wildcard"):
            pass  # already covered as critical above

    # -------------------------------------------------- Entity consistency
    names = Counter()
    for p in html_pages[:60]:
        for item in p.json_ld:
            t = str(item.get("@type", ""))
            if any(k in t for k in ("Organization", "LocalBusiness", "Store", "Corporation")) and item.get("name"):
                names[str(item["name"]).strip()] += 1
        og_site = p.og.get("site_name")
        if og_site:
            names[og_site.strip()] += 1
    if home is not None and home.title:
        tail = re.split(r"\s[|\-–—:]\s", home.title)
        if len(tail) > 1:
            names[tail[-1].strip()] += 1
    distinct = {n.lower(): n for n in names}
    if len(distinct) > 2:
        c.add("geo-entity-name-inconsistent", "medium", "Brand name spelled differently across schema, og:site_name and titles", "AI systems resolve entities by exact name matches; three spellings look like three different companies.", "Pick one canonical brand name and use it identically in Organization.name, og:site_name, title suffix and footer.", evidence=[f"'{n}' x{k}" for n, k in names.most_common(5)], effort="low")
    elif names:
        c.passed("geo-entity-name", f"Brand name consistent: {names.most_common(1)[0][0]}")

    same_as = []
    for p in html_pages[:30]:
        for item in p.json_ld:
            if isinstance(item.get("sameAs"), list):
                same_as.extend(item["sameAs"])
            elif isinstance(item.get("sameAs"), str):
                same_as.append(item["sameAs"])
    same_as = sorted(set(same_as))
    kg_links = [s for s in same_as if re.search(r"wikipedia\.org|wikidata\.org|crunchbase\.com|linkedin\.com/company", s)]
    if same_as and not kg_links:
        c.add("geo-no-kg-links", "low", "sameAs has social links but no knowledge-graph anchors", "Wikipedia, Wikidata, Crunchbase and LinkedIn company pages are the sources AI models trust for 'who is this brand'.", "Add LinkedIn company URL now; create a Wikidata item (free, allowed for any real organisation) and link it.", evidence=same_as[:5], effort="low")

    # ------------------------------------------------- AI discovery extras
    extras = {}
    for path in ("/.well-known/ai-plugin.json", "/ai.txt", "/agents.md", "/humans.txt", "/feed", "/rss.xml", "/feed.xml"):
        r = fetcher.get(f"{origin}{path}")
        extras[path] = r.status if r.error is None else 0
    has_feed = any(extras[p] == 200 for p in ("/feed", "/rss.xml", "/feed.xml"))
    # Content negotiation test (Accept: text/markdown)
    try:
        import requests

        r = requests.get(home_url, headers={"Accept": "text/markdown", "User-Agent": fetcher.session.headers.get("User-Agent")}, timeout=15)
        md_supported = "text/markdown" in (r.headers.get("content-type") or "")
    except Exception:
        md_supported = False
    if md_supported:
        c.passed("geo-markdown-negotiation", "Server returns Markdown for Accept: text/markdown")

    # Citability roll-up comes from content module; here we only flag structural AI readiness
    if html_pages:
        csr = [p for p in html_pages if p.word_count < 80 and p.external_scripts >= 3]
        if len(csr) >= max(2, len(html_pages) * 0.3):
            c.add("geo-csr-invisible", "high", "Primary content is not in the HTML that AI crawlers receive", "Unlike Googlebot, OAI-SearchBot, PerplexityBot and ClaudeBot do not execute JavaScript. They see an empty shell.", "Server-side render or pre-render content pages.", evidence=[f"{p.url} ({p.word_count} words)" for p in csr[:5]], affected_count=len(csr), effort="high")
        else:
            c.passed("geo-ssr", "Content is visible without JavaScript")

    out = c.to_dict()
    out["bot_status"] = {b[0]: {"status": statuses[b[0]], "role": b[1], "vendor": b[2], "note": b[3]} for b in AI_BOTS}
    out["cloudflare_managed_robots"] = cloudflare_managed
    out["ua_probes"] = probe_results
    out["llms_txt"] = {"present": llms_ok, "status": llms.status, **llms_info}
    out["llms_full_txt"] = llms_full.error is None and llms_full.status == 200 and "text/html" not in llms_full.content_type
    out["discovery_files"] = extras
    out["has_feed"] = has_feed
    out["markdown_negotiation"] = md_supported
    out["brand_names_seen"] = dict(names.most_common(5))
    out["same_as"] = same_as[:15]
    return out
