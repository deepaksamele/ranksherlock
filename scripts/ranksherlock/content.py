"""On-page, content quality, E-E-A-T, images, internal links and AEO (answer readiness) checks."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime

from .business import page_type, WORD_FLOORS
from .crawl import ORPHAN_DEPTH
from .findings import Collector

TRUST_PAGES = {
    "about": r"/(about|about-us|who-we-are|our-story|company|team)\b",
    "contact": r"/(contact|contact-us|get-in-touch|reach-us)\b",
    "privacy": r"/(privacy|privacy-policy)\b",
    "terms": r"/(terms|terms-of-service|terms-and-conditions|tos)\b",
}
FILLER = ["in today's fast-paced world", "in the ever-evolving", "delve", "it's important to note", "unlock the power", "game-changer", "seamlessly", "robust", "leverage", "cutting-edge", "in conclusion,", "look no further", "elevate your", "in the realm of", "navigating the", "a testament to", "tapestry"]
GENERIC_ANCHORS = {"click here", "read more", "learn more", "here", "more", "link", "this", "view", "see more", "continue"}


def syllables(word: str) -> int:
    word = word.lower()
    count = len(re.findall(r"[aeiouy]+", word))
    if word.endswith("e") and count > 1:
        count -= 1
    return max(count, 1)


def flesch(text: str) -> float:
    words = re.findall(r"[A-Za-z']+", text)
    sentences = [s for s in re.split(r"[.!?]+", text) if len(s.split()) > 2]
    if len(words) < 50 or not sentences:
        return 0.0
    syl = sum(syllables(w) for w in words)
    score = 206.835 - 1.015 * (len(words) / len(sentences)) - 84.6 * (syl / len(words))
    return round(max(0.0, min(100.0, score)), 1)


def citability_block_score(text: str, heading: str = "") -> dict:
    """Deterministic citability for one passage. 0-100. Mirrors the dimensions answer engines reward."""
    words = text.split()
    n = len(words)
    parts = {}
    aq = 0
    if re.search(r"\b(is|are|refers to|means|defined as|consists of)\b", " ".join(words[:25]), re.I):
        aq += 12
    if re.search(r"\d", " ".join(words[:60])):
        aq += 8
    if heading.strip().endswith("?") or re.match(r"^(what|how|why|when|where|who|which)\b", heading, re.I):
        aq += 10
    parts["answer_quality"] = min(aq, 30)
    sc = 0
    if 80 <= n <= 200:
        sc += 10
    elif 40 <= n <= 300:
        sc += 6
    pronouns = len(re.findall(r"\b(it|this|that|these|those|they|them)\b", text, re.I))
    ratio = pronouns / max(n, 1)
    sc += 8 if ratio < 0.02 else 5 if ratio < 0.04 else 2
    proper = len(re.findall(r"(?<![.!?]\s)(?<!^)\b[A-Z][a-z]{2,}\b", text))
    sc += 7 if proper >= 3 else 4 if proper >= 1 else 0
    parts["self_containment"] = min(sc, 25)
    st = 0
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    avg = n / max(len(sentences), 1)
    if 10 <= avg <= 22:
        st += 8
    if re.search(r"\b(for example|however|because|therefore|first|second|finally|in addition)\b", text, re.I):
        st += 4
    if re.search(r"(^|\n)\s*(\d+[.)]|[-*•])\s", text):
        st += 4
    if "\n" in text:
        st += 4
    parts["structure"] = min(st, 20)
    sd = 0
    sd += min(len(re.findall(r"\d+(\.\d+)?\s?%", text)) * 3, 6)
    sd += min(len(re.findall(r"[$₹€£]\s?\d", text)) * 3, 5)
    if re.search(r"\b(20[12]\d)\b", text):
        sd += 2
    if re.search(r"\b(according to|study|survey|report|research|data from)\b", text, re.I):
        sd += 2
    parts["stats_sourcing"] = min(sd, 15)
    u = 0
    if re.search(r"\b(we found|our (data|research|study|analysis|experience)|in our)\b", text, re.I):
        u += 5
    if re.search(r"\b(case study|for example|e\.g\.|such as)\b", text, re.I):
        u += 3
    if re.search(r"\b(using|with)\s+[A-Z][a-z]+", text):
        u += 2
    parts["uniqueness"] = min(u, 10)
    return {"score": sum(parts.values()), "parts": parts, "words": n}


def analyze_content(pages: list, home_url: str, origin: str, business: dict | None = None) -> dict:
    c = Collector("content")
    business = business or {}
    btype = business.get("business_type", "")
    html_pages = [p for p in pages if p.status == 200 and "text/html" in (p.content_type or "") and "noindex" not in (p.meta_robots or "").lower()]
    if not html_pages:
        c.skipped("content", "No indexable HTML pages to analyse")
        return c.to_dict()
    from urllib.parse import urlparse as _up

    n = len(html_pages)
    home = next((p for p in html_pages if p.url == home_url), html_pages[0])
    is_home = _up(home.final_url).path in ("", "/")
    ptype = {p.url: page_type(p.url, p) for p in html_pages}
    content_pages = [p for p in html_pages if ptype[p.url] not in ("cart", "search", "pagination", "tag", "legal", "author", "blog-index")]
    brand = ""
    if home.title:
        tail = re.split(r"\s[|\-–—:]\s", home.title)
        brand = tail[-1].strip() if len(tail) > 1 else ""

    # ================================================================ titles
    no_title = [p for p in html_pages if not p.title]
    if no_title:
        c.add("missing-title", "high", f"{len(no_title):,} pages have no <title>", "The title is the strongest on-page ranking signal and the headline in search results.", "Write a unique 50-60 character title with the primary keyword first.", evidence=[p.url for p in no_title[:6]], affected_count=len(no_title), pages=[p.url for p in no_title[:300]], effort="low")
    else:
        c.passed("title-present", "Every page has a title tag")
    long_t = [p for p in html_pages if len(p.title) > 65]
    short_t = [p for p in html_pages if 0 < len(p.title) < 30]
    if long_t and len(long_t) > n * 0.25:
        c.add("long-titles", "low", f"{len(long_t):,} titles are over 65 characters", "Truncated titles lose the brand or keyword in the SERP.", "Trim to 50-60 characters, keyword first, brand last.", evidence=[f"{p.url} ({len(p.title)} chars)" for p in long_t[:5]], affected_count=len(long_t), pages=[p.url for p in long_t[:200]], effort="low")
    if short_t and len(short_t) > n * 0.25:
        c.add("short-titles", "low", f"{len(short_t):,} titles are under 30 characters", "Short titles miss secondary keywords and context.", "Expand to 50-60 characters with a benefit or qualifier.", evidence=[f"{p.url}: '{p.title}'" for p in short_t[:5]], affected_count=len(short_t), effort="low")
    if not long_t and not short_t:
        c.passed("title-length", "Title lengths are within range")
    brand_only = [p for p in html_pages if is_home and p.title and home.title and p.title.strip().lower() == home.title.strip().lower() and p.url != home.url]
    if brand_only:
        c.add("title-same-as-home", "medium", f"{len(brand_only):,} inner pages reuse the homepage title", "The site name alone tells Google nothing about the page topic.", "Give each page its own topical title.", evidence=[p.url for p in brand_only[:6]], affected_count=len(brand_only), pages=[p.url for p in brand_only[:200]], effort="low")
    if brand:
        doubled = [p for p in html_pages if p.title.lower().count(brand.lower()) >= 2]
        if doubled and len(doubled) > 2:
            c.add("title-brand-doubled", "low", f"Brand name appears twice in {len(doubled):,} titles", "A template appends the brand to a title that already contains it, wasting the characters that get shown.", "Fix the title template so the brand suffix is added once.", evidence=[f"{p.url}: '{p.title[:80]}'" for p in doubled[:4]], affected_count=len(doubled), effort="low")
    defaults = [p for p in html_pages if re.search(r"\b(archives?|untitled|home page|new page|just another wordpress site|pages archive)\b", p.title, re.I) or p.title.strip().lower() in ("home", "index", "welcome")]
    if defaults:
        c.add("title-cms-default", "medium", f"{len(defaults):,} titles are CMS defaults or archive labels", "Titles such as 'Home' or 'Products Archives' carry no keyword and look auto-generated in results.", "Write descriptive titles for these templates.", evidence=[f"{p.url}: '{p.title[:60]}'" for p in defaults[:5]], affected_count=len(defaults), pages=[p.url for p in defaults[:200]], effort="low")

    # ============================================================ descriptions
    no_desc = [p for p in content_pages if not p.meta_description]
    if no_desc:
        sev = "medium" if len(no_desc) > len(content_pages) * 0.3 else "low"
        c.add("missing-description", sev, f"{len(no_desc):,} pages have no meta description", "Google writes its own snippet, usually worse, which lowers click-through rate.", "Write a 140-160 character description with the keyword and a reason to click.", evidence=[p.url for p in no_desc[:6]], affected_count=len(no_desc), pages=[p.url for p in no_desc[:300]], effort="low")
    else:
        c.passed("description-present", "Every content page has a meta description")
    long_d = [p for p in html_pages if len(p.meta_description) > 170]
    short_d = [p for p in html_pages if 0 < len(p.meta_description) < 70]
    if long_d and len(long_d) > n * 0.3:
        c.add("long-descriptions", "info", f"{len(long_d):,} meta descriptions are over 170 characters", "They get cut off in results.", "Keep to 140-160 characters.", affected_count=len(long_d), effort="low")
    if short_d and len(short_d) > n * 0.3:
        c.add("short-descriptions", "low", f"{len(short_d):,} meta descriptions are under 70 characters", "Very short descriptions waste the snippet space that sells the click.", "Expand to 140-160 characters with a benefit and a call to action.", affected_count=len(short_d), effort="low")

    # ================================================================== H1s
    no_h1 = [p for p in content_pages if not p.h1]
    multi_h1 = [p for p in content_pages if len(p.h1) > 1]
    if no_h1:
        sev = "high" if len(no_h1) > len(content_pages) * 0.3 or home in no_h1 else "medium"
        c.add("missing-h1", sev, f"{len(no_h1):,} pages have no H1", "The H1 states the page topic for users, crawlers and answer engines.", "Add exactly one H1 that matches search intent.", evidence=[p.url for p in no_h1[:6]], affected_count=len(no_h1), pages=[p.url for p in no_h1[:300]], effort="low")
    else:
        c.passed("h1-present", "Every content page has an H1")
    if multi_h1 and len(multi_h1) > len(content_pages) * 0.15:
        c.add("multiple-h1", "low", f"{len(multi_h1):,} pages have more than one H1", "Multiple H1s dilute the topic signal (common with logo or slider H1s).", "Keep one H1; demote the rest to H2 or a div.", evidence=[f"{p.url} ({len(p.h1)} H1s)" for p in multi_h1[:5]], affected_count=len(multi_h1), pages=[p.url for p in multi_h1[:200]], effort="low")
    skipped_levels = [p for p in html_pages if any(b - a > 1 for a, b in zip(p.heading_order, p.heading_order[1:]) if b > a)]
    if skipped_levels and len(skipped_levels) > n * 0.4:
        c.add("heading-hierarchy", "low", f"Heading levels skip on {len(skipped_levels):,} pages (H1 to H3, H2 to H4)", "A clean outline helps extraction of sections by answer engines and screen readers.", "Nest headings in order without skipping levels.", affected_count=len(skipped_levels), effort="low")
    empty_h = [p for p in html_pages if any(h == "" for h in p.h1 + p.h2)]
    if empty_h:
        c.add("empty-headings", "low", f"Empty heading tags on {len(empty_h):,} pages", "Empty H1/H2 are usually icon or image wrappers and waste the strongest structural tags.", "Remove empty headings or put real text in them.", evidence=[p.url for p in empty_h[:5]], affected_count=len(empty_h), effort="low")
    no_h2 = [p for p in content_pages if p.word_count > 600 and not p.h2]
    if no_h2 and len(no_h2) > 2:
        c.add("no-subheadings", "low", f"{len(no_h2):,} long pages have no H2 subheadings", "Walls of text are hard to scan and give answer engines no section boundaries to quote.", "Break long content into H2/H3 sections every 150 to 300 words.", evidence=[p.url for p in no_h2[:4]], affected_count=len(no_h2), effort="medium")
    ui_h = [p for p in html_pages if any(re.match(r"^(menu|navigation|search|cart|my cart|notice|cookies?|share|follow us|subscribe)\b", h, re.I) for h in p.h2)]
    if ui_h and len(ui_h) > n * 0.3:
        c.add("ui-chrome-headings", "low", "Headings used for interface chrome (menu, cart, search)", "Template widgets marked up as H2 pollute the document outline that crawlers and AI read first.", "Use div or span with styling for widget labels; keep headings for content.", evidence=[f"{p.url}: {[h for h in p.h2 if re.match(r'^(menu|navigation|search|cart|my cart|notice|cookies?|share|follow us|subscribe)', h, re.I)][0]}" for p in ui_h[:4]], affected_count=len(ui_h), effort="low")

    # =========================================================== thin by type
    thin = []
    for p in content_pages:
        floor = WORD_FLOORS.get(ptype[p.url], 200)
        if floor and p.word_count < floor * 0.5 and p.depth > 0:
            thin.append(p)
    if thin and len(thin) > max(2, len(content_pages) * 0.1):
        by_t = Counter(ptype[p.url] for p in thin)
        c.add("thin-content", "medium" if len(thin) < len(content_pages) * 0.4 else "high", f"{len(thin):,} pages are thin for their page type", "Thin pages rarely rank and drag down the site-wide quality assessment. Floors used: service 500, article 800, product 250, location 500, category 150 words.", "Expand with genuinely useful content, merge into a stronger page, or noindex.", evidence=[f"{p.url} ({p.word_count} words, {ptype[p.url]} page, floor {WORD_FLOORS.get(ptype[p.url], 200)})" for p in thin[:6]] + [f"by type: {dict(by_t.most_common(5))}"], affected_count=len(thin), pages=[p.url for p in thin[:300]], effort="high")
    else:
        c.passed("content-depth", "Pages meet the word-count floor for their type")
    avg_words = round(sum(p.word_count for p in html_pages) / n)
    low_ratio = [p for p in html_pages if p.text_to_html_ratio < 0.05 and p.word_count < 400]
    if low_ratio and len(low_ratio) > n * 0.4:
        c.add("low-text-ratio", "low", f"Very low text-to-HTML ratio on {len(low_ratio):,} pages", "Pages are mostly markup and scripts; little for crawlers to index.", "Reduce bloat (inline SVG, builder wrappers) and add substantive copy.", affected_count=len(low_ratio), effort="medium")
    placeholders = [p for p in html_pages if p.placeholder_text]
    if placeholders:
        c.add("placeholder-text", "high", f"Placeholder or template text on {len(placeholders):,} pages", "'Lorem ipsum', 'coming soon' and template tokens tell users and Google the page is unfinished.", "Replace placeholder text or unpublish the page.", evidence=[f"{p.url}: {', '.join(p.placeholder_text[:2])}" for p in placeholders[:5]], affected_count=len(placeholders), pages=[p.url for p in placeholders[:100]], effort="low")

    # ===================================================== template duplicates
    first_para = defaultdict(list)
    for p in content_pages:
        if p.first_paragraph and len(p.first_paragraph.split()) >= 15:
            first_para[p.first_paragraph[:160].lower()].append(p.url)
    tpl = [u for u in first_para.values() if len(u) >= 3]
    if tpl:
        total = sum(len(u) for u in tpl)
        c.add("template-duplicate-copy", "medium", f"{total:,} pages share an identical opening paragraph ({len(tpl)} template{'s' if len(tpl) != 1 else ''})", "Swapping a city or product name inside otherwise identical copy is the doorway-page pattern Google filters.", "Write a genuinely unique opening and body for each page, or consolidate them.", evidence=[f"'{k[:80]}...' on {len(first_para[k])} pages, e.g. {first_para[k][0]}" for k in list(first_para) if len(first_para[k]) >= 3][:4], affected_count=total, pages=[u for g in tpl for u in g][:300], effort="high")

    # ============================================================ readability
    long_pages = [p for p in content_pages if p.word_count >= 300]
    scores = [(p, p.readability or flesch(p.lead_text or p.text_sample)) for p in long_pages]
    hard = [p for p, s in scores if 0 < s < 40]
    if hard and len(hard) > len(long_pages) * 0.5:
        c.add("hard-to-read", "low", f"{len(hard):,} pages read at college level or above", "Plain language gets quoted more by answer engines and keeps readers longer.", "Shorten sentences to under 20 words, replace jargon, add subheads and lists.", evidence=[f"{p.url} (Flesch {s})" for p, s in scores if 0 < s < 40][:5], affected_count=len(hard), effort="medium")
    long_sent = [p for p in long_pages if p.avg_sentence_length > 28]
    if long_sent and len(long_sent) > len(long_pages) * 0.4:
        c.add("long-sentences", "info", f"Average sentence over 28 words on {len(long_sent):,} pages", "Long sentences are harder to extract as self-contained answers.", "Aim for 12 to 20 words per sentence.", affected_count=len(long_sent), effort="medium")
    filler_hits = []
    for p in long_pages:
        hits = [f for f in FILLER if f in (p.text_sample + " " + p.lead_text).lower()]
        if len(hits) >= 2:
            filler_hits.append(f"{p.url}: {', '.join(hits[:3])}")
    if filler_hits and len(filler_hits) > max(2, len(long_pages) * 0.3):
        c.add("generic-ai-filler", "low", f"Generic AI-style filler phrases on {len(filler_hits):,} pages", "Phrases like 'in today's fast-paced world' signal low-effort content to readers and raters.", "Rewrite with specific claims, numbers and first-hand detail.", evidence=filler_hits[:5], affected_count=len(filler_hits), effort="medium")
    long_no_toc = [p for p in content_pages if p.word_count > 2000 and p.anchor_links < 3]
    if long_no_toc and len(long_no_toc) > 2:
        c.add("no-table-of-contents", "info", f"{len(long_no_toc):,} very long pages have no table of contents", "Jump links help readers and give Google anchor-level sitelinks.", "Add an in-page table of contents with anchor links to each H2.", evidence=[f"{p.url} ({p.word_count} words)" for p in long_no_toc[:4]], affected_count=len(long_no_toc), effort="low")

    # ================================================================ E-E-A-T
    all_urls = [p.url for p in pages] + [l for p in html_pages[:500] for l in p.internal_links]
    trust_found = {k: any(re.search(rx, u, re.I) for u in all_urls) for k, rx in TRUST_PAGES.items()}
    missing_trust = [k for k, v in trust_found.items() if not v]
    if "about" in missing_trust:
        c.add("no-about-page", "medium", "No About page found", "About pages are a primary E-E-A-T signal: who is behind the site and why they are qualified.", "Create /about with team, credentials, history, address and photos.", effort="medium")
    if "contact" in missing_trust:
        c.add("no-contact-page", "medium", "No Contact page found", "Google's quality guidelines expect clear contact information for trust.", "Create /contact with address, phone, email and a form.", effort="low")
    if "privacy" in missing_trust:
        c.add("no-privacy-policy", "low", "No privacy policy link found", "Required by most privacy laws and treated as a basic trust marker.", "Add a privacy policy page and link it in the footer.", effort="low")
    if "terms" in missing_trust and btype in ("e-commerce", "SaaS / software", "finance"):
        c.add("no-terms-page", "low", "No terms of service page found", "Commercial sites are expected to publish terms; raters look for them.", "Add a terms page and link it in the footer.", effort="low")
    if not missing_trust:
        c.passed("trust-pages", "About, Contact, Privacy and Terms pages present")
    if home is not None and not home.has_tel_link and not home.has_email_link and not home.phones and not home.emails:
        c.add("no-contact-on-home", "low", "No phone or email visible on the homepage", "Visible contact details are a trust signal for raters and the first thing a local or B2B visitor looks for.", "Show a phone number (click-to-call) or email in the header or footer.", effort="low")
    if home is not None and not home.has_social_links:
        c.add("no-social-links", "low", "No social profile links on the homepage", "Linked profiles confirm the brand entity for Google and AI systems and reassure visitors the business is active.", "Link the official LinkedIn, Facebook, Instagram, YouTube or X profiles in the footer and mirror them in Organization.sameAs.", effort="low")
    else:
        if home is not None:
            c.passed("social-links", f"Social profiles linked: {', '.join(home.has_social_links[:5])}")

    article_pages = [p for p in html_pages if ptype[p.url] == "article" and p.word_count > 300]
    year = datetime.utcnow().year
    if article_pages:
        no_author = [p for p in article_pages if not p.author_signals]
        if len(no_author) > len(article_pages) * 0.5:
            c.add("no-author-bylines", "medium", f"{len(no_author):,} articles have no visible author", "Bylines with credentials are the clearest 'Experience and Expertise' signal for Google raters and AI systems. Anonymous content is discounted everywhere, not only on health and finance topics.", "Add a named author with a bio page and Person schema to every article.", evidence=[p.url for p in no_author[:5]], affected_count=len(no_author), pages=[p.url for p in no_author[:300]], effort="medium")
        else:
            c.passed("author-bylines", "Articles carry author signals")
        no_date = [p for p in article_pages if not p.date_signals]
        if len(no_date) > len(article_pages) * 0.5:
            c.add("no-dates", "low", f"{len(no_date):,} articles have no visible publish or update date", "Freshness is weighed for many queries; undated content looks stale to AI engines.", "Show published and updated dates and mirror them in Article schema.", evidence=[p.url for p in no_date[:5]], affected_count=len(no_date), effort="low")
        stale = []
        for p in article_pages:
            ys = [int(m) for d in p.date_signals for m in re.findall(r"\b(20[0-3]\d)\b", d)]
            if ys and max(ys) <= year - 3:
                stale.append((p, max(ys)))
        if stale and len(stale) > max(3, len(article_pages) * 0.3):
            c.add("stale-content", "low", f"{len(stale):,} articles were last dated {year - 3} or earlier", "Old dates on evergreen topics lose clicks and AI citations to fresher competitors.", "Review, update and re-date the articles that still matter; prune or consolidate the rest.", evidence=[f"{p.url} ({y})" for p, y in stale[:5]], affected_count=len(stale), effort="medium")
        citing = [p for p in article_pages if p.authority_ext_links or p.external_link_count >= 2]
        if len(citing) < len(article_pages) * 0.2:
            c.add("no-outbound-citations", "low", f"{len(article_pages) - len(citing):,} of {len(article_pages):,} articles cite no external sources", "Linking to authoritative sources raises trust and is one of the strongest measured lifts for AI citation.", "Cite 2 to 3 primary sources per article (studies, official data, standards).", affected_count=len(article_pages), effort="low")
        else:
            c.passed("outbound-citations", "Articles link to external sources")
        no_media = [p for p in article_pages if p.images_total <= 1 and not p.has_video]
        if no_media and len(no_media) > len(article_pages) * 0.5:
            c.add("articles-no-media", "info", f"{len(no_media):,} articles have no images or video", "Pages with original images, charts or video are selected far more often by AI and keep readers longer.", "Add at least one original image, chart or short video per article.", affected_count=len(no_media), effort="medium")
    if business.get("ymyl"):
        reviewed = [p for p in article_pages if p.has_reviewer_line]
        if article_pages and not reviewed:
            c.add("ymyl-no-reviewer", "medium", "YMYL content shows no expert review line", "Health, finance and legal pages are held to the highest E-E-A-T bar; an expert reviewer with credentials is expected.", "Add 'Reviewed by [Name, credentials]' with a date and a Person schema on every YMYL article.", affected_count=len(article_pages), effort="medium")
    if home is not None and not home.has_reviews_text and not any(p.has_reviews_text for p in html_pages[:40]):
        c.add("no-social-proof", "low", "No reviews, ratings or testimonials visible", "Visible reviews are a top trust signal for raters, buyers and AI assistants recommending businesses.", "Add a reviews or testimonials section fed from Google, Trustpilot or your own verified reviews.", effort="medium")

    # ================================================================= images
    missing_alt_total = sum(p.images_missing_alt for p in html_pages)
    img_total = sum(p.images_total for p in html_pages)
    if img_total and missing_alt_total / img_total > 0.15:
        pg = [p for p in html_pages if p.images_missing_alt]
        c.add("images-missing-alt", "medium" if missing_alt_total / img_total > 0.5 else "low", f"{missing_alt_total:,} of {img_total:,} images lack alt text", "Alt text is the only way image search, screen readers and AI models understand images.", "Write descriptive alt text for content images; leave decorative images with alt=\"\".", evidence=[f"{p.url} ({p.images_missing_alt}/{p.images_total})" for p in pg[:5]], affected_count=missing_alt_total, pages=[p.url for p in pg[:300]], effort="low")
    elif img_total:
        c.passed("images-alt", f"{img_total - missing_alt_total:,} of {img_total:,} images have alt text")
    poor_alt = sum(p.images_alt_poor for p in html_pages)
    if poor_alt > max(10, img_total * 0.1):
        c.add("images-alt-poor", "low", f"{poor_alt:,} images have filename-style or generic alt text", "Alt like 'IMG_2041.jpg' or 'image' adds nothing for search or accessibility.", "Describe what the image shows in 5 to 15 words.", affected_count=poor_alt, effort="low")
    modern = sum(p.images_modern_format for p in html_pages)
    if img_total > 20 and modern / img_total < 0.2:
        c.add("images-legacy-format", "low", f"Only {round(100 * modern / img_total)}% of images use WebP or AVIF", "Modern formats cut image weight 30 to 60 percent, which improves LCP.", "Convert JPEG/PNG to WebP (most CDNs and CMS plugins do this automatically).", affected_count=img_total - modern, effort="low")
    elif img_total > 20:
        c.passed("images-modern-format", f"{round(100 * modern / img_total)}% of images use modern formats")
    no_dims = sum(p.images_no_dims for p in html_pages)
    sampled = img_total
    if sampled > 10 and no_dims > sampled * 0.5:
        c.add("images-no-dimensions", "low", f"{round(100 * no_dims / sampled)}% of images lack width/height attributes", "Missing dimensions cause layout shift (CLS) as images load.", "Add width and height attributes or CSS aspect-ratio.", affected_count=no_dims, effort="low")
    srcset = sum(p.images_srcset for p in html_pages)
    if img_total > 20 and srcset / img_total < 0.2:
        c.add("images-no-srcset", "low", "Images are not responsive (no srcset or <picture>)", "Phones download desktop-size images, which wastes bandwidth and slows LCP.", "Serve multiple sizes with srcset/sizes or a <picture> element.", affected_count=img_total - srcset, effort="medium")
    first_lazy = [p for p in content_pages if p.first_image_lazy and p.images_total > 0]
    if first_lazy and len(first_lazy) > max(2, len(content_pages) * 0.3):
        c.add("hero-image-lazy", "medium", f"The first (hero) image is lazy-loaded on {len(first_lazy):,} pages", "Lazy-loading the largest above-the-fold image delays LCP by hundreds of milliseconds.", "Remove loading=lazy from the hero image and add fetchpriority=\"high\".", evidence=[p.url for p in first_lazy[:4]], affected_count=len(first_lazy), effort="low")
    tpl_imgs = Counter()
    for p in html_pages[:300]:
        for i in p.images:
            if not i.get("alt") and i.get("src"):
                tpl_imgs[i["src"]] += 1
    repeated = [(s, k) for s, k in tpl_imgs.most_common(5) if k >= max(5, n * 0.3)]
    if repeated:
        c.add("images-template-missing-alt", "low", "Template images (logo, icons) lack alt text on every page", "One fix in the template clears a missing-alt warning on every page at once.", "Add alt text to the header/footer image elements in the theme.", evidence=[f"{s[:90]} on {k} pages" for s, k in repeated[:3]], affected_count=sum(k for _, k in repeated), effort="low")

    # ========================================================= internal links
    few_links = [p for p in content_pages if (p.internal_link_count or len(p.internal_links)) < 5 and p.depth > 0]
    if few_links and len(few_links) > len(content_pages) * 0.3:
        c.add("weak-internal-linking", "medium", f"{len(few_links):,} pages have fewer than 5 internal links", "Internal links pass authority and help crawlers and users move between related pages.", "Add contextual links to related pages, plus breadcrumbs and related-content blocks.", evidence=[p.url for p in few_links[:5]], affected_count=len(few_links), pages=[p.url for p in few_links[:200]], effort="medium")
    low_density = [p for p in long_pages if p.word_count >= 800 and (p.internal_link_count or len(p.internal_links)) < 3 + p.word_count / 1000]
    if low_density and len(low_density) > len(long_pages) * 0.4 and len(low_density) > 3:
        c.add("low-link-density", "low", f"{len(low_density):,} long pages carry few contextual links", "Guides and articles should link to 3 to 5 related pages per 1,000 words so authority flows to money pages.", "Add in-body links to related services, products and guides.", evidence=[f"{p.url} ({p.word_count} words, {p.internal_link_count or len(p.internal_links)} links)" for p in low_density[:4]], affected_count=len(low_density), effort="medium")
    generic_anchor = Counter(a.lower() for p in html_pages[:500] for a in p.anchor_texts if a.lower() in GENERIC_ANCHORS)
    if sum(generic_anchor.values()) > max(15, n):
        c.add("generic-anchor-text", "low", f"{sum(generic_anchor.values()):,} links use generic anchor text", "Anchor text tells search engines what the target page is about; 'read more' tells them nothing.", "Use descriptive anchors that name the destination topic.", evidence=[f"'{k}' x{v}" for k, v in generic_anchor.most_common(4)], affected_count=sum(generic_anchor.values()), effort="low")
    huge_nav = [p for p in html_pages if (p.internal_link_count or len(p.internal_links)) > 300]
    if huge_nav and len(huge_nav) > n * 0.5:
        c.add("mega-menu-bloat", "low", f"Pages carry {round(sum(p.internal_link_count or len(p.internal_links) for p in huge_nav) / len(huge_nav))} internal links on average", "Hundreds of navigation links per page dilute link equity and bloat the DOM.", "Trim the mega menu and footer to the pages that matter; keep deep links in hub pages.", affected_count=len(huge_nav), effort="medium")
    nofollow_int = sum(p.nofollow_internal for p in html_pages)
    if nofollow_int > max(10, n):
        c.add("nofollow-internal-links", "low", f"{nofollow_int:,} internal links carry rel=nofollow", "nofollow on internal links throws away your own link equity.", "Remove nofollow from internal links (use noindex on the target page if it should not be indexed).", affected_count=nofollow_int, effort="low")
    many_ext = [p for p in content_pages if (p.external_link_count or len(p.external_links)) > 100]
    if many_ext and len(many_ext) > 2:
        c.add("excessive-external-links", "info", f"{len(many_ext):,} pages link out more than 100 times", "Link-heavy pages look like directories and dilute each link's weight.", "Trim outbound links to the ones that help the reader.", evidence=[p.url for p in many_ext[:4]], affected_count=len(many_ext), effort="low")

    # =================================================================== AEO
    faq_pages = [p for p in html_pages if p.has_faq_section]
    q_pages = [p for p in html_pages if p.question_headings]
    service_like = [p for p in content_pages if p.depth <= 2 and p.word_count > 250 and ptype[p.url] in ("service", "product", "category", "location", "home", "other", "pricing", "article")]
    if service_like and len(q_pages) < max(1, len(service_like) * 0.2):
        c.add("aeo-no-question-headings", "medium", f"Only {len(q_pages):,} of {len(service_like):,} key pages use question-style headings", "Answer engines match user questions to H2/H3 phrased as questions followed by a direct answer.", "Add 'What is...', 'How much does...', 'How long...' sections with a 40 to 60 word direct answer under each.", affected_count=len(service_like) - len(q_pages), effort="medium")
    else:
        c.passed("aeo-question-headings", f"Question headings found on {len(q_pages):,} pages")
    if not faq_pages:
        c.add("aeo-no-faq", "medium", "No FAQ sections found on the site", "FAQs are the most-quoted format in AI answers and People Also Ask.", "Add a 4 to 8 question FAQ to key service/product pages with FAQPage schema matching the visible text.", effort="medium")
    else:
        c.passed("aeo-faq", f"FAQ content on {len(faq_pages):,} pages")
        if not any(ptype[p.url] == "faq" for p in html_pages) and len(html_pages) > 20:
            c.add("aeo-no-central-faq", "info", "No dedicated FAQ or help page", "A central FAQ page ranks for long-tail questions and feeds AI assistants a clean list of answers.", "Create /faq with the 15 to 30 questions customers actually ask, grouped by topic.", effort="medium")
    key_pages = [p for p in content_pages if p.depth <= 1 and p.word_count > 200]
    no_answer_first = [p for p in key_pages if p.first_paragraph_words > 90]
    if key_pages and len(no_answer_first) > len(key_pages) * 0.5:
        c.add("aeo-no-answer-first", "low", f"Opening paragraphs are long preambles on {len(no_answer_first):,} key pages", "AI engines quote the first concise paragraph that answers the query; long intros are skipped.", "Open each page with a 2 to 3 sentence direct answer, then expand.", evidence=[p.url for p in no_answer_first[:5]], affected_count=len(no_answer_first), effort="medium")
    definition = [p for p in key_pages if re.search(r"\b(is|are|refers to|means|provides|offers|helps)\b", " ".join(p.first_paragraph.split()[:30]), re.I)]
    if key_pages and len(definition) < len(key_pages) * 0.4:
        c.add("aeo-no-definition-opening", "low", "Key pages do not open with a definition-style sentence", "'X is a ...' sentences in the first 60 words are the passages featured snippets and AI answers lift most often.", "Start each key page with one plain sentence that defines the service, product or topic.", affected_count=len(key_pages) - len(definition), effort="low")
    no_lists = [p for p in long_pages if p.list_count == 0 and p.table_count == 0]
    if long_pages and len(no_lists) > len(long_pages) * 0.5:
        c.add("aeo-no-structured-blocks", "low", f"{len(no_lists):,} long pages have no lists or tables", "Lists, steps and tables are the easiest blocks for featured snippets and AI answers to lift.", "Convert processes to numbered steps and comparisons to tables.", affected_count=len(no_lists), effort="low")
    if btype in ("e-commerce", "SaaS / software") and not any(p.table_count for p in content_pages[:300]):
        c.add("aeo-no-comparison-tables", "info", "No comparison or specification tables found", "AI shopping and comparison answers draw heavily on structured tables (specs, plans, versus).", "Add specification tables to products and a plan comparison table to pricing.", effort="medium")

    # Citability per page
    cit = []
    for p in content_pages:
        if p.word_count < 120:
            continue
        heading = p.h1[0] if p.h1 else p.title
        block = (p.lead_text or (p.first_paragraph + "\n" + p.text_sample))[:1500]
        r = citability_block_score(block, heading)
        cit.append({"url": p.url, "score": r["score"], "parts": r["parts"]})
    cit.sort(key=lambda x: x["score"])
    avg_cit = round(sum(x["score"] for x in cit) / len(cit)) if cit else 0
    if cit and avg_cit < 45:
        c.add("low-citability", "medium", f"Average passage citability score is {avg_cit}/100", "Passages that are vague, pronoun-heavy and number-free rarely get quoted by ChatGPT, Perplexity or AI Overviews.", "Rewrite key sections as self-contained 80 to 200 word answers with a definition sentence, a number, a named entity and a source.", evidence=[f"{x['url']} ({x['score']})" for x in cit[:5]], affected_count=len([x for x in cit if x["score"] < 45]), effort="medium")
    elif cit:
        c.passed("citability", f"Average passage citability {avg_cit}/100")

    # ============================================================ social meta
    no_og = [p for p in content_pages if not p.has_og]
    if no_og and len(no_og) > len(content_pages) * 0.3:
        c.add("missing-og-tags", "low", f"{len(no_og):,} pages lack Open Graph title or image", "Shared links show no preview image or a wrong title on WhatsApp, LinkedIn, Facebook and Slack, which cuts click-through.", "Set og:title, og:description, og:image (1200x630) and og:url per page.", evidence=[p.url for p in no_og[:4]], affected_count=len(no_og), effort="low")
    else:
        c.passed("og-tags", "Open Graph tags present")
    generic_og = [p for p in html_pages if (p.og.get("title") or "").strip().lower() in ("home", "homepage") and p.url != home.url]
    if generic_og:
        c.add("og-generic", "info", f"og:title is 'Home' on {len(generic_og):,} inner pages", "Shared links from inner pages all look like the homepage.", "Use the page title as og:title.", affected_count=len(generic_og), effort="low")
    no_tw = [p for p in content_pages if not p.has_twitter_card]
    if no_tw and len(no_tw) > len(content_pages) * 0.5 and home is not None and not home.has_twitter_card:
        c.add("missing-twitter-card", "info", "No Twitter/X card meta tags", "Without twitter:card the X preview falls back to a bare link.", "Add twitter:card=summary_large_image (og tags cover the rest).", effort="low")

    out = c.to_dict()
    out["avg_word_count"] = avg_words
    out["avg_citability"] = avg_cit
    out["citability_lowest"] = cit[:8]
    out["citability_highest"] = cit[-8:][::-1]
    cit_by_url = {x["url"]: x["score"] for x in cit}
    long_para_pages = [p for p in content_pages if p.long_paragraphs >= 2]
    out["long_paragraph_pages"] = len(long_para_pages)
    out["trust_pages"] = trust_found
    out["article_pages"] = len(article_pages)
    out["faq_pages"] = len(faq_pages)
    out["question_heading_pages"] = len(q_pages)
    out["images_total"] = img_total
    out["images_missing_alt"] = missing_alt_total
    out["page_types"] = dict(Counter(ptype.values()).most_common())
    out["readability_avg"] = round(sum(s for _, s in scores if s) / max(len([s for _, s in scores if s]), 1), 1) if scores else None
    out["page_table"] = [
        {"url": p.url, "type": ptype[p.url], "title": p.title[:90], "title_len": len(p.title), "desc_len": len(p.meta_description), "h1": (p.h1[0][:80] if p.h1 else ""), "h1_count": len(p.h1), "words": p.word_count, "internal_links": p.internal_link_count or len(p.internal_links), "images": p.images_total, "missing_alt": p.images_missing_alt, "schema": p.schema_types[:4], "canonical_ok": (not p.canonical) or p.canonical.rstrip('/') == p.final_url.rstrip('/'), "noindex": "noindex" in (p.meta_robots or '').lower(), "status": p.status, "ms": p.elapsed_ms, "depth": (p.depth if p.depth < ORPHAN_DEPTH else "orphan"), "citability": cit_by_url.get(p.url), "readability": p.readability or None, "first_paragraph": p.first_paragraph[:220], "description": p.meta_description[:200]}
        for p in sorted(html_pages, key=lambda x: (x.depth, x.url))[:400]
    ]
    return out
