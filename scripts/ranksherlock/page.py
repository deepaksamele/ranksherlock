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

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["headers"] = {k: v for k, v in self.headers.items() if k in KEEP_HEADERS}
        return d


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
        headers=headers,
    )
    page.x_robots_tag = headers.get("x-robots-tag", "")
    if not html:
        return page

    soup = BeautifulSoup(html, PARSER)
    page.detected_platform = detect_platform(html, headers)

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
        text = _clean(tag.get_text(" "))
        level = int(tag.name[1])
        page.heading_order.append(level)
        if level == 1:
            page.h1.append(text)
        elif level == 2:
            page.h2.append(text)
        elif level == 3:
            page.h3.append(text)
        if QUESTION_RE.match(text) or text.endswith("?"):
            page.question_headings.append(text)

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
    for el in soup.find_all(attrs={"itemtype": True}):
        t = el.get("itemtype", "")
        if isinstance(t, list):
            t = " ".join(t)
        page.microdata_types.append(t.split("/")[-1])
    page.microdata_types = sorted(set(page.microdata_types))
    types_present = {str(x.get("@type")) for x in page.json_ld}
    page.has_breadcrumb_markup = "BreadcrumbList" in types_present or "BreadcrumbList" in page.microdata_types or bool(soup.find(attrs={"aria-label": re.compile("breadcrumb", re.I)}))

    # Resource counts (before stripping)
    scripts = soup.find_all("script")
    page.scripts_count = len(scripts)
    page.external_scripts = sum(1 for s in scripts if s.get("src"))
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
    text = _clean(body.get_text(" "))
    words = WORD_RE.findall(text)
    page.word_count = len(words)
    page.text_sample = text[:600]
    page.text_to_html_ratio = round(len(text) / max(len(html), 1), 3)
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text) if len(s.split()) > 2]
    if sentences:
        page.avg_sentence_length = round(sum(len(s.split()) for s in sentences) / len(sentences), 1)
    paragraphs = [_clean(p.get_text(" ")) for p in body.find_all("p")]
    paragraphs = [p for p in paragraphs if len(p.split()) >= 8]
    page.paragraph_count = len(paragraphs)
    if paragraphs:
        page.first_paragraph = paragraphs[0][:400]
    page.list_count = len(body.find_all(["ul", "ol"]))
    page.table_count = len(body.find_all("table"))
    page.stat_mentions = len(STAT_RE.findall(text))
    page.phones = list(dict.fromkeys(_clean(m) for m in PHONE_RE.findall(text) if 9 <= len(re.sub(r"\D", "", m)) <= 15))[:5]
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
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
            continue
        absolute, _ = urldefrag(urljoin(final_url, href))
        rel = " ".join(a.get("rel", [])).lower()
        anchor = _clean(a.get_text(" "))[:80]
        if _same_site(absolute, final_url):
            if absolute not in seen_internal:
                seen_internal[absolute] = 0
                page.anchor_texts.append(anchor)
            seen_internal[absolute] += 1
            if "nofollow" in rel:
                page.nofollow_internal += 1
        else:
            page.external_links.append({"href": absolute, "rel": rel, "anchor": anchor})
    page.internal_links = list(seen_internal.keys())
    page.external_links = page.external_links[:200]

    # Images
    imgs = soup.find_all("img")
    page.images_total = len(imgs)
    for img in imgs:
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src") or ""
        src = urljoin(final_url, src) if src else ""
        alt = img.get("alt")
        loading = (img.get("loading") or "").lower()
        if alt is None or not _clean(alt):
            page.images_missing_alt += 1
        if loading == "lazy":
            page.images_lazy += 1
        if re.search(r"\.(webp|avif)(\?|$)", src, re.I):
            page.images_modern_format += 1
        if len(page.images) < 40:
            page.images.append({"src": src[:300], "alt": (_clean(alt) if alt else "")[:120], "loading": loading, "width": img.get("width"), "height": img.get("height")})
        if final_url.startswith("https://") and src.startswith("http://"):
            page.mixed_content += 1

    return page
