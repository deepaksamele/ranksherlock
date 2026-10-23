"""On-page, content quality, E-E-A-T and AEO (answer readiness) checks."""

from __future__ import annotations

import re
from collections import Counter

from .findings import Collector

TRUST_PAGES = {
    "about": r"/(about|about-us|who-we-are|our-story|company|team)\b",
    "contact": r"/(contact|contact-us|get-in-touch|reach-us)\b",
    "privacy": r"/(privacy|privacy-policy)\b",
    "terms": r"/(terms|terms-of-service|terms-and-conditions|tos)\b",
}
FILLER = ["in today's fast-paced world", "in the ever-evolving", "delve", "it's important to note", "unlock the power", "game-changer", "seamlessly", "robust", "leverage", "cutting-edge", "in conclusion,", "look no further", "elevate your"]


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
    score = 0
    parts = {}
    # Answer quality (30)
    aq = 0
    if re.search(r"\b(is|are|refers to|means|defined as|consists of)\b", " ".join(words[:25]), re.I):
        aq += 12
    if re.search(r"\d", " ".join(words[:60])):
        aq += 8
    if heading.strip().endswith("?") or re.match(r"^(what|how|why|when|where|who|which)\b", heading, re.I):
        aq += 10
    parts["answer_quality"] = min(aq, 30)
    # Self-containment (25)
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
    # Structure (20)
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
    # Statistics and sourcing (15)
    sd = 0
    sd += min(len(re.findall(r"\d+(\.\d+)?\s?%", text)) * 3, 6)
    sd += min(len(re.findall(r"[$₹€£]\s?\d", text)) * 3, 5)
    if re.search(r"\b(20[12]\d)\b", text):
        sd += 2
    if re.search(r"\b(according to|study|survey|report|research|data from)\b", text, re.I):
        sd += 2
    parts["stats_sourcing"] = min(sd, 15)
    # Uniqueness (10)
    u = 0
    if re.search(r"\b(we found|our (data|research|study|analysis|experience)|in our)\b", text, re.I):
        u += 5
    if re.search(r"\b(case study|for example|e\.g\.|such as)\b", text, re.I):
        u += 3
    if re.search(r"\b(using|with)\s+[A-Z][a-z]+", text):
        u += 2
    parts["uniqueness"] = min(u, 10)
    score = sum(parts.values())
    return {"score": score, "parts": parts, "words": n}


