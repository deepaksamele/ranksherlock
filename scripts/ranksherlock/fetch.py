"""HTTP fetching: polite, identifiable, thread-safe, rate-limited, with retries and size limits."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter

USER_AGENT = (
    "Mozilla/5.0 (compatible; RankSherlock/2.0; +https://github.com/deepaksamele/ranksherlock) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

DEFAULT_TIMEOUT = 20


@dataclass
class Response:
    url: str
    final_url: str
    status: int
    headers: dict
    text: str
    content: bytes
    elapsed_ms: int
    redirect_chain: list = field(default_factory=list)
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and 200 <= self.status < 400

    @property
    def content_type(self) -> str:
        return (self.headers.get("content-type") or "").lower()

    @property
    def is_html(self) -> bool:
        return "text/html" in self.content_type or "application/xhtml" in self.content_type


class RateLimiter:
    """Token bucket shared by all threads. Backs off automatically on 429 / 503."""

    def __init__(self, rate_per_s: float):
        self.rate = max(0.2, rate_per_s)
        self.base_rate = self.rate
        self.tokens = self.rate
        self.updated = time.monotonic()
        self.lock = threading.Lock()
        self.backoff_until = 0.0

    def acquire(self) -> None:
        while True:
            with self.lock:
                now = time.monotonic()
                if now < self.backoff_until:
                    wait = self.backoff_until - now
                else:
                    self.tokens = min(self.rate, self.tokens + (now - self.updated) * self.rate)
                    self.updated = now
                    if self.tokens >= 1:
                        self.tokens -= 1
                        return
                    wait = (1 - self.tokens) / self.rate
            time.sleep(min(wait, 2.0))

    def penalise(self, seconds: float = 5.0) -> None:
        with self.lock:
            self.backoff_until = max(self.backoff_until, time.monotonic() + seconds)
            self.rate = max(self.base_rate / 4, self.rate * 0.6)
            self.last_penalty = time.monotonic()

    def relax(self) -> None:
        with self.lock:
            if self.rate < self.base_rate:
                # Recover quickly: +15% per success, full reset 30 s after the last penalty.
                if time.monotonic() - getattr(self, "last_penalty", 0) > 30:
                    self.rate = self.base_rate
                else:
                    self.rate = min(self.base_rate, self.rate * 1.15)


class Fetcher:
    """Thread-safe session pool that records timing, redirects and errors instead of raising."""

    def __init__(self, timeout: int = DEFAULT_TIMEOUT, delay: float = 0.3, user_agent: str = USER_AGENT, rate_per_s: float | None = None, workers: int = 8):
        self.timeout = timeout
        self.user_agent = user_agent
        self.workers = workers
        self.limiter = RateLimiter(rate_per_s if rate_per_s else (1.0 / delay if delay > 0 else 8.0))
        self._local = threading.local()
        self._lock = threading.Lock()
        self.cache: dict[str, Response] = {}
        self.request_count = 0
        self.error_count = 0
        self.status_counts: dict[int, int] = {}

    # ----------------------------------------------------------------- session
    def _session(self) -> requests.Session:
        s = getattr(self._local, "session", None)
        if s is None:
            s = requests.Session()
            s.headers.update(
                {
                    "User-Agent": self.user_agent,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                }  # Accept-Encoding is left to requests: it only advertises brotli when it can decode it
            )
            adapter = HTTPAdapter(pool_connections=self.workers, pool_maxsize=self.workers * 2, max_retries=0)
            s.mount("https://", adapter)
            s.mount("http://", adapter)
            self._local.session = s
        return s

    def _record(self, resp: Response) -> None:
        with self._lock:
            self.request_count += 1
            if resp.error:
                self.error_count += 1
            self.status_counts[resp.status] = self.status_counts.get(resp.status, 0) + 1

    # --------------------------------------------------------------------- get
    def get(self, url: str, allow_redirects: bool = True, user_agent: Optional[str] = None, stream_limit: int = 5_000_000, cache: bool = True, retries: int = 1) -> Response:
        key = f"{user_agent or ''}|{url}"
        if cache:
            with self._lock:
                if key in self.cache:
                    return self.cache[key]
        headers = {"User-Agent": user_agent} if user_agent else None
        resp: Optional[Response] = None
        for attempt in range(retries + 1):
            self.limiter.acquire()
            started = time.time()
            try:
                r = self._session().get(url, timeout=self.timeout, allow_redirects=allow_redirects, headers=headers, stream=True)
                chunks = []
                size = 0
                for chunk in r.iter_content(chunk_size=65536):
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > stream_limit:
                        break
                r.close()
                content = b"".join(chunks)
                elapsed = int((time.time() - started) * 1000)
                encoding = r.encoding or "utf-8"
                try:
                    text = content.decode(encoding, errors="replace")
                except LookupError:
                    text = content.decode("utf-8", errors="replace")
                resp = Response(
                    url=url,
                    final_url=r.url,
                    status=r.status_code,
                    headers={k.lower(): v for k, v in r.headers.items()},
                    text=text,
                    content=content,
                    elapsed_ms=elapsed,
                    redirect_chain=[(h.status_code, h.url) for h in r.history],
                )
                if r.status_code in (429, 503):
                    self.limiter.penalise(10.0 if r.status_code == 429 else 4.0)
                    if attempt < retries:
                        continue
                else:
                    self.limiter.relax()
                break
            except requests.exceptions.SSLError as exc:
                resp = Response(url, url, 0, {}, "", b"", int((time.time() - started) * 1000), error=f"ssl: {exc.__class__.__name__}")
                break
            except requests.exceptions.Timeout:
                resp = Response(url, url, 0, {}, "", b"", int((time.time() - started) * 1000), error="timeout")
            except requests.exceptions.ConnectionError as exc:
                resp = Response(url, url, 0, {}, "", b"", int((time.time() - started) * 1000), error="connection")
                with self._lock:
                    self._conn_errors = getattr(self, "_conn_errors", 0) + 1
                    burst = self._conn_errors
                if burst % 5 == 0:  # only a burst of connection errors slows the crawl
                    self.limiter.penalise(3.0)
            except requests.exceptions.RequestException as exc:
                resp = Response(url, url, 0, {}, "", b"", int((time.time() - started) * 1000), error=f"{exc.__class__.__name__}")
                break
        assert resp is not None
        self._record(resp)
        if cache:
            with self._lock:
                if len(self.cache) < 5000:
                    self.cache[key] = resp
        return resp

    def head_status(self, url: str) -> tuple[int, Optional[str]]:
        """Cheap status check used for link validation. Falls back to GET when HEAD is refused."""
        self.limiter.acquire()
        try:
            s = self._session()
            r = s.head(url, timeout=self.timeout, allow_redirects=True)
            if r.status_code in (405, 403, 404) or r.status_code >= 500:
                r = s.get(url, timeout=self.timeout, allow_redirects=True, stream=True)
                r.close()
            with self._lock:
                self.request_count += 1
            return r.status_code, None
        except requests.exceptions.RequestException as exc:
            with self._lock:
                self.request_count += 1
            return 0, exc.__class__.__name__


def origin_of(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def registrable_host(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host.split(":")[0]
