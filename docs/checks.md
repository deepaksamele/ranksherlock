# RankSherlock checks

Generated from the engine source. Severity shown is the default; many checks escalate with scale.
Total distinct failing checks: 257.

## Technical SEO

| Check id | Severity | Finding |
|---|---|---|
| `robots-disallow-all` | critical | robots.txt blocks all crawlers from the whole site |
| `robots-no-sitemap` | low | robots.txt does not declare a Sitemap |
| `robots-blocks-assets` | medium | robots.txt blocks CSS or JS resources |
| `robots-syntax` | low | robots.txt contains lines that are not valid directives |
| `robots-crawl-traps` | low | Cart, checkout and search paths are not excluded in robots.txt |
| `robots-unreachable` | medium | robots.txt could not be fetched |
| `robots-missing` | low | No robots.txt file |
| `robots-blocks-internal-links` | medium | Internal links point to robots-blocked URLs |
| `sitemap-missing` | high | No XML sitemap found |
| `sitemap-child-errors` | medium | Sitemap index references files that do not load |
| `sitemap-url-limit` | critical | A sitemap file lists more than 50,000 URLs |
| `sitemap-size-limit` | high | A sitemap file is larger than 50 MB |
| `sitemap-duplicate-entries` | low | N duplicate URL entries across sitemap files |
| `sitemap-foreign-urls` | medium | Sitemap lists URLs on a different host |
| `sitemap-http-urls` | medium | Sitemap contains http:// URLs on an https site |
| `sitemap-no-lastmod` | low | Sitemap has no <lastmod> dates |
| `sitemap-lastmod-identical` | low | Every sitemap URL has the same <lastmod> date |
| `sitemap-lastmod-future` | low | Sitemap <lastmod> dates are in the future |
| `sitemap-non-200` | high | Sitemap includes URLs that return errors |
| `sitemap-redirected-urls` | medium | Sitemap lists URLs that redirect |
| `sitemap-noindex` | medium | Sitemap lists noindex pages |
| `sitemap-non-canonical` | medium | Sitemap lists URLs whose canonical points elsewhere |
| `sitemap-coverage-missing` | medium | N indexable pages are not listed in the sitemap |
| `orphan-pages` | varies | N sitemap pages have no internal links pointing to them |
| `crawl-incomplete` | info | Crawl stopped at N pages (N); sitemap lists N URLs |
| `ssl-error` | critical | TLS certificate errors on some URLs |
| `no-https` | critical | Site is served over HTTP, not HTTPS |
| `http-not-redirected` | high | http:// version does not redirect to https:// |
| `https-redirect-chain` | low | http:// reaches https:// through more than one redirect |
| `www-duplicate` | high | www and non-www both serve the site without redirecting |
| `redirect-chains` | varies | Redirect chains on N URLs (N with 3+ hops) |
| `redirect-temporary` | low | Internal links go through 302/307 temporary redirects |
| `internal-links-redirect` | medium | N internal links point to redirecting URLs |
| `redirect-loops` | high | Redirect loops detected |
| `meta-refresh-redirect` | medium | Pages use meta refresh redirects |
| `broken-internal-urls` | varies | N internal links lead to broken pages |
| `server-errors` | high | N URLs returned server errors (5xx) |
| `timeouts` | medium | N URLs timed out |
| `soft-404` | high | Soft 404 pages return status 200 |
| `404-returns-200` | high | Missing URLs return 200 instead of 404 |
| `custom-404-thin` | low | The 404 page offers no navigation or help |
| `homepage-noindex` | critical | Homepage is set to noindex |
| `page-noindex` | high | The audited page is set to noindex |
| `many-noindex` | medium | N crawled pages (N%) are noindex |
| `meta-nofollow` | medium | Pages carry a sitewide nofollow directive |
| `low-value-indexable` | medium | N utility pages (cart, login, search, tag or author archives) are indexable |
| `pagination-indexable` | low | N paginated pages are indexable with self-canonicals |
| `parameter-url-duplicates` | medium | N parameter URLs are indexable as separate pages |
| `missing-canonical` | varies | N pages have no canonical tag |
| `multiple-canonicals` | high | Pages declare more than one canonical |
| `canonical-to-homepage` | critical | N pages canonicalise to the homepage |
| `canonical-points-elsewhere` | medium | N pages canonicalise to a different URL |
| `canonical-cross-domain` | high | Canonical tags point to another domain |
| `canonical-http` | high | Canonical tags point to http:// URLs |
| `canonical-noindex-conflict` | medium | noindex pages also canonicalise elsewhere |
| `canonical-target-broken` | high | Canonical targets are broken or noindex |
| `duplicate-titles` | varies | Duplicate title tags on N pages |
| `duplicate-descriptions` | low | Duplicate meta descriptions on N pages |
| `duplicate-content` | varies | N pages have identical body text (N groups) |
| `url-trailing-slash` | low | N URLs serve both with and without a trailing slash |
| `url-whitespace-links` | low | N internal links contain spaces |
| `url-hygiene` | low | N URLs use uppercase, underscores or spaces |
| `url-length` | low | N URLs are longer than 115 characters |
| `url-numeric-slugs` | low | N URLs end in bare numeric IDs |
| `deep-pages` | low | N pages are 4+ clicks from the homepage |
| `no-hsts` | low | No Strict-Transport-Security header |
| `no-xcto` | low | Missing X-Content-Type-Options header |
| `no-xfo` | low | No clickjacking protection (X-Frame-Options / CSP frame-ancestors) |
| `no-csp` | info | No Content-Security-Policy header |
| `no-referrer-policy` | info | No Referrer-Policy header |
| `x-powered-by` | info | Server reveals its stack via X-Powered-By |
| `no-compression` | medium | HTML is served without gzip/brotli compression |
| `no-cache-headers` | info | HTML responses carry no Cache-Control, ETag or Last-Modified |
| `mixed-content` | medium | N HTTPS pages load http:// resources |
| `unsafe-target-blank` | info | Links open new tabs without rel=noopener |
| `no-viewport` | varies | N pages have no viewport meta tag |
| `viewport-zoom-lock` | medium | N pages disable pinch-zoom |
| `no-html-lang` | low | Missing lang attribute on <html> |
| `invalid-html-lang` | low | Invalid lang attribute values |
| `amp-in-use` | info | AMP markup on N pages |
| `csr-empty-html` | high | Pages ship almost no text in the raw HTML (client-side rendering) |
| `csr-some-pages` | medium | N pages are JavaScript shells with no server-rendered text |
| `hreflang-invalid-codes` | high | Invalid hreflang language or region codes |
| `hreflang-no-self` | high | hreflang sets omit the self-referencing entry |
| `hreflang-no-return` | high | hreflang links are not reciprocated |
| `hreflang-no-xdefault` | low | hreflang sets have no x-default |
| `hreflang-protocol` | medium | hreflang URLs use http:// on an https site |
| `hreflang-on-noncanonical` | high | hreflang declared on pages that canonicalise elsewhere |
| `broken-external-links` | low | N outbound links lead to dead pages |
| `heavy-html` | medium | N HTML documents are over 1.5 MB |
| `large-html` | low | N HTML documents are over 500 KB |
| `slow-ttfb` | medium | Server response over 2.5 s on N pages |
| `empty-links` | low | Links without text or label on N pages |
| `unlabeled-inputs` | low | Form fields without labels on N pages |
| `no-favicon` | low | No favicon declared |
| `no-skip-link` | info | No skip-to-content link |
| `no-analytics` | low | No analytics or tag manager detected |
| `legacy-ua-tag` | low | Legacy Universal Analytics tag still loads |

