"""Technical SEO checks: crawlability, indexability, URLs, redirects, security, mobile, duplicates."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from urllib.parse import urlparse

from .crawl import Crawler, normalize
from .fetch import Fetcher
from .findings import Collector


def _html_pages(crawler: Crawler):
    return [p for p in crawler.pages.values() if p.status == 200 and "text/html" in (p.content_type or "")]


def analyze_technical(crawler: Crawler, fetcher: Fetcher, check_links: int = 60) -> dict:
    c = Collector("technical")
    pages = list(crawler.pages.values())
    html_pages = _html_pages(crawler)
    origin = crawler.origin
    home = crawler.pages.get(crawler.start_url)

    # ---------------------------------------------------------------- robots
    if crawler.robots_status == 200:
        txt = crawler.robots_txt
        disallow_all = re.search(r"user-agent:\s*\*\s*(?:\n[^\n]*)*?\ndisallow:\s*/\s*$", txt, re.I | re.M)
        if re.search(r"^disallow:\s*/\s*$", txt, re.I | re.M) and re.search(r"^user-agent:\s*\*", txt, re.I | re.M):
            # Confirm the wildcard group actually contains Disallow: /
            groups = re.split(r"(?im)^user-agent:", txt)
            for g in groups:
                if g.strip().lower().startswith("*") and re.search(r"^disallow:\s*/\s*$", g, re.I | re.M) and not re.search(r"^allow:\s*/\s*$", g, re.I | re.M):
                    c.add("robots-disallow-all", "critical", "robots.txt blocks all crawlers from the whole site", "Disallow: / under User-agent: * tells Google and every other bot to stay out. Nothing can rank.", "Remove the Disallow: / line, or scope it to the paths that should stay private.", evidence=[g.strip()[:200]], effort="low")
                    break
        if not re.search(r"^sitemap:", txt, re.I | re.M):
            c.add("robots-no-sitemap", "low", "robots.txt does not declare a Sitemap", "A Sitemap: line helps every crawler find the XML sitemap without guessing.", "Add `Sitemap: {origin}/sitemap.xml` to robots.txt.".replace("{origin}", origin), effort="low")
        else:
            c.passed("robots-no-sitemap", "robots.txt declares a sitemap")
        if re.search(r"^disallow:\s*/?\*?\.(css|js)", txt, re.I | re.M) or re.search(r"^disallow:\s*/wp-includes", txt, re.I | re.M):
            c.add("robots-blocks-assets", "medium", "robots.txt blocks CSS or JS resources", "Googlebot needs CSS and JS to render pages. Blocking them can hide content and hurt mobile evaluation.", "Remove the Disallow rules for CSS/JS paths.", effort="low")
        c.passed("robots-exists", "robots.txt is present and readable")
    elif crawler.robots_status == 0:
        c.add("robots-unreachable", "medium", "robots.txt could not be fetched", "Crawlers treat an unreachable robots.txt (server error) as 'do not crawl'.", "Make /robots.txt return 200 with valid rules, or 404 if you want no rules.", evidence=[f"status {crawler.robots_status}"], effort="low")
    else:
        c.add("robots-missing", "low", "No robots.txt file", "Not fatal (crawlers assume everything is allowed) but you lose sitemap discovery and crawl hints.", "Create /robots.txt with a Sitemap: line and any paths to exclude.", effort="low")

    if crawler.blocked_by_robots:
        c.add("robots-blocks-internal-links", "medium", "Internal links point to robots-blocked URLs", "Link equity flows into pages crawlers cannot fetch.", "Either unblock these paths or stop linking to them from indexable pages.", evidence=crawler.blocked_by_robots[:8], affected_count=len(crawler.blocked_by_robots))

    # --------------------------------------------------------------- sitemap
    sm = crawler.sitemap_index
    if sm.get("total_urls", 0) == 0 and not any(i.get("is_index") for i in sm.get("fetched", {}).values()):
        c.add("sitemap-missing", "high", "No XML sitemap found", "Without a sitemap, crawlers depend entirely on internal links. New and deep pages get discovered late or never.", "Generate an XML sitemap (most CMSs have a plugin or built-in option), serve it at /sitemap.xml and reference it in robots.txt.", evidence=[f"tried: {', '.join(list(sm.get('fetched', {}).keys())[:4])}"], effort="low")
    else:
        c.passed("sitemap-exists", f"XML sitemap found with {sm.get('total_urls', 0)} URLs")
        bad = [u for u, i in sm.get("fetched", {}).items() if i["status"] not in (200, 0) and u in sm.get("children", [])]
        if bad:
            c.add("sitemap-child-errors", "medium", "Sitemap index references files that do not load", "Broken child sitemaps mean whole sections are invisible to the sitemap pipeline.", "Fix or remove the broken child sitemap entries.", evidence=bad[:6])
        locs = getattr(crawler, "_sitemap_locs", [])
        if locs:
            off_host = [l for l in locs[:500] if urlparse(l).netloc and urlparse(l).netloc.lower().replace("www.", "") != crawler.host]
            if off_host:
                c.add("sitemap-foreign-urls", "medium", "Sitemap lists URLs on a different host", "Google ignores sitemap URLs that do not match the sitemap's host (www vs non-www, http vs https).", "Regenerate the sitemap with the canonical host and protocol.", evidence=off_host[:5], affected_count=len(off_host))
            http_in = [l for l in locs[:500] if l.startswith("http://")]
            if http_in and origin.startswith("https://"):
                c.add("sitemap-http-urls", "medium", "Sitemap contains http:// URLs on an https site", "Each entry redirects, which wastes crawl budget and sends mixed canonical signals.", "Regenerate the sitemap with https URLs.", evidence=http_in[:5], affected_count=len(http_in))
            lastmod_total = sum(i.get("lastmod_count", 0) for i in sm.get("fetched", {}).values())
            if lastmod_total == 0:
                c.add("sitemap-no-lastmod", "low", "Sitemap has no <lastmod> dates", "Google uses lastmod (when accurate) to prioritise recrawling changed pages.", "Emit a truthful <lastmod> per URL.", effort="low")
            # Sitemap URLs that were crawled and did not return 200
            crawled_sm = [l for l in locs if normalize(l) in crawler.pages]
            non200 = [l for l in crawled_sm if crawler.pages[normalize(l)].status != 200]
            if non200:
                c.add("sitemap-non-200", "high", "Sitemap includes URLs that return errors or redirects", "Sitemaps should only list final, 200-status, indexable URLs. Errors here erode Google's trust in the whole file.", "Remove redirected and broken URLs from the sitemap.", evidence=[f"{l} -> {crawler.pages[normalize(l)].status}" for l in non200[:6]], affected_count=len(non200))
            noindexed = [l for l in crawled_sm if "noindex" in (crawler.pages[normalize(l)].meta_robots or "").lower()]
            if noindexed:
                c.add("sitemap-noindex", "medium", "Sitemap lists noindex pages", "Contradictory signals: the sitemap asks for indexing while the page refuses it.", "Drop noindex URLs from the sitemap.", evidence=noindexed[:5], affected_count=len(noindexed))
            # Orphans: in sitemap but never linked internally
            linked = set(crawler.inlinks.keys())
            orphan = [l for l in locs[:1000] if normalize(l) not in linked and normalize(l) != crawler.start_url]
            crawl_complete = crawler.summary()["queue_remaining"] == 0
            if locs and orphan and (crawl_complete or len(crawler.pages) >= 150):
                ratio = len(orphan) / max(len(locs[:1000]), 1)
                if ratio > 0.3:
                    c.add("orphan-pages", "medium", "Many sitemap URLs received no internal links in the crawl", "Pages with no inbound internal links rank poorly and get crawled rarely, even when listed in the sitemap.", "Link these pages from relevant hub pages, navigation or related-content blocks.", evidence=orphan[:6], affected_count=len(orphan), effort="medium")
            elif locs and len(locs) > len(crawler.pages) * 3:
                c.add("sitemap-larger-than-crawl", "info", f"Sitemap lists {len(locs)} URLs but only {len(crawler.pages)} pages were crawled", "Site-wide findings below are based on a sample. Raise --max-pages for full coverage of orphan and duplicate checks.", "Re-run with a higher page cap when a full inventory is needed.", effort="low")

    # ------------------------------------------------------- https + redirects
    if origin.startswith("http://"):
        c.add("no-https", "critical", "Site is served over HTTP, not HTTPS", "HTTPS is a ranking signal and browsers mark HTTP pages as not secure.", "Install a TLS certificate and 301 every http:// URL to https://.", effort="medium")
    else:
        c.passed("https", "Site is served over HTTPS")
        http_variant = fetcher.get(origin.replace("https://", "http://", 1), allow_redirects=True)
        if http_variant.error is None and not http_variant.final_url.startswith("https://"):
            c.add("http-not-redirected", "high", "http:// version does not redirect to https://", "Two live versions split signals and expose users to the insecure copy.", "Add a server-level 301 from http to https.", evidence=[f"{http_variant.url} -> {http_variant.status} {http_variant.final_url}"], effort="low")
        host = urlparse(origin).netloc
        alt = origin.replace("://www.", "://", 1) if host.startswith("www.") else origin.replace("://", "://www.", 1)
        alt_resp = fetcher.get(alt, allow_redirects=True)
        if alt_resp.error is None and alt_resp.status == 200 and urlparse(alt_resp.final_url).netloc.lower() != host.lower():
            c.add("www-duplicate", "high", "www and non-www both serve the site without redirecting", "Duplicate hostnames create duplicate pages and split links.", "Pick one hostname and 301 the other to it.", evidence=[f"{alt} -> {alt_resp.status} {alt_resp.final_url}"], effort="low")
        else:
            c.passed("www-redirect", "www / non-www resolves to one hostname")

    chains = [p for p in pages if len(p.redirect_chain) >= 2]
    if chains:
        c.add("redirect-chains", "medium", "Redirect chains (2+ hops) found", "Each hop leaks a little PageRank and slows users; Google stops following after a few hops.", "Point every link and redirect straight at the final URL.", evidence=[f"{p.url} ({len(p.redirect_chain)} hops)" for p in chains[:6]], affected_count=len(chains), effort="low")
    internal_redirects = [p for p in pages if p.redirect_chain and p.depth > 0]
    if len(internal_redirects) > max(3, len(pages) * 0.1):
        c.add("internal-links-redirect", "medium", "Many internal links point to redirecting URLs", "Internal links should hit the final URL directly; redirects waste crawl budget.", "Update internal links to the destination URLs.", evidence=[f"{p.url} -> {p.final_url}" for p in internal_redirects[:6]], affected_count=len(internal_redirects), effort="low")

    # ------------------------------------------------------------ status codes
    broken = [p for p in pages if p.status in (404, 410) or p.status >= 500 or (p.status == 0 and p.depth > 0)]
    if broken:
        sev = "high" if len(broken) > 3 else "medium"
        c.add("broken-internal-urls", sev, "Internal links lead to broken pages", "Dead ends waste crawl budget and frustrate users; Google reads many 404s as a quality signal.", "Fix or 301 the broken URLs and update the linking pages.", evidence=[f"{p.url} -> {p.status or p.error}" for p in broken[:8]], affected_count=len(broken), pages=[p.url for p in broken])
    else:
        c.passed("broken-internal-urls", "No broken internal URLs in the crawl")

    # Soft 404 detection: a 200 page whose title/body screams not found
    soft = [p for p in html_pages if re.search(r"\b(page not found|404|not found|nothing found)\b", (p.title or "") + " " + (p.h1[0] if p.h1 else ""), re.I) and p.word_count < 300]
    if soft:
        c.add("soft-404", "high", "Soft 404 pages return status 200", "Pages that say 'not found' but return 200 get indexed as thin junk and dilute the site.", "Return a real 404 or 410 status for missing content.", evidence=[f"{p.url} title='{p.title[:60]}'" for p in soft[:6]], affected_count=len(soft), pages=[p.url for p in soft])

    # Real 404 behaviour
    probe = fetcher.get(f"{origin}/ranksherlock-404-probe-{abs(hash(origin)) % 99999}")
    if probe.error is None and probe.status == 200:
        c.add("404-returns-200", "high", "Missing URLs return 200 instead of 404", "Any typo URL becomes an indexable duplicate page. Crawlers cannot tell real pages from junk.", "Configure the server or CMS to return 404 (or 410) for unknown paths.", evidence=[f"{probe.url} -> 200"], effort="low")
    elif probe.error is None:
        c.passed("404-handling", f"Unknown URLs return {probe.status}")

    # ------------------------------------------------------------ indexability
    noindex_pages = [p for p in html_pages if re.search(r"noindex", (p.meta_robots or "") + " " + (p.x_robots_tag or ""), re.I)]
    if home and re.search(r"noindex", (home.meta_robots or "") + " " + (home.x_robots_tag or ""), re.I):
        is_home = urlparse(home.final_url).path in ("", "/")
        if is_home:
            c.add("homepage-noindex", "critical", "Homepage is set to noindex", "The homepage cannot appear in search results at all.", "Remove the noindex directive from the homepage.", evidence=[home.meta_robots or home.x_robots_tag], effort="low")
        else:
            c.add("page-noindex", "high", "The audited page is set to noindex", "This page cannot appear in search results.", "Remove noindex if the page should rank.", evidence=[home.url, home.meta_robots or home.x_robots_tag], effort="low")
    if noindex_pages and len(noindex_pages) > len(html_pages) * 0.25:
        c.add("many-noindex", "medium", "A large share of crawled pages are noindex", "Possibly intentional, but worth confirming these are not money pages.", "Review the list and remove noindex from pages that should rank.", evidence=[p.url for p in noindex_pages[:6]], affected_count=len(noindex_pages), pages=[p.url for p in noindex_pages])

    # --------------------------------------------------------------- canonical
    no_canon = [p for p in html_pages if not p.canonical and "noindex" not in (p.meta_robots or "")]
    if no_canon:
        sev = "high" if len(no_canon) > len(html_pages) * 0.5 else "medium"
        c.add("missing-canonical", sev, "Pages without a canonical tag", "Without rel=canonical, parameter and duplicate versions compete with the original.", "Add a self-referencing canonical on every indexable page.", evidence=[p.url for p in no_canon[:6]], affected_count=len(no_canon), pages=[p.url for p in no_canon], effort="low")
    else:
        c.passed("canonical-present", "All indexable pages declare a canonical")
    multi = [p for p in html_pages if p.canonical_count > 1]
    if multi:
        c.add("multiple-canonicals", "high", "Pages declare more than one canonical", "Google ignores conflicting canonicals, so you lose control of the indexed URL.", "Keep exactly one canonical link per page (often a theme and an SEO plugin both print one).", evidence=[p.url for p in multi[:6]], affected_count=len(multi), pages=[p.url for p in multi], effort="low")
    canon_elsewhere = [p for p in html_pages if p.canonical and normalize(p.canonical) != normalize(p.final_url) and p.depth > 0]
    if canon_elsewhere and len(canon_elsewhere) > max(2, len(html_pages) * 0.15):
        # Distinguish "everything canonicals to homepage" (a known theme bug) from legitimate pagination canonicals
        to_home = [p for p in canon_elsewhere if normalize(p.canonical) == crawler.start_url]
        if len(to_home) >= 3:
            c.add("canonical-to-homepage", "critical", "Multiple pages canonicalise to the homepage", "Google is told these pages are copies of the homepage, so they drop out of the index.", "Make each page's canonical self-referencing. Usually a theme or plugin bug.", evidence=[p.url for p in to_home[:6]], affected_count=len(to_home), pages=[p.url for p in to_home], effort="low")
        else:
            c.add("canonical-points-elsewhere", "medium", "Many pages canonicalise to a different URL", "Fine for true duplicates; harmful if these are unique pages.", "Verify each non-self canonical is intentional.", evidence=[f"{p.url} -> {p.canonical}" for p in canon_elsewhere[:6]], affected_count=len(canon_elsewhere), pages=[p.url for p in canon_elsewhere])
    http_canon = [p for p in html_pages if p.canonical.startswith("http://") and origin.startswith("https://")]
    if http_canon:
        c.add("canonical-http", "high", "Canonical tags point to http:// URLs", "The canonical contradicts the secure URL and can push the HTTP copy into the index.", "Update canonicals to https.", evidence=[p.url for p in http_canon[:5]], affected_count=len(http_canon), effort="low")

    # -------------------------------------------------------------- duplicates
    titles = Counter(p.title for p in html_pages if p.title)
    dup_titles = {t: n for t, n in titles.items() if n > 1}
    if dup_titles:
        c.add("duplicate-titles", "medium" if len(dup_titles) < 5 else "high", "Duplicate title tags across pages", "Identical titles make pages compete and tell Google they may be duplicates.", "Write a unique, descriptive title for each page.", evidence=[f"'{t[:60]}' on {n} pages" for t, n in list(dup_titles.items())[:6]], affected_count=sum(dup_titles.values()))
    descs = Counter(p.meta_description for p in html_pages if p.meta_description)
    dup_desc = {t: n for t, n in descs.items() if n > 1}
    if dup_desc:
        c.add("duplicate-descriptions", "low", "Duplicate meta descriptions", "Google rewrites duplicates, so you lose control of the snippet.", "Write unique descriptions for key pages.", evidence=[f"'{t[:60]}' on {n} pages" for t, n in list(dup_desc.items())[:5]], affected_count=sum(dup_desc.values()), effort="low")
    h1s = Counter(p.h1[0] for p in html_pages if p.h1)
    dup_h1 = {t: n for t, n in h1s.items() if n > 2}
    if dup_h1:
        c.add("duplicate-h1", "medium", "Same H1 reused across many pages", "Often a theme bug that prints the site name as H1 everywhere, erasing each page's topic signal.", "Make the H1 the page's own headline.", evidence=[f"'{t[:60]}' on {n} pages" for t, n in list(dup_h1.items())[:4]], affected_count=sum(dup_h1.values()))

    # ----------------------------------------------------------------- URLs
    ugly = [p.url for p in html_pages if re.search(r"[A-Z]|%20|_{1}|\?.*=|&", urlparse(p.url).path + ("?" + urlparse(p.url).query if urlparse(p.url).query else ""))]
    if len(ugly) > len(html_pages) * 0.3 and ugly:
        c.add("url-hygiene", "low", "URLs use uppercase, underscores, spaces or query parameters", "Clean lowercase hyphenated URLs are easier to share and avoid case-duplicate issues.", "Prefer lowercase, hyphen-separated, parameter-free URLs for content pages.", evidence=ugly[:6], affected_count=len(ugly))
    deep = [p for p in html_pages if p.depth >= 4]
    if deep and len(deep) > len(html_pages) * 0.2:
        c.add("deep-pages", "low", "Many pages are 4+ clicks from the homepage", "Depth correlates with crawl frequency and perceived importance.", "Flatten the architecture with hub pages, footer links or breadcrumbs.", evidence=[p.url for p in deep[:5]], affected_count=len(deep))

    # ------------------------------------------------------------- security
    if home:
        h = home.headers
        if origin.startswith("https://") and not h.get("strict-transport-security"):
            c.add("no-hsts", "low", "No Strict-Transport-Security header", "HSTS stops protocol-downgrade attacks and removes the http redirect hop for repeat visitors.", "Send `Strict-Transport-Security: max-age=31536000; includeSubDomains`.", effort="low")
        else:
            c.passed("hsts", "HSTS header present")
        if not h.get("x-content-type-options"):
            c.add("no-xcto", "low", "Missing X-Content-Type-Options header", "Prevents MIME sniffing. A basic trust signal in security scanners.", "Send `X-Content-Type-Options: nosniff`.", effort="low")
        if not h.get("x-frame-options") and "frame-ancestors" not in (h.get("content-security-policy") or ""):
            c.add("no-xfo", "low", "No clickjacking protection (X-Frame-Options / CSP frame-ancestors)", "Lets other sites embed your pages in iframes.", "Send `X-Frame-Options: SAMEORIGIN` or a CSP frame-ancestors directive.", effort="low")
        if not h.get("referrer-policy"):
            c.add("no-referrer-policy", "info", "No Referrer-Policy header", "Minor hygiene; controls what URL data leaks to third parties.", "Send `Referrer-Policy: strict-origin-when-cross-origin`.", effort="low")
        if h.get("x-powered-by"):
            c.add("x-powered-by", "info", "Server reveals its stack via X-Powered-By", "Discloses software versions to attackers.", "Remove the X-Powered-By header.", evidence=[h.get("x-powered-by")], effort="low")
        if not h.get("content-encoding") and home.size_bytes > 50_000:
            c.add("no-compression", "medium", "HTML is served without gzip/brotli compression", "Uncompressed HTML is 3 to 5x larger, which slows every page load.", "Enable gzip or brotli at the server or CDN.", evidence=[f"homepage {home.size_bytes // 1024} KB, no content-encoding"], effort="low")
    mixed = [p for p in html_pages if p.mixed_content]
    if mixed:
        c.add("mixed-content", "medium", "HTTPS pages load http:// resources", "Browsers block or warn on mixed content; it breaks the padlock.", "Update resource URLs to https.", evidence=[p.url for p in mixed[:5]], affected_count=len(mixed), pages=[p.url for p in mixed], effort="low")

    # ---------------------------------------------------------------- mobile
    no_viewport = [p for p in html_pages if not p.viewport]
    if no_viewport:
        sev = "critical" if home in no_viewport else "high"
        c.add("no-viewport", sev, "Pages without a viewport meta tag", "Without it, mobile browsers render the desktop layout zoomed out. Google indexes mobile-first.", "Add `<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">`.", evidence=[p.url for p in no_viewport[:5]], affected_count=len(no_viewport), pages=[p.url for p in no_viewport], effort="low")
    else:
        c.passed("viewport", "Viewport meta present on all pages")
    no_lang = [p for p in html_pages if not p.lang]
    if no_lang and len(no_lang) > len(html_pages) * 0.5:
        c.add("no-html-lang", "low", "Missing lang attribute on <html>", "Helps search engines and screen readers identify the language.", "Add `<html lang=\"en\">` (or the right code).", affected_count=len(no_lang), effort="low")

    # --------------------------------------------------------- JS rendering
    thin_html = [p for p in html_pages if p.word_count < 80 and p.external_scripts >= 3 and p.depth <= 2]
    if thin_html and len(thin_html) >= max(2, len(html_pages) * 0.3):
        c.add("csr-empty-html", "high", "Pages ship almost no text in the raw HTML (client-side rendering)", "Google can render JS but AI crawlers and many bots cannot. Content that only appears after JS runs is invisible to them.", "Server-render or pre-render primary content so it is present in the initial HTML.", evidence=[f"{p.url} ({p.word_count} words, {p.external_scripts} scripts)" for p in thin_html[:5]], affected_count=len(thin_html), pages=[p.url for p in thin_html], effort="high")
    else:
        c.passed("ssr-content", "Primary content is present in the raw HTML")

    # ------------------------------------------------------- hreflang sanity
    hl_pages = [p for p in html_pages if p.hreflang]
    if hl_pages:
        bad_codes = []
        missing_self = []
        missing_xdefault = []
        for p in hl_pages:
            codes = [h["lang"] for h in p.hreflang]
            for code in codes:
                if not re.match(r"^(x-default|[a-z]{2,3}(-[A-Za-z]{2,4})?)$", code):
                    bad_codes.append(f"{p.url}: {code}")
            if not any(normalize(h["href"]) == normalize(p.final_url) for h in p.hreflang):
                missing_self.append(p.url)
            if "x-default" not in codes:
                missing_xdefault.append(p.url)
        if bad_codes:
            c.add("hreflang-invalid-codes", "medium", "Invalid hreflang language or region codes", "Google ignores malformed hreflang entries entirely.", "Use ISO 639-1 language and ISO 3166-1 Alpha-2 region codes (en, en-GB, x-default).", evidence=bad_codes[:5])
        if missing_self:
            c.add("hreflang-no-self", "medium", "hreflang sets omit the self-referencing entry", "Each page must list itself or the whole set is invalid.", "Include the page's own URL in its hreflang cluster.", evidence=missing_self[:5], affected_count=len(missing_self))
        if missing_xdefault:
            c.add("hreflang-no-xdefault", "low", "hreflang sets have no x-default", "x-default catches users whose language is not covered.", "Add an x-default alternate.", affected_count=len(missing_xdefault), effort="low")
        c.passed("hreflang-present", f"hreflang annotations found on {len(hl_pages)} pages")

    # ------------------------------------------------------ external links
    checked = 0
    dead_ext = []
    ext_seen = set()
    for p in html_pages:
        for l in p.external_links:
            href = l["href"]
            if href in ext_seen or checked >= check_links or not href.startswith("http"):
                continue
            ext_seen.add(href)
            status, err = fetcher.head_status(href)
            checked += 1
            if status in (404, 410) or status >= 500 or (status == 0 and err not in ("SSLError", "ConnectionError", "ReadTimeout", "ConnectTimeout", "Timeout")):
                dead_ext.append(f"{href} ({status or err}) on {p.url}")
    if dead_ext:
        c.add("broken-external-links", "low", "Outbound links to dead pages", "Broken outbound links read as neglect and hurt user trust.", "Fix or remove the dead links.", evidence=dead_ext[:6], affected_count=len(dead_ext), effort="low")
    elif checked:
        c.passed("external-links", f"Checked {checked} outbound links, none broken")

    # --------------------------------------------------------- page weight
    heavy = [p for p in html_pages if p.size_bytes > 1_500_000]
    if heavy:
        c.add("heavy-html", "medium", "HTML documents over 1.5 MB", "Giant HTML (inline SVG, base64 images, inlined CSS) delays first paint and can be truncated by crawlers.", "Move inline assets to files, remove unused inline CSS, lazy-load below-the-fold content.", evidence=[f"{p.url} ({p.size_bytes // 1024} KB)" for p in heavy[:5]], affected_count=len(heavy))
    slow = [p for p in html_pages if p.elapsed_ms > 2500]
    if slow and len(slow) >= max(2, len(html_pages) * 0.2):
        c.add("slow-ttfb", "medium", "Server response over 2.5 s on many pages", "Slow HTML responses cap how fast any page can load and reduce crawl rate.", "Add page caching, upgrade hosting or put a CDN in front.", evidence=[f"{p.url} ({p.elapsed_ms} ms)" for p in slow[:5]], affected_count=len(slow))

    out = c.to_dict()
    out["platform"] = Counter(p.detected_platform for p in html_pages if p.detected_platform).most_common(1)[0][0] if any(p.detected_platform for p in html_pages) else ""
    out["status_breakdown"] = dict(Counter(p.status for p in pages))
    out["indexable_pages"] = len([p for p in html_pages if "noindex" not in (p.meta_robots or "").lower()])
    out["noindex_pages"] = len(noindex_pages)
    out["avg_response_ms"] = round(sum(p.elapsed_ms for p in html_pages) / max(len(html_pages), 1))
    return out
