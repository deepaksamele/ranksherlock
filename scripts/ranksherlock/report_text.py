"""Client-language text used by the report: category labels, chapter introductions and the glossary."""

from __future__ import annotations

SEV_LABEL = {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low", "info": "Info"}
CAT_ORDER = ["technical", "content", "schema", "geo", "local", "ecommerce", "performance"]
CAT_LABELS = {"technical": "Technical SEO", "content": "Content, On-page and Answer Readiness", "schema": "Structured Data", "performance": "Performance and Core Web Vitals", "geo": "AI Visibility (GEO)", "local": "Local SEO", "ecommerce": "E-commerce"}
CAT_SHORT = {"technical": "Technical", "content": "Content and AEO", "schema": "Schema", "performance": "Performance", "geo": "AI Visibility", "local": "Local", "ecommerce": "E-commerce"}
CAT_INTRO = {
    "technical": "Technical SEO is the plumbing. It decides whether search engines and AI crawlers can reach every page, understand which version of a URL is the real one, and trust the site enough to index it. Problems here silently cap everything else: a brilliant article on a page that returns the wrong status code, or that is blocked in robots.txt, earns nothing. This chapter covers crawlability, indexability, redirects, canonical tags, duplicate pages, sitemap quality, security headers, mobile readiness and JavaScript rendering.",
    "content": "Content is what actually ranks and gets quoted. Google judges pages on experience, expertise, authoritativeness and trust (E-E-A-T), and answer engines such as ChatGPT, Perplexity and Google AI Overviews lift short, self-contained passages that answer a question directly. This chapter looks at titles, descriptions, headings, depth, readability, author and date signals, trust pages, images, internal links, and how answer-ready each page is.",
    "schema": "Structured data (schema.org JSON-LD) is a machine-readable summary of what each page is about: the organisation, its products, articles, FAQs, reviews and breadcrumbs. Search engines use it for rich results (stars, prices, FAQs, sitelinks) and AI systems use it to confirm facts about the business. Wrong or missing schema is a missed opportunity; self-serving or fake schema is a policy risk.",
    "geo": "AI visibility (often called GEO, generative engine optimisation) measures whether AI answer engines can fetch, understand and quote the site. Three layers matter: access (robots.txt, firewall rules and JavaScript rendering decide whether AI crawlers see anything), understanding (a consistent brand entity with Organization schema and profile links) and quotability (passages written as direct, factual, sourced answers). Training bots and retrieval bots are different: blocking training bots is a policy choice, blocking retrieval bots removes the site from AI answers.",
    "local": "Local SEO decides whether the business shows up when someone nearby searches for the service, including map results and 'near me' answers from AI assistants. It depends on a consistent name, address and phone number, LocalBusiness schema that matches the Google Business Profile, genuinely local pages for each service area, and visible reviews.",
    "ecommerce": "Online shops win or lose on category and product pages. This chapter checks whether those pages carry enough unique copy to rank, whether prices, reviews and buyer questions are visible to crawlers and AI shopping assistants, whether the catalogue is free of duplicate and demo listings, and whether the trust pages shoppers and Google Merchant Center expect (shipping, returns, secure payment) exist and are linked.",
    "performance": "Performance is user experience measured in numbers. Google's Core Web Vitals (how fast the main content appears, how quickly the page responds to taps, and how much the layout jumps around) are a ranking signal and a conversion driver. This chapter uses real-user data from Google when available, plus lab measurements and HTML-level checks that apply to every page crawled.",
}
LANE_LABEL = {"auto": "Developer can apply directly", "assisted": "Apply with review", "human": "Needs content or business input"}
OWNER_DEFAULT = {"technical": "Developer / hosting", "content": "Content team", "schema": "Developer", "geo": "Developer + content", "local": "Marketing", "performance": "Developer / hosting", "ecommerce": "Store team"}

GLOSSARY = [
    ("AEO (Answer Engine Optimisation)", "Writing and structuring pages so that search engines and AI assistants can lift a direct answer from them (featured snippets, People Also Ask, AI answers)."),
    ("AI Overviews / AI Mode", "Google's AI-generated answers shown above the classic results. They quote pages Googlebot can crawl and that allow snippets."),
    ("Canonical tag", "A line in the page's HTML that names the preferred URL when several URLs show the same content. Stops duplicate versions competing with each other."),
    ("Citability", "A 0 to 100 score RankSherlock assigns to a passage based on how self-contained, factual, structured and sourced it is. Higher means more likely to be quoted by an AI engine."),
    ("Core Web Vitals (CWV)", "Google's three user-experience metrics: LCP (loading), INP (responsiveness) and CLS (visual stability). Measured on real Chrome users over 28 days."),
    ("Crawl budget", "How many pages a search engine is willing to fetch from a site in a given period. Wasted on redirects, errors and duplicates."),
    ("Crawlability", "Whether a bot can reach a page: not blocked by robots.txt or a firewall, linked from somewhere, and returning a normal status code."),
    ("E-E-A-T", "Experience, Expertise, Authoritativeness and Trust: the qualities Google's quality raters look for. Shown through authors, credentials, sources, contact details and reviews."),
    ("GEO (Generative Engine Optimisation)", "Making a site visible and quotable inside AI answer engines such as ChatGPT, Perplexity, Claude and Google AI Overviews."),
    ("H1 / H2 / H3", "Heading levels in the page. The H1 is the page's headline; H2 and H3 structure the sections underneath. Answer engines use them to find the relevant passage."),
    ("hreflang", "Tags that tell search engines which language or country version of a page to show to which users."),
    ("Indexability", "Whether a crawled page is allowed into the search index: not noindex, not canonicalised elsewhere, returning 200."),
    ("JSON-LD", "The recommended format for structured data: a small block of JSON inside a script tag in the page."),
    ("LCP (Largest Contentful Paint)", "Time until the biggest visible element (usually the hero image or headline) is rendered. Good is under 2.5 seconds."),
    ("INP (Interaction to Next Paint)", "How long the page takes to respond visually after a tap or click. Good is under 200 ms."),
    ("CLS (Cumulative Layout Shift)", "How much the layout jumps while loading. Good is under 0.1."),
    ("llms.txt", "An emerging convention: a Markdown file at /llms.txt that gives AI agents a curated map of the most important pages. Cheap to add; no confirmed ranking weight yet."),
    ("Meta description", "The short summary under the title in search results. Google rewrites weak ones; a good one lifts click-through rate."),
    ("NAP", "Name, Address, Phone. Must be identical across the website, Google Business Profile and directories for local rankings."),
    ("noindex", "A directive (meta tag or HTTP header) that tells search engines not to list a page."),
    ("Orphan page", "A page that exists (often in the sitemap) but that no other page links to. Rarely crawled, rarely ranked, and unreachable by browsing."),
    ("PageSpeed Insights", "Google's free tool and API that reports Core Web Vitals field data and Lighthouse lab scores for a URL."),
    ("Retrieval bot vs training bot", "Retrieval bots (OAI-SearchBot, PerplexityBot, Claude-SearchBot, Googlebot, Bingbot) fetch pages to cite them in answers. Training bots (GPTBot, ClaudeBot, CCBot) collect data for future models. Blocking the first removes the site from AI answers; blocking the second is a policy choice."),
    ("Rich results", "Enhanced search listings (star ratings, prices, FAQs, breadcrumbs, sitelinks) that depend on valid structured data."),
    ("robots.txt", "A text file at the site root that tells crawlers which paths they may fetch. One wrong line can hide the whole site."),
    ("Schema.org", "The shared vocabulary for structured data types such as Organization, Product, Article, FAQPage and LocalBusiness."),
    ("Sitemap (XML)", "A file listing the URLs a site wants indexed, with optional last-modified dates. Should contain only final, 200-status, indexable URLs."),
    ("Soft 404", "A page that says 'not found' but returns status 200, so search engines index it as a real (thin) page."),
    ("Title tag", "The page title shown in the browser tab and as the blue link in search results. The strongest on-page ranking signal."),
    ("TTFB (Time to First Byte)", "How long the server takes to start sending the page. High TTFB caps every other speed metric."),
]
