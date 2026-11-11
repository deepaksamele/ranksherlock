"""Business-type and page-type classification. Deterministic, from crawl evidence only."""

from __future__ import annotations

import re
from collections import Counter

YMYL_RE = re.compile(r"\b(loan|mortgage|insurance|invest|trading|broker|stock|mutual fund|tax|credit card|bank|crypto|medical|doctor|clinic|hospital|symptom|treatment|pharma|drug|dentist|lawyer|attorney|legal|law firm|divorce|immigration|visa|pension|retirement)\b", re.I)

TYPE_RULES = [
    # (type, url regex, text regex, min hits)
    ("e-commerce", r"/(cart|checkout|collections?|products?|shop|store|catalog)\b", r"\b(add to (cart|bag|basket)|buy now|free shipping|in stock|out of stock|sku)\b", 3),
    ("SaaS / software", r"/(pricing|features|integrations|docs|api|changelog|login|signup|sign-up|demo)\b", r"\b(free trial|start free|book a demo|request a demo|pricing plans|per month|per user|api|dashboard|integrations?)\b", 3),
    ("publisher / media", r"/(news|article|articles|story|stories|opinion|editorial|magazine|category|tag|author)\b", r"\b(by [A-Z][a-z]+ [A-Z][a-z]+|published|updated on|min read|editor|newsroom)\b", 4),
    ("education", r"/(courses?|admissions?|programs?|faculty|campus|students?|syllabus|tuition|enroll)\b", r"\b(courses?|enrol|admission|students|faculty|curriculum|tuition|campus|alumni)\b", 3),
    ("healthcare", r"/(doctors?|treatments?|services|patients?|appointments?|clinic|departments?)\b", r"\b(patients?|appointment|clinic|doctor|physician|treatment|surgery|dental|therapy)\b", 3),
    ("real estate", r"/(properties|property|listings?|apartments?-for|for-sale|for-rent|rent|buy)\b", r"\b(for sale|for rent|property listings?|brokerage|realtor|mls|rera|possession|resale|open house)\b", 3),
    ("home services / construction", r"/(house-design|house-plans?|floor-plans?|interiors?|architects?|construction|renovation|remodel|roofing|plumbing|hvac|flooring|landscap|painting|cleaning)\b", r"\b(architects?|interior design|floor plans?|house plans?|construction|contractors?|renovation|remodel|turnkey|roofing|plumbing|hvac|flooring|installation|free estimate)\b", 3),
    ("finance", r"/(loans?|insurance|invest|trading|accounts?|cards?|mutual-funds?|ipo|calculators?)\b", r"\b(loan|interest rate|insurance|invest|trading|demat|brokerage|mutual fund|ipo|sip|emi)\b", 3),
    ("legal", r"/(practice-areas?|attorneys?|lawyers?|cases?|consultation)\b", r"\b(attorneys?|lawyers?|law firm|litigation|legal (services|advice|representation)|practice areas?)\b", 3),
    ("travel / hospitality", r"/(hotels?|rooms?|tours?|destinations?|booking|packages?|itinerary)\b", r"\b(book now|check-in|check-out|itinerary|night|resort|hotel|tour|destination)\b", 3),
    ("restaurant / food", r"/(menu|reservations?|order|delivery|catering)\b", r"\b(menu|reservation|dine|delivery|takeaway|chef|cuisine)\b", 3),
    ("agency / services", r"/(case-stud(y|ies)|portfolio|our-work|clients|industries|services)\b", r"\b(agency|our clients|case stud(y|ies)|portfolio|our work|we help|consult)\b", 3),
    ("nonprofit / government", r"/(donate|volunteer|programs?|causes?|about-us|departments?|tenders?)\b", r"\b(donate|donation|volunteer|non-?profit|ngo|charity|ministry|municipal|government)\b", 3),
    ("manufacturing / B2B", r"/(products?|industries|solutions|catalog|datasheets?|distributors?|oem)\b", r"\b(manufacturer|oem|distributor|wholesale|industrial|datasheet|iso 9001|b2b|rfq|request a quote)\b", 3),
]

