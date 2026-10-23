# RankSherlock checks

Generated from the engine source. Severity shown is the default; some checks escalate with scale.
Total distinct failing checks: 108.

## Technical SEO

| Check id | Severity | Finding |
|---|---|---|
| `robots-disallow-all` | critical | robots.txt blocks all crawlers from the whole site |
| `robots-no-sitemap` | low | robots.txt does not declare a Sitemap |
| `robots-blocks-assets` | medium | robots.txt blocks CSS or JS resources |
| `robots-unreachable` | medium | robots.txt could not be fetched |
| `robots-missing` | low | No robots.txt file |
| `robots-blocks-internal-links` | medium | Internal links point to robots-blocked URLs |
| `sitemap-missing` | high | No XML sitemap found |
| `sitemap-child-errors` | medium | Sitemap index references files that do not load |
| `sitemap-foreign-urls` | medium | Sitemap lists URLs on a different host |
| `sitemap-http-urls` | medium | Sitemap contains http:// URLs on an https site |
| `sitemap-no-lastmod` | low | Sitemap has no <lastmod> dates |
| `sitemap-non-200` | high | Sitemap includes URLs that return errors or redirects |
| `sitemap-noindex` | medium | Sitemap lists noindex pages |
| `orphan-pages` | medium | Many sitemap URLs received no internal links in the crawl |
| `no-https` | critical | Site is served over HTTP, not HTTPS |
| `http-not-redirected` | high | http:// version does not redirect to https:// |
| `www-duplicate` | high | www and non-www both serve the site without redirecting |
| `redirect-chains` | medium | Redirect chains (2+ hops) found |
| `internal-links-redirect` | medium | Many internal links point to redirecting URLs |
| `soft-404` | high | Soft 404 pages return status 200 |
| `404-returns-200` | high | Missing URLs return 200 instead of 404 |
| `homepage-noindex` | critical | Homepage is set to noindex |
| `page-noindex` | high | The audited page is set to noindex |
| `many-noindex` | medium | A large share of crawled pages are noindex |
| `multiple-canonicals` | high | Pages declare more than one canonical |
| `canonical-to-homepage` | critical | Multiple pages canonicalise to the homepage |
| `canonical-points-elsewhere` | medium | Many pages canonicalise to a different URL |
| `canonical-http` | high | Canonical tags point to http:// URLs |
| `duplicate-descriptions` | low | Duplicate meta descriptions |
| `duplicate-h1` | medium | Same H1 reused across many pages |
| `url-hygiene` | low | URLs use uppercase, underscores, spaces or query parameters |
| `deep-pages` | low | Many pages are 4+ clicks from the homepage |
| `no-hsts` | low | No Strict-Transport-Security header |
| `no-xcto` | low | Missing X-Content-Type-Options header |
| `no-xfo` | low | No clickjacking protection (X-Frame-Options / CSP frame-ancestors) |
| `no-referrer-policy` | info | No Referrer-Policy header |
| `x-powered-by` | info | Server reveals its stack via X-Powered-By |
| `no-compression` | medium | HTML is served without gzip/brotli compression |
| `mixed-content` | medium | HTTPS pages load http:// resources |
| `no-html-lang` | low | Missing lang attribute on <html> |
| `csr-empty-html` | high | Pages ship almost no text in the raw HTML (client-side rendering) |
| `hreflang-invalid-codes` | medium | Invalid hreflang language or region codes |
| `hreflang-no-self` | medium | hreflang sets omit the self-referencing entry |
| `hreflang-no-xdefault` | low | hreflang sets have no x-default |
| `broken-external-links` | low | Outbound links to dead pages |
| `heavy-html` | medium | HTML documents over 1.5 MB |
| `slow-ttfb` | medium | Server response over 2.5 s on many pages |

Pass markers: `robots-no-sitemap`, `robots-exists`, `sitemap-exists`, `https`, `www-redirect`, `broken-internal-urls`, `404-handling`, `canonical-present`, `hsts`, `viewport`, `ssr-content`, `hreflang-present`, `external-links`

## Structured data

| Check id | Severity | Finding |
|---|---|---|
| `schema-none` | high | No JSON-LD structured data anywhere on the crawled pages |
| `schema-coverage` | medium | Most pages have no structured data |
| `schema-invalid-json` | high | JSON-LD blocks with syntax errors |
| `schema-no-organization` | high | Homepage lacks Organization or LocalBusiness schema |
| `schema-no-sameas` | medium | Organization schema has no sameAs links |
| `schema-no-logo` | low | Organization schema has no logo |
| `schema-no-website` | low | No WebSite schema on homepage |
| `schema-missing-required` | medium | Schema items missing required properties |
| `schema-self-serving-rating` | high | Star ratings in schema without verifiable reviews |
| `schema-missing-recommended` | low | Schema items missing recommended properties |
| `schema-no-breadcrumbs` | low | Inner pages have no BreadcrumbList markup |
| `schema-articles-unmarked` | medium | Blog/article pages lack Article schema |
| `schema-products-unmarked` | high | Product pages lack Product schema |
| `schema-duplicate-organization` | low | Multiple Organization blocks on one page |

