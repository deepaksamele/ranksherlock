"""Offline smoke tests (no network). Run: python -m pytest tests  or  python tests/test_smoke.py"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from ranksherlock.catalog import CHECKS, lookup  # noqa: E402
from ranksherlock.crawl import normalize  # noqa: E402
from ranksherlock.findings import Collector, score_from_penalty, weighted_penalty  # noqa: E402
from ranksherlock.geo import analyze_llms_txt, bot_status  # noqa: E402
from ranksherlock.page import parse_page  # noqa: E402
from ranksherlock.score import build_scores, grade  # noqa: E402

HTML = """<!doctype html><html lang="en"><head><title>Seawall Repair in Tampa | Acme Marine</title>
<meta name="description" content="Acme Marine repairs seawalls and docks across Tampa Bay. Licensed, insured, free estimates.">
<meta name="viewport" content="width=device-width, initial-scale=1"><link rel="canonical" href="https://example.com/seawall-repair">
<meta property="og:title" content="Seawall Repair"><meta property="og:image" content="https://example.com/a.jpg">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[
{"@type":"Question","name":"How much does seawall repair cost?","acceptedAnswer":{"@type":"Answer","text":"From $150 per foot."}},
{"@type":"Question","name":"A question that is not on the page at all?","acceptedAnswer":{"@type":"Answer","text":"x"}}]}</script>
</head><body><header><nav><a href="/">Home</a><a href="/about">About us and our very long navigation label text here</a></nav></header>
<main><h1>Seawall Repair in Tampa</h1>
<p>Seawall repair is the process of restoring a failing retaining wall along a waterfront property. Acme Marine has repaired 420 seawalls in Tampa Bay since 2009, and most repairs take three to five days.</p>
<h2>How much does seawall repair cost?</h2><p>Most Tampa seawall repairs cost between $150 and $600 per linear foot depending on material and access.</p>
<ul><li>Vinyl</li><li>Concrete</li></ul><img src="/a.jpg" alt="Seawall crew at work" width="800" height="600"><img src="/b.jpg">
<a href="/docks">Dock building</a> <a href="https://www.epa.gov/x">EPA guidance</a></main>
<footer><p>Acme Marine, 123 Harbor Street, Tampa, FL 33602. Call us (813) 555-0100. Mon - Fri 8am - 5pm.</p></footer></body></html>"""


def test_parse_page_main_and_full_signals():
    p = parse_page("https://example.com/seawall-repair", "https://example.com/seawall-repair", 200, HTML, {"content-type": "text/html"}, 120, len(HTML), 1, [])
    assert p.title.startswith("Seawall Repair")
    assert p.h1 == ["Seawall Repair in Tampa"]
    assert p.word_count < p.full_word_count  # navigation and footer are excluded from the main-content count
    assert p.has_street_address and p.has_hours_text and p.phones  # footer signals still detected
    assert p.images_total == 2 and p.images_missing_alt == 1 and p.images_no_dims == 1
    assert p.question_headings and p.first_paragraph_words > 20
    assert p.faq_schema_questions == 2 and p.faq_schema_hidden == 1
    assert p.internal_link_count == 3 and p.authority_ext_links == 1
    assert "FAQPage" in p.schema_types and p.has_og


def test_normalize():
    assert normalize("https://Example.com/a//b/?utm_source=x&b=2#frag") == "https://example.com/a/b/?b=2"


def test_bot_status_and_llms():
    robots = "User-agent: *\nDisallow: /admin\n\nUser-agent: GPTBot\nDisallow: /\n\nUser-agent: PerplexityBot\nDisallow: /private\n"
    assert bot_status(robots, "GPTBot") == "blocked"
    assert bot_status(robots, "OAI-SearchBot") == "allowed-by-wildcard"
    assert bot_status(robots, "PerplexityBot") == "partial"
    assert bot_status("", "GPTBot") == "no-robots"
    info = analyze_llms_txt("# Acme\n> Marine contractor\n## Services\n- [Seawalls](https://example.com/seawalls): repair\n", "https://example.com")
    assert info["has_h1"] and info["has_description"] and info["links"] == 1


def test_scoring_is_deterministic_and_soft_capped():
    lows = [{"severity": "low"}] * 40
    assert weighted_penalty(lows) == 6 + (40 - 6) * 0.5  # 23
    assert score_from_penalty(weighted_penalty(lows)) == 54
    c = Collector("technical")
    c.add("no-hsts", "low", "No HSTS", "why", "fix")
    c.passed("https", "HTTPS")
    cats = {"technical": c.to_dict(), "content": Collector("content").to_dict(), "schema": Collector("schema").to_dict(), "geo": Collector("geo").to_dict()}
    s1 = build_scores(cats, {"business_type": "business / services"})
    s2 = build_scores(cats, {"business_type": "business / services"})
    assert s1["overall"] == s2["overall"] and s1["grade"] == grade(s1["overall"])
    assert s1["findings"][0]["what"]  # catalog text attached


def test_catalog_covers_declared_checks():
    import json
    import subprocess

    root = Path(__file__).resolve().parent.parent
    out = subprocess.run([sys.executable, str(root / "scripts" / "list_checks.py"), "--json"], capture_output=True, text=True).stdout
    ids = {f["id"] for m in json.loads(out).values() for f in m["fails"] + m["passes"]}
    missing = sorted(i for i in ids if not lookup(i))
    assert not missing, f"check ids without catalog text: {missing}"
    assert len(CHECKS) >= 300


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
