"""Breadth-first site crawler with a page cap, robots.txt respect and sitemap seeding."""

from __future__ import annotations

import re
import sys
import time
from collections import deque
from typing import Optional
from urllib import robotparser
from urllib.parse import urljoin, urlparse, urldefrag, parse_qs

from .fetch import Fetcher, origin_of, registrable_host
from .page import parse_page, PageData

SKIP_EXT = re.compile(r"\.(jpg|jpeg|png|gif|webp|avif|svg|ico|pdf|zip|rar|7z|gz|mp4|mp3|avi|mov|webm|doc|docx|xls|xlsx|ppt|pptx|css|js|json|xml|txt|woff2?|ttf|eot)(\?.*)?$", re.I)
NOISY_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid", "ref", "replytocom", "sessionid", "sid"}


def normalize(url: str) -> str:
    url, _ = urldefrag(url)
    p = urlparse(url)
    scheme = p.scheme.lower()
    netloc = p.netloc.lower()
    path = p.path or "/"
    if p.query:
        params = parse_qs(p.query, keep_blank_values=True)
        kept = {k: v for k, v in params.items() if k.lower() not in NOISY_PARAMS}
        query = "&".join(f"{k}={v[0]}" for k, v in sorted(kept.items()))
    else:
        query = ""
    rebuilt = f"{scheme}://{netloc}{path}"
    if query:
        rebuilt += f"?{query}"
    return rebuilt


class Crawler:
    def __init__(self, start_url: str, max_pages: int = 100, fetcher: Optional[Fetcher] = None, max_depth: int = 6, log=print):
        self.start_url = normalize(start_url)
        self.origin = origin_of(self.start_url)
        self.host = registrable_host(self.start_url)
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.fetcher = fetcher or Fetcher()
        self.log = log
        self.pages: dict[str, PageData] = {}
        self.queue: deque[tuple[str, int, str]] = deque()
        self.seen: set[str] = set()
        self.robots: Optional[robotparser.RobotFileParser] = None
        self.robots_txt: str = ""
        self.robots_status: int = 0
        self.sitemap_urls: list[str] = []
        self.sitemap_index: dict = {}
        self.inlinks: dict[str, set] = {}
        self.blocked_by_robots: list[str] = []
        self.started_at = time.time()

    # ------------------------------------------------------------------ robots
    def load_robots(self) -> None:
        url = f"{self.origin}/robots.txt"
        resp = self.fetcher.get(url)
        self.robots_status = resp.status
        self.robots = robotparser.RobotFileParser()
        if resp.ok and resp.status == 200:
            self.robots_txt = resp.text
            self.robots.parse(resp.text.splitlines())
            for line in resp.text.splitlines():
                if line.lower().startswith("sitemap:"):
                    self.sitemap_urls.append(line.split(":", 1)[1].strip())
        else:
            self.robots.parse([])

    def allowed(self, url: str) -> bool:
        if not self.robots:
            return True
        try:
            return self.robots.can_fetch("*", url) and self.robots.can_fetch("Googlebot", url)
        except Exception:
            return True

    # ---------------------------------------------------------------- sitemaps
    def load_sitemaps(self, limit_urls: int = 5000) -> None:
        candidates = list(dict.fromkeys(self.sitemap_urls + [f"{self.origin}/sitemap.xml", f"{self.origin}/sitemap_index.xml", f"{self.origin}/sitemap-index.xml", f"{self.origin}/wp-sitemap.xml"]))
        found: list[str] = []
        children: list[str] = []
        fetched: dict[str, dict] = {}
        to_fetch = deque(candidates)
        visited: set[str] = set()
        while to_fetch and len(found) < limit_urls and len(visited) < 40:
            sm = to_fetch.popleft()
            if sm in visited:
                continue
            visited.add(sm)
            resp = self.fetcher.get(sm, stream_limit=15_000_000)
            info = {"status": resp.status, "urls": 0, "is_index": False, "lastmod_count": 0, "error": resp.error, "size_bytes": len(resp.content)}
            fetched[sm] = info
            if not resp.ok or resp.status != 200:
                continue
            body = resp.text
            if resp.content[:2] == b"\x1f\x8b":
                import gzip

                try:
                    body = gzip.decompress(resp.content).decode("utf-8", "replace")
                except Exception:
                    continue
            if "<sitemapindex" in body[:2000].lower():
                info["is_index"] = True
                locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", body, re.I | re.S)
                children.extend(l.strip() for l in locs)
                to_fetch.extend(l.strip() for l in locs[:30])
                info["urls"] = len(locs)
                continue
            if "<urlset" in body[:3000].lower() or "<url>" in body[:5000].lower():
                locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", body, re.I | re.S)
                info["urls"] = len(locs)
                info["lastmod_count"] = len(re.findall(r"<lastmod>", body, re.I))
                found.extend(l.strip() for l in locs)
        self.sitemap_index = {"fetched": fetched, "children": children, "total_urls": len(found), "urls_sample": found[:50]}
        self.sitemap_urls = [u for u, i in fetched.items() if i["status"] == 200 and (i["urls"] or i["is_index"])]
        self._sitemap_locs = found

    # ------------------------------------------------------------------- crawl
    def _enqueue(self, url: str, depth: int, source: str) -> None:
        url = normalize(url)
        if url in self.seen:
            return
        if registrable_host(url) != self.host:
            return
        if SKIP_EXT.search(urlparse(url).path):
            return
        if depth > self.max_depth:
            return
        self.seen.add(url)
        self.queue.append((url, depth, source))

    def run(self) -> dict:
        self.load_robots()
        self.load_sitemaps()
        self._enqueue(self.start_url, 0, "start")
        # Seed a slice of sitemap URLs so deep sections get sampled even on big sites
        seeded = 0
        for loc in getattr(self, "_sitemap_locs", [])[: max(10, self.max_pages // 3)]:
            self._enqueue(loc, 1, "sitemap")
            seeded += 1
        fetched = 0
        while self.queue and fetched < self.max_pages:
            url, depth, source = self.queue.popleft()
            if not self.allowed(url):
                self.blocked_by_robots.append(url)
                continue
            resp = self.fetcher.get(url)
            fetched += 1
            final = normalize(resp.final_url) if resp.final_url else url
            html = resp.text if resp.is_html else ""
            page = parse_page(url, resp.final_url, resp.status, html, resp.headers, resp.elapsed_ms, len(resp.content), depth, resp.redirect_chain)
            page.error = resp.error
            self.pages[url] = page
            if resp.is_html and resp.status == 200 and registrable_host(final) == self.host:
                for link in page.internal_links:
                    n = normalize(link)
                    self.inlinks.setdefault(n, set()).add(url)
                    self._enqueue(link, depth + 1, url)
            if fetched % 10 == 0:
                self.log(f"  crawled {fetched}/{self.max_pages} pages, queue {len(self.queue)}")
        return self.summary()

    def summary(self) -> dict:
        return {
            "start_url": self.start_url,
            "origin": self.origin,
            "host": self.host,
            "pages_crawled": len(self.pages),
            "pages_discovered": len(self.seen),
            "queue_remaining": len(self.queue),
            "max_pages": self.max_pages,
            "blocked_by_robots": self.blocked_by_robots[:50],
            "robots_status": self.robots_status,
            "robots_txt": self.robots_txt[:6000],
            "sitemaps": self.sitemap_index,
            "sitemap_files": self.sitemap_urls,
            "duration_s": round(time.time() - self.started_at, 1),
            "requests": self.fetcher.request_count,
            "inlinks": {k: sorted(v)[:20] for k, v in self.inlinks.items()},
        }