Pass markers: `robots-disallow-all`, `robots-no-sitemap`, `robots-blocks-assets`, `robots-crawl-traps`, `robots-exists`, `sitemap-exists`, `sitemap-lastmod`, `sitemap-urls-clean`, `sitemap-coverage`, `orphan-pages`, `https`, `http-redirect`, `www-redirect`, `redirect-chains`, `broken-internal-urls`, `soft-404`, `404-handling`, `custom-404`, `homepage-indexable`, `canonical-present`, `duplicate-titles`, `duplicate-content`, `crawl-depth`, `hsts`, `compression`, `mixed-content`, `viewport`, `html-lang`, `ssr-content`, `spa-ssr`, `hreflang-present`, `external-links`, `html-size`, `server-response`, `analytics`, `consent-banner`

## Structured data

| Check id | Severity | Finding |
|---|---|---|
| `schema-microdata-only` | medium | Structured data exists only as Microdata, not JSON-LD |
| `schema-none` | high | No JSON-LD structured data anywhere on the crawled pages |
| `schema-coverage` | medium | N content pages have no structured data |
| `schema-invalid-json` | high | JSON-LD syntax errors on N pages |
| `schema-no-organization` | high | Homepage lacks Organization or LocalBusiness schema |
| `schema-no-sameas` | medium | Organization schema has no sameAs links |
| `schema-no-logo` | low | Organization schema has no logo |
| `schema-no-contactpoint` | low | Organization schema has no contactPoint or telephone |
| `schema-organization-thin` | low | Organization schema is thin (no address, description or founding date) |
| `schema-no-website` | low | No WebSite schema on homepage |
| `schema-no-searchaction` | info | WebSite schema has no SearchAction although the site has search |
| `schema-self-serving-rating` | high | Star ratings in schema without verifiable reviews on N items |
| `schema-placeholders` | high | Schema contains placeholder or template text |
| `schema-http-context` | low | @context uses http://schema.org on N pages |
| `schema-relative-urls` | low | Schema uses relative URLs for url, logo or image |
| `schema-invalid-dates` | medium | Schema dates are not in ISO 8601 format |
| `schema-faq-not-visible` | medium | FAQPage schema questions do not appear in the visible page text |
| `schema-missing-recommended` | low | Schema items miss recommended properties (N gaps) |
| `schema-entity-inconsistent` | medium | Organization blocks use different names across pages |
| `schema-entity-url-inconsistent` | low | Organization url differs across schema blocks |
| `schema-no-breadcrumbs` | low | N inner pages have no BreadcrumbList markup |
| `schema-articles-unmarked` | medium | N blog/article pages lack Article schema |
| `schema-no-person-author` | low | Article schema does not identify the author as a Person |
| `schema-products-unmarked` | high | N product pages lack Product schema |
| `schema-offers-incomplete` | medium | Product offers lack price, currency or availability |
| `schema-no-shipping-returns` | low | No shipping or return policy structured data |
| `schema-no-videoobject` | low | N pages embed video without VideoObject schema |
| `schema-X-deprecated` | varies | N schema present on N items |
| `schema-faqpage-note` | info | FAQPage schema present on N items |
| `schema-type-opportunities` | low | Schema types expected for a N site are missing: N |
| `schema-duplicate-organization` | low | Multiple Organization blocks on N pages |

