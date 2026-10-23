"""Local SEO signals: NAP consistency, LocalBusiness schema, map embeds, location pages."""

from __future__ import annotations

import re
from collections import Counter

from .findings import Collector
from .schema_check import LOCAL_TYPES, _types

LOCAL_HINTS = re.compile(r"\b(near me|serving|service area|our location|visit us|directions|opening hours|open hours|hours of operation|call us|free estimate|free quote|licensed|insured|locally owned|family owned)\b", re.I)
ADDRESS_RE = re.compile(r"\b\d{1,6}\s+[A-Z][A-Za-z0-9.'-]*(\s+[A-Z][A-Za-z0-9.'-]*){0,4}\s+(Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Way|Court|Ct|Place|Pl|Highway|Hwy|Parkway|Pkwy|Suite|Ste|Marg|Nagar|Colony)\b", re.I)


def detect_local_business(pages: list, schema_result: dict) -> tuple[bool, list[str]]:
    reasons = []
    if schema_result.get("is_local_business"):
        reasons.append("LocalBusiness schema present")
    html_pages = [p for p in pages if p.status == 200 and "text/html" in (p.content_type or "")]
    hint_hits = sum(1 for p in html_pages[:40] if LOCAL_HINTS.search(p.text_sample))
    if hint_hits >= max(2, len(html_pages[:40]) * 0.2):
        reasons.append(f"local service language on {hint_hits} pages")
    phones = sum(1 for p in html_pages[:40] if p.phones)
    addresses = sum(1 for p in html_pages[:40] if ADDRESS_RE.search(p.text_sample) or p.has_address_tag)
    if phones >= len(html_pages[:40]) * 0.5 and addresses >= 1:
        reasons.append("phone and street address shown sitewide")
    if any(p.has_map_embed for p in html_pages[:40]):
        reasons.append("Google Maps embed found")
    return len(reasons) >= 2, reasons


