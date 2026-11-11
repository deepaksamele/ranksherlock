"""GEO: AI crawler access, WAF challenges, llms.txt, entity consistency, AI discovery files, platform readiness."""

from __future__ import annotations

import re
from collections import Counter
from urllib.parse import urlparse

from .business import page_type
from .fetch import Fetcher
from .findings import Collector

# Roles are deliberately conservative. Training bots do not gate citations; retrieval bots do.
AI_BOTS = [
    ("OAI-SearchBot", "retrieval", "OpenAI", "Powers ChatGPT search results and citations"),
    ("ChatGPT-User", "user-fetch", "OpenAI", "Fetches pages when a ChatGPT user asks about a URL"),
    ("GPTBot", "training", "OpenAI", "Collects training data; blocking does not stop ChatGPT search citations"),
    ("Claude-SearchBot", "retrieval", "Anthropic", "Indexes pages for Claude search answers"),
    ("Claude-User", "user-fetch", "Anthropic", "Fetches pages on a Claude user's request"),
    ("ClaudeBot", "training", "Anthropic", "Training crawler"),
    ("anthropic-ai", "training", "Anthropic", "Legacy training token"),
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
    ("Meta-ExternalFetcher", "user-fetch", "Meta", "Fetches links shared with Meta AI"),
    ("CCBot", "training", "Common Crawl", "Open dataset used by many model trainers"),
    ("Bytespider", "training", "ByteDance", "Known to ignore robots.txt"),
    ("cohere-ai", "training", "Cohere", "Training crawler"),
    ("meta-webindexer", "retrieval", "Meta", "Meta AI search index"),
    ("Amzn-SearchBot", "retrieval", "Amazon", "Rufus and Alexa+ shopping answers"),
    ("xAI-SearchBot", "retrieval", "xAI", "Grok search answers"),
    ("DeepSeekBot", "retrieval", "DeepSeek", "DeepSeek search answers"),
    ("AzureAI-SearchBot", "retrieval", "Microsoft", "Azure AI search grounding"),
    ("Kimi-SearchBot", "retrieval", "Moonshot", "Kimi answers"),
    ("YouBot", "retrieval", "You.com", "You.com answers"),
    ("kagi-fetcher", "user-fetch", "Kagi", "Kagi assistant fetches"),
    ("MistralAI-User", "user-fetch", "Mistral", "Le Chat fetches"),
    ("MistralAI-Training", "training", "Mistral", "Training crawler"),
    ("Google-CloudVertexBot", "training", "Google", "Vertex AI customer grounding crawler"),
    ("Diffbot", "training", "Diffbot", "Knowledge graph crawler"),
]
RETRIEVAL_BOTS = [b for b in AI_BOTS if b[1] in ("retrieval", "user-fetch")]
TRAINING_BOTS = [b for b in AI_BOTS if b[1] == "training"]

PROBE_UAS = {
    "GPTBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.2; +https://openai.com/gptbot",
    "OAI-SearchBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot",
    "ChatGPT-User": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ChatGPT-User/1.0; +https://openai.com/bot",
    "ClaudeBot": "Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)",
    "Claude-SearchBot": "Mozilla/5.0 (compatible; Claude-SearchBot/1.0; +https://www.anthropic.com/claude-searchbot)",
    "PerplexityBot": "Mozilla/5.0 (compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)",
    "Googlebot": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Bingbot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm) Chrome/116.0 Safari/537.36",
}
CHALLENGE_MARKERS = ["cf-challenge", "challenge-platform", "just a moment", "attention required", "access denied", "verify you are human", "ddos-guard", "incapsula", "perimeterx", "px-captcha", "akamai", "captcha", "request blocked", "bot detection"]

PLATFORMS = {
    "Google AI Overviews / AI Mode": ["Googlebot"],
    "ChatGPT search": ["OAI-SearchBot", "ChatGPT-User", "Bingbot"],
    "Perplexity": ["PerplexityBot", "Perplexity-User"],
    "Claude": ["Claude-SearchBot", "Claude-User"],
    "Microsoft Copilot / Bing": ["Bingbot"],
    "Apple Siri / Spotlight": ["Applebot"],
}


