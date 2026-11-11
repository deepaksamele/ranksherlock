"""Structured data detection and validation (JSON-LD first, microdata noted)."""

from __future__ import annotations

import re
from collections import Counter

from .business import page_type
from .findings import Collector

REQUIRED = {
    "Organization": ["name", "url"],
    "LocalBusiness": ["name", "address", "telephone"],
    "Product": ["name", "image", "offers"],
    "ProductGroup": ["name", "hasVariant"],
    "Offer": ["price|priceSpecification|lowPrice", "priceCurrency|priceSpecification"],
    "Article": ["headline", "datePublished", "author", "image"],
    "FAQPage": ["mainEntity"],
    "BreadcrumbList": ["itemListElement"],
    "WebSite": ["name", "url"],
    "WebPage": ["name"],
    "Person": ["name"],
    "Event": ["name", "startDate", "location"],
    "Recipe": ["name", "image", "recipeIngredient"],
    "VideoObject": ["name", "thumbnailUrl", "uploadDate", "description"],
    "JobPosting": ["title", "datePosted", "hiringOrganization", "jobLocation", "description"],
    "Service": ["name", "provider"],
    "SoftwareApplication": ["name", "applicationCategory", "offers", "operatingSystem"],
    "Course": ["name", "provider", "description"],
    "HowTo": ["name", "step"],
    "Review": ["itemReviewed", "reviewRating", "author"],
    "AggregateRating": ["ratingValue", "reviewCount|ratingCount"],
    "MerchantReturnPolicy": ["returnPolicyCategory", "applicableCountry"],
}
RECOMMENDED = {
    "Organization": ["logo", "sameAs", "contactPoint", "address", "telephone"],
    "LocalBusiness": ["openingHoursSpecification", "geo", "priceRange", "image", "url", "sameAs", "areaServed"],
    "Product": ["description", "brand", "sku", "aggregateRating", "review"],
    "Offer": ["availability", "url"],
    "Article": ["dateModified", "publisher", "mainEntityOfPage", "description"],
    "Person": ["url", "sameAs", "jobTitle", "image"],
    "WebSite": ["potentialAction"],
    "FAQPage": [],
    "Service": ["areaServed", "description", "offers"],
    "VideoObject": ["duration", "contentUrl|embedUrl"],
}
LOCAL_TYPES = {"LocalBusiness", "Restaurant", "Store", "Dentist", "Plumber", "Electrician", "Attorney", "LegalService", "MedicalBusiness", "AutoRepair", "HomeAndConstructionBusiness", "RoofingContractor", "HVACBusiness", "RealEstateAgent", "FinancialService", "ProfessionalService", "HealthAndBeautyBusiness", "LodgingBusiness", "Hotel", "Physician", "ChildCare", "School", "EducationalOrganization", "GeneralContractor", "MovingCompany", "Locksmith", "Florist", "Bakery", "CafeOrCoffeeShop", "BarOrPub", "FoodEstablishment", "SportsActivityLocation", "ExerciseGym", "BeautySalon", "HairSalon", "DaySpa", "NailSalon", "VeterinaryCare", "AnimalShelter", "AutoDealer", "AutoBodyShop", "InsuranceAgency", "TravelAgency", "Pharmacy", "Hospital", "MedicalClinic", "Optician", "AccountingService", "Architect", "HousePainter", "Plumber", "Electrician", "DryCleaningOrLaundry", "TaxiService", "Library", "Museum", "GovernmentOffice"}
ARTICLE_TYPES = {"Article", "NewsArticle", "BlogPosting", "TechArticle", "ScholarlyArticle", "Report"}
DEPRECATED = {
    "HowTo": ("info", "HowTo rich results were removed by Google in September 2023; keep only if useful for AI extraction."),
    "SpecialAnnouncement": ("low", "SpecialAnnouncement rich results ended 31 July 2025; the markup is now dead weight."),
    "CourseInfo": ("low", "Course info rich results were retired in June 2025."),
    "EstimatedSalary": ("low", "Estimated salary rich results were retired in June 2025."),
    "LearningVideo": ("low", "Learning video rich results were retired in June 2025."),
    "ClaimReview": ("low", "Fact-check rich results were retired in June 2025."),
    "VehicleListing": ("low", "Vehicle listing structured data was retired in June 2025."),
}
PLACEHOLDER_RE = re.compile(r"\[(?i:business|company|city|insert|your|name|url|phone)[^\]]{0,30}\]|(?i:lorem ipsum)|//(www\.)?example\.(com|org)|\bREPLACE_ME\b|\bTODO:|\bYOUR_(NAME|URL|PHONE|BUSINESS|COMPANY)\b")
EXPECTED_BY_TYPE = {
    "e-commerce": ["Product", "BreadcrumbList", "Organization"],
    "publisher / media": ["Article|NewsArticle|BlogPosting", "Person", "Organization"],
    "local business": ["LocalBusiness", "Service|Product", "BreadcrumbList"],
    "SaaS / software": ["SoftwareApplication|Product", "Organization", "FAQPage"],
    "agency / services": ["Organization|ProfessionalService", "Service", "Person"],
    "education": ["EducationalOrganization|Organization", "Course"],
    "healthcare": ["MedicalBusiness|Physician|Hospital|LocalBusiness", "Person"],
    "real estate": ["RealEstateAgent|Organization|LocalBusiness", "RealEstateListing|Residence|Product|Offer"],
    "home services / construction": ["LocalBusiness|HomeAndConstructionBusiness|GeneralContractor|ProfessionalService|Organization", "Service"],
    "restaurant / food": ["Restaurant|FoodEstablishment|LocalBusiness", "Menu|MenuItem"],
    "legal": ["LegalService|Attorney|LocalBusiness", "Person"],
    "finance": ["FinancialService|Organization", "FAQPage"],
}