Pass markers: `schema-present`, `schema-coverage`, `schema-valid-json`, `schema-organization`, `schema-sameas`, `schema-required`, `schema-breadcrumbs`, `schema-articles`, `schema-products`

## Content, on-page and AEO

| Check id | Severity | Finding |
|---|---|---|
| `missing-title` | high | N pages have no <title> |
| `long-titles` | low | N titles are over 65 characters |
| `short-titles` | low | N titles are under 30 characters |
| `title-same-as-home` | medium | N inner pages reuse the homepage title |
| `title-brand-doubled` | low | Brand name appears twice in N titles |
| `title-cms-default` | medium | N titles are CMS defaults or archive labels |
| `missing-description` | varies | N pages have no meta description |
| `long-descriptions` | info | N meta descriptions are over 170 characters |
| `short-descriptions` | low | N meta descriptions are under 70 characters |
| `missing-h1` | varies | N pages have no H1 |
| `multiple-h1` | low | N pages have more than one H1 |
| `heading-hierarchy` | low | Heading levels skip on N pages (H1 to H3, H2 to H4) |
| `empty-headings` | low | Empty heading tags on N pages |
| `no-subheadings` | low | N long pages have no H2 subheadings |
| `ui-chrome-headings` | low | Headings used for interface chrome (menu, cart, search) |
| `low-text-ratio` | low | Very low text-to-HTML ratio on N pages |
| `placeholder-text` | high | Placeholder or template text on N pages |
| `template-duplicate-copy` | medium | N pages share an identical opening paragraph (N templateN) |
| `hard-to-read` | low | N pages read at college level or above |
| `long-sentences` | info | Average sentence over 28 words on N pages |
| `generic-ai-filler` | low | Generic AI-style filler phrases on N pages |
| `no-table-of-contents` | info | N very long pages have no table of contents |
| `no-about-page` | medium | No About page found |
| `no-contact-page` | medium | No Contact page found |
| `no-privacy-policy` | low | No privacy policy link found |
| `no-terms-page` | low | No terms of service page found |
| `no-contact-on-home` | low | No phone or email visible on the homepage |
| `no-social-links` | low | No social profile links on the homepage |
| `no-author-bylines` | medium | N articles have no visible author |
| `no-dates` | low | N articles have no visible publish or update date |
| `stale-content` | low | N articles were last dated N or earlier |
| `no-outbound-citations` | low | N of N articles cite no external sources |
| `articles-no-media` | info | N articles have no images or video |
| `ymyl-no-reviewer` | medium | YMYL content shows no expert review line |
| `no-social-proof` | low | No reviews, ratings or testimonials visible |
| `images-alt-poor` | low | N images have filename-style or generic alt text |
| `images-legacy-format` | low | Only N% of images use WebP or AVIF |
| `images-no-dimensions` | low | N% of images lack width/height attributes |
| `images-no-srcset` | low | Images are not responsive (no srcset or <picture>) |
| `hero-image-lazy` | medium | The first (hero) image is lazy-loaded on N pages |
| `images-template-missing-alt` | low | Template images (logo, icons) lack alt text on every page |
| `weak-internal-linking` | medium | N pages have fewer than 5 internal links |
| `low-link-density` | low | N long pages carry few contextual links |
| `generic-anchor-text` | low | N links use generic anchor text |
| `mega-menu-bloat` | low | Pages carry N internal links on average |
| `nofollow-internal-links` | low | N internal links carry rel=nofollow |
| `excessive-external-links` | info | N pages link out more than 100 times |
| `aeo-no-question-headings` | medium | Only N of N key pages use question-style headings |
| `aeo-no-faq` | medium | No FAQ sections found on the site |
| `aeo-no-central-faq` | info | No dedicated FAQ or help page |
| `aeo-no-answer-first` | low | Opening paragraphs are long preambles on N key pages |
| `aeo-no-definition-opening` | low | Key pages do not open with a definition-style sentence |
| `aeo-no-structured-blocks` | low | N long pages have no lists or tables |
| `aeo-no-comparison-tables` | info | No comparison or specification tables found |
| `low-citability` | medium | Average passage citability score is N/100 |
| `missing-og-tags` | low | N pages lack Open Graph title or image |
| `og-generic` | info | og:title is 'Home' on N inner pages |
| `missing-twitter-card` | info | No Twitter/X card meta tags |