def _robots_groups(txt: str) -> list[tuple[list[str], list[str], list[str]]]:
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
    """7-state status: no-robots, not-mentioned, allowed, blocked, partial, blocked-by-wildcard, allowed-by-wildcard."""
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


def analyze_llms_txt(text: str, origin: str = "") -> dict:
    lines = [l.rstrip() for l in text.splitlines()]
    non_empty = [l for l in lines if l.strip()]
    first = non_empty[0] if non_empty else ""
    links = re.findall(r"\[[^\]]+\]\((https?://[^)]+)\)", text)
    return {
        "has_h1": first.startswith("# "),
        "has_description": any(l.startswith("> ") for l in non_empty[:6]),
        "sections": len([l for l in lines if l.startswith("## ")]),
        "links": len(links),
        "foreign_links": sum(1 for l in links if origin and urlparse(l).netloc.lower().replace("www.", "") != urlparse(origin).netloc.lower().replace("www.", "")),
        "placeholders": bool(re.search(r"\[(your|insert|company)[^\]]*\]|example\.com|lorem", text, re.I)),
        "lines": len(lines),
        "words": len(text.split()),
        "link_urls": links[:40],
    }


def analyze_geo(pages: list, robots_txt: str, robots_status: int, origin: str, fetcher: Fetcher, home_url: str, brand_name: str = "", business: dict | None = None, external: bool = True) -> dict:
    c = Collector("geo")
    business = business or {}
    html_pages = [p for p in pages if p.status == 200 and "text/html" in (p.content_type or "")]
    home = next((p for p in html_pages if p.url == home_url), html_pages[0] if html_pages else None)
    n = max(len(html_pages), 1)

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
    elif not blocked_training and robots_status == 200:
        c.passed("geo-training-bots", "Training crawlers are not blocked (maximises brand recall inside future models)")
    partial = [b[0] for b in RETRIEVAL_BOTS if statuses[b[0]] == "partial"]
    if partial:
        groups = _robots_groups(robots_txt or "")
        ev = []
        for b in partial:
            paths = [d for g in groups if b.lower() in g[0] for d in g[2] if d.strip()]
            ev.append(f"{b}: Disallow {', '.join(paths[:6])}{' ...' if len(paths) > 6 else ''}")
        only_private = all(re.match(r"^/(api|admin|account|cart|checkout|login|wp-admin|search|_next|private|dashboard)\b", d.strip()) for g in groups for b in partial if b.lower() in g[0] for d in g[2] if d.strip())
        c.add("geo-retrieval-bots-partial", "info" if only_private else "low", f"Some paths are hidden from answer-engine bots: {', '.join(partial)}", "Specific Disallow rules for AI bots keep those sections out of AI answers. Rules that only cover private areas (admin, API, cart, account) are good practice.", "Review the per-bot Disallow rules and confirm the hidden sections are intentional.", evidence=ev, effort="low")
    rsl = bool(re.search(r"^license:", robots_txt or "", re.I | re.M))
    content_signal = {}
    m = re.search(r"^content-signal:\s*(.+)$", robots_txt or "", re.I | re.M)
    if m:
        for part in m.group(1).split(","):
            if "=" in part:
                k, v = part.split("=", 1)
                content_signal[k.strip().lower()] = v.strip().lower()
        if content_signal.get("ai-input") == "no" or content_signal.get("search") == "no":
            c.add("geo-content-signal-blocks-ai", "high", f"Content-Signal line opts out of AI answers ({m.group(1).strip()})", "The Content-Signal directive (read by Cloudflare and a growing set of AI crawlers) tells answer engines not to use the site as input. It removes the site from AI answers on those platforms.", "Set ai-input=yes and search=yes; keep ai-train=no if training opt-out is the policy.", evidence=[m.group(0)], effort="low")
        elif content_signal.get("ai-train") == "yes" and blocked_training:
            c.add("geo-content-signal-conflict", "low", "Content-Signal allows AI training while robots.txt blocks training bots", "Contradictory policy signals confuse crawlers and compliance reviewers.", "Align Content-Signal ai-train with the robots.txt rules.", evidence=[m.group(0)], effort="low")
        else:
            c.passed("geo-content-signal", f"Content-Signal declared: {m.group(1).strip()}")
    noai_pages = [p for p in html_pages if re.search(r"\bnoai\b|\bnoimageai\b", (p.meta_robots or "") + " " + (p.x_robots_tag or ""), re.I)]
    if noai_pages:
        c.add("geo-noai-directive", "info", f"noai / noimageai directive on {len(noai_pages):,} pages", "An opt-out convention honoured by some AI companies; it has no effect on search rankings.", "Keep if deliberate; remove if AI visibility is a goal.", affected_count=len(noai_pages), effort="low")
    injection_pages = [p for p in html_pages if re.search(r"ignore (all )?(previous|prior|above) instructions|you are (chatgpt|an ai)|system prompt|disregard (the|your) (previous|prior)", p.text_sample + " " + p.lead_text, re.I)]
    if injection_pages:
        c.add("geo-hidden-ai-instructions", "info", f"Text that reads like instructions to AI systems on {len(injection_pages):,} pages", "Prompt-style text aimed at AI crawlers is treated as spam by AI vendors and can get a site excluded from answers.", "Remove any text that addresses AI models directly.", evidence=[p.url for p in injection_pages[:3]], affected_count=len(injection_pages), effort="low")

    # ------------------------------------------------------- WAF / UA probes
    probe_results = {}
    deep_probes = {}
    if home is not None:
        baseline_status = home.status

        def probe(url, bot, ua, baseline_words):
            r = fetcher.get(url, user_agent=ua, cache=False)
            body = (r.text or "")[:4000].lower()
            hard_block = r.status in (401, 403, 406, 451) or (any(m in body for m in CHALLENGE_MARKERS) and r.status != 200)
            inconclusive = r.status in (429,) or r.status >= 500 or r.error is not None
            words = len(re.sub(r"<[^>]+>", " ", r.text or "").split()) if r.status == 200 else 0
            cloaked = bool(r.status == 200 and baseline_words > 200 and words < baseline_words * 0.3)
            return {"status": r.status, "challenged": bool(hard_block), "inconclusive": bool(inconclusive and not hard_block), "server": r.headers.get("server", ""), "cf": bool(r.headers.get("cf-ray")), "words": words, "cloaked": cloaked}

        for bot, ua in PROBE_UAS.items():
            probe_results[bot] = probe(home_url, bot, ua, home.word_count)
        deep_pages = [p for p in html_pages if p.url != home_url and 1 <= p.depth <= 2 and p.word_count > 200][:2]
        for p in deep_pages:
            deep_probes[p.url] = {bot: probe(p.url, bot, PROBE_UAS[bot], p.word_count) for bot in ("OAI-SearchBot", "PerplexityBot", "Googlebot")}
        blocked = [b for b, r in probe_results.items() if r["challenged"] and baseline_status == 200]
        deep_blocked = sorted({b for res in deep_probes.values() for b, r in res.items() if r["challenged"]})
        inconclusive = [b for b, r in probe_results.items() if r["inconclusive"]]
        if blocked:
            c.add("geo-waf-blocks-ai-bots", "high", f"Firewall/CDN challenges AI crawlers: {', '.join(blocked)}", "robots.txt may allow them, but the edge returns a challenge or 403, so answer engines never see the content.", "In Cloudflare (or the WAF in use) disable 'Block AI bots' / bot-fight mode for verified search and AI retrieval bots, or add allow rules for their user agents.", evidence=[f"{b}: HTTP {probe_results[b]['status']} (server: {probe_results[b]['server'] or 'n/a'})" for b in blocked], effort="low")
        elif deep_blocked:
            c.add("geo-waf-blocks-ai-bots-inner", "high", f"Inner pages challenge AI crawlers: {', '.join(deep_blocked)}", "The homepage is open but deeper pages return a challenge to AI bots, so the content that should be cited is the part they cannot read.", "Apply the bot allow rules to the whole site, not only the homepage path.", evidence=[f"{u}: {', '.join(b for b, r in res.items() if r['challenged'])}" for u, res in deep_probes.items() if any(r["challenged"] for r in res.values())], effort="low")
        else:
            c.passed("geo-waf", f"All {len(PROBE_UAS)} AI and search bot user agents receive the homepage and {len(deep_pages)} inner pages without a challenge")
        if inconclusive:
            c.add("geo-probe-inconclusive", "info", f"Bot probes were inconclusive for {', '.join(inconclusive)} (rate limit or server error)", "A 429 or 5xx during the probe is not proof of blocking; it may be rate limiting.", "Re-run the audit later or check server logs for these user agents.", evidence=[f"{b}: HTTP {probe_results[b]['status']}" for b in inconclusive], effort="low")
        cloaked = [b for b, r in probe_results.items() if r["cloaked"]]
        if cloaked:
            c.add("geo-bots-get-less-content", "medium", f"Bots receive a much shorter page than browsers: {', '.join(cloaked)}", "The server sends a reduced page to these user agents (consent walls, bot pages or lazy templates), so answer engines index a fraction of the content.", "Serve the same HTML to bots as to users.", evidence=[f"{b}: {probe_results[b]['words']} words vs {home.word_count} for a normal visitor" for b in cloaked], effort="medium")

    # ------------------------------------------------------------- llms.txt
    llms = fetcher.get(f"{origin}/llms.txt")
    llms_full = fetcher.get(f"{origin}/llms-full.txt")
    llms_ok = llms.error is None and llms.status == 200 and "text/html" not in llms.content_type and len(llms.text.strip()) > 20
    llms_info = analyze_llms_txt(llms.text, origin) if llms_ok else {}
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
        if llms_info["placeholders"]:
            issues.append("contains template placeholders")
        dead = []
        for u in llms_info.get("link_urls", [])[:15]:
            st, _ = fetcher.head_status(u)
            if st in (404, 410) or st >= 500:
                dead.append(f"{u} -> {st}")
        if dead:
            issues.append(f"{len(dead)} linked URLs are dead ({dead[0]})")
        if issues:
            c.add("geo-llms-txt-malformed", "low", "/llms.txt exists but does not follow the spec", "Agents parse the H1, blockquote and link list; a free-form file is ignored and dead links waste the agent's budget.", "Reformat per llmstxt.org: H1, blockquote summary, H2 sections, '- [Title](url): note' links, all resolving to 200.", evidence=issues, effort="low")
        else:
            c.passed("geo-llms-txt", f"/llms.txt present and well-formed ({llms_info['links']} links, {llms_info['sections']} sections)")
        if llms_full.error is None and llms_full.status == 200 and "text/html" not in llms_full.content_type:
            c.passed("geo-llms-full", "/llms-full.txt present")

    # ----------------------------------------------------- Google AI gate
    nosnip = [p for p in html_pages if re.search(r"nosnippet|max-snippet:\s*0", (p.meta_robots or "") + " " + (p.x_robots_tag or ""), re.I)]
    if home is not None:
        robots_meta = (home.meta_robots or "") + " " + (home.x_robots_tag or "")
        if re.search(r"nosnippet|max-snippet:\s*0", robots_meta, re.I):
            c.add("geo-nosnippet", "critical", "Start page forbids snippets (nosnippet / max-snippet:0)", "Google AI Overviews and AI Mode only quote pages that allow snippets. This directive opts the page out entirely.", "Remove nosnippet or raise max-snippet (or drop the directive).", evidence=[robots_meta.strip()], effort="low")
        elif nosnip:
            c.add("geo-nosnippet-pages", "medium", f"{len(nosnip):,} pages forbid snippets", "These pages cannot be quoted in Google AI Overviews, AI Mode or featured snippets.", "Remove nosnippet / max-snippet:0 unless the exclusion is deliberate.", evidence=[p.url for p in nosnip[:4]], affected_count=len(nosnip), effort="low")
        else:
            c.passed("geo-snippets-allowed", "Pages allow snippets (eligible for AI Overviews and featured snippets)")

    # -------------------------------------------------- Entity consistency
    names = Counter()
    for p in html_pages[:80]:
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
    top_n = names.most_common(1)[0][1] if names else 0
    names = Counter({n: k for n, k in names.items() if k >= max(2, top_n * 0.1) or k == top_n})
    distinct = {re.sub(r"[^a-z0-9]", "", n.lower()): n for n in names}
    if len(distinct) > 2:
        c.add("geo-entity-name-inconsistent", "medium", "Brand name spelled differently across schema, og:site_name and titles", "AI systems resolve entities by exact name matches; three spellings look like three different companies.", "Pick one canonical brand name and use it identically in Organization.name, og:site_name, title suffix and footer.", evidence=[f"'{n}' x{k}" for n, k in names.most_common(5)], effort="low")
    elif names:
        c.passed("geo-entity-name", f"Brand name consistent: {names.most_common(1)[0][0]}")
    brand = brand_name or (names.most_common(1)[0][0] if names else "")

    same_as = []
    for p in html_pages[:40]:
        for item in p.json_ld:
            if isinstance(item.get("sameAs"), list):
                same_as.extend(str(x) for x in item["sameAs"])
            elif isinstance(item.get("sameAs"), str):
                same_as.append(item["sameAs"])
    same_as = sorted(set(same_as))
    kg_links = [s for s in same_as if re.search(r"wikipedia\.org|wikidata\.org|crunchbase\.com|linkedin\.com/company", s)]
    if same_as and not kg_links:
        c.add("geo-no-kg-links", "low", "sameAs has social links but no knowledge-graph anchors", "Wikipedia, Wikidata, Crunchbase and LinkedIn company pages are the sources AI models trust for 'who is this brand'.", "Add LinkedIn company URL now; create a Wikidata item (free, allowed for any real organisation) and link it.", evidence=same_as[:5], effort="low")
    elif kg_links:
        c.passed("geo-kg-links", f"Knowledge-graph anchors in sameAs: {', '.join(urlparse(k).netloc for k in kg_links[:3])}")

    # Entity facts on About / homepage
    about = next((p for p in html_pages if page_type(p.url, p) == "about"), None)
    fact_text = " ".join(x.text_sample + " " + x.lead_text for x in [home, about] if x)
    facts = {
        "founding year": bool(re.search(r"\b(founded|established|since|est\.)\s*(in\s*)?(19|20)\d{2}\b", fact_text, re.I)),
        "location": bool(re.search(r"\b(based in|located in|headquartered in|offices? in|serving)\b", fact_text, re.I)),
        "what the business does": bool(re.search(r"\b(we (are|provide|offer|help|build|design|sell|specialise|specialize)|is an? (leading|independent|family|award))\b", fact_text, re.I)),
        "team size or scale": bool(re.search(r"\b\d[\d,]*\+?\s*(employees|clients|customers|projects|years|offices|locations|members|students|patients)\b", fact_text, re.I)),
    }
    missing_facts = [k for k, v in facts.items() if not v]
    if home is not None and len(missing_facts) >= 3:
        c.add("geo-entity-facts-thin", "low", f"Homepage and About page state few verifiable facts about the business ({', '.join(missing_facts)})", "AI systems describe a brand from plain, checkable statements: what it does, where it is, since when, how big. Without them the model guesses or stays silent.", "Add a short fact paragraph on the About page (founded, location, what you do, scale, credentials) and mirror it in Organization schema.", evidence=[f"missing: {', '.join(missing_facts)}"], effort="low")
    elif home is not None:
        c.passed("geo-entity-facts", "Homepage/About state concrete facts about the business")

    # ---------------------------------------------- Wikidata (external, free)
    wikidata = {"checked": False}
    if external and brand:
        try:
            import requests

            r = requests.get("https://www.wikidata.org/w/api.php", params={"action": "wbsearchentities", "search": brand, "language": "en", "format": "json", "limit": 3}, timeout=12, headers={"User-Agent": fetcher.user_agent})
            hits = r.json().get("search", []) if r.status_code == 200 else []
            exact = [h for h in hits if h.get("label", "").strip().lower() == brand.strip().lower()]
            wikidata = {"checked": True, "brand": brand, "matches": [{"id": h.get("id"), "label": h.get("label"), "description": h.get("description", "")} for h in hits[:3]], "exact": bool(exact)}
            if exact:
                c.passed("geo-wikidata", f"Wikidata item exists for '{brand}' ({exact[0].get('id')}: {exact[0].get('description', '')[:60]})")
                if not any("wikidata.org" in s for s in same_as):
                    c.add("geo-wikidata-not-linked", "low", "A Wikidata item exists but the site does not link it in sameAs", "Linking the Wikidata item ties the website to the knowledge-graph entity AI models already know.", f"Add https://www.wikidata.org/wiki/{exact[0].get('id')} to Organization.sameAs.", effort="low")
            else:
                c.add("geo-no-wikidata", "low", f"No Wikidata item found for '{brand}'", "Wikidata is a primary source for knowledge panels and for how LLMs resolve brand entities. Any real organisation may create an item.", "Create a Wikidata item (official website, industry, location, founding date, social profiles) and link it from Organization.sameAs.", evidence=[f"wikidata search '{brand}': {len(hits)} loose matches, none exact"], effort="low")
        except Exception as exc:  # pragma: no cover
            wikidata = {"checked": False, "error": exc.__class__.__name__}

    # ------------------------------------------------- AI discovery extras
    extras = {}
    for path in ("/.well-known/ai-plugin.json", "/ai.txt", "/agents.md", "/humans.txt", "/feed", "/rss.xml", "/feed.xml", "/atom.xml", "/.well-known/security.txt", "/license.xml", "/rsl.xml"):
        r = fetcher.get(f"{origin}{path}")
        extras[path] = r.status if r.error is None and "text/html" not in r.content_type else (0 if r.error else -r.status)
    has_feed = any(extras[p] == 200 for p in ("/feed", "/rss.xml", "/feed.xml", "/atom.xml")) or any(bool(re.search(r"rss|atom", str(p.headers.get("link", "")), re.I)) for p in html_pages[:5])
    if business.get("business_type") in ("publisher / media",) and not has_feed:
        c.add("geo-no-feed", "low", "No RSS/Atom feed found", "Feeds let AI crawlers, aggregators and Google Discover pick up new articles within minutes.", "Enable the CMS feed and link it with <link rel=\"alternate\" type=\"application/rss+xml\">.", effort="low")
    elif has_feed:
        c.passed("geo-feed", "RSS/Atom feed available")
    if extras.get("/agents.md") == 200:
        c.passed("geo-agents-md", "/agents.md present (agent readiness file)")
    if rsl or extras.get("/license.xml") == 200 or extras.get("/rsl.xml") == 200:
        c.passed("geo-rsl", "Machine-readable AI licensing signal present (RSL / License directive)")
    try:
        import requests

        r = requests.get(home_url, headers={"Accept": "text/markdown", "User-Agent": fetcher.user_agent}, timeout=15)
        md_supported = "text/markdown" in (r.headers.get("content-type") or "")
    except Exception:
        md_supported = False
    if md_supported:
        c.passed("geo-markdown-negotiation", "Server returns Markdown for Accept: text/markdown")

    # --------------------------------------------------- structural readiness
    if html_pages:
        csr = [p for p in html_pages if (p.word_count < 80 and p.external_scripts >= 3) or p.render_hint]
        if len(csr) >= max(2, n * 0.3):
            c.add("geo-csr-invisible", "high", "Primary content is not in the HTML that AI crawlers receive", "Unlike Googlebot, OAI-SearchBot, PerplexityBot and ClaudeBot do not execute JavaScript. They see an empty shell.", "Server-side render or pre-render content pages.", evidence=[f"{p.url} ({p.word_count} words)" for p in csr[:5]], affected_count=len(csr), effort="high")
        else:
            c.passed("geo-ssr", "Content is visible without JavaScript")
        content_pages = [p for p in html_pages if page_type(p.url, p) in ("service", "article", "product", "home", "other", "location", "faq", "pricing") and p.word_count > 150]
        good_blocks = [p for p in content_pages if any(40 <= w <= 170 for w in (p.lead_paragraph_words or [p.first_paragraph_words])[:4])]
        if content_pages and len(good_blocks) < len(content_pages) * 0.3:
            c.add("geo-no-answer-blocks", "medium", f"Only {len(good_blocks):,} of {len(content_pages):,} content pages open with an answer-sized paragraph", "AI engines lift self-contained passages of roughly 40 to 170 words. One-line intros and 300-word walls are both skipped.", "Open key pages and sections with a complete 60 to 120 word answer paragraph that names the entity and the key fact.", evidence=[f"{p.url} (opening paragraphs: {', '.join(str(w) for w in p.lead_paragraph_words[:4]) or '0'} words)" for p in content_pages if p not in good_blocks][:5], affected_count=len(content_pages) - len(good_blocks), effort="medium")
        elif content_pages:
            c.passed("geo-answer-blocks", f"{len(good_blocks):,} pages open with answer-sized paragraphs")
        stats_pages = [p for p in content_pages if p.stat_mentions >= 3]
        if content_pages and len(stats_pages) < len(content_pages) * 0.3:
            c.add("geo-few-citable-facts", "low", f"Only {len(stats_pages):,} of {len(content_pages):,} content pages contain numbers, dates or statistics", "AI answers prefer passages with specific, checkable figures; vague copy is paraphrased without attribution.", "Add concrete numbers (prices, timelines, counts, dates, percentages) and name their source on key pages.", affected_count=len(content_pages) - len(stats_pages), effort="medium")
        if home is not None and not home.has_social_links:
            pass  # reported in content

    # Platform readiness
    probe_blocked = {b for b, r in probe_results.items() if r.get("challenged")}
    platform_ready = {}
    for name, bots in PLATFORMS.items():
        blocked_bots = [b for b in bots if statuses.get(b) in ("blocked", "blocked-by-wildcard") or b in probe_blocked]
        ok = not blocked_bots
        if name.startswith("Google") and nosnip and home in nosnip:
            ok = False
            blocked_bots.append("nosnippet")
        platform_ready[name] = {"ready": ok, "blocked": blocked_bots}

    out = c.to_dict()
    out["bot_status"] = {b[0]: {"status": statuses[b[0]], "role": b[1], "vendor": b[2], "note": b[3]} for b in AI_BOTS}
    out["cloudflare_managed_robots"] = cloudflare_managed
    out["ua_probes"] = probe_results
    out["ua_probes_inner"] = deep_probes
    out["content_signal"] = content_signal
    out["llms_txt"] = {"present": llms_ok, "status": llms.status, **{k: v for k, v in llms_info.items() if k != "link_urls"}}
    out["llms_full_txt"] = llms_full.error is None and llms_full.status == 200 and "text/html" not in llms_full.content_type
    out["discovery_files"] = extras
    out["has_feed"] = has_feed
    out["markdown_negotiation"] = md_supported
    out["brand_names_seen"] = dict(names.most_common(5))
    out["same_as"] = same_as[:15]
    out["entity_facts"] = facts
    out["wikidata"] = wikidata
    out["platform_readiness"] = platform_ready
    out["rsl"] = rsl
    return out
