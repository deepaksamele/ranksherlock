"""Structured data detection and validation (JSON-LD first, microdata noted)."""

from __future__ import annotations

import re
from collections import Counter

from .findings import Collector

REQUIRED = {
    "Organization": ["name", "url"],
    "LocalBusiness": ["name", "address", "telephone"],
    "Product": ["name", "offers"],
    "Offer": ["price", "priceCurrency"],
    "Article": ["headline", "datePublished", "author"],
    "NewsArticle": ["headline", "datePublished", "author"],
    "BlogPosting": ["headline", "datePublished", "author"],
    "FAQPage": ["mainEntity"],
    "BreadcrumbList": ["itemListElement"],
    "WebSite": ["name", "url"],
    "WebPage": ["name"],
    "Person": ["name"],
    "Event": ["name", "startDate", "location"],
    "Recipe": ["name", "image", "recipeIngredient"],
    "VideoObject": ["name", "thumbnailUrl", "uploadDate"],
    "JobPosting": ["title", "datePosted", "hiringOrganization", "jobLocation"],
    "Service": ["name", "provider"],
    "SoftwareApplication": ["name", "applicationCategory", "offers"],
    "Course": ["name", "provider"],
    "HowTo": ["name", "step"],
    "Review": ["itemReviewed", "reviewRating", "author"],
    "AggregateRating": ["ratingValue", "reviewCount"],
}
RECOMMENDED = {
    "Organization": ["logo", "sameAs", "contactPoint"],
    "LocalBusiness": ["openingHoursSpecification", "geo", "priceRange", "image", "url", "sameAs"],
    "Product": ["image", "description", "brand", "sku", "aggregateRating"],
    "Article": ["image", "dateModified", "publisher"],
    "BlogPosting": ["image", "dateModified", "publisher"],
    "Person": ["url", "sameAs", "jobTitle"],
}
LOCAL_TYPES = {"LocalBusiness", "Restaurant", "Store", "Dentist", "Plumber", "Electrician", "Attorney", "LegalService", "MedicalBusiness", "AutoRepair", "HomeAndConstructionBusiness", "RoofingContractor", "HVACBusiness", "RealEstateAgent", "FinancialService", "ProfessionalService", "HealthAndBeautyBusiness", "LodgingBusiness", "Hotel", "Physician", "Dentist", "ChildCare", "School", "EducationalOrganization", "GeneralContractor", "MovingCompany", "Locksmith", "Florist", "Bakery", "CafeOrCoffeeShop", "BarOrPub", "FoodEstablishment", "SportsActivityLocation", "ExerciseGym", "BeautySalon", "HairSalon", "DaySpa", "NailSalon", "VeterinaryCare", "AnimalShelter", "AutoDealer", "AutoBodyShop", "InsuranceAgency", "TravelAgency", "Pharmacy", "Hospital", "MedicalClinic", "Optician"}
DEPRECATED_NOTE = {
    "HowTo": "HowTo rich results were removed by Google in 2023; keep only if useful for AI extraction.",
    "FAQPage": "FAQ rich results are now restricted to a small set of sites, but FAQPage still helps answer engines extract Q&A.",
}


def _types(item: dict) -> list[str]:
    t = item.get("@type")
    if isinstance(t, list):
        return [str(x) for x in t]
    return [str(t)] if t else []


def _has(item: dict, prop: str) -> bool:
    v = item.get(prop)
    if v is None:
        return False
    if isinstance(v, (list, dict, str)) and len(v) == 0:
        return False
    return True


