"""Local SEO signals: NAP consistency, LocalBusiness schema, hours, map embeds, location pages, reviews."""

from __future__ import annotations

import re
from collections import Counter

from .business import page_type
from .findings import Collector
from .schema_check import LOCAL_TYPES, _types, _walk

LOCAL_HINTS = re.compile(r"\b(near me|serving|service area|our location|visit us|directions|opening hours|open hours|hours of operation|call us|free estimate|free quote|licensed|insured|locally owned|family owned|same.day|emergency service)\b", re.I)
ADDRESS_RE = re.compile(r"\b\d{1,6}\s+[A-Z][A-Za-z0-9.'-]*(\s+[A-Z][A-Za-z0-9.'-]*){0,4}\s+(Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Way|Court|Ct|Place|Pl|Highway|Hwy|Parkway|Pkwy|Suite|Ste|Marg|Nagar|Colony|Sector|Phase)\b", re.I)


def detect_local_business(pages: list, schema_result: dict) -> tuple[bool, list[str]]:
    reasons = []
    if schema_result.get("is_local_business"):
        reasons.append("LocalBusiness schema present")
    html_pages = [p for p in pages if p.status == 200 and "text/html" in (p.content_type or "")]
    sample = html_pages[:60]
    hint_hits = sum(1 for p in sample if p.has_local_language)
    if hint_hits >= max(2, len(sample) * 0.2):
        reasons.append(f"local service language on {hint_hits} pages")
    phones = sum(1 for p in sample if p.phones or p.has_tel_link)
    addresses = sum(1 for p in sample if p.has_street_address or p.has_address_tag)
    if phones >= len(sample) * 0.5 and addresses >= 1:
        reasons.append("phone and street address shown sitewide")
    if any(p.has_map_embed for p in sample):
        reasons.append("Google Maps embed found")
    if any(p.has_hours_text for p in sample[:20]):
        reasons.append("opening hours shown")
    loc_pages = [p for p in html_pages if page_type(p.url, p) == "location"]
    if len(loc_pages) >= 3:
        reasons.append(f"{len(loc_pages)} location pages")
    return len(reasons) >= 2, reasons