Pass markers: `title-present`, `title-length`, `description-present`, `h1-present`, `content-depth`, `trust-pages`, `social-links`, `author-bylines`, `outbound-citations`, `images-alt`, `images-modern-format`, `aeo-question-headings`, `aeo-faq`, `citability`, `og-tags`

## AI visibility (GEO)

| Check id | Severity | Finding |
|---|---|---|
| `geo-retrieval-bots-blocked` | varies | robots.txt blocks answer-engine crawlers: N |
| `geo-training-bots-blocked` | info | Training crawlers blocked: N |
| `geo-content-signal-blocks-ai` | high | Content-Signal line opts out of AI answers (N) |
| `geo-content-signal-conflict` | low | Content-Signal allows AI training while robots.txt blocks training bots |
| `geo-noai-directive` | info | noai / noimageai directive on N pages |
| `geo-hidden-ai-instructions` | info | Text that reads like instructions to AI systems on N pages |
| `geo-waf-blocks-ai-bots` | high | Firewall/CDN challenges AI crawlers: N |
| `geo-waf-blocks-ai-bots-inner` | high | Inner pages challenge AI crawlers: N |
| `geo-probe-inconclusive` | info | Bot probes were inconclusive for N (rate limit or server error) |
| `geo-bots-get-less-content` | medium | Bots receive a much shorter page than browsers: N |
| `geo-no-llms-txt` | low | No /llms.txt file |
| `geo-llms-txt-malformed` | low | /llms.txt exists but does not follow the spec |
| `geo-nosnippet` | critical | Start page forbids snippets (nosnippet / max-snippet:0) |
| `geo-nosnippet-pages` | medium | N pages forbid snippets |
| `geo-entity-name-inconsistent` | medium | Brand name spelled differently across schema, og:site_name and titles |
| `geo-no-kg-links` | low | sameAs has social links but no knowledge-graph anchors |
| `geo-entity-facts-thin` | low | Homepage and About page state few verifiable facts about the business (N) |
| `geo-wikidata-not-linked` | low | A Wikidata item exists but the site does not link it in sameAs |
| `geo-no-wikidata` | low | No Wikidata item found for 'N' |
| `geo-no-feed` | low | No RSS/Atom feed found |
| `geo-csr-invisible` | high | Primary content is not in the HTML that AI crawlers receive |
| `geo-no-answer-blocks` | medium | Only N of N content pages open with an answer-sized paragraph |
| `geo-few-citable-facts` | low | Only N of N content pages contain numbers, dates or statistics |