def analyze_schema(pages: list, home_url: str) -> dict:
    c = Collector("schema")
    html_pages = [p for p in pages if p.status == 200 and "text/html" in (p.content_type or "")]
    pages_with = [p for p in html_pages if p.json_ld]
    pages_without = [p for p in html_pages if not p.json_ld and not p.microdata_types]
    all_types: Counter = Counter()
    for p in pages_with:
        for item in p.json_ld:
            for t in _types(item):
                all_types[t] += 1

    from urllib.parse import urlparse as _up

    home = next((p for p in html_pages if p.url == home_url or p.final_url.rstrip("/") == home_url.rstrip("/")), None)
    if home is not None and _up(home.final_url).path not in ("", "/"):
        home = None  # single-page run on an inner URL: homepage-only checks do not apply

    if not pages_with:
        c.add("schema-none", "high", "No JSON-LD structured data anywhere on the crawled pages", "Without schema, Google cannot show rich results and answer engines have no machine-readable entity facts.", "Add Organization (or LocalBusiness) + WebSite on the homepage, BreadcrumbList sitewide, and page-type schema (Article, Product, Service, FAQPage) where relevant.", affected_count=len(html_pages), effort="medium")
    else:
        c.passed("schema-present", f"JSON-LD found on {len(pages_with)} of {len(html_pages)} pages ({', '.join(t for t, _ in all_types.most_common(6))})")
        if pages_without and len(pages_without) > len(html_pages) * 0.4:
            c.add("schema-coverage", "medium", "Most pages have no structured data", "Schema only helps the pages that carry it.", "Extend page-type schema (Article/Product/Service) across templates, not just the homepage.", evidence=[p.url for p in pages_without[:6]], affected_count=len(pages_without), pages=[p.url for p in pages_without])

    # JSON errors
    err_pages = [p for p in html_pages if p.json_ld_errors]
    if err_pages:
        c.add("schema-invalid-json", "high", "JSON-LD blocks with syntax errors", "Invalid JSON is ignored completely by Google, so the markup might as well not exist.", "Validate with the Rich Results Test and fix the JSON (trailing commas, unescaped quotes, bad nesting).", evidence=[f"{p.url}: {p.json_ld_errors[0]}" for p in err_pages[:6]], affected_count=len(err_pages), pages=[p.url for p in err_pages], effort="low")

    # Homepage entity
    if home is not None:
        home_types = {t for item in home.json_ld for t in _types(item)}
        has_org = bool(home_types & ({"Organization", "Corporation", "OnlineStore"} | LOCAL_TYPES))
        if not has_org:
            c.add("schema-no-organization", "high", "Homepage lacks Organization or LocalBusiness schema", "This is the entity anchor that search engines and AI models use to understand who the site belongs to (name, logo, sameAs profiles).", "Add an Organization (or specific LocalBusiness subtype) JSON-LD block on the homepage with name, url, logo, sameAs and contactPoint.", evidence=[f"homepage types: {', '.join(sorted(home_types)) or 'none'}"], effort="low")
        else:
            c.passed("schema-organization", "Homepage declares an Organization/LocalBusiness entity")
            org = next((i for i in home.json_ld if set(_types(i)) & ({"Organization", "Corporation", "OnlineStore"} | LOCAL_TYPES)), {})
            if org and not _has(org, "sameAs"):
                c.add("schema-no-sameas", "medium", "Organization schema has no sameAs links", "sameAs links to LinkedIn, Wikipedia, Wikidata, Crunchbase and social profiles are how AI systems disambiguate your brand from others with similar names.", "Add a sameAs array with every official profile URL.", effort="low")
            if org and not _has(org, "logo"):
                c.add("schema-no-logo", "low", "Organization schema has no logo", "Logo powers the knowledge panel and brand display in search.", "Add a logo property with an absolute https URL to a square-ish PNG/SVG.", effort="low")
        if "WebSite" not in home_types:
            c.add("schema-no-website", "low", "No WebSite schema on homepage", "WebSite schema names the site and can enable sitelinks search box.", "Add a WebSite block with name, url and (optionally) potentialAction SearchAction.", effort="low")

    # Required/recommended properties
    missing_required = []
    missing_recommended: Counter = Counter()
    fake_rating = []
    for p in pages_with:
        for item in p.json_ld:
            for t in _types(item):
                base = t
                if t in LOCAL_TYPES:
                    base = "LocalBusiness"
                elif t in ("NewsArticle", "BlogPosting", "TechArticle"):
                    base = "Article"
                req = REQUIRED.get(base) or REQUIRED.get(t)
                if req:
                    miss = [r for r in req if not _has(item, r)]
                    if miss:
                        missing_required.append(f"{p.url}: {t} missing {', '.join(miss)}")
                for r in RECOMMENDED.get(base, []):
                    if not _has(item, r):
                        missing_recommended[f"{base}.{r}"] += 1
                if "aggregateRating" in item and isinstance(item["aggregateRating"], dict):
                    ar = item["aggregateRating"]
                    rc = ar.get("reviewCount") or ar.get("ratingCount")
                    has_reviews = _has(item, "review")
                    if not has_reviews and (rc is None or str(rc).strip() in ("", "0")):
                        fake_rating.append(f"{p.url}: {t} aggregateRating without reviews")
                    elif t in ("Organization", "LocalBusiness") or t in LOCAL_TYPES:
                        if not has_reviews:
                            fake_rating.append(f"{p.url}: self-serving {t} rating (no review objects)")
                if t == "FAQPage":
                    qs = item.get("mainEntity") or []
                    if isinstance(qs, list) and qs:
                        sample = qs[0] if isinstance(qs[0], dict) else {}
                        q_text = str(sample.get("name", ""))[:60]
                        if q_text and q_text.lower()[:40] not in (p.text_sample + " ".join(p.h2 + p.h3)).lower() and q_text.lower()[:40] not in " ".join(p.question_headings).lower():
                            pass  # cannot verify visible text from sample alone; handled in content module
    if missing_required:
        c.add("schema-missing-required", "medium", "Schema items missing required properties", "Google only shows rich results when required properties are present; AI extraction also degrades.", "Fill in the missing properties listed in the evidence.", evidence=missing_required[:8], affected_count=len(missing_required))
    if fake_rating:
        c.add("schema-self-serving-rating", "high", "Star ratings in schema without verifiable reviews", "Google's guidelines prohibit self-serving aggregateRating on Organization/LocalBusiness and ratings without real reviews. This can trigger a manual action.", "Remove the aggregateRating or back it with real, visible, dated review objects (or move ratings to a third-party platform).", evidence=fake_rating[:6], affected_count=len(fake_rating), effort="low")
    if missing_recommended:
        top = missing_recommended.most_common(5)
        c.add("schema-missing-recommended", "low", "Schema items missing recommended properties", "Recommended properties unlock richer displays and better entity understanding.", "Add the properties where the data exists.", evidence=[f"{k} missing on {n} items" for k, n in top], affected_count=sum(missing_recommended.values()), effort="low")

    # Breadcrumbs
    bc_pages = [p for p in html_pages if p.has_breadcrumb_markup]
    deep_pages = [p for p in html_pages if p.depth >= 2]
    if deep_pages and len(bc_pages) < len(deep_pages) * 0.3:
        c.add("schema-no-breadcrumbs", "low", "Inner pages have no BreadcrumbList markup", "Breadcrumbs replace the URL in search snippets and clarify site structure for crawlers.", "Add visible breadcrumbs with BreadcrumbList JSON-LD on inner pages.", affected_count=len(deep_pages) - len(bc_pages), effort="low")
    elif bc_pages:
        c.passed("schema-breadcrumbs", f"Breadcrumb markup present on {len(bc_pages)} pages")

    # Article pages without Article schema
    article_like = [p for p in html_pages if re.search(r"/(blog|news|article|post|guide|learn|resources?)/", p.url, re.I) and p.word_count > 400]
    no_article = [p for p in article_like if not ({"Article", "BlogPosting", "NewsArticle", "TechArticle"} & {t for i in p.json_ld for t in _types(i)})]
    if article_like and len(no_article) > len(article_like) * 0.5:
        c.add("schema-articles-unmarked", "medium", "Blog/article pages lack Article schema", "Article schema carries author, dates and publisher, the core E-E-A-T signals for both Google and AI engines.", "Add BlogPosting/Article JSON-LD with headline, author (Person with url), datePublished, dateModified, publisher and image.", evidence=[p.url for p in no_article[:6]], affected_count=len(no_article), pages=[p.url for p in no_article])

    # Product pages without Product schema
    product_like = [p for p in html_pages if re.search(r"/(product|products|shop|item|p)/", p.url, re.I) or "Product" in p.microdata_types]
    no_product = [p for p in product_like if "Product" not in {t for i in p.json_ld for t in _types(i)} and "Product" not in p.microdata_types]
    if product_like and len(no_product) > len(product_like) * 0.5:
        c.add("schema-products-unmarked", "high", "Product pages lack Product schema", "Product schema drives price, availability and review rich results plus shopping-graph eligibility.", "Emit Product JSON-LD with name, image, description, sku, brand, offers (price, priceCurrency, availability).", evidence=[p.url for p in no_product[:6]], affected_count=len(no_product), pages=[p.url for p in no_product])

    for t, note in DEPRECATED_NOTE.items():
        if all_types.get(t):
            c.add(f"schema-{t.lower()}-note", "info", f"{t} schema present on {all_types[t]} items", note, "No action required unless you expected rich results from it.", effort="low")

    # Duplicate Organization per page
    dup_org = [p.url for p in pages_with if sum(1 for i in p.json_ld if "Organization" in _types(i)) > 1]
    if dup_org:
        c.add("schema-duplicate-organization", "low", "Multiple Organization blocks on one page", "Conflicting entity blocks (usually theme + SEO plugin) confuse entity resolution.", "Keep one Organization block, ideally in an @graph with a stable @id.", evidence=dup_org[:5], affected_count=len(dup_org), effort="low")

    out = c.to_dict()
    out["types_found"] = dict(all_types.most_common(20))
    out["pages_with_schema"] = len(pages_with)
    out["pages_total"] = len(html_pages)
    out["is_local_business"] = bool(set(all_types) & LOCAL_TYPES)
    out["has_product"] = bool(all_types.get("Product"))
    return out