def analyze_local(pages: list, schema_result: dict, home_url: str, force: bool = False) -> dict:
    c = Collector("local")
    html_pages = [p for p in pages if p.status == 200 and "text/html" in (p.content_type or "")]
    is_local, reasons = detect_local_business(pages, schema_result)
    out_extra = {"is_local_business": is_local or force, "detection_reasons": reasons}
    if not (is_local or force):
        c.skipped("local", "Site does not look like a local business; local checks not scored")
        out = c.to_dict()
        out.update(out_extra)
        out["measured"] = False
        return out

    from urllib.parse import urlparse as _up

    home = next((p for p in html_pages if p.url == home_url), html_pages[0] if html_pages else None)
    home_is_root = home is not None and _up(home.final_url).path in ("", "/")

    # LocalBusiness schema
    lb_items = [x for p in html_pages for i in p.json_ld for x in _walk(i) if set(_types(x)) & LOCAL_TYPES]
    if not lb_items:
        c.add("local-no-schema", "high", "No LocalBusiness schema", "LocalBusiness JSON-LD (with the specific subtype, address, phone, hours and geo) is how Google ties the site to the Business Profile and how AI assistants answer 'is there a X near me'.", "Add LocalBusiness (or the exact subtype such as Plumber, Dentist, RoofingContractor) JSON-LD on the homepage and contact page with name, address (PostalAddress), telephone, openingHoursSpecification, geo, url, image, priceRange and sameAs (Google Business Profile, Facebook, Yelp).", effort="low")
    else:
        c.passed("local-schema", f"LocalBusiness schema present ({_types(lb_items[0])[0]})")
        item = lb_items[0]
        missing = [k for k in ("address", "telephone", "openingHoursSpecification", "geo", "image", "priceRange", "url") if not item.get(k)]
        if missing:
            c.add("local-schema-incomplete", "medium", f"LocalBusiness schema is missing {len(missing)} key properties", "Each missing field is a fact Google cannot confirm against the Business Profile and AI assistants cannot repeat.", f"Add: {', '.join(missing)}.", evidence=missing, effort="low")
        else:
            c.passed("local-schema-complete", "LocalBusiness schema carries address, phone, hours, geo, image and price range")
        generic = [i for i in lb_items if _types(i) == ["LocalBusiness"]]
        if generic and len(generic) == len(lb_items):
            c.add("local-schema-generic-type", "low", "Schema uses generic LocalBusiness instead of a specific subtype", "Specific subtypes (Dentist, Plumber, Restaurant) map directly to Business Profile categories.", "Switch @type to the most specific schema.org subtype.", effort="low")
        if not item.get("areaServed"):
            c.add("local-no-areaserved", "low", "LocalBusiness schema does not declare areaServed", "areaServed tells search engines and assistants which cities or regions the business covers, which matters for service-area businesses.", "Add areaServed with the cities, districts or a GeoCircle.", effort="low")
        same_as = item.get("sameAs") or []
        same_as = same_as if isinstance(same_as, list) else [same_as]
        if not any(re.search(r"google\.com/maps|g\.page|maps\.app\.goo\.gl|business\.google", str(s)) for s in same_as):
            c.add("local-no-gbp-in-sameas", "low", "Google Business Profile URL is not in LocalBusiness sameAs", "Linking the profile from schema connects the website entity with the map listing.", "Add the Google Maps / Business Profile share link to sameAs.", effort="low")
        # NAP: schema phone vs visible phones
        tel = re.sub(r"\D", "", str(item.get("telephone") or ""))
        visible = Counter(re.sub(r"\D", "", ph) for p in html_pages for ph in p.phones)
        if tel and visible and not any(tel.endswith(v[-8:]) or v.endswith(tel[-8:]) for v in visible if len(v) >= 8):
            c.add("local-nap-schema-mismatch", "medium", "Phone number in schema differs from the numbers shown on the pages", "Conflicting NAP data between schema and visible text lowers Google's confidence in both.", "Use one primary number in schema, header, footer and contact page.", evidence=[f"schema: {item.get('telephone')}", f"visible: {', '.join(list(visible)[:3])}"], effort="low")

    # NAP consistency
    phones = Counter(re.sub(r"\D", "", ph) for p in html_pages for ph in p.phones)
    phone_variants = [ph for ph, n in phones.items() if n >= 2]
    if len(phone_variants) > 2:
        c.add("local-multiple-phones", "medium", f"{len(phone_variants)} different phone numbers repeat across the site", "Conflicting NAP (name, address, phone) data lowers local ranking confidence.", "Standardise on one primary number in header, footer, contact page and schema; mark tracking numbers with the same display number or schema-only.", evidence=[f"{ph} on {n} pages" for ph, n in phones.most_common(5)], effort="low")
    elif phones:
        c.passed("local-phone", f"Primary phone appears on {phones.most_common(1)[0][1]} pages")
    if home is not None and home_is_root and not home.phones and not home.has_tel_link:
        c.add("local-no-phone-home", "medium", "No phone number visible on the homepage", "Local searchers and AI assistants expect a phone number in the first screen.", "Add a click-to-call phone number in the header.", effort="low")
    addr_pages = [p for p in html_pages if p.has_street_address or p.has_address_tag]
    schema_addr = any(isinstance(i.get("address"), (dict, list)) and i.get("address") for i in lb_items)
    if not addr_pages and schema_addr:
        c.add("local-address-schema-only", "low", "The street address is in schema but not recognisable in the visible page text", "Google cross-checks the visible address against the Business Profile; an address that exists only in markup is a weaker signal and unhelpful to visitors.", "Show the full postal address as text in the footer and on the contact page, matching the schema exactly.", effort="low")
    elif not addr_pages:
        c.add("local-no-address", "medium", "No street address found in page text", "Google and AI assistants verify the address against the Business Profile; hidden or image-only addresses do not count.", "Show the full address as text in the footer and contact page, wrapped in <address> and matching the schema.", effort="low")
    else:
        c.passed("local-address", f"Street address visible on {len(addr_pages)} pages")
    if not any(p.has_hours_text for p in html_pages[:60]):
        c.add("local-no-hours", "low", "Opening hours are not shown as text", "Hours are a top local ranking factor and the most common question assistants answer about a business.", "Show opening hours on the contact page and footer, and mirror them in openingHoursSpecification.", effort="low")
    else:
        c.passed("local-hours", "Opening hours shown on the site")
    if not any(p.has_map_embed for p in html_pages):
        c.add("local-no-map", "low", "No Google Maps embed", "A map embed reinforces the location entity and helps users.", "Embed the Google Business Profile map on the contact page.", effort="low")
    else:
        c.passed("local-map", "Map embed present")

    # Location / service-area pages
    loc_pages = [p for p in html_pages if page_type(p.url, p) == "location" or re.search(r"\b(in|near|serving)\s+[A-Z][a-z]+(,\s*[A-Z]{2})?\b", p.title or "")]
    if not loc_pages:
        c.add("local-no-location-pages", "medium", "No city or service-area pages found", "Each target city needs its own page to rank for 'service + city' queries outside the main location.", "Create one genuinely localised page per city or service area (local proof, photos, reviews, directions, embedded map), not duplicated templates.", effort="high")
    else:
        c.passed("local-location-pages", f"{len(loc_pages)} location/service-area pages found")
        dup_bodies = Counter(p.first_paragraph[:120] for p in loc_pages if p.first_paragraph)
        dups = [k for k, n in dup_bodies.items() if n > 1]
        if dups:
            c.add("local-doorway-pages", "high", f"{sum(dup_bodies[d] for d in dups)} location pages share identical copy", "Near-duplicate city pages are doorway pages under Google's spam policy and get filtered or penalised.", "Rewrite each with unique local content: team, projects, reviews, landmarks, directions.", evidence=[f"'{d[:70]}...' repeated {dup_bodies[d]}x" for d in dups[:3]], affected_count=sum(dup_bodies[d] for d in dups), effort="high")
        thin_loc = [p for p in loc_pages if p.word_count < 300]
        if thin_loc and len(thin_loc) > len(loc_pages) * 0.5:
            c.add("local-thin-location-pages", "medium", f"{len(thin_loc)} location pages have under 300 words", "Thin city pages rarely rank and look like doorway pages.", "Give each location page 500+ words of genuinely local content.", evidence=[f"{p.url} ({p.word_count} words)" for p in thin_loc[:4]], affected_count=len(thin_loc), effort="high")
        if len(loc_pages) >= 50:
            c.add("local-location-page-scale", "medium", f"{len(loc_pages)} location pages: scale that needs per-page uniqueness and a Business Profile per location", "Google treats large sets of city pages as doorway pages unless each has unique local proof and a real presence.", "Keep only locations with real presence or clients; make each page 60%+ unique with local photos, team, reviews and landmarks.", affected_count=len(loc_pages), effort="high")
        elif len(loc_pages) >= 30:
            c.add("local-location-page-scale", "low", f"{len(loc_pages)} location pages: watch uniqueness", "Thirty-plus city pages need strong per-page differentiation to avoid doorway classification.", "Audit uniqueness per page (60%+ unique words) and add local proof.", affected_count=len(loc_pages), effort="medium")

    # Reviews
    review_signal = any(p.has_reviews_text for p in html_pages[:60])
    if not review_signal:
        c.add("local-no-reviews", "low", "No review or testimonial content found", "Reviews are a top local ranking factor and a primary E-E-A-T signal.", "Add a reviews section fed from Google Business Profile (with real, dated reviews) and link to the profile.", effort="medium")
    else:
        c.passed("local-reviews", "Review or testimonial content present")
    gbp = any(re.search(r"google\.com/maps|g\.page/|maps\.app\.goo\.gl|business\.google", l["href"]) for p in html_pages[:200] for l in p.external_links)
    if not gbp:
        c.add("local-no-gbp-link", "low", "No link to the Google Business Profile", "Linking the profile connects the website entity with the map listing.", "Link 'Leave a review' and the map to the Business Profile URL.", effort="low")
    else:
        c.passed("local-gbp-link", "Google Business Profile linked")

    out = c.to_dict()
    out.update(out_extra)
    out["measured"] = True
    out["phones"] = dict(phones.most_common(5))
    out["location_pages"] = [p.url for p in loc_pages[:30]]
    out["location_page_count"] = len(loc_pages)
    return out
