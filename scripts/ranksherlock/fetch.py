"""HTTP fetching with a polite, identifiable user agent and simple caching."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

import requests

USER_AGENT = (
    "Mozilla/5.0 (compatible; RankSherlock/1.0; +https://github.com/deepaksamele/ranksherlock) "
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


class Fetcher:
    """Session wrapper that records timing, redirects and errors instead of raising."""

    def __init__(self, timeout: int = DEFAULT_TIMEOUT, delay: float = 0.3, user_agent: str = USER_AGENT):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        self.timeout = timeout
        self.delay = delay
        self._last_request_at = 0.0
        self.cache: dict[str, Response] = {}
        self.request_count = 0

    def _throttle(self) -> None:
        wait = self.delay - (time.time() - self._last_request_at)
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.time()

    def get(self, url: str, allow_redirects: bool = True, user_agent: Optional[str] = None, stream_limit: int = 5_000_000) -> Response:
        key = f"{user_agent or ''}|{url}"
        if key in self.cache:
            return self.cache[key]
        self._throttle()
        headers = {"User-Agent": user_agent} if user_agent else None
        started = time.time()
        try:
            r = self.session.get(url, timeout=self.timeout, allow_redirects=allow_redirects, headers=headers, stream=True)
            content = b""
            for chunk in r.iter_content(chunk_size=65536):
                content += chunk
                if len(content) > stream_limit:
                    break
            r.close()
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
        except requests.exceptions.SSLError as exc:
            resp = Response(url, url, 0, {}, "", b"", int((time.time() - started) * 1000), error=f"ssl: {exc.__class__.__name__}")
        except requests.exceptions.Timeout:
            resp = Response(url, url, 0, {}, "", b"", int((time.time() - started) * 1000), error="timeout")
        except requests.exceptions.RequestException as exc:
            resp = Response(url, url, 0, {}, "", b"", int((time.time() - started) * 1000), error=f"{exc.__class__.__name__}")
        self.request_count += 1
        self.cache[key] = resp
        return resp

    def head_status(self, url: str) -> tuple[int, Optional[str]]:
        """Cheap status check used for link validation. Falls back to GET when HEAD is refused."""
        self._throttle()
        try:
            r = self.session.head(url, timeout=self.timeout, allow_redirects=True)
            if r.status_code in (405, 403, 404) or r.status_code >= 500:
                r = self.session.get(url, timeout=self.timeout, allow_redirects=True, stream=True)
                r.close()
            self.request_count += 1
            return r.status_code, None
        except requests.exceptions.RequestException as exc:
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