Pass markers: `schema-present`, `schema-organization`, `schema-breadcrumbs`

## Content, on-page and AEO

| Check id | Severity | Finding |
|---|---|---|
| `missing-title` | high | Pages without a <title> |
| `long-titles` | low | Titles over 65 characters get truncated |
| `short-titles` | low | Very short titles waste SERP space |
| `title-same-as-home` | medium | Inner pages reuse the homepage title |
| `long-descriptions` | info | Meta descriptions over 170 characters |
| `multiple-h1` | low | Pages with more than one H1 |
| `heading-hierarchy` | low | Heading levels skip (H1 to H3, H2 to H4) |
| `empty-headings` | low | Empty heading tags |
| `low-text-ratio` | low | Very low text-to-HTML ratio |
| `hard-to-read` | low | Content reads at college level or above |
| `long-sentences` | info | Average sentence length over 28 words |
| `generic-ai-filler` | low | Generic AI-style filler phrases detected |
| `no-about-page` | medium | No About page found |
| `no-contact-page` | medium | No Contact page found |
| `no-privacy-policy` | low | No privacy policy link found |
| `no-author-bylines` | medium | Articles without a visible author |
| `no-dates` | low | Articles without visible publish/update dates |
| `no-outbound-citations` | low | Articles cite no external sources |
| `images-legacy-format` | low | Few images use WebP or AVIF |
| `images-no-dimensions` | low | Images without width/height attributes |
| `weak-internal-linking` | medium | Pages with fewer than 5 internal links |
| `generic-anchor-text` | low | Generic anchor text (click here, read more) |
| `aeo-no-question-headings` | medium | Almost no question-style headings |
| `aeo-no-faq` | medium | No FAQ sections found on the site |
| `aeo-no-answer-first` | low | Opening paragraphs are long preambles |
| `aeo-no-structured-blocks` | low | Long pages with no lists or tables |

Pass markers: `h1-present`, `trust-pages`, `author-bylines`, `images-alt`, `aeo-question-headings`, `aeo-faq`

## AI visibility (GEO)

| Check id | Severity | Finding |
|---|---|---|
| `geo-no-llms-txt` | low | No /llms.txt file |
| `geo-llms-txt-malformed` | low | /llms.txt exists but does not follow the spec |
| `geo-nosnippet` | critical | Start page forbids snippets (nosnippet / max-snippet:0) |
| `geo-entity-name-inconsistent` | medium | Brand name spelled differently across schema, og:site_name and titles |
| `geo-no-kg-links` | low | sameAs has social links but no knowledge-graph anchors |
| `geo-csr-invisible` | high | Primary content is not in the HTML that AI crawlers receive |

Pass markers: `geo-retrieval-bots`, `geo-waf`, `geo-llms-txt`, `geo-llms-full`, `geo-entity-name`, `geo-markdown-negotiation`, `geo-ssr`

## Local SEO

| Check id | Severity | Finding |
|---|---|---|
| `local-no-schema` | high | No LocalBusiness schema |
| `local-schema-incomplete` | medium | LocalBusiness schema missing key properties |
| `local-schema-generic-type` | low | Schema uses generic LocalBusiness instead of a specific subtype |
| `local-multiple-phones` | medium | More than two phone numbers repeat across the site |
| `local-no-phone-home` | medium | No phone number visible on the homepage |
| `local-no-address` | medium | No street address found in page text |
| `local-no-map` | low | No Google Maps embed |
| `local-no-location-pages` | medium | No city or service-area pages found |
| `local-doorway-pages` | high | Location pages share identical copy |
| `local-no-reviews` | low | No review or testimonial content found |
| `local-no-gbp-link` | low | No link to the Google Business Profile |

Pass markers: `local-schema`, `local-phone`, `local-address`, `local-location-pages`

## Performance

| Check id | Severity | Finding |
|---|---|---|
| `cwv-no-field-data` | info | No real-user (CrUX) data for this site |
| `many-scripts` | low | Pages load 25+ external scripts |
| `no-lazy-loading` | low | Image-heavy pages without lazy loading |
| `huge-inline-css` | low | Pages with over 150 KB of inline CSS |

Pass markers: `cwv-field`, `psi-mobile`
