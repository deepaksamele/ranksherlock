"""E-commerce checks: product and category content, trust pages, catalogue hygiene. Measured only for shops."""

from __future__ import annotations

import re
from collections import Counter

from .business import page_type
from .findings import Collector


def analyze_ecommerce(pages: list, business: dict, schema_result: dict) -> dict:
    c = Collector("ecommerce")
    html_pages = [p for p in pages if p.status == 200 and "text/html" in (p.content_type or "") and "noindex" not in (p.meta_robots or "").lower()]
    if business.get("business_type") != "e-commerce":
        c.skipped("ecommerce", "Not an e-commerce site; shop checks not scored")
        out = c.to_dict()
        out["measured"] = False
        return out
    ptype = {p.url: page_type(p.url, p) for p in html_pages}
    products = [p for p in html_pages if ptype[p.url] == "product" or ("Product" in p.schema_types and p.has_add_to_cart)]
    categories = [p for p in html_pages if ptype[p.url] == "category"]
    all_links = {l for p in html_pages[:500] for l in p.internal_links}

    if products:
        thin = [p for p in products if p.word_count < 120]
        if thin and len(thin) > len(products) * 0.3:
            c.add("ecom-thin-products", "medium", f"{len(thin):,} product pages have under 120 words of copy", "Spec-only product pages compete with hundreds of identical listings; unique descriptions, use cases and FAQs are what rank and get quoted by AI shopping answers.", "Write 150 to 400 words per product: who it is for, key specs in a table, materials, sizing, care, and 3 to 5 buyer questions.", evidence=[f"{p.url} ({p.word_count} words)" for p in thin[:5]], affected_count=len(thin), pages=[p.url for p in thin[:300]], effort="high")
        else:
            c.passed("ecom-product-copy", "Product pages carry descriptive copy")
        dup_desc = Counter(p.first_paragraph[:150] for p in products if p.first_paragraph and len(p.first_paragraph.split()) > 12)
        dups = [k for k, n in dup_desc.items() if n >= 3]
        if dups:
            c.add("ecom-duplicate-product-copy", "medium", f"{sum(dup_desc[d] for d in dups):,} products share identical descriptions", "Copy-pasted (often manufacturer) descriptions make products interchangeable in Google's eyes and rarely rank.", "Rewrite the top-selling products first with unique descriptions.", evidence=[f"'{d[:70]}...' on {dup_desc[d]} products" for d in dups[:3]], affected_count=sum(dup_desc[d] for d in dups), effort="high")
        no_price = [p for p in products if not p.has_price_text and not any("Offer" in str(i) for i in p.json_ld)]
        if no_price and len(no_price) > len(products) * 0.3:
            c.add("ecom-no-visible-price", "low", f"{len(no_price):,} product pages show no price in the HTML", "Price is a required field for product rich results and the first thing shopping assistants look for; JS-only prices are invisible to AI crawlers.", "Render the price server-side and include it in Offer schema.", evidence=[p.url for p in no_price[:4]], affected_count=len(no_price), effort="medium")
        no_reviews = [p for p in products if not p.has_reviews_text]
        if no_reviews and len(no_reviews) > len(products) * 0.7:
            c.add("ecom-no-product-reviews", "low", f"{len(no_reviews):,} product pages show no reviews", "Reviews drive star rich results, conversion and AI recommendations.", "Add a verified review widget and Review schema backed by real reviews.", affected_count=len(no_reviews), effort="medium")
        no_faq = [p for p in products if not p.has_faq_section and not p.question_headings]
        if no_faq and len(no_faq) > len(products) * 0.8:
            c.add("ecom-no-product-faq", "low", "Product pages have no buyer Q&A section", "Buyer questions (fit, shipping time, compatibility, warranty) are exactly what AI shopping assistants and People Also Ask surface.", "Add a 3 to 5 question FAQ block to top product templates.", affected_count=len(no_faq), effort="medium")
        copies = [p for p in products if re.search(r"-copy(-\d+)?/?$|-\d+/?$", p.url) and p.title and p.title.lower() in {q.title.lower() for q in products if q is not p}]
        if copies:
            c.add("ecom-duplicate-listings", "medium", f"{len(copies):,} product URLs look like duplicated listings", "URLs ending in -copy or -2 with the same title split rankings and confuse shoppers.", "Merge duplicates and 301 the copies to the original.", evidence=[p.url for p in copies[:4]], affected_count=len(copies), effort="low")
    if categories:
        no_intro = [p for p in categories if p.word_count < 80]
        if no_intro and len(no_intro) > len(categories) * 0.5:
            c.add("ecom-category-no-copy", "medium", f"{len(no_intro):,} category pages have no descriptive copy", "Category pages are the main ranking pages for 'buy X' queries, but a bare product grid gives Google nothing to rank.", "Add a 100 to 300 word introduction or buying guide above or below the grid, with an H1 and FAQ.", evidence=[p.url for p in no_intro[:4]], affected_count=len(no_intro), pages=[p.url for p in no_intro[:200]], effort="medium")
        else:
            c.passed("ecom-category-copy", "Category pages carry descriptive copy")
        demo = [p for p in categories if re.search(r"/collections/(frontpage|all)/?$|/category/uncategori[sz]ed", p.url, re.I)]
        if demo:
            c.add("ecom-demo-collections", "low", "Default or demo collections are indexable", "'frontpage', 'all' and 'uncategorized' collections are theme defaults that duplicate real categories.", "Noindex or redirect default collections.", evidence=[p.url for p in demo[:3]], affected_count=len(demo), effort="low")
    policy = {k: any(re.search(rx, u, re.I) for u in all_links) for k, rx in {"shipping": r"shipping|delivery", "returns": r"return|refund|exchange"}.items()}
    missing_policy = [k for k, v in policy.items() if not v]
    if missing_policy:
        c.add("ecom-no-policy-pages", "medium", f"No {' or '.join(missing_policy)} policy page linked", "Shipping and returns pages are trust requirements for shoppers, Google Merchant Center and AI shopping answers.", "Publish clear shipping and returns pages and link them in the footer and on product pages.", effort="low")
    else:
        c.passed("ecom-policy-pages", "Shipping and returns policies linked")
    if not any(p.has_payment_trust for p in products[:50] + html_pages[:10]):
        c.add("ecom-no-trust-signals", "info", "No payment or security trust signals visible", "Shoppers and raters look for recognised payment badges and security messaging near the buy button.", "Show accepted payment methods and a secure checkout note on product pages and checkout.", effort="low")
    out = c.to_dict()
    out["measured"] = True
    out["product_pages"] = len(products)
    out["category_pages"] = len(categories)
    return out
