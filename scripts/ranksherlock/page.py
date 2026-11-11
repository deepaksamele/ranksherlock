"""Parse one HTML document into the evidence RankSherlock needs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Optional
from urllib.parse import urljoin, urlparse, urldefrag

from bs4 import BeautifulSoup

try:
    import lxml  # noqa: F401

    PARSER = "lxml"
except ImportError:  # pragma: no cover
    PARSER = "html.parser"

WORD_RE = re.compile(r"[A-Za-zÀ-ɏऀ-ॿ0-9']+")
QUESTION_RE = re.compile(r"^(who|what|when|where|why|how|which|can|does|do|is|are|should|will)\b", re.I)
PHONE_RE = re.compile(r"(\+?\d[\d\s().-]{7,}\d)")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
STREET_RE = re.compile(
    r"\b\d{1,6},?\s+[A-Z][A-Za-z0-9.'-]*(\s+[A-Z][A-Za-z0-9.'-]*){0,4}\s+(?i:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Way|Court|Ct|Place|Pl|Highway|Hwy|Parkway|Pkwy|Suite|Ste|Marg|Nagar|Colony|Sector|Phase|Square|Plaza|Tower|Complex)\b"
    r"|\b(?i:Plot|Shop|Office|Flat|House|Unit|Suite)\s*(?i:No\.?|#)\s*\d+"
    r"|\b[A-Z][a-z]+,\s+[A-Z]{2}\s+\d{5}(-\d{4})?\b"
    r"|\b[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}\b"
    r"|(?i:Madhya Pradesh|Maharashtra|Delhi|Karnataka|Gujarat|Rajasthan|Tamil Nadu|Uttar Pradesh|West Bengal|Punjab|Haryana|Kerala|Telangana|India)[\s,.-]{1,4}\d{3}\s?\d{3}\b"
    r"|\b[A-Z][a-z]+[\s,-]{1,3}\d{3}\s?\d{3}\b(?=[\s,.]{0,3}(?i:India|M\.?P\.?|Madhya|Maharashtra|Gujarat|Rajasthan|Karnataka))"
)
LOCAL_LANG_RE = re.compile(r"\b(near me|serving|service area|our location|visit us|directions|opening hours|open hours|hours of operation|call us|free estimate|free quote|licensed|insured|locally owned|family owned|same.day|emergency service)\b", re.I)
AUTHORITY_RE = re.compile(r"\.(gov|edu|ac\.[a-z]{2}|gov\.[a-z]{2})\b|wikipedia\.org|nih\.gov|who\.int|sebi\.gov|rbi\.org|europa\.eu|nature\.com|sciencedirect|statista|pewresearch|\.org/", re.I)
CHROME_CLASS_RE = re.compile(r"(^|[\s_-])(navbar|site-header|site-footer|mega-?menu|cookie|breadcrumbs?|sidebar|widget-area|off-?canvas|drawer|modal|popup|newsletter|share-buttons?)([\s_-]|$)", re.I)
STAT_RE = re.compile(r"\b\d[\d,.]*\s?(%|percent|million|billion|crore|lakh|k\b|x\b|\$|₹|€|£)|\b(19|20)\d{2}\b", re.I)


@dataclass
class PageData:
    url: str
    final_url: str
    status: int
    elapsed_ms: int
    size_bytes: int
    content_type: str
    depth: int
    error: Optional[str] = None
    redirect_chain: list = field(default_factory=list)
    title: str = ""
    meta_description: str = ""
    meta_robots: str = ""
    x_robots_tag: str = ""
    canonical: str = ""
    canonical_count: int = 0
    lang: str = ""
    charset: str = ""
    viewport: str = ""
    h1: list = field(default_factory=list)
    h2: list = field(default_factory=list)
    h3: list = field(default_factory=list)
    heading_order: list = field(default_factory=list)
    word_count: int = 0
    text_sample: str = ""
    paragraph_count: int = 0
    avg_sentence_length: float = 0.0
    list_count: int = 0
    table_count: int = 0
    question_headings: list = field(default_factory=list)
    first_paragraph: str = ""
    stat_mentions: int = 0
    internal_links: list = field(default_factory=list)
    external_links: list = field(default_factory=list)
    nofollow_internal: int = 0
    anchor_texts: list = field(default_factory=list)
    images: list = field(default_factory=list)
    images_total: int = 0
    images_missing_alt: int = 0
    images_lazy: int = 0
    images_modern_format: int = 0
    json_ld: list = field(default_factory=list)
    json_ld_errors: list = field(default_factory=list)
    microdata_types: list = field(default_factory=list)
    og: dict = field(default_factory=dict)
    twitter: dict = field(default_factory=dict)
    hreflang: list = field(default_factory=list)
    scripts_count: int = 0
    external_scripts: int = 0
    inline_css_bytes: int = 0
    stylesheets: int = 0
    iframes: int = 0
    forms: int = 0
    has_noscript_content: bool = False
    text_to_html_ratio: float = 0.0
    phones: list = field(default_factory=list)
    emails: list = field(default_factory=list)
    has_address_tag: bool = False
    has_map_embed: bool = False
    author_signals: list = field(default_factory=list)
    date_signals: list = field(default_factory=list)
    mixed_content: int = 0
    has_breadcrumb_markup: bool = False
    has_faq_section: bool = False
    skip_links: bool = False
    headers: dict = field(default_factory=dict)
    detected_platform: str = ""

    internal_link_count: int = 0
    external_link_count: int = 0
    html_lang_mismatch: bool = False
    has_search_form: bool = False
    has_video: bool = False
    has_tel_link: bool = False
    has_email_link: bool = False
    has_social_links: list = field(default_factory=list)
    has_analytics: list = field(default_factory=list)
    has_cookie_banner: bool = False
    has_favicon: bool = False
    has_amp: bool = False
    meta_keywords: str = ""
    generator: str = ""
    render_hint: str = ""
    word_count_sample_hash: str = ""
    legal_pages_linked: list = field(default_factory=list)
    unsafe_targets: int = 0
    empty_links: int = 0
    h1_in_header_only: bool = False
    headings_total: int = 0
    anchor_links: int = 0  # in-page #links (table of contents)
    first_image_lazy: bool = False
    images_srcset: int = 0
    images_fetchpriority: int = 0
    images_decoding_async: int = 0
    images_alt_poor: int = 0  # alt like IMG_1234, "image", filename
    images_alt_long: int = 0
    image_srcs: list = field(default_factory=list)
    blocking_scripts: int = 0  # <head> scripts without async/defer/module
    third_party_script_hosts: list = field(default_factory=list)
    dom_nodes: int = 0
    unlabeled_inputs: int = 0
    inputs_total: int = 0
    meta_refresh: str = ""
    zoom_locked: bool = False
    has_og: bool = False
    has_twitter_card: bool = False
    placeholder_text: list = field(default_factory=list)
    body_hash: str = ""
    preload_hints: int = 0
    font_display_swap: bool = False
    has_hours_text: bool = False
    has_price_text: bool = False
    has_add_to_cart: bool = False
    has_reviews_text: bool = False
    year_mentions: list = field(default_factory=list)
    schema_types: list = field(default_factory=list)
    full_word_count: int = 0
    has_street_address: bool = False
    has_local_language: bool = False
    has_reviewer_line: bool = False
    has_payment_trust: bool = False
    biz_terms: list = field(default_factory=list)
    faq_schema_questions: int = 0
    faq_schema_hidden: int = 0
    images_no_dims: int = 0
    authority_ext_links: int = 0
    first_paragraph_words: int = 0
    lead_paragraph_words: list = field(default_factory=list)
    lead_text: str = ""
    long_paragraphs: int = 0
    readability: float = 0.0

    def slim(self) -> None:
        """Drop bulky per-page lists once the crawler has consumed them (keeps a 50,000-page crawl in memory)."""
        self.internal_links = self.internal_links[:15]
        self.anchor_texts = self.anchor_texts[:15]
        self.external_links = self.external_links[:10]
        self.images = self.images[:4]
        self.image_srcs = []
        self.h2 = self.h2[:12]
        self.h3 = self.h3[:8]
        self.heading_order = self.heading_order[:60]
        self.text_sample = self.text_sample[:500]
        self.lead_text = self.lead_text[:900]
        self.first_paragraph = self.first_paragraph[:500]
        self.json_ld = self.json_ld[:12]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["headers"] = {k: v for k, v in self.headers.items() if k in KEEP_HEADERS}
        return d


def page_from_dict(d: dict) -> "PageData":
    known = {f for f in PageData.__dataclass_fields__}
    return PageData(**{k: v for k, v in d.items() if k in known})


KEEP_HEADERS = {
    "content-type",
    "content-length",
    "content-encoding",
    "cache-control",
    "server",
    "x-powered-by",
    "strict-transport-security",
    "content-security-policy",
    "x-content-type-options",
    "x-frame-options",
    "referrer-policy",
    "permissions-policy",
    "x-robots-tag",
    "link",
    "vary",
    "cf-ray",
    "x-cache",
    "age",
    "last-modified",
    "etag",
}


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _phones(text: str) -> list:
    """Phone numbers only: skip registration ids, dates, prices and long numeric codes."""
    out = []
    for m in re.finditer(r"(?<![A-Za-z0-9.,/-])(\+?\(?\d[\d\s().-]{7,17}\d)(?![A-Za-z0-9])", text):
        raw = _clean(m.group(1))
        digits = re.sub(r"\D", "", raw)
        if not (10 <= len(digits) <= 13 or (raw.startswith("+") and 8 <= len(digits) <= 15)):
            continue
        if digits.startswith("000") or len(set(digits)) <= 2:
            continue
        if re.match(r"^(19|20)\d{2}[\s./-]\d{1,2}[\s./-]\d{1,2}", raw) or re.search(r"\d{1,2}[./-]\d{1,2}[./-](19|20)\d{2}", raw):
            continue  # dates
        if "." in raw and not re.search(r"\d{3}\.\d{3}\.\d{4}", raw):
            continue  # decimals and prices
        if not raw.startswith("+") and not re.search(r"[\s().-]", raw) and len(digits) != 10 and not digits.startswith("1800"):
            continue  # unformatted long numbers are ids, not phones
        if raw not in out:
            out.append(raw)
        if len(out) >= 5:
            break
    return out


def _same_site(a: str, b: str) -> bool:
    ha, hb = urlparse(a).netloc.lower(), urlparse(b).netloc.lower()
    strip = lambda h: h[4:] if h.startswith("www.") else h
    return strip(ha) == strip(hb)


def detect_platform(html: str, headers: dict) -> str:
    h = html[:200000].lower()
    checks = [
        ("wp-content", "WordPress"),
        ("shopify", "Shopify"),
        ("wix.com", "Wix"),
        ("squarespace", "Squarespace"),
        ("webflow", "Webflow"),
        ("_next/static", "Next.js"),
        ("nuxt", "Nuxt"),
        ("gatsby", "Gatsby"),
        ("drupal", "Drupal"),
        ("joomla", "Joomla"),
        ("magento", "Magento"),
        ("bigcommerce", "BigCommerce"),
        ("hubspot", "HubSpot CMS"),
        ("elementor", "WordPress (Elementor)"),
        ("duda", "Duda"),
        ("godaddy", "GoDaddy Builder"),
        ("framer", "Framer"),
    ]
    found = [name for key, name in checks if key in h]
    if "WordPress (Elementor)" in found:
        return "WordPress (Elementor)"
    if found:
        return found[0]
    powered = (headers.get("x-powered-by") or "").lower()
    if "express" in powered:
        return "Node/Express"
    if "php" in powered:
        return "PHP"
    return ""


def parse_page(url: str, final_url: str, status: int, html: str, headers: dict, elapsed_ms: int, size_bytes: int, depth: int, redirect_chain: list) -> PageData:
    page = PageData(
        url=url,
        final_url=final_url,
        status=status,
        elapsed_ms=elapsed_ms,
        size_bytes=size_bytes,
        content_type=headers.get("content-type", ""),
        depth=depth,
        redirect_chain=redirect_chain,
        headers={k: v for k, v in headers.items() if k in KEEP_HEADERS},
    )
    page.x_robots_tag = headers.get("x-robots-tag", "")
    if not html:
        return page

    soup = BeautifulSoup(html, PARSER)
    page.detected_platform = detect_platform(html, headers)
    low = html[:300000].lower()
    for key, name in (("googletagmanager.com/gtm.js", "Google Tag Manager"), ("gtag/js", "GA4 (gtag)"), ("google-analytics.com/analytics.js", "Universal Analytics (legacy)"), ("connect.facebook.net", "Meta Pixel"), ("clarity.ms", "Microsoft Clarity"), ("hotjar.com", "Hotjar"), ("static.hsappstatic.net", "HubSpot"), ("plausible.io", "Plausible"), ("matomo", "Matomo"), ("bat.bing.com", "Microsoft Ads UET"), ("linkedin.com/insight", "LinkedIn Insight"), ("tiktok.com/i18n/pixel", "TikTok Pixel")):
        if key in low:
            page.has_analytics.append(name)
    page.has_cookie_banner = bool(re.search(r"cookie(consent|banner|notice|bot)|cc-window|onetrust|cookieyes|iubenda|gdpr", low))
    page.has_amp = bool(re.search(r"<html[^>]*\s(amp|⚡)[\s>]", low[:2000])) or 'rel="amphtml"' in low
    page.has_favicon = bool(soup.find("link", rel=lambda v: v and "icon" in v))  # bs4 calls this once per rel token
    page.has_video = bool(soup.find("video")) or bool(re.search(r"youtube\.com/embed|player\.vimeo\.com|wistia", low))
    page.has_search_form = bool(soup.find("input", attrs={"type": "search"})) or bool(soup.find("form", attrs={"role": "search"}))

    html_tag = soup.find("html")
    if html_tag:
        page.lang = _clean(html_tag.get("lang", ""))

    if soup.title and soup.title.string:
        page.title = _clean(soup.title.string)
    elif soup.title:
        page.title = _clean(soup.title.get_text())

    for meta in soup.find_all("meta"):
        name = (meta.get("name") or "").lower()
        prop = (meta.get("property") or "").lower()
        content = _clean(meta.get("content", ""))
        if name == "description" and not page.meta_description:
            page.meta_description = content
        elif name == "robots":
            page.meta_robots = content
        elif name == "keywords":
            page.meta_keywords = content[:200]
        elif name == "generator":
            page.generator = content[:80]
        elif name == "viewport":
            page.viewport = content
        elif meta.get("charset"):
            page.charset = meta.get("charset")
        elif prop.startswith("og:"):
            page.og[prop[3:]] = content
        elif name.startswith("twitter:"):
            page.twitter[name[8:]] = content
        elif name in ("author", "article:author"):
            page.author_signals.append(f"meta:{content}")
        elif name in ("article:published_time", "article:modified_time", "date", "dc.date") or prop in ("article:published_time", "article:modified_time"):
            page.date_signals.append(f"{name or prop}:{content}")

    canonicals = soup.find_all("link", rel=lambda v: v and "canonical" in v)
    page.canonical_count = len(canonicals)
    if canonicals:
        page.canonical = urljoin(final_url, canonicals[0].get("href", ""))

    for link in soup.find_all("link", rel=lambda v: v and "alternate" in v):
        if link.get("hreflang"):
            page.hreflang.append({"lang": link.get("hreflang"), "href": urljoin(final_url, link.get("href", ""))})

    # Headings in document order
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        text = _clean(tag.get_text(" "))[:200]
        level = int(tag.name[1])
        page.heading_order.append(level)
        page.headings_total += 1
        if level == 1:
            page.h1.append(text)
        elif level == 2 and len(page.h2) < 60:
            page.h2.append(text)
        elif level == 3 and len(page.h3) < 60:
            page.h3.append(text)
        if (QUESTION_RE.match(text) or text.endswith("?")) and len(page.question_headings) < 40:
            page.question_headings.append(text)
    page.heading_order = page.heading_order[:200]

    # Structured data (must run before scripts are stripped for text analysis)
    for s in soup.find_all("script", type=lambda t: t and "ld+json" in t.lower()):
        raw = s.string or s.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            cleaned = re.sub(r",\s*([}\]])", r"\1", raw)
            try:
                data = json.loads(cleaned)
                page.json_ld_errors.append(f"Recovered after trailing-comma fix: {exc.msg}")
            except json.JSONDecodeError:
                page.json_ld_errors.append(f"Invalid JSON-LD: {exc.msg} at char {exc.pos}")
                continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and "@graph" in item and isinstance(item["@graph"], list):
                page.json_ld.extend(x for x in item["@graph"] if isinstance(x, dict))
            elif isinstance(item, dict):
                page.json_ld.append(item)
    page.json_ld = page.json_ld[:40]
    for el in soup.find_all(attrs={"itemtype": True}):
        t = el.get("itemtype", "")
        if isinstance(t, list):
            t = " ".join(t)
        page.microdata_types.append(t.split("/")[-1])
    page.microdata_types = sorted(set(page.microdata_types))
    types_present = {str(x.get("@type")) for x in page.json_ld}
    page.has_breadcrumb_markup = "BreadcrumbList" in types_present or "BreadcrumbList" in page.microdata_types or bool(soup.find(attrs={"aria-label": re.compile("breadcrumb", re.I)}))

    _st = set()
    for x in page.json_ld:
        t = x.get("@type")
        for v in (t if isinstance(t, list) else [t]):
            if v:
                _st.add(str(v))
    page.schema_types = sorted(_st)
    page.has_og = bool(page.og.get("title")) and bool(page.og.get("image"))
    page.has_twitter_card = bool(page.twitter.get("card"))
    mr = soup.find("meta", attrs={"http-equiv": re.compile("^refresh$", re.I)})
    if mr:
        page.meta_refresh = _clean(mr.get("content", ""))[:120]
    page.zoom_locked = bool(re.search(r"user-scalable\s*=\s*(no|0)|maximum-scale\s*=\s*1(\.0)?\b", page.viewport or "", re.I))
    page.preload_hints = len(soup.find_all("link", rel=lambda v: v and ("preload" in v or "preconnect" in v)))
    page.font_display_swap = "font-display:swap" in re.sub(r"\s", "", low)
    page.dom_nodes = len(soup.find_all(True))

    # Resource counts (before stripping)
    scripts = soup.find_all("script")
    page.scripts_count = len(scripts)
    page.external_scripts = sum(1 for s in scripts if s.get("src"))
    head = soup.head
    if head:
        for s in head.find_all("script"):
            if s.get("src") and not (s.has_attr("async") or s.has_attr("defer") or (s.get("type") or "").lower() == "module"):
                page.blocking_scripts += 1
    hosts = set()
    for s in scripts:
        src = s.get("src") or ""
        if src.startswith("http"):
            h = urlparse(src).netloc.lower()
            if h and not _same_site(src, final_url):
                hosts.add(h)
    page.third_party_script_hosts = sorted(hosts)[:40]
    inputs = soup.find_all(["input", "textarea", "select"])
    labelled_for = {l.get("for") for l in soup.find_all("label") if l.get("for")}
    for inp in inputs:
        t = (inp.get("type") or "text").lower()
        if t in ("hidden", "submit", "button", "image", "reset", "checkbox", "radio"):
            continue
        page.inputs_total += 1
        if not (inp.get("id") in labelled_for or inp.get("aria-label") or inp.get("aria-labelledby") or inp.get("placeholder") or inp.get("title") or (inp.parent and inp.parent.name == "label")):
            page.unlabeled_inputs += 1
    page.stylesheets = len(soup.find_all("link", rel=lambda v: v and "stylesheet" in v))
    page.inline_css_bytes = sum(len(s.get_text()) for s in soup.find_all("style"))
    page.iframes = len(soup.find_all("iframe"))
    page.forms = len(soup.find_all("form"))
    for tag in soup.find_all(["script", "link", "iframe"]):
        src = tag.get("src") or tag.get("href") or ""
        if final_url.startswith("https://") and src.startswith("http://"):
            page.mixed_content += 1

    # Remove non-content before text analysis
    body = soup.body or soup
    for tag in body.find_all(["script", "style", "noscript", "template", "svg"]):
        if tag.name == "noscript" and _clean(tag.get_text()):
            page.has_noscript_content = True
        tag.decompose()
    # ---- Signals that need the FULL page text (header, footer and all) ----
    text = _clean(body.get_text(" "))
    low_text = text.lower()
    page.full_word_count = len(WORD_RE.findall(text))
    import hashlib

    for ph in ("lorem ipsum", "[business name]", "[city]", "[insert", "replace this text", "your text here", "dummy text", "placeholder text"):
        if ph in low_text:
            page.placeholder_text.append(ph)
    page.has_street_address = bool(STREET_RE.search(text))
    page.has_local_language = bool(LOCAL_LANG_RE.search(text))
    page.has_reviewer_line = bool(re.search(r"\b(reviewed by|medically reviewed|fact.checked by|verified by|expert review)\b", text, re.I))
    page.has_payment_trust = bool(re.search(r"\b(secure (checkout|payment)|ssl|razorpay|stripe|paypal|visa|mastercard|upi|cash on delivery|money.back)\b", text, re.I))
    try:
        from .business import TYPE_RULES

        page.biz_terms = [name for name, _u, text_rx, _n in TYPE_RULES if len(re.findall(text_rx, text, re.I)) >= 2]
    except Exception:  # pragma: no cover
        page.biz_terms = []
    # FAQPage schema questions that never appear in the visible text
    squeezed = re.sub(r"[^a-z0-9]", "", low_text)
    for item in page.json_ld:
        if "FAQPage" in str(item.get("@type")):
            qs = item.get("mainEntity") or []
            qs = qs if isinstance(qs, list) else [qs]
            page.faq_schema_questions += len(qs)
            for q in qs[:25]:
                name = re.sub(r"[^a-z0-9]", "", str((q or {}).get("name", "")).lower()) if isinstance(q, dict) else ""
                if len(name) > 12 and name[:40] not in squeezed:
                    page.faq_schema_hidden += 1
    page.has_hours_text = bool(re.search(r"\b(mon|tue|wed|thu|fri|sat|sun)[a-z]*\s*(-|to|–)\s*(mon|tue|wed|thu|fri|sat|sun)[a-z]*\b|\b\d{1,2}(:\d{2})?\s?(am|pm)\s?(-|to|–)\s?\d{1,2}(:\d{2})?\s?(am|pm)\b|opening hours|business hours|hours of operation", text, re.I))
    page.has_price_text = bool(re.search(r"(₹|\$|€|£|rs\.?|inr|usd)\s?\d[\d,]*(\.\d+)?", text, re.I))
    page.has_add_to_cart = bool(re.search(r"\b(add to (cart|bag|basket)|buy now|checkout)\b", text, re.I))
    page.has_reviews_text = bool(re.search(r"\b(\d[\d,]*\s+reviews?|customer reviews|testimonials?|rated\s+\d(\.\d)?|\d(\.\d)?\s*(/|out of)\s*5)\b", text, re.I))
    page.year_mentions = sorted({m for m in re.findall(r"\b(20[0-3]\d)\b", text)})[-6:]
    page.anchor_links = sum(1 for a in soup.find_all("a", href=True) if a["href"].startswith("#") and len(a["href"]) > 1)
    if page.full_word_count < 40 and page.scripts_count >= 3 and re.search(r'<div[^>]+id=["\'](root|app|__next|__nuxt|___gatsby)["\']', html[:60000], re.I):
        page.render_hint = "client-side rendered shell"
    page.text_to_html_ratio = round(len(text) / max(len(html), 1), 3)
    page.phones = _phones(text)
    page.emails = list(dict.fromkeys(EMAIL_RE.findall(text)))[:5]
    page.has_address_tag = bool(body.find("address"))
    page.has_map_embed = bool(body.find("iframe", src=re.compile(r"google\.com/maps|maps\.google|openstreetmap", re.I)))
    page.has_faq_section = bool(re.search(r"\b(faq|frequently asked questions)\b", text, re.I)) or len(page.question_headings) >= 3
    page.skip_links = bool(body.find("a", href=re.compile(r"^#(main|content|skip)", re.I)))

    for sel in ["[rel=author]", ".author", ".byline", "[class*=author]", "[itemprop=author]"]:
        el = body.select_one(sel)
        if el:
            name = _clean(el.get_text(" "))[:80]
            if name:
                page.author_signals.append(f"{sel}:{name}")
                break
    for el in body.find_all("time"):
        dt = el.get("datetime") or _clean(el.get_text())
        if dt:
            page.date_signals.append(f"time:{dt}")
            break

    # Links
    seen_internal: dict[str, int] = {}
    social = re.compile(r"(facebook|instagram|linkedin|twitter|x\.com|youtube|tiktok|pinterest|threads\.net|wa\.me|whatsapp)", re.I)
    legal = re.compile(r"(privacy|terms|conditions|refund|return-policy|shipping-policy|disclaimer|cookie)", re.I)
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("tel:"):
            page.has_tel_link = True
            continue
        if href.startswith("mailto:"):
            page.has_email_link = True
            continue
        if not href or href.startswith(("#", "javascript:", "data:")):
            continue
        absolute, _ = urldefrag(urljoin(final_url, href))
        rel = " ".join(a.get("rel", [])).lower()
        anchor = _clean(a.get_text(" "))[:80]
        if not anchor and not a.get("aria-label") and not a.find("img", alt=True) and not a.get("title"):
            page.empty_links += 1
        if (a.get("target") or "").lower() == "_blank" and "noopener" not in rel and "noreferrer" not in rel:
            page.unsafe_targets += 1
        if _same_site(absolute, final_url):
            if absolute not in seen_internal:
                seen_internal[absolute] = 0
                page.anchor_texts.append(anchor)
            seen_internal[absolute] += 1
            if "nofollow" in rel:
                page.nofollow_internal += 1
            if legal.search(absolute) and len(page.legal_pages_linked) < 8:
                m = legal.search(absolute).group(1).lower()
                if m not in page.legal_pages_linked:
                    page.legal_pages_linked.append(m)
        else:
            sm = social.search(absolute)
            if sm and sm.group(1).lower() not in page.has_social_links:
                page.has_social_links.append(sm.group(1).lower())
            page.external_link_count += 1
            if len(page.external_links) < 80:
                page.external_links.append({"href": absolute[:300], "rel": rel, "anchor": anchor})
    page.internal_link_count = len(seen_internal)
    page.internal_links = list(seen_internal.keys())[:400]
    page.anchor_texts = page.anchor_texts[:400]

    # Images
    imgs = soup.find_all("img")
    page.images_total = len(imgs)
    _hero_seen = False
    for idx, img in enumerate(imgs):
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src") or ""
        src = urljoin(final_url, src) if src else ""
        alt = img.get("alt")
        loading = (img.get("loading") or "").lower()
        if alt is None or not _clean(alt):
            if not ((img.get("role") or "").lower() == "presentation" or alt == ""):
                page.images_missing_alt += 1
        else:
            a = _clean(alt)
            if re.match(r"^(img|image|photo|picture|dsc|screenshot|untitled|logo)?[\s_-]*\d{2,}$", a, re.I) or re.search(r"\.(jpe?g|png|gif|webp|svg)$", a, re.I) or a.lower() in ("image", "photo", "picture", "icon", "img"):
                page.images_alt_poor += 1
            if len(a) > 125:
                page.images_alt_long += 1
        if loading == "lazy":
            page.images_lazy += 1
        # "Hero" = first sizeable content image (not a logo, icon, avatar or flag, not inside nav/header)
        if not _hero_seen:
            w = str(img.get("width") or "")
            small = w.isdigit() and int(w) < 200
            chrome_img = bool(re.search(r"logo|icon|sprite|avatar|flag|badge|favicon", (src + " " + str(alt or "")), re.I)) or bool(img.find_parent(["nav", "header", "footer"]))
            if not small and not chrome_img and src:
                _hero_seen = True
                page.first_image_lazy = loading == "lazy"
        if img.get("srcset") or (img.parent and img.parent.name == "picture"):
            page.images_srcset += 1
        if (img.get("fetchpriority") or "").lower() == "high":
            page.images_fetchpriority += 1
        if (img.get("decoding") or "").lower() == "async":
            page.images_decoding_async += 1
        if re.search(r"\.(webp|avif)(\?|$)", src, re.I) or re.search(r"format=webp|/f_auto|/_next/image|fm=webp|auto=format|\.svg(\?|$)|cdn\.shopify\.com", src, re.I):
            page.images_modern_format += 1
        if not (img.get("width") and img.get("height")) and "aspect-ratio" not in (img.get("style") or ""):
            page.images_no_dims += 1
        if src and not src.startswith("data:") and len(page.image_srcs) < 40:
            page.image_srcs.append(src[:300])
        if len(page.images) < 20:
            page.images.append({"src": src[:300], "alt": (_clean(alt) if alt else "")[:120], "loading": loading, "width": img.get("width"), "height": img.get("height")})
        if final_url.startswith("https://") and src.startswith("http://"):
            page.mixed_content += 1
    page.authority_ext_links = sum(1 for l in page.external_links if AUTHORITY_RE.search(l["href"]))

    # ---- Main-content metrics: strip site chrome (nav, header, footer, aside) AFTER links and images ----
    main = body.find("main") or body.find(attrs={"role": "main"}) or body
    try:
        for tag in main.find_all(["nav", "aside", "button", "select"]):
            tag.decompose()
        for tag in main.find_all(["header", "footer"]):
            if getattr(tag, "decomposed", False):
                continue
            if not tag.find_parent(["article", "section"]) and not tag.find("h1"):
                tag.decompose()
        for tag in main.find_all(attrs={"class": CHROME_CLASS_RE}):
            if getattr(tag, "decomposed", False):
                continue
            if tag.name not in ("body", "main", "article", "html") and not tag.find(["h1", "article", "main"]):
                tag.decompose()
    except Exception:  # pragma: no cover - never let odd markup break a crawl
        pass
    mtext = _clean(main.get_text(" "))
    if len(WORD_RE.findall(mtext)) < 30 and page.full_word_count >= 100:
        mtext = text  # chrome stripping removed the content (unusual markup): fall back to the full text
        main = body
    page.word_count = len(WORD_RE.findall(mtext))
    page.text_sample = mtext[:1200]
    squeezed_main = re.sub(r"[^a-z0-9]", "", mtext.lower())
    page.word_count_sample_hash = hashlib.sha1(squeezed_main[:3000].encode()).hexdigest()[:16]
    page.body_hash = hashlib.sha1(squeezed_main.encode()).hexdigest()[:16]
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", mtext) if len(s.split()) > 2]
    if sentences:
        page.avg_sentence_length = round(sum(len(s.split()) for s in sentences) / len(sentences), 1)
    paragraphs = [_clean(p.get_text(" ")) for p in main.find_all("p")]
    paragraphs = [p for p in paragraphs if len(p.split()) >= 8]
    page.paragraph_count = len(paragraphs)
    if paragraphs:
        page.first_paragraph = paragraphs[0][:1200]
        page.first_paragraph_words = len(paragraphs[0].split())
        page.lead_paragraph_words = [len(p.split()) for p in paragraphs[:6]]
        page.lead_text = "\n".join(paragraphs[:6])[:1800]
        page.long_paragraphs = sum(1 for p in paragraphs if len(p.split()) > 150)
    page.list_count = len(main.find_all(["ul", "ol"]))
    page.table_count = len(main.find_all("table"))
    page.stat_mentions = len(STAT_RE.findall(mtext))
    page.readability = _flesch(mtext[:6000])
    return page


def _syllables(word: str) -> int:
    word = word.lower()
    count = len(re.findall(r"[aeiouy]+", word))
    if word.endswith("e") and count > 1:
        count -= 1
    return max(count, 1)


def _flesch(text: str) -> float:
    words = re.findall(r"[A-Za-z']+", text)
    sentences = [s for s in re.split(r"[.!?]+", text) if len(s.split()) > 2]
    if len(words) < 80 or not sentences:
        return 0.0
    syl = sum(_syllables(w) for w in words)
    score = 206.835 - 1.015 * (len(words) / len(sentences)) - 84.6 * (syl / len(words))
    return round(max(0.0, min(100.0, score)), 1)