Pass markers: `geo-retrieval-bots`, `geo-training-bots`, `geo-content-signal`, `geo-waf`, `geo-llms-txt`, `geo-llms-full`, `geo-snippets-allowed`, `geo-entity-name`, `geo-kg-links`, `geo-entity-facts`, `geo-wikidata`, `geo-feed`, `geo-agents-md`, `geo-rsl`, `geo-markdown-negotiation`, `geo-ssr`, `geo-answer-blocks`

## Local SEO

| Check id | Severity | Finding |
|---|---|---|
| `local-no-schema` | high | No LocalBusiness schema |
| `local-schema-incomplete` | medium | LocalBusiness schema is missing N key properties |
| `local-schema-generic-type` | low | Schema uses generic LocalBusiness instead of a specific subtype |
| `local-no-areaserved` | low | LocalBusiness schema does not declare areaServed |
| `local-no-gbp-in-sameas` | low | Google Business Profile URL is not in LocalBusiness sameAs |
| `local-nap-schema-mismatch` | medium | Phone number in schema differs from the numbers shown on the pages |
| `local-multiple-phones` | medium | N different phone numbers repeat across the site |
| `local-no-phone-home` | medium | No phone number visible on the homepage |
| `local-address-schema-only` | low | The street address is in schema but not recognisable in the visible page text |
| `local-no-address` | medium | No street address found in page text |
| `local-no-hours` | low | Opening hours are not shown as text |
| `local-no-map` | low | No Google Maps embed |
| `local-no-location-pages` | medium | No city or service-area pages found |
| `local-doorway-pages` | high | N location pages share identical copy |
| `local-thin-location-pages` | medium | N location pages have under 300 words |
| `local-location-page-scale` | medium | N location pages: scale that needs per-page uniqueness and a Business Profile per location |
| `local-no-reviews` | low | No review or testimonial content found |
| `local-no-gbp-link` | low | No link to the Google Business Profile |

Pass markers: `local-schema`, `local-schema-complete`, `local-phone`, `local-address`, `local-hours`, `local-map`, `local-location-pages`, `local-reviews`, `local-gbp-link`

## E-commerce

| Check id | Severity | Finding |
|---|---|---|
| `ecom-thin-products` | medium | N product pages have under 120 words of copy |
| `ecom-duplicate-product-copy` | medium | N products share identical descriptions |
| `ecom-no-visible-price` | low | N product pages show no price in the HTML |
| `ecom-no-product-reviews` | low | N product pages show no reviews |
| `ecom-no-product-faq` | low | Product pages have no buyer Q&A section |
| `ecom-duplicate-listings` | medium | N product URLs look like duplicated listings |
| `ecom-category-no-copy` | medium | N category pages have no descriptive copy |
| `ecom-demo-collections` | low | Default or demo collections are indexable |
| `ecom-no-policy-pages` | medium | No N policy page linked |
| `ecom-no-trust-signals` | info | No payment or security trust signals visible |

Pass markers: `ecom-product-copy`, `ecom-category-copy`, `ecom-policy-pages`

## Performance

| Check id | Severity | Finding |
|---|---|---|
| `cwv-field-poor` | high | Core Web Vitals fail in real-user data: N |
| `cwv-field-needs-improvement` | medium | Core Web Vitals need improvement: N |
| `ttfb-field-poor` | medium | Real-user time to first byte is N ms |
| `cwv-no-field-data` | info | No real-user (CrUX) data for this site |
| `psi-mobile-poor` | high | Mobile Lighthouse performance score is N/100 |
| `psi-mobile-average` | medium | Mobile Lighthouse performance score is N/100 |
| `page-weight` | medium | Homepage weighs N MB |
| `dom-size` | low | Homepage DOM has N nodes |
| `tbt-high` | medium | Total blocking time is N ms |
| `psi-inner-pages-poor` | medium | N sampled inner page templates score under 50 on mobile |
| `many-scripts` | low | Pages load N external scripts on average |
| `render-blocking-scripts` | medium | N render-blocking scripts in <head> on most pages |
| `third-party-scripts` | low | Homepage loads scripts from N third-party hosts |
| `no-lazy-loading` | low | N image-heavy pages do not lazy-load images |
| `huge-inline-css` | low | N pages carry over 150 KB of inline CSS |
| `dom-size-html` | low | N pages have more than 2,500 HTML elements |
| `no-cdn` | info | No CDN or edge cache detected on HTML responses |
| `no-preload-hints` | info | No preload or preconnect hints on the homepage |
| `no-fetchpriority` | info | Hero image is not marked fetchpriority=high |

Pass markers: `cwv-field`, `psi-mobile`, `render-blocking-scripts`, `cdn`, `image-weight`