def analyze_local(pages: list, schema_result: dict, home_url: str) -> dict:
    c = Collector("local")
    html_pages = [p for p in pages if p.status == 200 and "text/html" in (p.content_type or "")]
    is_local, reasons = detect_local_business(pages, schema_result)
    out_extra = {"is_local_business": is_local, "detection_reasons": reasons}
    if not is_local:
        c.skipped("local", "Site does not look like a local business; local checks not scored")
        out = c.to_dict()
        out.update(out_extra)
        out["measured"] = False
        return out

    home = next((p for p in html_pages if p.url == home_url), html_pages[0] if html_pages else None)

    # LocalBusiness schema
    lb_items = [i for p in html_pages for i in p.json_ld if set(_types(i)) & LOCAL_TYPES]
    if not lb_items:
        c.add("local-no-schema", "high", "No LocalBusiness schema", "LocalBusiness JSON-LD (with the specific subtype, address, phone, hours and geo) is how Google ties the site to the Business Profile and how AI assistants answer 'is there a X near me'.", "Add LocalBusiness (or the exact subtype such as Plumber, Dentist, RoofingContractor) JSON-LD on the homepage and contact page with name, address (PostalAddress), telephone, openingHoursSpecification, geo, url, image, priceRange and sameAs (Google Business Profile, Facebook, Yelp).", effort="low")
    else:
        c.passed("local-schema", f"LocalBusiness schema present ({_types(lb_items[0])[0]})")
        item = lb_items[0]
        missing = [k for k in ("address", "telephone", "openingHoursSpecification", "geo", "image", "priceRange") if not item.get(k)]
        if missing:
            c.add("local-schema-incomplete", "medium", "LocalBusiness schema missing key properties", "Each missing field is a fact Google cannot confirm against the Business Profile.", f"Add: {', '.join(missing)}.", evidence=missing, effort="low")
        generic = [i for i in lb_items if _types(i) == ["LocalBusiness"]]
        if generic and len(generic) == len(lb_items):
            c.add("local-schema-generic-type", "low", "Schema uses generic LocalBusiness instead of a specific subtype", "Specific subtypes (Dentist, Plumber, Restaurant) map directly to Business Profile categories.", "Switch @type to the most specific schema.org subtype.", effort="low")

    # NAP consistency
    phones = Counter(re.sub(r"\D", "", ph) for p in html_pages for ph in p.phones)
    phone_variants = [ph for ph, n in phones.items() if n >= 2]
    if len(phone_variants) > 2:
        c.add("local-multiple-phones", "medium", "More than two phone numbers repeat across the site", "Conflicting NAP (name, address, phone) data lowers local ranking confidence.", "Standardise on one primary number in header, footer, contact page and schema; mark tracking numbers with the same display number or schema-only.", evidence=[f"{ph} on {n} pages" for ph, n in phones.most_common(5)], effort="low")
    elif phones:
        c.passed("local-phone", f"Primary phone appears on {phones.most_common(1)[0][1]} pages")
    from urllib.parse import urlparse as _up

    if home is not None and _up(home.final_url).path in ("", "/") and not home.phones:
        c.add("local-no-phone-home", "medium", "No phone number visible on the homepage", "Local searchers and AI assistants expect a phone number in the first screen.", "Add a click-to-call phone number in the header.", effort="low")
    addr_pages = [p for p in html_pages if ADDRESS_RE.search(p.text_sample) or p.has_address_tag]
    if not addr_pages:
        c.add("local-no-address", "medium", "No street address found in page text", "Google and AI assistants verify the address against the Business Profile; hidden or image-only addresses do not count.", "Show the full address as text in the footer and contact page, wrapped in <address> and matching the schema.", effort="low")
    else:
        c.passed("local-address", f"Street address visible on {len(addr_pages)} pages")
    if not any(p.has_map_embed for p in html_pages):
        c.add("local-no-map", "low", "No Google Maps embed", "A map embed reinforces the location entity and helps users.", "Embed the Google Business Profile map on the contact page.", effort="low")

    # Location / service-area pages
    loc_pages = [p for p in html_pages if re.search(r"/(locations?|areas?|service-areas?|cities|near|[a-z]+-(tx|ca|fl|ny|ga|nc|va|wa|az|co|il|oh|pa|mi|nj|ma|md|mn|mo|tn|wi|in|or|sc|al|la|ky|ok|ct|ia|ut|nv|ar|ms|ks|nm|ne|id|wv|hi|nh|me|ri|mt|de|sd|nd|ak|vt|wy|dc))/", p.url, re.I) or re.search(r"\b(in|near|serving)\s+[A-Z][a-z]+(,\s*[A-Z]{2})?\b", p.title or "")]
    if not loc_pages:
        c.add("local-no-location-pages", "medium", "No city or service-area pages found", "Each target city needs its own page to rank for 'service + city' queries outside the main location.", "Create one genuinely localised page per city or service area (local proof, photos, reviews, directions, embedded map), not duplicated templates.", effort="high")
    else:
        c.passed("local-location-pages", f"{len(loc_pages)} location/service-area pages found")
        dup_bodies = Counter(p.first_paragraph[:120] for p in loc_pages if p.first_paragraph)
        dups = [k for k, n in dup_bodies.items() if n > 1]
        if dups:
            c.add("local-doorway-pages", "high", "Location pages share identical copy", "Near-duplicate city pages are doorway pages under Google's spam policy and get filtered or penalised.", "Rewrite each with unique local content: team, projects, reviews, landmarks, directions.", evidence=[f"'{d[:70]}...' repeated" for d in dups[:3]], affected_count=sum(dup_bodies[d] for d in dups), effort="high")

    # Reviews
    review_signal = any(re.search(r"\b(reviews?|testimonials?|rating|stars)\b", p.text_sample, re.I) for p in html_pages[:30])
    if not review_signal:
        c.add("local-no-reviews", "low", "No review or testimonial content found", "Reviews are a top local ranking factor and a primary E-E-A-T signal.", "Add a reviews section fed from Google Business Profile (with real, dated reviews) and link to the profile.", effort="medium")

    gbp = any(re.search(r"google\.com/maps|g\.page/|maps\.app\.goo\.gl|business\.google", l["href"]) for p in html_pages for l in p.external_links)
    if not gbp:
        c.add("local-no-gbp-link", "low", "No link to the Google Business Profile", "Linking the profile connects the website entity with the map listing.", "Link 'Leave a review' and the map to the Business Profile URL.", effort="low")

    out = c.to_dict()
    out.update(out_extra)
    out["measured"] = True
    out["phones"] = dict(phones.most_common(5))
    out["location_pages"] = [p.url for p in loc_pages[:20]]
    return out
