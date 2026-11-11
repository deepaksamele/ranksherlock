"""Whole-site crawler: concurrent, rate-limited, robots-aware, sitemap-complete, SQLite-backed.

Design
- Links are crawled breadth-first from the homepage so every page gets its true click depth.
- Every URL in every sitemap is also queued; sitemap-only URLs that no page links to keep depth 99,
  which is how orphan pages are detected on a full crawl.
- Fetch + parse run in a thread pool; all shared state is mutated on the main thread only.
- Parsed pages are written to crawl.db (SQLite) in batches so a 50,000-page crawl can be resumed.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Optional
from urllib import robotparser
from urllib.parse import parse_qs, urldefrag, urlparse

from .fetch import Fetcher, origin_of, registrable_host
from .page import PageData, parse_page, page_from_dict

SKIP_EXT = re.compile(r"\.(jpg|jpeg|png|gif|webp|avif|svg|ico|zip|rar|7z|gz|mp4|mp3|avi|mov|webm|doc|docx|xls|xlsx|ppt|pptx|css|js|json|xml|txt|woff2?|ttf|eot)(\?.*)?$", re.I)
DOC_EXT = re.compile(r"\.(pdf)(\?.*)?$", re.I)
NOISY_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid", "msclkid", "ref", "replytocom", "sessionid", "sid", "phpsessid", "mc_cid", "mc_eid"}
ORPHAN_DEPTH = 99


def normalize(url: str) -> str:
    url, _ = urldefrag(url)
    p = urlparse(url)
    scheme = p.scheme.lower()
    netloc = p.netloc.lower()
    path = re.sub(r"/{2,}", "/", p.path or "/")
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


class CrawlStore:
    """SQLite persistence for pages and sitemap URLs (lets huge crawls resume and keeps RAM bounded)."""

    def __init__(self, path: Optional[Path]):
        self.path = path
        self.conn = sqlite3.connect(str(path)) if path else sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("CREATE TABLE IF NOT EXISTS pages (url TEXT PRIMARY KEY, status INTEGER, depth INTEGER, source TEXT, data TEXT)")
        self.conn.execute("CREATE TABLE IF NOT EXISTS sitemap_urls (url TEXT PRIMARY KEY, sitemap TEXT, lastmod TEXT)")
        self.conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        self.conn.commit()
        self._buffer: list[tuple] = []

    def put(self, page: PageData, source: str) -> None:
        self._buffer.append((page.url, page.status, page.depth, source, json.dumps(page.to_dict(), ensure_ascii=False)))
        if len(self._buffer) >= 100:
            self.flush()

    def flush(self) -> None:
        if self._buffer:
            self.conn.executemany("INSERT OR REPLACE INTO pages (url, status, depth, source, data) VALUES (?,?,?,?,?)", self._buffer)
            self._buffer = []
            self.conn.commit()

    def put_sitemap_urls(self, rows: list[tuple[str, str, str]]) -> None:
        self.conn.executemany("INSERT OR IGNORE INTO sitemap_urls (url, sitemap, lastmod) VALUES (?,?,?)", rows)
        self.conn.commit()

    def set_meta(self, key: str, value) -> None:
        self.conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)", (key, json.dumps(value)))
        self.conn.commit()

    def load_pages(self) -> dict[str, PageData]:
        out = {}
        for url, data in self.conn.execute("SELECT url, data FROM pages"):
            out[url] = page_from_dict(json.loads(data))
        return out

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]

    def close(self) -> None:
        self.flush()
        self.conn.close()


class Crawler:
    def __init__(self, start_url: str, max_pages: int = 50000, fetcher: Optional[Fetcher] = None, max_depth: int = 25, log=print, workers: int = 8, store_path: Optional[Path] = None, max_minutes: float = 120, resume: bool = False, max_sitemap_urls: int = 200000):
        self.start_url = normalize(start_url)
        self.origin = origin_of(self.start_url)
        self.host = registrable_host(self.start_url)
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.workers = max(1, workers)
        self.max_minutes = max_minutes
        self.max_sitemap_urls = max_sitemap_urls
        self.fetcher = fetcher or Fetcher(workers=self.workers)
        self.log = log
        self.store = CrawlStore(store_path)
        self.pages: dict[str, PageData] = {}
        self.link_queue: deque[tuple[str, int, str]] = deque()
        self.sitemap_queue: deque[tuple[str, int, str]] = deque()
        self.seen: set[str] = set()
        self.robots: Optional[robotparser.RobotFileParser] = None
        self.robots_txt: str = ""
        self.robots_status: int = 0
        self.sitemap_urls: list[str] = []
        self.sitemap_index: dict = {}
        self._sitemap_locs: list[str] = []
        self.sitemap_lastmod: dict[str, str] = {}
        self.depth_hint: dict[str, int] = {}
        self.in_flight_urls: set[str] = set()
        self.inlinks: dict[str, list] = {}  # url -> up to 5 source pages
        self.inlink_counts: dict[str, int] = {}
        self.anchor_for: dict[str, list] = {}  # url -> sample anchor texts pointing at it
        self.blocked_by_robots: list[str] = []
        self.malformed_links: dict[str, list] = {}
        self.malformed_counts: dict[str, int] = {}
        self.documents: list[str] = []  # linked PDFs etc.
        self.external_hosts: dict[str, int] = {}
        self.external_samples: dict[str, str] = {}  # outbound URL -> page it was found on
        self._absorbed = 0
        self.started_at = time.time()
        self.stopped_reason = ""
        if resume:
            self.pages = self.store.load_pages()
            self.seen.update(self.pages.keys())
            if self.pages:
                self.log(f"  resuming: {len(self.pages)} pages already in crawl.db")

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
    def load_sitemaps(self, max_files: int = 600) -> None:
        candidates = list(dict.fromkeys(self.sitemap_urls + [f"{self.origin}/sitemap.xml", f"{self.origin}/sitemap_index.xml", f"{self.origin}/sitemap-index.xml", f"{self.origin}/wp-sitemap.xml", f"{self.origin}/sitemap/sitemap.xml", f"{self.origin}/sitemaps.xml"]))
        found: list[str] = []
        children: list[str] = []
        fetched: dict[str, dict] = {}
        to_fetch = deque(candidates)
        visited: set[str] = set()
        rows: list[tuple[str, str, str]] = []
        while to_fetch and len(found) < self.max_sitemap_urls and len(visited) < max_files:
            sm = to_fetch.popleft()
            if sm in visited:
                continue
            visited.add(sm)
            resp = self.fetcher.get(sm, stream_limit=60_000_000, cache=False)
            info = {"status": resp.status, "urls": 0, "is_index": False, "lastmod_count": 0, "error": resp.error, "size_bytes": len(resp.content), "foreign_host_urls": 0, "http_urls": 0}
            fetched[sm] = info
            if not resp.ok or resp.status != 200:
                continue
            body = resp.text
            if resp.content[:2] == b"\x1f\x8b":
                import gzip

                try:
                    body = gzip.decompress(resp.content).decode("utf-8", "replace")
                except Exception:
                    info["error"] = "gzip decode failed"
                    continue
            head = body[:3000].lower()
            if "<sitemapindex" in head:
                info["is_index"] = True
                locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", body, re.I | re.S)
                locs = [l.strip() for l in locs]
                children.extend(locs)
                to_fetch.extend(locs)
                info["urls"] = len(locs)
                continue
            if "<urlset" in head or "<url>" in body[:5000].lower() or sm.endswith(".txt"):
                if sm.endswith(".txt") and "<" not in head:
                    locs = [l.strip() for l in body.splitlines() if l.strip().startswith("http")]
                    entries = [(l, "") for l in locs]
                else:
                    entries = []
                    for m in re.finditer(r"<url>(.*?)</url>", body, re.I | re.S):
                        block = m.group(1)
                        loc = re.search(r"<loc>\s*(.*?)\s*</loc>", block, re.I | re.S)
                        if not loc:
                            continue
                        lm = re.search(r"<lastmod>\s*(.*?)\s*</lastmod>", block, re.I | re.S)
                        entries.append((loc.group(1).strip(), lm.group(1).strip() if lm else ""))
                    if not entries:
                        entries = [(l.strip(), "") for l in re.findall(r"<loc>\s*(.*?)\s*</loc>", body, re.I | re.S)]
                info["urls"] = len(entries)
                info["lastmod_count"] = sum(1 for _, lm in entries if lm)
                for loc, lm in entries:
                    if registrable_host(loc) != self.host:
                        info["foreign_host_urls"] += 1
                    if loc.startswith("http://") and self.origin.startswith("https://"):
                        info["http_urls"] += 1
                    found.append(loc)
                    if lm:
                        self.sitemap_lastmod[normalize(loc)] = lm
                    rows.append((normalize(loc), sm, lm))
        self.store.put_sitemap_urls(rows)
        unique = {normalize(l) for l in found}
        self.sitemap_index = {"fetched": fetched, "children": children[:500], "total_urls": len(found), "unique_urls": len(unique), "duplicate_entries": len(found) - len(unique), "urls_sample": found[:50], "files_fetched": len(visited), "truncated": len(found) >= self.max_sitemap_urls or len(visited) >= max_files}
        self.sitemap_urls = [u for u, i in fetched.items() if i["status"] == 200 and (i["urls"] or i["is_index"])]
        self._sitemap_locs = found

    # ------------------------------------------------------------------- crawl
    def _enqueue(self, url: str, depth: int, source: str, from_sitemap: bool = False) -> None:
        raw_path = urlparse(url).path or ""
        if "//" in raw_path and not from_sitemap:
            self.malformed_links.setdefault("double-slash", []).append(f"{url} (on {source})") if len(self.malformed_links.get("double-slash", [])) < 50 else None
            self.malformed_counts["double-slash"] = self.malformed_counts.get("double-slash", 0) + 1
        if re.search(r"\s|%20$", url) and not from_sitemap:
            self.malformed_counts["whitespace"] = self.malformed_counts.get("whitespace", 0) + 1
            self.malformed_links.setdefault("whitespace", []).append(f"{url} (on {source})") if len(self.malformed_links.get("whitespace", [])) < 20 else None
        url = normalize(url)
        if registrable_host(url) != self.host:
            return
        path = urlparse(url).path
        if DOC_EXT.search(path):
            if url not in self.documents and len(self.documents) < 2000:
                self.documents.append(url)
            return
        if SKIP_EXT.search(path):
            return
        if url in self.seen:
            if from_sitemap:
                return
            # A link reached a URL we already know (fetched, in flight, or waiting in the sitemap queue):
            # record the better depth, and let the link queue fetch it first if it is still waiting.
            page = self.pages.get(url)
            if page is not None:
                if depth < page.depth:
                    page.depth = depth
                return
            if depth < self.depth_hint.get(url, ORPHAN_DEPTH):
                self.depth_hint[url] = depth
                if url not in self.in_flight_urls and depth <= self.max_depth:
                    self.link_queue.append((url, depth, source))
            return
        if depth > self.max_depth and not from_sitemap:
            return
        self.seen.add(url)
        if from_sitemap:
            self.sitemap_queue.append((url, ORPHAN_DEPTH, source))
        else:
            self.depth_hint[url] = depth
            self.link_queue.append((url, depth, source))

    def _next(self) -> Optional[tuple[str, int, str]]:
        if self.link_queue:
            return self.link_queue.popleft()
        if self.sitemap_queue:
            return self.sitemap_queue.popleft()
        return None

    def _fetch_parse(self, url: str, depth: int, source: str) -> tuple[PageData, str]:
        resp = self.fetcher.get(url, cache=False)
        html = resp.text if resp.is_html else ""
        page = parse_page(url, resp.final_url or url, resp.status, html, resp.headers, resp.elapsed_ms, len(resp.content), depth, resp.redirect_chain)
        page.error = resp.error
        return page, source

    def _absorb(self, page: PageData, source: str, store: bool = True) -> None:
        self.pages[page.url] = page
        if store:
            self.store.put(page, source)
        final = normalize(page.final_url) if page.final_url else page.url
        if page.status == 200 and page.text_sample is not None and registrable_host(final) == self.host and (page.title or page.word_count or page.internal_links):
            depth = page.depth if page.depth < ORPHAN_DEPTH else self.max_depth  # links from orphan pages do not define depth
            for link, anchor in zip(page.internal_links, page.anchor_texts or [""] * len(page.internal_links)):
                n = normalize(link)
                self.inlink_counts[n] = self.inlink_counts.get(n, 0) + 1
                src = self.inlinks.setdefault(n, [])
                if len(src) < 5 and page.url not in src:
                    src.append(page.url)
                if anchor:
                    a = self.anchor_for.setdefault(n, [])
                    if len(a) < 5:
                        a.append(anchor)
                self._enqueue(link, depth + 1, page.url)
            for ext in page.external_links:
                h = registrable_host(ext.get("href", ""))
                if h:
                    self.external_hosts[h] = self.external_hosts.get(h, 0) + 1
                href = ext.get("href", "")
                if href.startswith("http") and len(self.external_samples) < 400 and href not in self.external_samples:
                    self.external_samples[href] = page.url
        # Keep full detail for the first 500 pages (template analysis); slim the rest so 50,000 pages fit in memory.
        self._absorbed += 1
        if self._absorbed > 500 and page.depth > 1:
            page.slim()

    def run(self) -> dict:
        self.load_robots()
        self.load_sitemaps()
        self._enqueue(self.start_url, 0, "start")
        for loc in self._sitemap_locs:
            self._enqueue(loc, 1, "sitemap", from_sitemap=True)
        # Pages loaded from a resumed crawl need their links replayed into the queues.
        for p in list(self.pages.values()):
            self._absorb(p, "resume", store=False)
        fetched = len(self.pages)
        deadline = self.started_at + self.max_minutes * 60
        in_flight: dict = {}
        last_log = time.time()
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            while True:
                while len(in_flight) < self.workers and fetched + len(in_flight) < self.max_pages:
                    item = self._next()
                    if item is None:
                        break
                    url, depth, source = item
                    if url in self.pages or url in self.in_flight_urls:
                        continue
                    depth = min(depth, self.depth_hint.get(url, depth))
                    if not self.allowed(url):
                        if url not in self.blocked_by_robots:
                            self.blocked_by_robots.append(url)
                        continue
                    self.in_flight_urls.add(url)
                    fut = pool.submit(self._fetch_parse, url, depth, source)
                    in_flight[fut] = url
                if not in_flight:
                    self.stopped_reason = "complete" if fetched < self.max_pages else "page cap"
                    break
                done, _ = wait(list(in_flight.keys()), timeout=60, return_when=FIRST_COMPLETED)
                for fut in done:
                    url = in_flight.pop(fut, None)
                    self.in_flight_urls.discard(url)
                    try:
                        page, source = fut.result()
                    except Exception as exc:  # pragma: no cover
                        self.log(f"  worker error: {exc.__class__.__name__}: {str(exc)[:120]}")
                        continue
                    fetched += 1
                    page.depth = min(page.depth, self.depth_hint.get(page.url, page.depth))
                    self._absorb(page, source)
                now = time.time()
                if now - last_log >= 5:
                    rate = fetched / max(now - self.started_at, 1)
                    remaining = len(self.link_queue) + len(self.sitemap_queue)
                    eta = int(min(remaining, self.max_pages - fetched) / max(rate, 0.1))
                    self.log(f"  crawled {fetched} pages ({rate:.1f}/s), queue {remaining}, eta {eta // 60}m{eta % 60:02d}s")
                    last_log = now
                if now > deadline:
                    self.stopped_reason = f"time budget ({self.max_minutes} min)"
                    for fut in in_flight:
                        fut.cancel()
                    break
                if fetched >= self.max_pages and not in_flight:
                    self.stopped_reason = "page cap"
                    break
        self.store.flush()
        self.store.set_meta("summary", self.summary(light=True))
        return self.summary()

    def summary(self, light: bool = False) -> dict:
        remaining = len(self.link_queue) + len(self.sitemap_queue)
        out = {
            "start_url": self.start_url,
            "origin": self.origin,
            "host": self.host,
            "pages_crawled": len(self.pages),
            "pages_discovered": len(self.seen),
            "queue_remaining": remaining,
            "max_pages": self.max_pages,
            "complete": remaining == 0 and self.stopped_reason in ("complete", ""),
            "stopped_reason": self.stopped_reason,
            "workers": self.workers,
            "blocked_by_robots": self.blocked_by_robots[:100],
            "blocked_by_robots_count": len(self.blocked_by_robots),
            "robots_status": self.robots_status,
            "robots_txt": self.robots_txt[:6000],
            "sitemaps": self.sitemap_index,
            "sitemap_files": self.sitemap_urls,
            "documents": self.documents[:200],
            "documents_count": len(self.documents),
            "malformed_links": {k: v[:10] for k, v in self.malformed_links.items()},
            "malformed_counts": dict(self.malformed_counts),
            "external_hosts": dict(sorted(self.external_hosts.items(), key=lambda kv: -kv[1])[:100]),
            "duration_s": round(time.time() - self.started_at, 1),
            "requests": self.fetcher.request_count,
            "request_errors": self.fetcher.error_count,
            "status_counts": dict(self.fetcher.status_counts),
        }
        if not light:
            out["inlinks"] = self.inlinks
            out["inlink_counts"] = self.inlink_counts
        return out