def _types(item: dict) -> list[str]:
    t = item.get("@type")
    if isinstance(t, list):
        return [str(x) for x in t]
    return [str(t)] if t else []


def _has(item: dict, prop: str) -> bool:
    for alt in prop.split("|"):
        v = item.get(alt)
        if v is None:
            continue
        if isinstance(v, (list, dict, str)) and len(v) == 0:
            continue
        return True
    return False


def _base_type(t: str) -> str:
    if t in LOCAL_TYPES:
        return "LocalBusiness"
    if t in ARTICLE_TYPES:
        return "Article"
    if t in ("Corporation", "OnlineStore", "NGO", "Brand"):
        return "Organization"
    return t


def _walk(item, depth=0):
    """Yield nested typed objects (offers, author, aggregateRating ...)."""
    if depth > 4 or not isinstance(item, dict):
        return
    yield item
    for v in item.values():
        if isinstance(v, dict) and v.get("@type"):
            yield from _walk(v, depth + 1)
        elif isinstance(v, list):
            for x in v:
                if isinstance(x, dict) and x.get("@type"):
                    yield from _walk(x, depth + 1)


def analyze_schema(pages: list, home_url: str, business: dict | None = None) -> dict:
    c = Collector("schema")
    business = business or {}
    btype = business.get("business_type", "")
    html_pages = [p for p in pages if p.status == 200 and "text/html" in (p.content_type or "")]
    pages_with = [p for p in html_pages if p.json_ld]
    pages_without = [p for p in html_pages if not p.json_ld and not p.microdata_types]
    all_types: Counter = Counter()
    for p in pages_with:
        for item in p.json_ld:
            for t in _types(item):
                all_types[t] += 1
    microdata_pages = [p for p in html_pages if p.microdata_types and not p.json_ld]

    from urllib.parse import urlparse as _up

    home = next((p for p in html_pages if p.url == home_url or p.final_url.rstrip("/") == home_url.rstrip("/")), None)
    if home is not None and _up(home.final_url).path not in ("", "/"):
        home = None

    if not pages_with:
        if microdata_pages:
            c.add("schema-microdata-only", "medium", "Structured data exists only as Microdata, not JSON-LD", "Google recommends JSON-LD; Microdata is fragile when templates change and harder for AI systems to read.", "Add JSON-LD blocks (keep Microdata if the theme needs it, but make JSON-LD the source of truth).", evidence=[f"{p.url}: {', '.join(p.microdata_types[:3])}" for p in microdata_pages[:3]], affected_count=len(microdata_pages), effort="medium")
        else:
            c.add("schema-none", "high", "No JSON-LD structured data anywhere on the crawled pages", "Without schema, Google cannot show rich results and answer engines have no machine-readable entity facts.", "Add Organization (or LocalBusiness) + WebSite on the homepage, BreadcrumbList sitewide, and page-type schema (Article, Product, Service, FAQPage) where relevant.", affected_count=len(html_pages), effort="medium")
    else:
        c.passed("schema-present", f"JSON-LD found on {len(pages_with):,} of {len(html_pages):,} pages ({', '.join(t for t, _ in all_types.most_common(6))})")
        content_without = [p for p in pages_without if page_type(p.url, p) not in ("cart", "search", "pagination", "tag", "legal")]
        if content_without and len(content_without) > len(html_pages) * 0.4:
            c.add("schema-coverage", "medium", f"{len(content_without):,} content pages have no structured data", "Schema only helps the pages that carry it.", "Extend page-type schema (Article/Product/Service) across templates, not just the homepage.", evidence=[p.url for p in content_without[:6]], affected_count=len(content_without), pages=[p.url for p in content_without[:300]])
        else:
            c.passed("schema-coverage", "Most content pages carry structured data")

    err_pages = [p for p in html_pages if p.json_ld_errors]
    if err_pages:
        c.add("schema-invalid-json", "high", f"JSON-LD syntax errors on {len(err_pages):,} pages", "Invalid JSON is ignored completely by Google, so the markup might as well not exist.", "Validate with the Rich Results Test and fix the JSON (trailing commas, unescaped quotes, bad nesting).", evidence=[f"{p.url}: {p.json_ld_errors[0]}" for p in err_pages[:6]], affected_count=len(err_pages), pages=[p.url for p in err_pages[:200]], effort="low")
    else:
        if pages_with:
            c.passed("schema-valid-json", "All JSON-LD blocks parse")

    # ---------------------------------------------------------- homepage entity
    org_names: Counter = Counter()
    org_urls: Counter = Counter()
    if home is not None:
        home_types = {t for item in home.json_ld for t in _types(item)}
        has_org = bool(home_types & ({"Organization", "Corporation", "OnlineStore", "NGO"} | LOCAL_TYPES))
        if not has_org:
            c.add("schema-no-organization", "high", "Homepage lacks Organization or LocalBusiness schema", "This is the entity anchor that search engines and AI models use to understand who the site belongs to (name, logo, sameAs profiles).", "Add an Organization (or specific LocalBusiness subtype) JSON-LD block on the homepage with name, url, logo, sameAs and contactPoint.", evidence=[f"homepage types: {', '.join(sorted(home_types)) or 'none'}"], effort="low")
        else:
            c.passed("schema-organization", "Homepage declares an Organization/LocalBusiness entity")
            org = next((i for i in home.json_ld if set(_types(i)) & ({"Organization", "Corporation", "OnlineStore", "NGO"} | LOCAL_TYPES)), {})
            if org and not _has(org, "sameAs"):
                c.add("schema-no-sameas", "medium", "Organization schema has no sameAs links", "sameAs links to LinkedIn, Wikipedia, Wikidata, Crunchbase and social profiles are how AI systems disambiguate your brand from others with similar names.", "Add a sameAs array with every official profile URL.", effort="low")
            else:
                c.passed("schema-sameas", "Organization sameAs links present")
            if org and not _has(org, "logo"):
                c.add("schema-no-logo", "low", "Organization schema has no logo", "Logo powers the knowledge panel and brand display in search.", "Add a logo property with an absolute https URL to a square-ish PNG/SVG.", effort="low")
            if org and not _has(org, "contactPoint") and not _has(org, "telephone"):
                c.add("schema-no-contactpoint", "low", "Organization schema has no contactPoint or telephone", "Contact details in schema feed knowledge panels and AI assistants answering 'how do I contact X'.", "Add contactPoint (telephone, contactType, areaServed) or telephone and email.", effort="low")
            if org and btype not in ("local business",) and not _has(org, "address") and not _has(org, "foundingDate") and not _has(org, "description"):
                c.add("schema-organization-thin", "low", "Organization schema is thin (no address, description or founding date)", "A richer entity record (description, address, foundingDate, founder, numberOfEmployees) gives AI systems verifiable facts to repeat.", "Expand the Organization block with the facts shown on the About page.", effort="low")
        if "WebSite" not in home_types:
            c.add("schema-no-website", "low", "No WebSite schema on homepage", "WebSite schema names the site and can enable sitelinks search box.", "Add a WebSite block with name, url and (optionally) potentialAction SearchAction.", effort="low")
        else:
            ws = next((i for i in home.json_ld if "WebSite" in _types(i)), {})
            if ws and not _has(ws, "potentialAction") and any(p.has_search_form for p in html_pages[:50]):
                c.add("schema-no-searchaction", "info", "WebSite schema has no SearchAction although the site has search", "SearchAction is what makes the sitelinks search box eligible.", "Add potentialAction: SearchAction with the search URL template.", effort="low")

    # ------------------------------------------------------- property checks
    missing_required = []
    missing_recommended: Counter = Counter()
    fake_rating = []
    placeholders = []
    http_context = []
    relative_urls = []
    bad_dates = []
    faq_mismatch = []
    product_pages_ok = 0
    for p in pages_with:
        seen_blocks = Counter()
        for top in p.json_ld:
            ctx = str(top.get("@context", ""))
            if ctx.startswith("http://"):
                http_context.append(p.url)
            blob = str(top)[:4000]
            if PLACEHOLDER_RE.search(blob):
                placeholders.append(f"{p.url}: {PLACEHOLDER_RE.search(blob).group(0)}")
            key = tuple(sorted(_types(top))) + (str(top.get("name") or top.get("headline") or "")[:40],)
            seen_blocks[key] += 1
            for item in _walk(top):
                for t in _types(item):
                    base = _base_type(t)
                    nested = item is not top
                    # Nested summaries (blog posts inside a Blog list, an author inside an Article) are not held
                    # to the full required set; only offers and ratings are validated when nested.
                    check_props = (not nested) or base in ("Offer", "AggregateRating", "Review")
                    req = (REQUIRED.get(base) or REQUIRED.get(t)) if check_props else None
                    if req:
                        miss = [r for r in req if not _has(item, r)]
                        if miss:
                            missing_required.append(f"{p.url}: {t} missing {', '.join(miss)}")
                    for r in (RECOMMENDED.get(base, []) if check_props else []):
                        if not _has(item, r):
                            missing_recommended[f"{base}.{r}"] += 1
                    for prop in ("url", "logo", "image"):
                        v = item.get(prop)
                        vals = v if isinstance(v, list) else [v]
                        for x in vals:
                            s = x.get("url") if isinstance(x, dict) else x
                            if isinstance(s, str) and s and not s.startswith(("http://", "https://", "data:")):
                                relative_urls.append(f"{p.url}: {t}.{prop}={s[:60]}")
                    for prop in ("datePublished", "dateModified", "startDate", "uploadDate", "datePosted"):
                        v = item.get(prop)
                        if isinstance(v, str) and v and not re.match(r"^\d{4}-\d{2}-\d{2}", v):
                            bad_dates.append(f"{p.url}: {t}.{prop}='{v[:30]}'")
                    if base in ("Organization", "LocalBusiness") and item.get("name") and not nested:
                        org_names[str(item["name"]).strip()] += 1
                        if item.get("url"):
                            org_urls[str(item["url"]).strip().rstrip("/")] += 1
                    if "aggregateRating" in item and isinstance(item["aggregateRating"], dict):
                        ar = item["aggregateRating"]
                        rc = ar.get("reviewCount") or ar.get("ratingCount")
                        has_reviews = _has(item, "review")
                        if base in ("Organization", "LocalBusiness"):
                            fake_rating.append(f"{p.url}: self-serving {t} rating (Google forbids aggregateRating on the organisation itself)")
                        elif not has_reviews and (rc is None or str(rc).strip() in ("", "0")):
                            fake_rating.append(f"{p.url}: {t} aggregateRating without review count or review objects")
                        elif not p.has_reviews_text:
                            fake_rating.append(f"{p.url}: {t} rating in schema but no reviews visible in page text")
                    if t == "FAQPage" and item is top:
                        # page.py compared every FAQ question against the full visible text at crawl time
                        if p.faq_schema_questions >= 2 and p.faq_schema_hidden > p.faq_schema_questions * 0.5:
                            faq_mismatch.append(f"{p.url}: {p.faq_schema_hidden} of {p.faq_schema_questions} FAQ schema questions do not appear in the visible text")
                    if t == "Product":
                        offers = item.get("offers")
                        off = offers[0] if isinstance(offers, list) and offers else offers
                        if isinstance(off, dict) and _has(off, "price") and _has(off, "priceCurrency") and _has(off, "availability"):
                            product_pages_ok += 1
        dup = [k for k, v in seen_blocks.items() if v > 1]
        if dup:
            missing_recommended["duplicate-blocks"] += 0
    if missing_required:
        by_gap = Counter(m.split(": ", 1)[1] for m in missing_required)
        c.add("schema-missing-required", "medium" if len(missing_required) > 2 else "low", f"{len(missing_required):,} schema items miss required properties ({'; '.join(f'{k} x{v}' for k, v in by_gap.most_common(3))})", "Google only shows rich results when required properties are present; AI extraction also degrades.", "Fill in the missing properties listed in the evidence.", evidence=missing_required[:8], affected_count=len(missing_required))
    else:
        if pages_with:
            c.passed("schema-required", "All typed items carry their required properties")
    if fake_rating:
        c.add("schema-self-serving-rating", "high", f"Star ratings in schema without verifiable reviews on {len(fake_rating):,} items", "Google's guidelines prohibit self-serving aggregateRating on Organization/LocalBusiness and ratings without real reviews. This can trigger a manual action.", "Remove the aggregateRating or back it with real, visible, dated review objects (or move ratings to a third-party platform).", evidence=fake_rating[:6], affected_count=len(fake_rating), effort="low")
    if placeholders:
        c.add("schema-placeholders", "high", "Schema contains placeholder or template text", "Placeholders such as '[Business Name]' or example.com publish false facts about the business.", "Replace every placeholder with real values.", evidence=placeholders[:5], affected_count=len(placeholders), effort="low")
    if http_context:
        c.add("schema-http-context", "low", f"@context uses http://schema.org on {len(set(http_context)):,} pages", "Works today, but https://schema.org is the canonical context and some validators warn.", "Change @context to https://schema.org.", affected_count=len(set(http_context)), effort="low")
    if relative_urls:
        c.add("schema-relative-urls", "low", "Schema uses relative URLs for url, logo or image", "Structured data must use absolute URLs; relative ones are often unresolvable to Google.", "Use full https:// URLs in schema.", evidence=relative_urls[:4], affected_count=len(relative_urls), effort="low")
    if bad_dates:
        c.add("schema-invalid-dates", "medium", "Schema dates are not in ISO 8601 format", "Google ignores dates it cannot parse, which drops freshness signals and can invalidate Article items.", "Use YYYY-MM-DD or full ISO 8601 with timezone.", evidence=bad_dates[:4], affected_count=len(bad_dates), effort="low")
    if faq_mismatch:
        c.add("schema-faq-not-visible", "medium", "FAQPage schema questions do not appear in the visible page text", "Marking up content users cannot see violates Google's structured data policies and risks a manual action.", "Only mark up questions and answers that are visible on the page, word for word.", evidence=faq_mismatch[:4], affected_count=len(faq_mismatch), effort="low")
    if missing_recommended:
        top = [(k, v) for k, v in missing_recommended.most_common(6) if k != "duplicate-blocks"]
        if top:
            c.add("schema-missing-recommended", "low", f"Schema items miss recommended properties ({sum(v for _, v in top):,} gaps)", "Recommended properties unlock richer displays and better entity understanding.", "Add the properties where the data exists.", evidence=[f"{k} missing on {v} items" for k, v in top], affected_count=sum(v for _, v in top), effort="low")
    top_n = org_names.most_common(1)[0][1] if org_names else 0
    org_names = Counter({n: k for n, k in org_names.items() if k >= max(2, top_n * 0.1)})
    org_urls = Counter({u: k for u, k in org_urls.items() if k >= max(2, top_n * 0.1)})
    if len({n.lower() for n in org_names}) > 1:
        c.add("schema-entity-inconsistent", "medium", "Organization blocks use different names across pages", "Two spellings of the brand in schema look like two entities to Google and AI systems.", "Use one exact brand name in every Organization/LocalBusiness block (ideally one block with a stable @id).", evidence=[f"'{n}' x{k}" for n, k in org_names.most_common(4)], effort="low")
    if len(org_urls) > 1:
        c.add("schema-entity-url-inconsistent", "low", "Organization url differs across schema blocks", "The entity's canonical URL should be identical everywhere (www vs non-www, trailing slash).", "Use the canonical homepage URL in every block.", evidence=[f"{u} x{k}" for u, k in org_urls.most_common(3)], effort="low")

    # ----------------------------------------------------------- breadcrumbs
    bc_pages = [p for p in html_pages if p.has_breadcrumb_markup]
    deep_pages = [p for p in html_pages if p.depth >= 2]
    if deep_pages and len(bc_pages) < len(deep_pages) * 0.3:
        c.add("schema-no-breadcrumbs", "low", f"{len(deep_pages) - len(bc_pages):,} inner pages have no BreadcrumbList markup", "Breadcrumbs replace the URL in search snippets and clarify site structure for crawlers.", "Add visible breadcrumbs with BreadcrumbList JSON-LD on inner pages.", affected_count=len(deep_pages) - len(bc_pages), effort="low")
    elif bc_pages:
        c.passed("schema-breadcrumbs", f"Breadcrumb markup present on {len(bc_pages):,} pages")

    # ------------------------------------------------------- page-type schema
    article_like = [p for p in html_pages if page_type(p.url, p) == "article" and p.word_count > 400]
    no_article = [p for p in article_like if not (ARTICLE_TYPES & set(p.schema_types))]
    if article_like and len(no_article) > len(article_like) * 0.5:
        c.add("schema-articles-unmarked", "medium", f"{len(no_article):,} blog/article pages lack Article schema", "Article schema carries author, dates and publisher, the core E-E-A-T signals for both Google and AI engines.", "Add BlogPosting/Article JSON-LD with headline, author (Person with url), datePublished, dateModified, publisher and image.", evidence=[p.url for p in no_article[:6]], affected_count=len(no_article), pages=[p.url for p in no_article[:300]])
    elif article_like:
        c.passed("schema-articles", f"Article schema present on {len(article_like) - len(no_article):,} of {len(article_like):,} articles")
        authors = [p for p in article_like if any("Person" in _types(x) for i in p.json_ld for x in _walk(i))]
        if article_like and len(authors) < len(article_like) * 0.3:
            c.add("schema-no-person-author", "low", "Article schema does not identify the author as a Person", "A Person author with url and sameAs links the article to a real expert, which is the author signal Google and AI systems look for.", "Set author to a Person object with name, url (author page) and sameAs.", affected_count=len(article_like) - len(authors), effort="low")
    # A /products/ URL on a bank or SaaS site is a service page, not a shop product: require shop evidence.
    product_like = [p for p in html_pages if "Product" in p.microdata_types or p.has_add_to_cart or (page_type(p.url, p) == "product" and btype == "e-commerce")]
    no_product = [p for p in product_like if not ({"Product", "ProductGroup"} & set(p.schema_types)) and "Product" not in p.microdata_types]
    if product_like and len(no_product) > len(product_like) * 0.5:
        c.add("schema-products-unmarked", "high", f"{len(no_product):,} product pages lack Product schema", "Product schema drives price, availability and review rich results plus shopping-graph eligibility.", "Emit Product JSON-LD with name, image, description, sku, brand, offers (price, priceCurrency, availability).", evidence=[p.url for p in no_product[:6]], affected_count=len(no_product), pages=[p.url for p in no_product[:300]])
    elif product_like:
        c.passed("schema-products", f"Product schema present on {len(product_like) - len(no_product):,} of {len(product_like):,} product pages")
        if product_pages_ok < (len(product_like) - len(no_product)) * 0.5:
            c.add("schema-offers-incomplete", "medium", "Product offers lack price, currency or availability", "Merchant listings and price rich results need all three; AI shopping answers also quote them.", "Complete the Offer: price, priceCurrency, availability (schema.org/InStock), url.", affected_count=len(product_like) - len(no_product) - product_pages_ok, effort="low")
        if btype == "e-commerce" and not all_types.get("MerchantReturnPolicy") and not all_types.get("OfferShippingDetails"):
            c.add("schema-no-shipping-returns", "low", "No shipping or return policy structured data", "OfferShippingDetails and MerchantReturnPolicy (with applicableCountry) power the delivery and returns badges in Google Shopping results.", "Add shippingDetails and hasMerchantReturnPolicy to offers, or set them once in Merchant Center.", effort="medium")
    video_pages = [p for p in html_pages if p.has_video]
    if video_pages and not all_types.get("VideoObject") and len(video_pages) >= 3:
        c.add("schema-no-videoobject", "low", f"{len(video_pages):,} pages embed video without VideoObject schema", "VideoObject enables video rich results and key moments; without it the videos are invisible to video search.", "Add VideoObject with name, description, thumbnailUrl, uploadDate and embedUrl.", affected_count=len(video_pages), effort="low")
    for t, (sev, note) in DEPRECATED.items():
        if all_types.get(t):
            c.add(f"schema-{t.lower()}-deprecated", sev, f"{t} schema present on {all_types[t]} items", note, "Remove or keep only if it still helps AI extraction; it no longer produces rich results.", effort="low")
    if all_types.get("FAQPage") and btype not in ("healthcare", "nonprofit / government"):
        c.add("schema-faqpage-note", "info", f"FAQPage schema present on {all_types['FAQPage']} items", "Since August 2023 Google shows FAQ rich results only for authoritative government and health sites, but FAQPage still helps answer engines extract Q&A when it matches the visible text.", "Keep it if the questions are visible on the page; do not expect rich results.", effort="low")
    expected = EXPECTED_BY_TYPE.get(btype, [])
    missing_types = [e for e in expected if not any(all_types.get(x) for x in e.split("|"))]
    if missing_types and pages_with:
        c.add("schema-type-opportunities", "low", f"Schema types expected for a {btype} site are missing: {', '.join(m.split('|')[0] for m in missing_types)}", "Each page type has a matching schema type that unlocks rich results and gives AI systems structured facts.", "Add the missing types to the relevant templates.", evidence=[f"present: {', '.join(t for t, _ in all_types.most_common(8))}"], effort="medium")

    dup_org = [p.url for p in pages_with if sum(1 for i in p.json_ld if "Organization" in _types(i)) > 1]
    if dup_org:
        c.add("schema-duplicate-organization", "low", f"Multiple Organization blocks on {len(dup_org):,} pages", "Conflicting entity blocks (usually theme + SEO plugin) confuse entity resolution.", "Keep one Organization block, ideally in an @graph with a stable @id.", evidence=dup_org[:5], affected_count=len(dup_org), effort="low")

    out = c.to_dict()
    out["types_found"] = dict(all_types.most_common(25))
    out["pages_with_schema"] = len(pages_with)
    out["pages_total"] = len(html_pages)
    out["is_local_business"] = bool(set(all_types) & LOCAL_TYPES)
    out["has_product"] = bool(all_types.get("Product") or all_types.get("ProductGroup"))
    out["org_names"] = dict(org_names.most_common(5))
    out["microdata_pages"] = len([p for p in html_pages if p.microdata_types])
    return out
