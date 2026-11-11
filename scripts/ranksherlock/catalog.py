"""Merged client-facing knowledge base: what each check measures, why it matters, how to fix and verify it.

Entries live in catalog_technical.py, catalog_content.py and catalog_other.py (one dict each, keyed by check id).
Ids produced with f-strings (for example psi-<audit-id>) fall back to their template entry (psi-X)."""

from __future__ import annotations

import re

CHECKS: dict[str, dict] = {}
for _mod in ("catalog_technical", "catalog_content", "catalog_other"):
    try:
        _m = __import__(f"{__package__}.{_mod}", fromlist=["CHECKS"])
        CHECKS.update(getattr(_m, "CHECKS", {}))
    except Exception:  # pragma: no cover
        continue

EXTRA = {
    "large-html": {"group": "Performance basics", "what": "We measured the size of each HTML document and flagged pages between 500 KB and 1.5 MB.", "why_long": "HTML this large is almost always page-builder bloat, inlined CSS or embedded SVG. Every visitor downloads it before anything renders, and crawlers spend their budget on markup instead of content.", "business_impact": "Slower first paint on every page, especially on mobile data.", "steps": ["Open one flagged page and view source to see what inflates it (inline styles, SVG icons, hidden sliders).", "Move inline CSS and SVG sprites to cached external files.", "Paginate or lazy-load long lists and galleries.", "Re-run the audit and check the average HTML size in the crawl overview."], "verify": "Reload the page with DevTools open; the document request should be well under 500 KB uncompressed.", "owner": "Developer", "ref": "https://web.dev/articles/optimize-lcp"},
    "html-size": {"group": "Performance basics", "what": "We measured the size of every HTML document in the crawl.", "why_long": "Compact HTML renders faster and is cheaper for crawlers to fetch, so pages get crawled more often.", "business_impact": "Pages load quickly on mobile.", "steps": ["No action needed; keep inline CSS and SVG out of the templates when adding features."], "verify": "Watch the average HTML size in future audits.", "owner": "Developer", "ref": "https://web.dev/articles/optimize-lcp"},
    "schema-X-deprecated": {"group": "Policy risks", "what": "We looked for structured data types whose rich results Google has retired.", "why_long": "Retired types no longer produce rich results. The markup is harmless if valid, but it costs maintenance and can mislead the team into expecting results that will not appear.", "business_impact": "Effort spent on markup that no longer changes how the site appears in search.", "steps": ["Confirm the type is on Google's retired list.", "Remove it, or keep it only if it still helps AI extraction and is accurate.", "Redirect the effort to types that still earn rich results (Product, Article, LocalBusiness, BreadcrumbList)."], "verify": "Run the Rich Results Test; no warnings about unsupported types.", "owner": "Developer", "ref": "https://developers.google.com/search/docs/appearance/structured-data/search-gallery"},
    "geo-content-signal-blocks-ai": {"group": "AI crawler access", "what": "We read the Content-Signal line in robots.txt, a directive that tells AI systems whether the site may be used for search, AI answers and training.", "why_long": "search=no or ai-input=no asks answer engines not to use the site when composing answers. Crawlers that honour it (Cloudflare-fronted sites and a growing list of AI vendors) drop the site from AI results.", "business_impact": "The brand disappears from AI answers on platforms that honour the signal.", "steps": ["Open robots.txt and find the Content-Signal line.", "Set search=yes and ai-input=yes.", "Keep ai-train=no if the business does not want its content used for model training.", "If Cloudflare manages robots.txt, change the setting under AI Crawl Control instead of editing the file."], "verify": "Fetch /robots.txt and confirm the Content-Signal values.", "owner": "Developer", "ref": "https://developers.google.com/search/docs/crawling-indexing/robots/intro"},
    "geo-content-signal-conflict": {"group": "AI crawler access", "what": "We compared the Content-Signal ai-train value with the robots.txt rules for training bots.", "why_long": "Saying training is allowed while blocking GPTBot, ClaudeBot or CCBot sends mixed signals; compliance teams and crawlers may interpret either one.", "business_impact": "Unclear policy; no direct ranking effect.", "steps": ["Decide the training policy once.", "Set ai-train in Content-Signal to match.", "Align the robots.txt groups for GPTBot, ClaudeBot, CCBot, Google-Extended and Bytespider with that decision."], "verify": "robots.txt shows one consistent policy.", "owner": "Developer", "ref": "https://developers.google.com/search/docs/crawling-indexing/robots/intro"},
    "geo-content-signal": {"group": "AI crawler access", "what": "We read the Content-Signal line in robots.txt.", "why_long": "A declared Content-Signal makes the site's AI policy explicit to crawlers that honour it.", "business_impact": "Clear policy for AI vendors.", "steps": ["No action needed; revisit the values if the AI policy changes."], "verify": "Fetch /robots.txt after any change.", "owner": "Developer", "ref": "https://developers.google.com/search/docs/crawling-indexing/robots/intro"},
    "geo-noai-directive": {"group": "AI crawler access", "what": "We looked for noai or noimageai in meta robots tags and X-Robots-Tag headers.", "why_long": "These opt-out tokens are honoured by a few AI companies. They have no effect on Google or Bing rankings, but they can reduce AI reuse of the content.", "business_impact": "Less AI reuse; no search effect.", "steps": ["Confirm the directive is intentional.", "Remove it if AI visibility is a goal."], "verify": "View source; the meta robots tag no longer contains noai.", "owner": "Developer", "ref": "https://developers.google.com/search/docs/crawling-indexing/robots-meta-tag"},
    "geo-hidden-ai-instructions": {"group": "Quotability", "what": "We scanned page text for sentences that address AI models directly (for example 'ignore previous instructions').", "why_long": "AI vendors treat prompt-style text aimed at their crawlers as manipulation. It can get a domain excluded from answers and reads as spam to human visitors.", "business_impact": "Risk of exclusion from AI answers and loss of reader trust.", "steps": ["Open the flagged pages and remove any text written for AI systems rather than people.", "Check hidden elements and footers where such text is often placed."], "verify": "Re-run the audit; the finding disappears.", "owner": "Content team", "ref": "https://developers.google.com/search/docs/essentials/spam-policies"},
    "geo-waf-blocks-ai-bots-inner": {"group": "AI crawler access", "what": "We requested two inner pages pretending to be OAI-SearchBot, PerplexityBot and Googlebot and checked for challenges or 403 responses.", "why_long": "A firewall rule scoped to inner paths lets the homepage through but hides the service, product or article pages, which are exactly the pages answer engines need to quote.", "business_impact": "Only the homepage can be cited; the pages that sell are invisible to AI.", "steps": ["In the WAF or Cloudflare dashboard, find rules that apply to paths other than /.", "Allow verified search and AI retrieval bots on every path.", "Test with curl -A 'OAI-SearchBot/1.0' against an inner URL."], "verify": "curl with the bot user agent returns 200 and the full HTML for inner pages.", "owner": "Hosting / DevOps", "ref": "https://platform.openai.com/docs/bots"},
    "local-address-schema-only": {"group": "NAP consistency", "what": "We looked for a street address in the visible text of every page and compared it with the address in LocalBusiness schema.", "why_long": "Google confirms a local business by matching the address shown on the site with the Google Business Profile and directories. An address that exists only in hidden markup is a weaker signal, and visitors cannot see it.", "business_impact": "Weaker local pack confidence and visitors who cannot find where you are.", "steps": ["Add the full postal address as plain text in the footer of every page.", "Repeat it on the contact page inside an <address> element.", "Make it match the schema and the Google Business Profile character for character."], "verify": "View the page source and search for the street name; it should appear in visible text, not only inside the JSON-LD script.", "owner": "Developer", "ref": "https://developers.google.com/search/docs/appearance/structured-data/local-business"},
    "geo-probe-inconclusive": {"group": "AI crawler access", "what": "Some bot probes returned 429 or a server error, so we could not tell whether the bot is blocked.", "why_long": "Rate limiting during the audit is not proof of blocking. Server logs or a later re-test settle it.", "business_impact": "Unknown; needs a re-test.", "steps": ["Re-run the audit at a quieter time.", "Check server or CDN logs for the listed user agents."], "verify": "A later probe returns 200.", "owner": "Hosting / DevOps", "ref": "https://developers.google.com/search/docs/crawling-indexing/overview-google-crawlers"},
}
for _k, _v in EXTRA.items():
    CHECKS.setdefault(_k, _v)

_TEMPLATES = [(k, re.compile("^" + re.escape(k).replace("X", ".+") + "$")) for k in CHECKS if "X" in k]


def lookup(check_id: str) -> dict:
    if check_id in CHECKS:
        return CHECKS[check_id]
    for key, rx in _TEMPLATES:
        if rx.match(check_id):
            return CHECKS[key]
    return {}


class _Lookup(dict):
    def get(self, key, default=None):  # type: ignore[override]
        v = lookup(key)
        return v if v else default


CHECKS = _Lookup(CHECKS)