PAGE_TYPE_RULES = [
    ("home", r"^/?$", None),
    ("contact", r"/(contact|contact-us|get-in-touch|reach-us|enquiry|inquiry)\b", None),
    ("about", r"/(about|about-us|who-we-are|our-story|company|team|our-team)\b", None),
    ("legal", r"/(privacy|terms|refund|return|shipping-policy|disclaimer|cookie)", None),
    ("faq", r"/(faq|faqs|help|support|knowledge-?base)\b", None),
    ("blog-index", r"/(blog|news|articles?|insights?|resources?)/?$", None),
    ("article", r"/(blog|news|articles?|post|guide|guides|learn|insights?|resources?|stories|story)/.+", None),
    ("product", r"/(products?|item|p|shop)/[^/]+/?$", None),
    ("category", r"/(collections?|category|categories|c|shop|products?)/?([^/]+/?)?$", None),
    ("location", r"/(locations?|areas?|service-areas?|cities|near|in)/|-(in|near)-[a-z-]+/?$", None),
    ("service", r"/(services?|solutions?|treatments?|practice-areas?|what-we-do)/", None),
    ("pricing", r"/(pricing|plans|packages?)\b", None),
    ("author", r"/(author|authors|people|profile)/", None),
    ("search", r"/(search|\?s=|\?q=)", None),
    ("tag", r"/(tags?|topics?)/", None),
    ("pagination", r"/page/\d+|[?&]page=\d+|[?&]paged=\d+", None),
    ("cart", r"/(cart|checkout|basket|account|login|register|wishlist|my-account)\b", None),
]

WORD_FLOORS = {"home": 300, "service": 500, "location": 500, "article": 800, "product": 250, "category": 150, "about": 300, "landing": 400, "faq": 400, "pricing": 200, "contact": 80, "legal": 200, "other": 200, "blog-index": 50, "author": 100, "tag": 50, "pagination": 50, "cart": 0, "search": 0}


def page_type(url: str, page=None) -> str:
    from urllib.parse import urlparse

    path = urlparse(url).path or "/"
    full = path + ("?" + urlparse(url).query if urlparse(url).query else "")
    for name, rx, _ in PAGE_TYPE_RULES:
        if re.search(rx, full, re.I):
            return name
    if page is not None:
        if "Product" in page.schema_types or page.has_add_to_cart:
            return "product"
        if any(t in page.schema_types for t in ("Article", "BlogPosting", "NewsArticle")):
            return "article"
        if page.date_signals and page.word_count > 500:
            return "article"
    return "other"


def detect_business_type(pages: list, schema_result: dict, local_result: dict) -> dict:
    html_pages = [p for p in pages if p.status == 200 and "text/html" in (p.content_type or "")]
    sample = html_pages[:80]
    text = " ".join((p.text_sample or "")[:500] + " " + (p.title or "") for p in sample).lower()
    urls = " ".join(p.url for p in html_pages)
    scores = Counter()
    n_pages = max(len(html_pages), 1)
    n_sample = max(len(sample), 1)
    for name, url_rx, text_rx, _ in TYPE_RULES:
        url_frac = sum(1 for p in html_pages if re.search(url_rx, p.url, re.I)) / n_pages
        text_frac = sum(1 for p in sample if name in (p.biz_terms or []) or re.search(text_rx, p.title or "", re.I)) / n_sample
        scores[name] = round(url_frac * 8 + text_frac * 10, 2)
    if any(p.has_add_to_cart for p in sample):
        scores["e-commerce"] += 10
    if schema_result.get("has_product"):
        scores["e-commerce"] += 6
    is_local = bool(local_result.get("is_local_business"))
    article_share = sum(1 for p in html_pages if page_type(p.url, p) == "article") / n_pages
    if article_share > 0.5:
        scores["publisher / media"] += 10
    else:
        scores["publisher / media"] = round(scores["publisher / media"] * 0.5, 2)
    best, best_score = (scores.most_common(1)[0] if scores else ("business / services", 0))
    if best_score < 4:
        best = "local business" if is_local else "business / services"
        best_score = 12 if is_local else best_score
    industry = best
    # "Local" is a delivery model, not an industry: keep the industry label and flag locality separately.
    if is_local and best in ("business / services", "agency / services"):
        best = "local business"
    ymyl = len(YMYL_RE.findall(text)) >= 6 or best in ("finance", "healthcare", "legal")
    ptypes = Counter(page_type(p.url, p) for p in html_pages)
    return {"business_type": best, "industry": industry, "confidence": round(min(1.0, best_score / 15), 2), "ymyl": ymyl, "candidates": dict(scores.most_common(4)), "page_types": dict(ptypes.most_common()), "is_local": is_local}