def analyze_content(pages: list, home_url: str, origin: str) -> dict:
    c = Collector("content")
    html_pages = [p for p in pages if p.status == 200 and "text/html" in (p.content_type or "") and "noindex" not in (p.meta_robots or "").lower()]
    if not html_pages:
        c.skipped("content", "No indexable HTML pages to analyse")
        return c.to_dict()
    from urllib.parse import urlparse as _up

    home = next((p for p in html_pages if p.url == home_url), html_pages[0])
    is_home = _up(home.final_url).path in ("", "/")

    # ----------------------------------------------------------- titles
    no_title = [p for p in html_pages if not p.title]
    if no_title:
        c.add("missing-title", "high", "Pages without a <title>", "The title is the strongest on-page ranking signal and the headline in search results.", "Write a unique 50-60 character title with the primary keyword first.", evidence=[p.url for p in no_title[:6]], affected_count=len(no_title), pages=[p.url for p in no_title], effort="low")
    long_t = [p for p in html_pages if len(p.title) > 65]
    short_t = [p for p in html_pages if 0 < len(p.title) < 25]
    if long_t and len(long_t) > len(html_pages) * 0.3:
        c.add("long-titles", "low", "Titles over 65 characters get truncated", "Truncated titles lose the brand or keyword in the SERP.", "Trim to 50-60 characters, keyword first, brand last.", evidence=[f"{p.url} ({len(p.title)} chars)" for p in long_t[:5]], affected_count=len(long_t), effort="low")
    if short_t and len(short_t) > len(html_pages) * 0.3:
        c.add("short-titles", "low", "Very short titles waste SERP space", "Short titles miss secondary keywords and context.", "Expand to 50-60 characters with a benefit or qualifier.", evidence=[f"{p.url}: '{p.title}'" for p in short_t[:5]], affected_count=len(short_t), effort="low")
    brand_only = [p for p in html_pages if is_home and p.title and home.title and p.title.strip().lower() == home.title.strip().lower() and p.url != home.url]
    if brand_only:
        c.add("title-same-as-home", "medium", "Inner pages reuse the homepage title", "The site name alone tells Google nothing about the page topic.", "Give each page its own topical title.", evidence=[p.url for p in brand_only[:6]], affected_count=len(brand_only), pages=[p.url for p in brand_only], effort="low")

    # ----------------------------------------------------- descriptions
    no_desc = [p for p in html_pages if not p.meta_description]
    if no_desc:
        sev = "medium" if len(no_desc) > len(html_pages) * 0.3 else "low"
        c.add("missing-description", sev, "Pages without a meta description", "Google writes its own snippet, usually worse, which lowers click-through rate.", "Write a 140-160 character description with the keyword and a reason to click.", evidence=[p.url for p in no_desc[:6]], affected_count=len(no_desc), pages=[p.url for p in no_desc], effort="low")
    long_d = [p for p in html_pages if len(p.meta_description) > 170]
    if long_d and len(long_d) > len(html_pages) * 0.3:
        c.add("long-descriptions", "info", "Meta descriptions over 170 characters", "They get cut off in results.", "Keep to 140-160 characters.", affected_count=len(long_d), effort="low")

    # ------------------------------------------------------------- H1s
    no_h1 = [p for p in html_pages if not p.h1]
    multi_h1 = [p for p in html_pages if len(p.h1) > 1]
    if no_h1:
        sev = "high" if len(no_h1) > len(html_pages) * 0.3 else "medium"
        c.add("missing-h1", sev, "Pages without an H1", "The H1 states the page topic for users, crawlers and answer engines.", "Add exactly one H1 that matches search intent.", evidence=[p.url for p in no_h1[:6]], affected_count=len(no_h1), pages=[p.url for p in no_h1], effort="low")
    else:
        c.passed("h1-present", "Every page has an H1")
    if multi_h1 and len(multi_h1) > len(html_pages) * 0.2:
        c.add("multiple-h1", "low", "Pages with more than one H1", "Multiple H1s dilute the topic signal (common with logo or slider H1s).", "Keep one H1; demote the rest to H2 or a div.", evidence=[f"{p.url} ({len(p.h1)} H1s)" for p in multi_h1[:5]], affected_count=len(multi_h1), effort="low")
    skipped_levels = [p for p in html_pages if any(b - a > 1 for a, b in zip(p.heading_order, p.heading_order[1:]) if b > a)]
    if skipped_levels and len(skipped_levels) > len(html_pages) * 0.4:
        c.add("heading-hierarchy", "low", "Heading levels skip (H1 to H3, H2 to H4)", "A clean outline helps extraction of sections by answer engines and screen readers.", "Nest headings in order without skipping levels.", affected_count=len(skipped_levels), effort="low")
    empty_h = [p for p in html_pages if any(h == "" for h in p.h1 + p.h2)]
    if empty_h:
        c.add("empty-headings", "low", "Empty heading tags", "Empty H1/H2 are usually icon or image wrappers and waste the strongest structural tags.", "Remove empty headings or put real text in them.", evidence=[p.url for p in empty_h[:5]], affected_count=len(empty_h), effort="low")

    # ------------------------------------------------------------ thin
    thin = [p for p in html_pages if p.word_count < 150 and p.depth > 0]
    if thin and len(thin) > max(2, len(html_pages) * 0.2):
        c.add("thin-content", "medium" if len(thin) < len(html_pages) * 0.5 else "high", "Thin pages with under 150 words", "Thin pages rarely rank and can drag down site-wide quality assessment.", "Expand with genuinely useful content, merge into a stronger page, or noindex.", evidence=[f"{p.url} ({p.word_count} words)" for p in thin[:6]], affected_count=len(thin), pages=[p.url for p in thin], effort="high")
    avg_words = round(sum(p.word_count for p in html_pages) / len(html_pages))
    low_ratio = [p for p in html_pages if p.text_to_html_ratio < 0.05 and p.word_count < 400]
    if low_ratio and len(low_ratio) > len(html_pages) * 0.4:
        c.add("low-text-ratio", "low", "Very low text-to-HTML ratio", "Pages are mostly markup and scripts; little for crawlers to index.", "Reduce bloat (inline SVG, builder wrappers) and add substantive copy.", affected_count=len(low_ratio), effort="medium")

    # ----------------------------------------------------- readability
    long_pages = [p for p in html_pages if p.word_count >= 300]
    scores = [(p, flesch(p.text_sample + " " + p.first_paragraph)) for p in long_pages]
    hard = [p for p, s in scores if 0 < s < 40]
    if hard and len(hard) > len(long_pages) * 0.5:
        c.add("hard-to-read", "low", "Content reads at college level or above", "Plain language gets quoted more by answer engines and keeps readers longer.", "Shorten sentences to under 20 words, replace jargon, add subheads and lists.", evidence=[f"{p.url} (Flesch {s})" for p, s in scores if 0 < s < 40][:5], affected_count=len(hard), effort="medium")
    long_sent = [p for p in long_pages if p.avg_sentence_length > 28]
    if long_sent and len(long_sent) > len(long_pages) * 0.4:
        c.add("long-sentences", "info", "Average sentence length over 28 words", "Long sentences are harder to extract as self-contained answers.", "Aim for 12 to 20 words per sentence.", affected_count=len(long_sent), effort="medium")
    filler_hits = []
    for p in long_pages:
        hits = [f for f in FILLER if f in (p.text_sample + p.first_paragraph).lower()]
        if len(hits) >= 2:
            filler_hits.append(f"{p.url}: {', '.join(hits[:3])}")
    if filler_hits and len(filler_hits) > max(2, len(long_pages) * 0.3):
        c.add("generic-ai-filler", "low", "Generic AI-style filler phrases detected", "Phrases like 'in today's fast-paced world' signal low-effort content to readers and raters.", "Rewrite with specific claims, numbers and first-hand detail.", evidence=filler_hits[:5], affected_count=len(filler_hits), effort="medium")

    # ---------------------------------------------------------- E-E-A-T
    all_urls = [p.url for p in pages] + [l for p in html_pages for l in p.internal_links]
    trust_found = {k: any(re.search(rx, u, re.I) for u in all_urls) for k, rx in TRUST_PAGES.items()}
    missing_trust = [k for k, v in trust_found.items() if not v]
    if "about" in missing_trust:
        c.add("no-about-page", "medium", "No About page found", "About pages are a primary E-E-A-T signal: who is behind the site and why they are qualified.", "Create /about with team, credentials, history, address and photos.", effort="medium")
    if "contact" in missing_trust:
        c.add("no-contact-page", "medium", "No Contact page found", "Google's quality guidelines expect clear contact information for trust.", "Create /contact with address, phone, email and a form.", effort="low")
    if "privacy" in missing_trust:
        c.add("no-privacy-policy", "low", "No privacy policy link found", "Required by most privacy laws and treated as a basic trust marker.", "Add a privacy policy page and link it in the footer.", effort="low")
    if not missing_trust:
        c.passed("trust-pages", "About, Contact, Privacy and Terms pages present")

    article_pages = [p for p in html_pages if p.word_count > 500 and (re.search(r"/(blog|news|article|post|guide|learn|resources?|insights?)/", p.url, re.I) or p.date_signals)]
    if article_pages:
        no_author = [p for p in article_pages if not p.author_signals]
        if len(no_author) > len(article_pages) * 0.5:
            c.add("no-author-bylines", "medium", "Articles without a visible author", "Bylines with credentials are the clearest 'Experience and Expertise' signal for Google raters and AI systems.", "Add a named author with a bio page and Person schema to every article.", evidence=[p.url for p in no_author[:5]], affected_count=len(no_author), pages=[p.url for p in no_author], effort="medium")
        else:
            c.passed("author-bylines", "Articles carry author signals")
        no_date = [p for p in article_pages if not p.date_signals]
        if len(no_date) > len(article_pages) * 0.5:
            c.add("no-dates", "low", "Articles without visible publish/update dates", "Freshness is weighed for many queries; undated content looks stale to AI engines.", "Show published and updated dates and mirror them in Article schema.", evidence=[p.url for p in no_date[:5]], affected_count=len(no_date), effort="low")

    ext_auth = sum(1 for p in article_pages for l in p.external_links if re.search(r"\.(gov|edu|org)\b|wikipedia|nih\.gov|who\.int", l["href"]))
    if article_pages and ext_auth == 0:
        c.add("no-outbound-citations", "low", "Articles cite no external sources", "Linking to authoritative sources raises trust and is one of the strongest measured lifts for AI citation.", "Cite 2 to 3 primary sources per article (studies, official data, standards).", affected_count=len(article_pages), effort="low")

    # ---------------------------------------------------------- Images
    missing_alt_total = sum(p.images_missing_alt for p in html_pages)
    img_total = sum(p.images_total for p in html_pages)
    if img_total and missing_alt_total / img_total > 0.2:
        pg = [p for p in html_pages if p.images_missing_alt]
        c.add("images-missing-alt", "medium" if missing_alt_total / img_total > 0.5 else "low", f"{missing_alt_total} of {img_total} images lack alt text", "Alt text is the only way image search, screen readers and AI models understand images.", "Write descriptive alt text for content images; leave decorative images with alt=\"\".", evidence=[f"{p.url} ({p.images_missing_alt}/{p.images_total})" for p in pg[:5]], affected_count=missing_alt_total, pages=[p.url for p in pg], effort="low")
    elif img_total:
        c.passed("images-alt", f"{img_total - missing_alt_total} of {img_total} images have alt text")
    modern = sum(p.images_modern_format for p in html_pages)
    if img_total > 20 and modern / img_total < 0.2:
        c.add("images-legacy-format", "low", "Few images use WebP or AVIF", "Modern formats cut image weight 30 to 60 percent, which improves LCP.", "Convert JPEG/PNG to WebP (most CDNs and CMS plugins do this automatically).", affected_count=img_total - modern, effort="low")
    no_dims = sum(1 for p in html_pages for i in p.images if not (i.get("width") and i.get("height")))
    if img_total > 10 and no_dims > img_total * 0.5:
        c.add("images-no-dimensions", "low", "Images without width/height attributes", "Missing dimensions cause layout shift (CLS) as images load.", "Add width and height attributes or CSS aspect-ratio.", affected_count=no_dims, effort="low")

    # ------------------------------------------------------- Internal links
    few_links = [p for p in html_pages if len(p.internal_links) < 5 and p.depth > 0]
    if few_links and len(few_links) > len(html_pages) * 0.3:
        c.add("weak-internal-linking", "medium", "Pages with fewer than 5 internal links", "Internal links pass authority and help crawlers and users move between related pages.", "Add contextual links to related pages, plus breadcrumbs and related-content blocks.", evidence=[p.url for p in few_links[:5]], affected_count=len(few_links), effort="medium")
    generic_anchor = Counter(a.lower() for p in html_pages for a in p.anchor_texts if a.lower() in ("click here", "read more", "learn more", "here", "more", "link"))
    if sum(generic_anchor.values()) > 15:
        c.add("generic-anchor-text", "low", "Generic anchor text (click here, read more)", "Anchor text tells search engines what the target page is about.", "Use descriptive anchors that name the destination topic.", evidence=[f"'{k}' x{v}" for k, v in generic_anchor.most_common(4)], affected_count=sum(generic_anchor.values()), effort="low")

    # -------------------------------------------------------------- AEO
    faq_pages = [p for p in html_pages if p.has_faq_section]
    q_pages = [p for p in html_pages if p.question_headings]
    service_like = [p for p in html_pages if p.depth <= 2 and p.word_count > 250]
    if service_like and len(q_pages) < max(1, len(service_like) * 0.2):
        c.add("aeo-no-question-headings", "medium", "Almost no question-style headings", "Answer engines match user questions to H2/H3 phrased as questions followed by a direct answer.", "Add 'What is...', 'How much does...', 'How long...' sections with a 40 to 60 word direct answer under each.", affected_count=len(service_like) - len(q_pages), effort="medium")
    else:
        c.passed("aeo-question-headings", f"Question headings found on {len(q_pages)} pages")
    if not faq_pages:
        c.add("aeo-no-faq", "medium", "No FAQ sections found on the site", "FAQs are the most-quoted format in AI answers and People Also Ask.", "Add a 4 to 8 question FAQ to key service/product pages with FAQPage schema matching the visible text.", effort="medium")
    else:
        c.passed("aeo-faq", f"FAQ content on {len(faq_pages)} pages")
    # Answer-first: first paragraph should be a direct definition/answer on key pages
    key_pages = [p for p in html_pages if p.depth <= 1 and p.word_count > 200]
    no_answer_first = [p for p in key_pages if p.first_paragraph and len(p.first_paragraph.split()) > 90]
    if key_pages and len(no_answer_first) > len(key_pages) * 0.5:
        c.add("aeo-no-answer-first", "low", "Opening paragraphs are long preambles", "AI engines quote the first concise paragraph that answers the query; long intros are skipped.", "Open each page with a 2 to 3 sentence direct answer, then expand.", evidence=[p.url for p in no_answer_first[:5]], affected_count=len(no_answer_first), effort="medium")
    no_lists = [p for p in long_pages if p.list_count == 0 and p.table_count == 0]
    if long_pages and len(no_lists) > len(long_pages) * 0.5:
        c.add("aeo-no-structured-blocks", "low", "Long pages with no lists or tables", "Lists, steps and tables are the easiest blocks for featured snippets and AI answers to lift.", "Convert processes to numbered steps and comparisons to tables.", affected_count=len(no_lists), effort="low")

    # Citability per page (deterministic)
    cit = []
    for p in html_pages:
        if p.word_count < 120:
            continue
        heading = p.h1[0] if p.h1 else p.title
        block = (p.first_paragraph + "\n" + p.text_sample)[:1500]
        r = citability_block_score(block, heading)
        cit.append({"url": p.url, "score": r["score"], "parts": r["parts"]})
    cit.sort(key=lambda x: x["score"])
    avg_cit = round(sum(x["score"] for x in cit) / len(cit)) if cit else 0
    if cit and avg_cit < 45:
        c.add("low-citability", "medium", f"Average passage citability score is {avg_cit}/100", "Passages that are vague, pronoun-heavy and number-free rarely get quoted by ChatGPT, Perplexity or AI Overviews.", "Rewrite key sections as self-contained 80 to 200 word answers with a definition sentence, a number, a named entity and a source.", evidence=[f"{x['url']} ({x['score']})" for x in cit[:5]], affected_count=len([x for x in cit if x["score"] < 45]), effort="medium")

    out = c.to_dict()
    out["avg_word_count"] = avg_words
    out["avg_citability"] = avg_cit
    out["citability_lowest"] = cit[:5]
    out["citability_highest"] = cit[-5:][::-1]
    out["trust_pages"] = trust_found
    out["article_pages"] = len(article_pages)
    out["faq_pages"] = len(faq_pages)
    out["question_heading_pages"] = len(q_pages)
    out["images_total"] = img_total
    out["images_missing_alt"] = missing_alt_total
    out["page_table"] = [
        {"url": p.url, "title": p.title[:90], "title_len": len(p.title), "desc_len": len(p.meta_description), "h1": (p.h1[0][:80] if p.h1 else ""), "h1_count": len(p.h1), "words": p.word_count, "internal_links": len(p.internal_links), "images": p.images_total, "missing_alt": p.images_missing_alt, "schema": sorted({str(i.get('@type')) for i in p.json_ld})[:4], "canonical_ok": (not p.canonical) or p.canonical.rstrip('/') == p.final_url.rstrip('/'), "noindex": "noindex" in (p.meta_robots or '').lower(), "status": p.status, "ms": p.elapsed_ms}
        for p in sorted(html_pages, key=lambda x: (x.depth, x.url))[:200]
    ]
    return out
