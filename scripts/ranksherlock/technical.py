"""Technical SEO checks: crawlability, indexability, sitemaps, URLs, redirects, duplicates, security,
mobile, rendering, hreflang, accessibility basics and tracking detection."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime
from urllib.parse import urlparse

from .business import page_type
from .crawl import Crawler, normalize, ORPHAN_DEPTH
from .fetch import Fetcher
from .findings import Collector

LOW_VALUE_RE = re.compile(r"/(cart|checkout|basket|my-account|account|login|log-in|signin|sign-in|register|wishlist|wp-admin|wp-login|admin|search|\?s=|\?q=|tag/|tags/|author/|feed/?$|xmlrpc|\.php\?|replytocom=|print/?$|\?print=)", re.I)


def _html_pages(crawler: Crawler):
    return [p for p in crawler.pages.values() if p.status == 200 and "text/html" in (p.content_type or "")]


def _indexable(p) -> bool:
    return "noindex" not in ((p.meta_robots or "") + " " + (p.x_robots_tag or "")).lower()


def analyze_technical(crawler: Crawler, fetcher: Fetcher, check_links: int = 80, business: dict | None = None) -> dict:
    c = Collector("technical")
    pages = list(crawler.pages.values())
    html_pages = _html_pages(crawler)
    indexable = [p for p in html_pages if _indexable(p)]
    origin = crawler.origin
    home = crawler.pages.get(crawler.start_url)
    n_html = max(len(html_pages), 1)
    business = business or {}
    btype = business.get("business_type", "")
    crawl_complete = crawler.summary(light=True)["complete"]
    single_page = len(html_pages) <= 1

    # ================================================================ robots
    if crawler.robots_status == 200:
        txt = crawler.robots_txt
        groups = re.split(r"(?im)^user-agent:", txt)
        for g in groups:
            if g.strip().lower().startswith("*") and re.search(r"^disallow:\s*/\s*$", g, re.I | re.M) and not re.search(r"^allow:\s*/\s*$", g, re.I | re.M):
                c.add("robots-disallow-all", "critical", "robots.txt blocks all crawlers from the whole site", "Disallow: / under User-agent: * tells Google and every other bot to stay out. Nothing can rank.", "Remove the Disallow: / line, or scope it to the paths that should stay private.", evidence=[g.strip()[:200]], effort="low")
                break
        else:
            c.passed("robots-disallow-all", "robots.txt does not block the whole site")
        if not re.search(r"^sitemap:", txt, re.I | re.M):
            c.add("robots-no-sitemap", "low", "robots.txt does not declare a Sitemap", "A Sitemap: line helps every crawler find the XML sitemap without guessing.", "Add `Sitemap: {origin}/sitemap.xml` to robots.txt.".replace("{origin}", origin), effort="low")
        else:
            c.passed("robots-no-sitemap", "robots.txt declares a sitemap")
        if re.search(r"^disallow:\s*/?\*?\.(css|js)", txt, re.I | re.M) or re.search(r"^disallow:\s*/wp-includes", txt, re.I | re.M) or re.search(r"^disallow:\s*/(assets|static|_next/static)\b", txt, re.I | re.M):
            c.add("robots-blocks-assets", "medium", "robots.txt blocks CSS or JS resources", "Googlebot needs CSS and JS to render pages. Blocking them can hide content and hurt mobile evaluation.", "Remove the Disallow rules for CSS/JS/static asset paths.", effort="low")
        else:
            c.passed("robots-blocks-assets", "robots.txt does not block CSS/JS assets")
        bad_lines = [l for l in txt.splitlines() if l.strip() and not l.strip().startswith("#") and ":" not in l]
        if bad_lines:
            c.add("robots-syntax", "low", "robots.txt contains lines that are not valid directives", "Malformed lines are ignored, which can silently disable the rule you intended.", "Each line must be `Directive: value`.", evidence=bad_lines[:5], effort="low")
        if btype == "e-commerce":
            if re.search(r"^disallow:\s*/(cart|checkout|account|search)", txt, re.I | re.M):
                c.passed("robots-crawl-traps", "Cart, checkout, account or search paths are kept out of crawl")
            else:
                c.add("robots-crawl-traps", "low", "Cart, checkout and search paths are not excluded in robots.txt", "Crawlers waste budget on endless filter, search and cart URLs instead of products and categories.", "Add Disallow rules for /cart, /checkout, /account and internal search result URLs (keep them noindex too).", effort="low")
        c.passed("robots-exists", "robots.txt is present and readable")
    elif crawler.robots_status == 0:
        c.add("robots-unreachable", "medium", "robots.txt could not be fetched", "Crawlers treat an unreachable robots.txt (server error) as 'do not crawl'.", "Make /robots.txt return 200 with valid rules, or 404 if you want no rules.", evidence=[f"status {crawler.robots_status}"], effort="low")
    else:
        c.add("robots-missing", "low", "No robots.txt file", "Not fatal (crawlers assume everything is allowed) but you lose sitemap discovery and crawl hints.", "Create /robots.txt with a Sitemap: line and any paths to exclude.", effort="low")

    if crawler.blocked_by_robots:
        c.add("robots-blocks-internal-links", "medium", "Internal links point to robots-blocked URLs", "Link equity flows into pages crawlers cannot fetch, and users can reach pages search engines cannot.", "Either unblock these paths or stop linking to them from indexable pages.", evidence=crawler.blocked_by_robots[:8], affected_count=len(crawler.blocked_by_robots), effort="low")

    # =============================================================== sitemap
    sm = crawler.sitemap_index
    locs = list(getattr(crawler, "_sitemap_locs", []))
    norm_locs = {normalize(l) for l in locs}
    if sm.get("total_urls", 0) == 0 and not any(i.get("is_index") for i in sm.get("fetched", {}).values()):
        c.add("sitemap-missing", "high", "No XML sitemap found", "Without a sitemap, crawlers depend entirely on internal links. New and deep pages get discovered late or never.", "Generate an XML sitemap (most CMSs have a plugin or built-in option), serve it at /sitemap.xml and reference it in robots.txt.", evidence=[f"tried: {', '.join(list(sm.get('fetched', {}).keys())[:4])}"], effort="low")
    else:
        c.passed("sitemap-exists", f"XML sitemap found with {sm.get('unique_urls', sm.get('total_urls', 0)):,} unique URLs in {sm.get('files_fetched', 0)} files")
        bad = [u for u, i in sm.get("fetched", {}).items() if i["status"] not in (200, 0) and u in sm.get("children", [])]
        if bad:
            c.add("sitemap-child-errors", "medium", "Sitemap index references files that do not load", "Broken child sitemaps mean whole sections are invisible to the sitemap pipeline.", "Fix or remove the broken child sitemap entries.", evidence=[f"{u} -> {sm['fetched'][u]['status']}" for u in bad[:6]], affected_count=len(bad))
        big_files = [(u, i["urls"]) for u, i in sm.get("fetched", {}).items() if i.get("urls", 0) > 50000 and not i.get("is_index")]
        if big_files:
            c.add("sitemap-url-limit", "critical", "A sitemap file lists more than 50,000 URLs", "The sitemap protocol caps each file at 50,000 URLs and 50 MB; Google ignores oversize files entirely.", "Split into multiple files under a sitemap index.", evidence=[f"{u}: {n:,} URLs" for u, n in big_files[:3]], effort="medium")
        huge = [(u, i["size_bytes"]) for u, i in sm.get("fetched", {}).items() if i.get("size_bytes", 0) > 50_000_000]
        if huge:
            c.add("sitemap-size-limit", "high", "A sitemap file is larger than 50 MB", "Files over the 50 MB (uncompressed) limit are rejected.", "Split the sitemap or gzip it and keep each under the limit.", evidence=[f"{u}: {s // 1_000_000} MB" for u, s in huge[:3]])
        if sm.get("duplicate_entries", 0) > max(5, sm.get("total_urls", 0) * 0.05):
            c.add("sitemap-duplicate-entries", "low", f"{sm['duplicate_entries']:,} duplicate URL entries across sitemap files", "Duplicates inflate the file and signal a sloppy generator; Google dedupes but wastes fetch time.", "List each URL once, in one sitemap file.", effort="low")
        if locs:
            off_host = [l for l in locs if urlparse(l).netloc and urlparse(l).netloc.lower().replace("www.", "") != crawler.host]
            if off_host:
                c.add("sitemap-foreign-urls", "medium", "Sitemap lists URLs on a different host", "Google ignores sitemap URLs that do not match the sitemap's host (www vs non-www, http vs https, staging domains).", "Regenerate the sitemap with the canonical host and protocol.", evidence=off_host[:5], affected_count=len(off_host))
            http_in = [l for l in locs if l.startswith("http://")]
            if http_in and origin.startswith("https://"):
                c.add("sitemap-http-urls", "medium", "Sitemap contains http:// URLs on an https site", "Each entry redirects, which wastes crawl budget and sends mixed canonical signals.", "Regenerate the sitemap with https URLs.", evidence=http_in[:5], affected_count=len(http_in))
            lastmods = list(crawler.sitemap_lastmod.values())
            lastmod_total = sum(i.get("lastmod_count", 0) for i in sm.get("fetched", {}).values())
            if lastmod_total == 0:
                c.add("sitemap-no-lastmod", "low", "Sitemap has no <lastmod> dates", "Google uses lastmod (when accurate) to prioritise recrawling changed pages.", "Emit a truthful <lastmod> per URL.", effort="low")
            else:
                distinct = set(lm[:10] for lm in lastmods)
                if len(lastmods) >= 20 and len(distinct) == 1:
                    c.add("sitemap-lastmod-identical", "low", "Every sitemap URL has the same <lastmod> date", "Identical dates mean the generator stamps the build time, not the real change time; Google learns to ignore the field.", "Emit the real last-modified date per page, or omit lastmod.", evidence=[f"all {len(lastmods):,} URLs: {lastmods[0][:10]}"], effort="low")
                future = [lm for lm in lastmods if lm[:10] > datetime.utcnow().strftime("%Y-%m-%d")]
                if future:
                    c.add("sitemap-lastmod-future", "low", "Sitemap <lastmod> dates are in the future", "Future dates are invalid and discredit the whole field.", "Fix the timezone or generator clock.", evidence=future[:4], affected_count=len(future), effort="low")
                c.passed("sitemap-lastmod", f"<lastmod> present on {lastmod_total:,} URLs")
            # Entries fetched during the crawl
            fetched_sm = [crawler.pages[n] for n in norm_locs if n in crawler.pages]
            non200 = [p for p in fetched_sm if p.status != 200]
            if non200:
                redirected = [p for p in non200 if 300 <= p.status < 400 or p.redirect_chain]
                errors = [p for p in non200 if p.status >= 400 or p.status == 0]
                if errors:
                    c.add("sitemap-non-200", "high", "Sitemap includes URLs that return errors", "Sitemaps should only list final, 200-status, indexable URLs. Errors here erode Google's trust in the whole file.", "Remove broken URLs from the sitemap (or fix the pages).", evidence=[f"{p.url} -> {p.status or p.error}" for p in errors[:6]], affected_count=len(errors), pages=[p.url for p in errors])
                if redirected:
                    c.add("sitemap-redirected-urls", "medium", "Sitemap lists URLs that redirect", "Each redirecting entry costs an extra fetch and tells Google the sitemap is stale.", "Replace with the final destination URLs.", evidence=[f"{p.url} -> {p.final_url}" for p in redirected[:6]], affected_count=len(redirected), effort="low")
            redirecting_sm = [p for p in fetched_sm if p.status == 200 and p.redirect_chain]
            if redirecting_sm and not c.has("sitemap-redirected-urls"):
                c.add("sitemap-redirected-urls", "medium", "Sitemap lists URLs that redirect", "Each redirecting entry costs an extra fetch and tells Google the sitemap is stale.", "Replace with the final destination URLs.", evidence=[f"{p.url} -> {p.final_url}" for p in redirecting_sm[:6]], affected_count=len(redirecting_sm), effort="low")
            noindexed = [p for p in fetched_sm if p.status == 200 and not _indexable(p)]
            if noindexed:
                c.add("sitemap-noindex", "medium", "Sitemap lists noindex pages", "Contradictory signals: the sitemap asks for indexing while the page refuses it.", "Drop noindex URLs from the sitemap.", evidence=[p.url for p in noindexed[:5]], affected_count=len(noindexed), effort="low")
            noncanon = [p for p in fetched_sm if p.status == 200 and p.canonical and normalize(p.canonical) != normalize(p.final_url)]
            if noncanon:
                c.add("sitemap-non-canonical", "medium", "Sitemap lists URLs whose canonical points elsewhere", "The sitemap says 'index this' while the page says 'index that other URL'.", "List only canonical URLs in the sitemap.", evidence=[f"{p.url} -> canonical {p.canonical}" for p in noncanon[:5]], affected_count=len(noncanon), effort="low")
            if not non200 and not noindexed and not noncanon and fetched_sm:
                c.passed("sitemap-urls-clean", f"All {len(fetched_sm):,} fetched sitemap URLs return 200, are indexable and self-canonical")
            # Indexable crawled pages missing from the sitemap
            missing = [p for p in indexable if normalize(p.url) not in norm_locs and not p.redirect_chain and p.depth < ORPHAN_DEPTH and page_type(p.url, p) not in ("pagination", "search", "cart", "tag")]
            if missing and len(missing) > max(3, len(indexable) * 0.1) and sm.get("truncated") is False:
                c.add("sitemap-coverage-missing", "medium", f"{len(missing):,} indexable pages are not listed in the sitemap", "Pages absent from the sitemap are discovered only through links and are recrawled less often.", "Regenerate the sitemap from the CMS so every indexable page is included.", evidence=[p.url for p in missing[:6]], affected_count=len(missing), pages=[p.url for p in missing[:200]], effort="low")
            elif not missing and crawl_complete:
                c.passed("sitemap-coverage", "Every indexable crawled page is listed in the sitemap")
            # Orphans
            linked = set(crawler.inlinks.keys())
            orphan = [p.url for p in html_pages if p.url not in linked and p.url != crawler.start_url and normalize(p.url) in norm_locs]
            if orphan and (crawl_complete or len(crawler.pages) >= 150):
                ratio = len(orphan) / n_html
                sev = "high" if ratio > 0.3 else "medium" if ratio > 0.1 else "low"
                c.add("orphan-pages", sev, f"{len(orphan):,} sitemap pages have no internal links pointing to them", "Pages with no inbound internal links rank poorly and get crawled rarely, even when listed in the sitemap. Users cannot reach them by browsing either.", "Link these pages from relevant hub pages, navigation, related-content blocks or an HTML sitemap.", evidence=orphan[:8], affected_count=len(orphan), pages=orphan[:300], effort="medium")
            elif crawl_complete:
                c.passed("orphan-pages", "Every sitemap page receives at least one internal link")
    if not crawl_complete:
        c.add("crawl-incomplete", "info", f"Crawl stopped at {len(crawler.pages):,} pages ({crawler.stopped_reason}); sitemap lists {sm.get('unique_urls', 0):,} URLs", "Site-wide counts cover the crawled pages only. Orphan, duplicate and coverage checks are partial.", "Re-run with a higher --max-pages or --max-minutes (or --resume) for full coverage.", effort="low")

    # ======================================================= https + redirects
    ssl_errors = [p for p in pages if p.error and str(p.error).startswith("ssl")]
    if ssl_errors:
        c.add("ssl-error", "critical", "TLS certificate errors on some URLs", "Browsers show a full-page warning and crawlers refuse the page.", "Renew or fix the certificate chain for every hostname in use.", evidence=[f"{p.url}: {p.error}" for p in ssl_errors[:4]], affected_count=len(ssl_errors), effort="medium")
    if origin.startswith("http://"):
        c.add("no-https", "critical", "Site is served over HTTP, not HTTPS", "HTTPS is a ranking signal and browsers mark HTTP pages as not secure.", "Install a TLS certificate and 301 every http:// URL to https://.", effort="medium")
    else:
        c.passed("https", "Site is served over HTTPS")
        http_variant = fetcher.get(origin.replace("https://", "http://", 1), allow_redirects=True)
        if http_variant.error is None and not http_variant.final_url.startswith("https://"):
            c.add("http-not-redirected", "high", "http:// version does not redirect to https://", "Two live versions split signals and expose users to the insecure copy.", "Add a server-level 301 from http to https.", evidence=[f"{http_variant.url} -> {http_variant.status} {http_variant.final_url}"], effort="low")
        else:
            c.passed("http-redirect", "http:// redirects to https://")
            if http_variant.error is None and len(http_variant.redirect_chain) >= 2:
                c.add("https-redirect-chain", "low", "http:// reaches https:// through more than one redirect", "Each extra hop slows the first visit and leaks a little link equity.", "Redirect http://host and http://www.host straight to the final https URL in one hop.", evidence=[" -> ".join(f"{s} {u}" for s, u in http_variant.redirect_chain)], effort="low")
        host = urlparse(origin).netloc
        alt = origin.replace("://www.", "://", 1) if host.startswith("www.") else origin.replace("://", "://www.", 1)
        alt_resp = fetcher.get(alt, allow_redirects=True)
        if alt_resp.error is None and alt_resp.status == 200 and urlparse(alt_resp.final_url).netloc.lower() != host.lower():
            c.add("www-duplicate", "high", "www and non-www both serve the site without redirecting", "Duplicate hostnames create duplicate pages and split links.", "Pick one hostname and 301 the other to it.", evidence=[f"{alt} -> {alt_resp.status} {alt_resp.final_url}"], effort="low")
        else:
            c.passed("www-redirect", "www / non-www resolves to one hostname")

    chains = [p for p in pages if len(p.redirect_chain) >= 2]
    long_chains = [p for p in chains if len(p.redirect_chain) >= 3]
    if chains:
        sev = "high" if long_chains else "medium"
        c.add("redirect-chains", sev, f"Redirect chains on {len(chains):,} URLs ({len(long_chains)} with 3+ hops)", "Each hop leaks a little PageRank and slows users; Google stops following after a few hops, so 3+ hop chains can drop pages from the index.", "Point every link and redirect straight at the final URL.", evidence=[f"{p.url} ({len(p.redirect_chain)} hops: {' -> '.join(str(s) for s, _ in p.redirect_chain)})" for p in (long_chains + chains)[:6]], affected_count=len(chains), pages=[p.url for p in chains[:100]], effort="low")
    else:
        c.passed("redirect-chains", "No redirect chains")
    temp_redirects = [p for p in pages if any(s in (302, 307) for s, _ in p.redirect_chain) and p.depth > 0]
    if temp_redirects and len(temp_redirects) > 2:
        c.add("redirect-temporary", "low", "Internal links go through 302/307 temporary redirects", "Temporary redirects tell Google the old URL may come back, so it keeps indexing the old one instead of the destination.", "Use 301 (or 308) for permanent moves.", evidence=[f"{p.url} -> {p.final_url}" for p in temp_redirects[:5]], affected_count=len(temp_redirects), effort="low")
    internal_redirects = [p for p in pages if p.redirect_chain and p.depth > 0 and p.depth < ORPHAN_DEPTH]
    if len(internal_redirects) > max(3, len(pages) * 0.05):
        c.add("internal-links-redirect", "medium", f"{len(internal_redirects):,} internal links point to redirecting URLs", "Internal links should hit the final URL directly; redirects waste crawl budget and dilute signals.", "Update internal links (menus, footers, content) to the destination URLs.", evidence=[f"{p.url} -> {p.final_url}" for p in internal_redirects[:6]], affected_count=len(internal_redirects), pages=[p.url for p in internal_redirects[:200]], effort="low")
    loops = [p for p in pages if p.error and "TooManyRedirects" in str(p.error)]
    if loops:
        c.add("redirect-loops", "high", "Redirect loops detected", "The URL never resolves; browsers and crawlers give up.", "Fix the conflicting redirect rules.", evidence=[p.url for p in loops[:5]], affected_count=len(loops))
    meta_refresh = [p for p in html_pages if p.meta_refresh]
    if meta_refresh:
        c.add("meta-refresh-redirect", "medium", "Pages use meta refresh redirects", "Meta refresh is slow, passes little signal, and is flagged as a sneaky-redirect pattern when misused.", "Replace with server-side 301 redirects.", evidence=[f"{p.url}: {p.meta_refresh}" for p in meta_refresh[:4]], affected_count=len(meta_refresh), effort="low")

    # ============================================================ status codes
    broken = [p for p in pages if p.status in (404, 410) or (p.status == 0 and p.depth > 0 and p.depth < ORPHAN_DEPTH and not (p.error or "").startswith("ssl"))]
    server_err = [p for p in pages if p.status >= 500]
    if broken:
        sev = "high" if len(broken) > 3 else "medium"
        src = {}
        for p in broken[:200]:
            s = crawler.inlinks.get(p.url, [])
            src[p.url] = s[0] if s else ""
        c.add("broken-internal-urls", sev, f"{len(broken):,} internal link{'s lead' if len(broken) != 1 else ' leads'} to broken pages", "Dead ends waste crawl budget and frustrate users; Google reads many 404s as a quality signal.", "Fix or 301 the broken URLs and update the linking pages.", evidence=[f"{p.url} -> {p.status or p.error}" + (f" (linked from {src.get(p.url)})" if src.get(p.url) else "") for p in broken[:8]], affected_count=len(broken), pages=[p.url for p in broken[:300]])
    else:
        c.passed("broken-internal-urls", "No broken internal URLs in the crawl")
    if server_err:
        c.add("server-errors", "high", f"{len(server_err):,} URLs returned server errors (5xx)", "Server errors drop pages from the index if they persist and signal unreliable hosting.", "Check server logs for the failing URLs; fix the application or hosting fault.", evidence=[f"{p.url} -> {p.status}" for p in server_err[:6]], affected_count=len(server_err), pages=[p.url for p in server_err[:100]])
    timeouts = [p for p in pages if p.error == "timeout"]
    if timeouts and len(timeouts) > max(2, len(pages) * 0.02):
        c.add("timeouts", "medium", f"{len(timeouts):,} URLs timed out", "Timeouts mean crawlers give up before seeing the page; users would too.", "Investigate slow endpoints and server capacity.", evidence=[p.url for p in timeouts[:5]], affected_count=len(timeouts))

    # Soft 404
    soft = [p for p in html_pages if re.search(r"\b(page not found|404|not found|nothing found|no results found|doesn't exist|does not exist)\b", (p.title or "") + " " + (p.h1[0] if p.h1 else ""), re.I) and p.word_count < 300]
    if soft:
        c.add("soft-404", "high", "Soft 404 pages return status 200", "Pages that say 'not found' but return 200 get indexed as thin junk and dilute the site.", "Return a real 404 or 410 status for missing content.", evidence=[f"{p.url} title='{p.title[:60]}'" for p in soft[:6]], affected_count=len(soft), pages=[p.url for p in soft[:100]])
    else:
        c.passed("soft-404", "No soft-404 pages detected")

    # Real 404 behaviour
    probe = fetcher.get(f"{origin}/ranksherlock-404-probe-{abs(hash(origin)) % 99999}")
    if probe.error is None and probe.status == 200:
        c.add("404-returns-200", "high", "Missing URLs return 200 instead of 404", "Any typo URL becomes an indexable duplicate page. Crawlers cannot tell real pages from junk.", "Configure the server or CMS to return 404 (or 410) for unknown paths.", evidence=[f"{probe.url} -> 200"], effort="low")
    elif probe.error is None:
        c.passed("404-handling", f"Unknown URLs return {probe.status}")
        if probe.status == 404 and probe.is_html:
            body = re.sub(r"<[^>]+>", " ", probe.text[:200000])
            words = len(body.split())
            links = len(re.findall(r"<a\s", probe.text, re.I))
            if words < 40 or links < 3:
                c.add("custom-404-thin", "low", "The 404 page offers no navigation or help", "A helpful 404 page (search box, popular links, home link) keeps visitors on the site instead of bouncing.", "Design a custom 404 page with navigation, search and links to key pages; keep the 404 status.", evidence=[f"{words} words, {links} links on the 404 page"], effort="low")
            else:
                c.passed("custom-404", "Custom 404 page offers navigation")

    # =========================================================== indexability
    noindex_pages = [p for p in html_pages if not _indexable(p)]
    if home and not _indexable(home):
        is_home = urlparse(home.final_url).path in ("", "/")
        if is_home:
            c.add("homepage-noindex", "critical", "Homepage is set to noindex", "The homepage cannot appear in search results at all.", "Remove the noindex directive from the homepage.", evidence=[home.meta_robots or home.x_robots_tag], effort="low")
        else:
            c.add("page-noindex", "high", "The audited page is set to noindex", "This page cannot appear in search results.", "Remove noindex if the page should rank.", evidence=[home.url, home.meta_robots or home.x_robots_tag], effort="low")
    else:
        c.passed("homepage-indexable", "Homepage is indexable")
    if noindex_pages and len(noindex_pages) > n_html * 0.25:
        c.add("many-noindex", "medium", f"{len(noindex_pages):,} crawled pages ({round(100 * len(noindex_pages) / n_html)}%) are noindex", "Possibly intentional, but worth confirming these are not money pages.", "Review the list and remove noindex from pages that should rank.", evidence=[p.url for p in noindex_pages[:6]], affected_count=len(noindex_pages), pages=[p.url for p in noindex_pages[:200]])
    nofollow_pages = [p for p in html_pages if re.search(r"\bnofollow\b", (p.meta_robots or "") + " " + (p.x_robots_tag or ""), re.I)]
    if nofollow_pages and len(nofollow_pages) > 2:
        c.add("meta-nofollow", "medium", "Pages carry a sitewide nofollow directive", "nofollow on the page stops every outgoing link from passing signals, cutting the page off from the rest of the site.", "Remove nofollow from meta robots unless the page is deliberately isolated.", evidence=[p.url for p in nofollow_pages[:5]], affected_count=len(nofollow_pages), effort="low")
    low_value = [p for p in indexable if LOW_VALUE_RE.search(p.url) or page_type(p.url, p) in ("cart", "search")]
    if low_value:
        c.add("low-value-indexable", "medium", f"{len(low_value):,} utility pages (cart, login, search, tag or author archives) are indexable", "Utility and archive pages are thin, duplicate the real content and dilute crawl budget; they occasionally outrank the pages that matter.", "Add noindex to cart, checkout, account, login, internal search and thin archive pages; keep them out of the sitemap.", evidence=[p.url for p in low_value[:6]], affected_count=len(low_value), pages=[p.url for p in low_value[:200]], effort="low")
    pagin = [p for p in indexable if page_type(p.url, p) == "pagination"]
    if pagin and len(pagin) > 5:
        bad_pagin = [p for p in pagin if not p.canonical or normalize(p.canonical) == normalize(p.final_url)]
        if bad_pagin:
            c.add("pagination-indexable", "low", f"{len(pagin):,} paginated pages are indexable with self-canonicals", "Fine for large catalogues, but paginated archives usually add duplicate titles and thin pages to the index.", "Keep pagination crawlable, give each page a unique title ('Page 2 of ...'), and consider noindex on deep pages that add no value.", evidence=[p.url for p in pagin[:5]], affected_count=len(pagin), effort="low")
    param_pages = [p for p in indexable if urlparse(p.url).query and (not p.canonical or normalize(p.canonical) == normalize(p.final_url))]
    if param_pages and len(param_pages) > max(3, len(indexable) * 0.05):
        c.add("parameter-url-duplicates", "medium", f"{len(param_pages):,} parameter URLs are indexable as separate pages", "Sort, filter and tracking parameters create endless near-duplicate URLs that split signals and burn crawl budget.", "Canonicalise parameter URLs to the clean version, or noindex them, and strip tracking parameters at the edge.", evidence=[p.url for p in param_pages[:6]], affected_count=len(param_pages), pages=[p.url for p in param_pages[:200]], effort="medium")

    # ============================================================== canonical
    no_canon = [p for p in indexable if not p.canonical]
    if no_canon:
        sev = "high" if len(no_canon) > len(indexable) * 0.5 else "medium"
        c.add("missing-canonical", sev, f"{len(no_canon):,} pages have no canonical tag", "Without rel=canonical, parameter and duplicate versions compete with the original.", "Add a self-referencing canonical on every indexable page.", evidence=[p.url for p in no_canon[:6]], affected_count=len(no_canon), pages=[p.url for p in no_canon[:300]], effort="low")
    else:
        c.passed("canonical-present", "All indexable pages declare a canonical")
    multi = [p for p in html_pages if p.canonical_count > 1]
    if multi:
        c.add("multiple-canonicals", "high", "Pages declare more than one canonical", "Google ignores conflicting canonicals, so you lose control of the indexed URL.", "Keep exactly one canonical link per page (often a theme and an SEO plugin both print one).", evidence=[p.url for p in multi[:6]], affected_count=len(multi), pages=[p.url for p in multi[:200]], effort="low")
    canon_elsewhere = [p for p in html_pages if p.canonical and normalize(p.canonical) != normalize(p.final_url) and p.depth > 0]
    to_home = [p for p in canon_elsewhere if normalize(p.canonical) == crawler.start_url]
    if len(to_home) >= 3:
        c.add("canonical-to-homepage", "critical", f"{len(to_home):,} pages canonicalise to the homepage", "Google is told these pages are copies of the homepage, so they drop out of the index.", "Make each page's canonical self-referencing. Usually a theme or plugin bug.", evidence=[p.url for p in to_home[:6]], affected_count=len(to_home), pages=[p.url for p in to_home[:300]], effort="low")
    elif canon_elsewhere and len(canon_elsewhere) > max(2, n_html * 0.15):
        c.add("canonical-points-elsewhere", "medium", f"{len(canon_elsewhere):,} pages canonicalise to a different URL", "Fine for true duplicates; harmful if these are unique pages.", "Verify each non-self canonical is intentional.", evidence=[f"{p.url} -> {p.canonical}" for p in canon_elsewhere[:6]], affected_count=len(canon_elsewhere), pages=[p.url for p in canon_elsewhere[:200]])
    cross = [p for p in html_pages if p.canonical and urlparse(p.canonical).netloc and urlparse(p.canonical).netloc.lower().replace("www.", "") != crawler.host]
    if cross:
        c.add("canonical-cross-domain", "high", "Canonical tags point to another domain", "These pages hand their ranking rights to a different site (often a staging domain or the old domain left in a template).", "Point canonicals at this domain unless cross-domain syndication is intended.", evidence=[f"{p.url} -> {p.canonical}" for p in cross[:5]], affected_count=len(cross), effort="low")
    http_canon = [p for p in html_pages if p.canonical.startswith("http://") and origin.startswith("https://")]
    if http_canon:
        c.add("canonical-http", "high", "Canonical tags point to http:// URLs", "The canonical contradicts the secure URL and can push the HTTP copy into the index.", "Update canonicals to https.", evidence=[p.url for p in http_canon[:5]], affected_count=len(http_canon), effort="low")
    canon_noindex = [p for p in html_pages if not _indexable(p) and p.canonical and normalize(p.canonical) != normalize(p.final_url)]
    if canon_noindex:
        c.add("canonical-noindex-conflict", "medium", "noindex pages also canonicalise elsewhere", "Mixed signals: noindex says 'ignore me', canonical says 'count me as that page'. Google may apply noindex to the canonical target.", "Use one signal: canonical for duplicates, noindex for pages that should vanish.", evidence=[f"{p.url} -> {p.canonical}" for p in canon_noindex[:5]], affected_count=len(canon_noindex), effort="low")
    canon_targets_broken = []
    for p in indexable:
        if p.canonical and normalize(p.canonical) != normalize(p.final_url) and normalize(p.canonical) != p.url:
            t = crawler.pages.get(normalize(p.canonical))
            if t and (t.status >= 400 or (t.status == 200 and not _indexable(t))):
                canon_targets_broken.append(f"{p.url} -> {p.canonical} ({t.status}{', noindex' if t.status == 200 else ''})")
    if canon_targets_broken:
        c.add("canonical-target-broken", "high", "Canonical targets are broken or noindex", "Pointing at a dead or noindex canonical removes both pages from the index.", "Fix the canonical targets.", evidence=canon_targets_broken[:5], affected_count=len(canon_targets_broken), effort="low")

    # ============================================================= duplicates
    titles = Counter(p.title for p in indexable if p.title)
    dup_titles = {t: n for t, n in titles.items() if n > 1}
    if dup_titles:
        total = sum(dup_titles.values())
        sev = "high" if total > max(5, len(indexable) * 0.1) else "medium"
        c.add("duplicate-titles", sev, f"Duplicate title tags on {total:,} pages", "Identical titles make pages compete and tell Google they may be duplicates.", "Write a unique, descriptive title for each page.", evidence=[f"'{t[:60]}' on {n} pages" for t, n in sorted(dup_titles.items(), key=lambda kv: -kv[1])[:6]], affected_count=total, pages=[p.url for p in indexable if p.title in dup_titles][:300])
    else:
        c.passed("duplicate-titles", "All page titles are unique")
    descs = Counter(p.meta_description for p in indexable if p.meta_description)
    dup_desc = {t: n for t, n in descs.items() if n > 1}
    if dup_desc:
        c.add("duplicate-descriptions", "low", f"Duplicate meta descriptions on {sum(dup_desc.values()):,} pages", "Google rewrites duplicates, so you lose control of the snippet.", "Write unique descriptions for key pages.", evidence=[f"'{t[:60]}' on {n} pages" for t, n in sorted(dup_desc.items(), key=lambda kv: -kv[1])[:5]], affected_count=sum(dup_desc.values()), effort="low")
    h1s = Counter(p.h1[0] for p in indexable if p.h1)
    dup_h1 = {t: n for t, n in h1s.items() if n > 2}
    if dup_h1:
        total = sum(dup_h1.values())
        c.add("duplicate-h1", "high" if total > max(10, len(indexable) * 0.3) else "medium", f"Same H1 reused across {total:,} pages", "Often a theme bug that prints the site name as H1 everywhere, erasing each page's topic signal.", "Make the H1 the page's own headline.", evidence=[f"'{t[:60]}' on {n} pages" for t, n in sorted(dup_h1.items(), key=lambda kv: -kv[1])[:4]], affected_count=total, pages=[p.url for p in indexable if p.h1 and p.h1[0] in dup_h1][:300])
    bodies = defaultdict(list)
    for p in indexable:
        if p.word_count >= 100 and p.body_hash:
            bodies[p.body_hash].append(p.url)
    dup_groups = [urls for urls in bodies.values() if len(urls) > 1]
    if dup_groups:
        total = sum(len(g) for g in dup_groups)
        sev = "high" if total > max(5, len(indexable) * 0.1) else "medium"
        c.add("duplicate-content", sev, f"{total:,} pages have identical body text ({len(dup_groups)} groups)", "Exact duplicates compete with each other; Google picks one and may drop the rest or choose the wrong one.", "Canonicalise or 301 duplicates to one URL (trailing slash, parameter, print or category-path variants are the usual cause).", evidence=[f"{g[0]} = {g[1]}" + (f" (+{len(g) - 2} more)" if len(g) > 2 else "") for g in dup_groups[:5]], affected_count=total, pages=[u for g in dup_groups for u in g][:300], effort="medium")
    else:
        c.passed("duplicate-content", "No exact duplicate pages")
    slash_pairs = 0
    urlset = set(crawler.pages.keys())
    for u in list(urlset)[:5000]:
        if u.endswith("/") and len(u) > len(origin) + 1 and u[:-1] in urlset:
            a, b = crawler.pages[u], crawler.pages[u[:-1]]
            if a.status == 200 and b.status == 200 and not a.redirect_chain and not b.redirect_chain:
                slash_pairs += 1
    if slash_pairs:
        c.add("url-trailing-slash", "low", f"{slash_pairs} URLs serve both with and without a trailing slash", "Two live versions of the same page; a canonical usually rescues it, but it is cleaner to redirect.", "Pick one form and 301 the other site-wide.", affected_count=slash_pairs, effort="low")

    # ================================================================== URLs
    ds = crawler.malformed_counts.get("double-slash", 0)
    if ds:
        c.add("url-double-slash-links", "medium" if ds > 10 else "low", f"{ds:,} internal links contain a double slash in the path", "Links like /our-products//hardwood create duplicate URLs that return the same page; Google indexes both versions and splits their signals.", "Fix the link template (usually a trailing slash in the base URL plus a leading slash in the path) and 301 the double-slash URLs to the clean ones.", evidence=crawler.malformed_links.get("double-slash", [])[:6], affected_count=ds, effort="low")
    ws = crawler.malformed_counts.get("whitespace", 0)
    if ws:
        c.add("url-whitespace-links", "low", f"{ws:,} internal links contain spaces", "URLs with spaces get encoded inconsistently and often break.", "Replace spaces with hyphens in slugs and fix the links.", evidence=crawler.malformed_links.get("whitespace", [])[:4], affected_count=ws, effort="low")
    ugly = [p.url for p in indexable if re.search(r"[A-Z]|%20|_|\s", urlparse(p.url).path)]
    if ugly and len(ugly) > len(indexable) * 0.2:
        c.add("url-hygiene", "low", f"{len(ugly):,} URLs use uppercase, underscores or spaces", "Clean lowercase hyphenated URLs are easier to share and avoid case-duplicate issues.", "Prefer lowercase, hyphen-separated URLs for content pages (redirect the old forms).", evidence=ugly[:6], affected_count=len(ugly))
    long_urls = [p.url for p in indexable if len(p.url) > 115]
    if long_urls and len(long_urls) > max(3, len(indexable) * 0.1):
        c.add("url-length", "low", f"{len(long_urls):,} URLs are longer than 115 characters", "Long URLs get truncated in results and are harder to share; they often signal deep category paths or stuffed slugs.", "Shorten slugs and flatten unnecessary folders for new pages.", evidence=long_urls[:4], affected_count=len(long_urls))
    numeric = [p.url for p in indexable if re.search(r"/\d{3,}(-\d+)?(\.html?)?/?$", p.url) and page_type(p.url, p) not in ("pagination",) and not re.search(r"/[a-z0-9]+(-[a-z0-9]+){2,}/", urlparse(p.url).path, re.I)]
    if numeric and len(numeric) > max(3, len(indexable) * 0.1):
        c.add("url-numeric-slugs", "low", f"{len(numeric):,} URLs end in bare numeric IDs", "Numeric slugs tell users and engines nothing about the page.", "Use descriptive slugs for content and product pages.", evidence=numeric[:4], affected_count=len(numeric))
    deep = [p for p in indexable if 4 <= p.depth < ORPHAN_DEPTH]
    if deep and len(deep) > len(indexable) * 0.2:
        c.add("deep-pages", "low", f"{len(deep):,} pages are 4+ clicks from the homepage", "Depth correlates with crawl frequency and perceived importance.", "Flatten the architecture with hub pages, footer links or breadcrumbs.", evidence=[f"{p.url} (depth {p.depth})" for p in deep[:5]], affected_count=len(deep), pages=[p.url for p in deep[:200]])
    else:
        c.passed("crawl-depth", "Most pages sit within 3 clicks of the homepage")

    # ============================================================== security
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
        if not h.get("content-security-policy"):
            c.add("no-csp", "info", "No Content-Security-Policy header", "CSP limits what scripts can run; absence is common but security scanners flag it.", "Add a CSP once third-party scripts are inventoried (start in report-only mode).", effort="medium")
        if not h.get("referrer-policy"):
            c.add("no-referrer-policy", "info", "No Referrer-Policy header", "Minor hygiene; controls what URL data leaks to third parties.", "Send `Referrer-Policy: strict-origin-when-cross-origin`.", effort="low")
        if h.get("x-powered-by"):
            c.add("x-powered-by", "info", "Server reveals its stack via X-Powered-By", "Discloses software versions to attackers.", "Remove the X-Powered-By header.", evidence=[h.get("x-powered-by")], effort="low")
        if not h.get("content-encoding") and home.size_bytes > 50_000:
            c.add("no-compression", "medium", "HTML is served without gzip/brotli compression", "Uncompressed HTML is 3 to 5x larger, which slows every page load.", "Enable gzip or brotli at the server or CDN.", evidence=[f"homepage {home.size_bytes // 1024} KB, no content-encoding"], effort="low")
        else:
            c.passed("compression", f"HTML is compressed ({h.get('content-encoding', 'small page')})")
        cc = (h.get("cache-control") or "").lower()
        if not cc and not h.get("etag") and not h.get("last-modified"):
            c.add("no-cache-headers", "info", "HTML responses carry no Cache-Control, ETag or Last-Modified", "Conditional requests let crawlers skip unchanged pages (304) and spend budget on new ones.", "Send Last-Modified or ETag and a sensible Cache-Control for HTML.", effort="low")
    mixed = [p for p in html_pages if p.mixed_content]
    if mixed:
        c.add("mixed-content", "medium", f"{len(mixed):,} HTTPS pages load http:// resources", "Browsers block or warn on mixed content; it breaks the padlock.", "Update resource URLs to https.", evidence=[p.url for p in mixed[:5]], affected_count=len(mixed), pages=[p.url for p in mixed[:200]], effort="low")
    else:
        c.passed("mixed-content", "No mixed content")
    unsafe = [p for p in html_pages if p.unsafe_targets]
    if unsafe and len(unsafe) > n_html * 0.3:
        c.add("unsafe-target-blank", "info", "Links open new tabs without rel=noopener", "Legacy browsers let the opened page control the opener (tabnabbing). Modern browsers default to noopener, so this is hygiene.", "Add rel=\"noopener\" to target=_blank links.", affected_count=sum(p.unsafe_targets for p in unsafe), effort="low")

    # ================================================================ mobile
    no_viewport = [p for p in html_pages if not p.viewport]
    if no_viewport:
        sev = "critical" if home in no_viewport else "high"
        c.add("no-viewport", sev, f"{len(no_viewport):,} pages have no viewport meta tag", "Without it, mobile browsers render the desktop layout zoomed out. Google indexes mobile-first.", "Add `<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">`.", evidence=[p.url for p in no_viewport[:5]], affected_count=len(no_viewport), pages=[p.url for p in no_viewport[:200]], effort="low")
    else:
        c.passed("viewport", "Viewport meta present on all pages")
    zoom = [p for p in html_pages if p.zoom_locked]
    if zoom:
        c.add("viewport-zoom-lock", "medium", f"{len(zoom):,} pages disable pinch-zoom", "user-scalable=no or maximum-scale=1 blocks zooming, fails accessibility guidelines and is flagged by Lighthouse.", "Remove user-scalable=no and maximum-scale from the viewport meta.", evidence=[p.url for p in zoom[:4]], affected_count=len(zoom), effort="low")
    no_lang = [p for p in html_pages if not p.lang]
    if no_lang and len(no_lang) > n_html * 0.5:
        c.add("no-html-lang", "low", "Missing lang attribute on <html>", "Helps search engines and screen readers identify the language.", "Add `<html lang=\"en\">` (or the right code).", affected_count=len(no_lang), effort="low")
    else:
        bad_lang = [p for p in html_pages if p.lang and not re.match(r"^[a-zA-Z]{2,3}(-[a-zA-Z0-9]{2,8})*$", p.lang)]
        if bad_lang:
            c.add("invalid-html-lang", "low", "Invalid lang attribute values", "Invalid codes are ignored by browsers and assistive tech.", "Use BCP 47 codes such as en, en-IN, hi.", evidence=[f"{p.url}: '{p.lang}'" for p in bad_lang[:4]], affected_count=len(bad_lang), effort="low")
        else:
            c.passed("html-lang", "lang attribute set on <html>")
    amp = [p for p in html_pages if p.has_amp]
    if amp:
        c.add("amp-in-use", "info", f"AMP markup on {len(amp):,} pages", "AMP no longer carries ranking or Top Stories advantages; it adds maintenance and duplicate pages.", "Plan to retire AMP once the canonical pages pass Core Web Vitals.", affected_count=len(amp), effort="medium")

    # ========================================================== JS rendering
    thin_html = [p for p in html_pages if p.word_count < 80 and p.external_scripts >= 3 and p.depth <= 2]
    csr = [p for p in html_pages if p.render_hint]
    if (thin_html and len(thin_html) >= max(2, n_html * 0.3)) or (csr and len(csr) >= max(2, n_html * 0.3)):
        ex = csr or thin_html
        c.add("csr-empty-html", "high", "Pages ship almost no text in the raw HTML (client-side rendering)", "Google can render JS but AI crawlers and many bots cannot. Content that only appears after JS runs is invisible to them.", "Server-render or pre-render primary content so it is present in the initial HTML.", evidence=[f"{p.url} ({p.word_count} words, {p.external_scripts} scripts)" for p in ex[:5]], affected_count=len(ex), pages=[p.url for p in ex[:200]], effort="high")
    else:
        c.passed("ssr-content", "Primary content is present in the raw HTML")
        if csr:
            c.add("csr-some-pages", "medium", f"{len(csr):,} pages are JavaScript shells with no server-rendered text", "These pages are blank to AI crawlers and slow for Google to index.", "Server-render these templates.", evidence=[p.url for p in csr[:5]], affected_count=len(csr), pages=[p.url for p in csr[:100]], effort="high")
    frameworks = Counter()
    for p in html_pages[:200]:
        if p.detected_platform in ("Next.js", "Nuxt", "Gatsby"):
            frameworks[p.detected_platform] += 1
    if frameworks and not csr:
        c.passed("spa-ssr", f"JavaScript framework ({frameworks.most_common(1)[0][0]}) serves server-rendered HTML")

    # ======================================================== hreflang sanity
    hl_pages = [p for p in html_pages if p.hreflang]
    if hl_pages:
        bad_codes, missing_self, missing_xdefault, no_return, proto_mismatch, on_noncanon = [], [], [], [], [], []
        for p in hl_pages:
            codes = [h["lang"] for h in p.hreflang]
            for code in codes:
                if not re.match(r"^(x-default|[a-z]{2,3}(-[A-Za-z]{2,4})?)$", code) or re.match(r"^(en-uk|en-UK|es-la|es-LA|jp|eng|cn)$", code):
                    bad_codes.append(f"{p.url}: {code}")
            if not any(normalize(h["href"]) == normalize(p.final_url) for h in p.hreflang):
                missing_self.append(p.url)
            if "x-default" not in codes:
                missing_xdefault.append(p.url)
            if p.canonical and normalize(p.canonical) != normalize(p.final_url):
                on_noncanon.append(p.url)
            for h in p.hreflang:
                if h["href"].startswith("http://") and origin.startswith("https://"):
                    proto_mismatch.append(f"{p.url} -> {h['href']}")
                t = crawler.pages.get(normalize(h["href"]))
                if t and t.status == 200 and t.hreflang and not any(normalize(x["href"]) == normalize(p.final_url) for x in t.hreflang):
                    no_return.append(f"{p.url} -> {h['href']} (no return tag)")
        if bad_codes:
            c.add("hreflang-invalid-codes", "high", "Invalid hreflang language or region codes", "Google ignores malformed hreflang entries entirely.", "Use ISO 639-1 language and ISO 3166-1 Alpha-2 region codes (en, en-GB, x-default).", evidence=bad_codes[:5], affected_count=len(bad_codes))
        if missing_self:
            c.add("hreflang-no-self", "high", "hreflang sets omit the self-referencing entry", "Each page must list itself or the whole set is invalid.", "Include the page's own URL in its hreflang cluster.", evidence=missing_self[:5], affected_count=len(missing_self))
        if no_return:
            c.add("hreflang-no-return", "high", "hreflang links are not reciprocated", "Google requires both pages to reference each other; one-way links are ignored.", "Make every alternate list the full set, including the page that links to it.", evidence=no_return[:5], affected_count=len(no_return))
        if missing_xdefault:
            c.add("hreflang-no-xdefault", "low", "hreflang sets have no x-default", "x-default catches users whose language is not covered.", "Add an x-default alternate.", affected_count=len(missing_xdefault), effort="low")
        if proto_mismatch:
            c.add("hreflang-protocol", "medium", "hreflang URLs use http:// on an https site", "The alternates point at redirecting URLs, which breaks the cluster.", "Use the final https URLs in every hreflang tag.", evidence=proto_mismatch[:4], affected_count=len(proto_mismatch), effort="low")
        if on_noncanon:
            c.add("hreflang-on-noncanonical", "high", "hreflang declared on pages that canonicalise elsewhere", "hreflang only works on canonical URLs; on duplicates it is ignored.", "Declare hreflang on the canonical versions only.", evidence=on_noncanon[:4], affected_count=len(on_noncanon))
        c.passed("hreflang-present", f"hreflang annotations found on {len(hl_pages):,} pages")

    # ========================================================= external links
    checked = 0
    dead_ext = []
    by_host: dict[str, int] = {}
    for href, found_on in crawler.external_samples.items():
        if checked >= check_links:
            break
        h = urlparse(href).netloc.lower()
        if by_host.get(h, 0) >= 3 or re.search(r"(facebook|instagram|linkedin|twitter|x)\.com|wa\.me|whatsapp", h):
            continue  # social hosts block HEAD requests; max 3 checks per host
        by_host[h] = by_host.get(h, 0) + 1
        status, err = fetcher.head_status(href)
        checked += 1
        if status in (404, 410) or (status == 0 and err not in ("SSLError", "ConnectionError", "ReadTimeout", "ConnectTimeout", "Timeout")):
            dead_ext.append(f"{href} ({status or err}) on {found_on}")
    if dead_ext:
        c.add("broken-external-links", "low", f"{len(dead_ext)} outbound links lead to dead pages", "Broken outbound links read as neglect and hurt user trust.", "Fix or remove the dead links.", evidence=dead_ext[:6], affected_count=len(dead_ext), effort="low")
    elif checked:
        c.passed("external-links", f"Checked {checked} outbound links, none broken")

    # ============================================================ page weight
    heavy = [p for p in html_pages if p.size_bytes > 1_500_000]
    large = [p for p in html_pages if 500_000 < p.size_bytes <= 1_500_000]
    if heavy:
        c.add("heavy-html", "medium", f"{len(heavy):,} HTML documents are over 1.5 MB", "Giant HTML (inline SVG, base64 images, inlined CSS) delays first paint and can be truncated by crawlers.", "Move inline assets to files, remove unused inline CSS, lazy-load below-the-fold content.", evidence=[f"{p.url} ({p.size_bytes // 1024} KB)" for p in heavy[:5]], affected_count=len(heavy))
    elif large and len(large) > n_html * 0.3:
        c.add("large-html", "low", f"{len(large):,} HTML documents are over 500 KB", "HTML this large is usually page-builder bloat or inlined assets; every visit downloads it before anything renders.", "Trim inline CSS/SVG, paginate long lists and move assets to cached files.", evidence=[f"{p.url} ({p.size_bytes // 1024} KB)" for p in large[:4]], affected_count=len(large), effort="medium")
    else:
        c.passed("html-size", "HTML documents are a reasonable size")
    slow = [p for p in html_pages if p.elapsed_ms > 2500]
    if slow and len(slow) >= max(2, n_html * 0.2):
        c.add("slow-ttfb", "medium", f"Server response over 2.5 s on {len(slow):,} pages", "Slow HTML responses cap how fast any page can load and reduce crawl rate.", "Add page caching, upgrade hosting or put a CDN in front.", evidence=[f"{p.url} ({p.elapsed_ms} ms)" for p in slow[:5]], affected_count=len(slow))
    else:
        avg_ms = round(sum(p.elapsed_ms for p in html_pages) / n_html)
        c.passed("server-response", f"Average server response {avg_ms} ms")

    # ========================================================= accessibility
    empty_links = [p for p in html_pages if p.empty_links >= 3]
    if empty_links and len(empty_links) > n_html * 0.3:
        c.add("empty-links", "low", f"Links without text or label on {len(empty_links):,} pages", "Icon links with no accessible name are invisible to screen readers and pass no anchor-text signal.", "Add aria-label or visually hidden text to icon-only links; give image links alt text.", evidence=[f"{p.url} ({p.empty_links} links)" for p in empty_links[:4]], affected_count=sum(p.empty_links for p in empty_links), effort="low")
    unlabeled = [p for p in html_pages if p.unlabeled_inputs]
    if unlabeled and len(unlabeled) > n_html * 0.3:
        c.add("unlabeled-inputs", "low", f"Form fields without labels on {len(unlabeled):,} pages", "Unlabelled fields fail accessibility checks and lower Lighthouse accessibility scores.", "Add <label for> or aria-label to every input.", evidence=[f"{p.url} ({p.unlabeled_inputs} fields)" for p in unlabeled[:4]], affected_count=sum(p.unlabeled_inputs for p in unlabeled), effort="low")
    if home and not home.has_favicon:
        c.add("no-favicon", "low", "No favicon declared", "Google shows favicons in mobile results; a missing one looks unfinished.", "Add a 48x48 (or SVG) favicon with <link rel=\"icon\">.", effort="low")
    if home and not home.skip_links and (home.internal_link_count or len(home.internal_links)) > 40:
        c.add("no-skip-link", "info", "No skip-to-content link", "Keyboard users must tab through the whole menu on every page.", "Add a visually hidden 'Skip to main content' link as the first focusable element.", effort="low")

    # ============================================================== tracking
    analytics = Counter(a for p in html_pages[:100] for a in p.has_analytics)
    if home is not None:
        if not analytics:
            c.add("no-analytics", "low", "No analytics or tag manager detected", "Without GA4 or a tag manager there is no way to measure organic traffic, conversions or the impact of these fixes.", "Install GA4 via Google Tag Manager and connect Search Console.", effort="low")
        else:
            c.passed("analytics", f"Tracking detected: {', '.join(k for k, _ in analytics.most_common(5))}")
        if analytics.get("Universal Analytics (legacy)"):
            c.add("legacy-ua-tag", "low", "Legacy Universal Analytics tag still loads", "UA stopped processing data in July 2024; the tag is dead weight.", "Remove analytics.js and keep GA4 only.", effort="low")
        if home.has_cookie_banner:
            c.passed("consent-banner", "Cookie consent banner present")

    out = c.to_dict()
    out["platform"] = Counter(p.detected_platform for p in html_pages if p.detected_platform).most_common(1)[0][0] if any(p.detected_platform for p in html_pages) else ""
    out["generator"] = Counter(p.generator for p in html_pages if p.generator).most_common(1)[0][0] if any(p.generator for p in html_pages) else ""
    out["status_breakdown"] = dict(Counter(p.status for p in pages))
    out["indexable_pages"] = len(indexable)
    out["noindex_pages"] = len(noindex_pages)
    out["avg_response_ms"] = round(sum(p.elapsed_ms for p in html_pages) / n_html)
    out["depth_distribution"] = dict(sorted(Counter(("orphan" if p.depth >= ORPHAN_DEPTH else p.depth) for p in html_pages).items(), key=lambda kv: (isinstance(kv[0], str), kv[0])))
    out["analytics"] = dict(analytics.most_common(10))
    out["third_party_hosts"] = dict(Counter(h for p in html_pages[:100] for h in p.third_party_script_hosts).most_common(15))
    out["hreflang_pages"] = len(hl_pages)
    return out
