from __future__ import annotations

import hashlib
import ipaddress
import socket
import time
import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from dataset_forge.services.research import normalize_public_url

_USER_AGENT = "DatasetForgeAI/0.1 (+responsible research crawler)"


@dataclass(frozen=True)
class CrawlSettings:
    max_pages: int = 20
    max_depth: int = 2
    max_concurrent_requests: int = 2
    request_timeout: float = 30.0
    max_retries: int = 2
    max_content_bytes: int = 2_000_000
    delay_seconds: float = 1.0
    respect_robots_txt: bool = True

    def __post_init__(self) -> None:
        if not 1 <= self.max_pages <= 500:
            raise ValueError("max_pages must be between 1 and 500.")
        if not 0 <= self.max_depth <= 5:
            raise ValueError("max_depth must be between 0 and 5.")
        if not 1 <= self.max_concurrent_requests <= 4:
            raise ValueError("max_concurrent_requests must be between 1 and 4.")
        if not 1 <= self.request_timeout <= 120:
            raise ValueError("request_timeout must be between 1 and 120 seconds.")
        if not 0 <= self.max_retries <= 5:
            raise ValueError("max_retries must be between 0 and 5.")
        if not 1024 <= self.max_content_bytes <= 10_000_000:
            raise ValueError("max_content_bytes must be between 1 KiB and 10 MB.")
        if not 0 <= self.delay_seconds <= 30:
            raise ValueError("delay_seconds must be between 0 and 30 seconds.")


@dataclass(frozen=True)
class ExtractedPage:
    requested_url: str
    final_url: str
    title: str
    text: str
    links: tuple[str, ...]
    content_hash: str
    http_status: int
    fetched_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds")
    )


@dataclass(frozen=True)
class CrawlFailure:
    url: str
    reason: str
    http_status: int | None = None


@dataclass(frozen=True)
class CrawlResult:
    pages: tuple[ExtractedPage, ...]
    failures: tuple[CrawlFailure, ...]


class _PageParser(HTMLParser):
    _IGNORED = {"script", "style", "noscript", "svg", "canvas", "iframe", "nav", "footer"}
    _BLOCKS = {"p", "div", "section", "article", "main", "h1", "h2", "h3", "h4",
               "h5", "h6", "li", "br", "tr"}

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[str] = []
        self._ignored_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag in self._IGNORED:
            self._ignored_depth += 1
        if tag == "title":
            self._in_title = True
        if (
            tag == "a"
            and attributes.get("href")
            and not self._ignored_depth
            and len(self.links) < 500
        ):
            try:
                self.links.append(
                    normalize_public_url(urljoin(self.base_url, attributes["href"]))
                )
            except ValueError:
                pass
        if tag in self._BLOCKS:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._IGNORED and self._ignored_depth:
            self._ignored_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag in self._BLOCKS:
            self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if not value:
            return
        if self._in_title:
            self.title_parts.append(value)
        if not self._ignored_depth:
            self.text_parts.append(value)


def extract_html(html: str, base_url: str) -> tuple[str, str, tuple[str, ...]]:
    parser = _PageParser(base_url)
    parser.feed(html)
    parser.close()
    title = " ".join(parser.title_parts).strip()[:500]
    text = "\n".join(part for part in parser.text_parts if part).strip()
    return title, text[:1_000_000], tuple(dict.fromkeys(parser.links))


def _validate_public_dns(hostname: str, resolver=socket.getaddrinfo) -> None:
    try:
        records = resolver(hostname, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError(f"Could not resolve source hostname: {exc}") from exc
    if not records:
        raise ValueError("Source hostname did not resolve to an IP address.")
    for record in records:
        address = ipaddress.ip_address(record[4][0].split("%", 1)[0])
        if not address.is_global:
            raise ValueError("Source hostname resolves to a non-public network address.")


class WebCrawler:
    """Bounded HTTP crawler. It never executes page scripts or follows unsafe redirects."""

    def __init__(
        self,
        settings: CrawlSettings | None = None,
        *,
        client: httpx.Client | None = None,
        resolver=socket.getaddrinfo,
    ) -> None:
        self.settings = settings or CrawlSettings()
        self._owns_client = client is None
        self.client = client or httpx.Client(
            timeout=self.settings.request_timeout,
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": _USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        )
        self._resolver = resolver
        self._robots_cache: dict[str, RobotFileParser] = {}
        self._last_request: dict[str, float] = {}

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> WebCrawler:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _request(self, url: str) -> httpx.Response:
        current = normalize_public_url(url)
        for _ in range(6):
            parsed = urlsplit(current)
            _validate_public_dns(parsed.hostname or "", self._resolver)
            domain = parsed.hostname or ""
            elapsed = time.monotonic() - self._last_request.get(domain, 0)
            wait = self.settings.delay_seconds - elapsed
            if wait > 0:
                time.sleep(wait)
            with self.client.stream("GET", current, follow_redirects=False) as response:
                self._last_request[domain] = time.monotonic()
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if location:
                        current = normalize_public_url(urljoin(current, location))
                        continue
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > self.settings.max_content_bytes:
                        raise ValueError(
                            "Response exceeded the configured content-size limit."
                        )
                return httpx.Response(
                    status_code=response.status_code,
                    headers=response.headers,
                    content=bytes(body),
                    request=response.request,
                    extensions=response.extensions,
                )
        raise ValueError("Too many redirects (maximum 5).")

    def _robots(self, origin: str) -> RobotFileParser:
        if origin not in self._robots_cache:
            parser = RobotFileParser()
            parser.set_url(urljoin(origin, "/robots.txt"))
            try:
                response = self._request(parser.url)
                if response.status_code == 200:
                    parser.parse(response.text.splitlines())
                elif response.status_code == 404:
                    # RFC 9309 treats a missing robots.txt as unavailable, not as a
                    # blanket crawl prohibition. Set RobotFileParser's explicit
                    # allow-all state because an empty or parsed rule set can still
                    # be interpreted as disallowing requests by some parser paths.
                    parser.parse([])
                    parser.allow_all = True
                    parser.disallow_all = False
                else:
                    parser.parse(["User-agent: *", "Disallow: /"])
            except (httpx.HTTPError, ValueError):
                parser.parse(["User-agent: *", "Disallow: /"])
            self._robots_cache[origin] = parser
        return self._robots_cache[origin]

    def fetch(self, url: str) -> ExtractedPage:
        requested = normalize_public_url(url)
        response: httpx.Response | None = None
        last_error: Exception | None = None
        for attempt in range(self.settings.max_retries + 1):
            try:
                response = self._request(requested)
                if response.status_code in {429, 500, 502, 503, 504}:
                    if attempt < self.settings.max_retries:
                        time.sleep(min(2 ** attempt, 5))
                        continue
                break
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt >= self.settings.max_retries:
                    raise
                time.sleep(min(2 ** attempt, 5))
        if response is None:
            raise RuntimeError(f"Request failed: {last_error}")
        if response.status_code != 200:
            raise ValueError(f"HTTP request returned status {response.status_code}.")
        content_type = response.headers.get("content-type", "").lower()
        if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
            raise ValueError(f"Unsupported content type: {content_type or 'unknown'}.")
        body = bytearray()
        for chunk in response.iter_bytes():
            body.extend(chunk)
            if len(body) > self.settings.max_content_bytes:
                raise ValueError("Page exceeded the configured content-size limit.")
        encoding = response.encoding or "utf-8"
        html = bytes(body).decode(encoding, errors="replace")
        title, text, links = extract_html(html, str(response.url))
        if not text:
            raise ValueError("No readable page text was extracted.")
        return ExtractedPage(
            requested_url=requested,
            final_url=str(response.url),
            title=title,
            text=text,
            links=links,
            content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            http_status=response.status_code,
        )

    def parse_sitemap(self, url: str, *, max_urls: int = 500) -> tuple[str, ...]:
        if not 1 <= max_urls <= 5000:
            raise ValueError("max_urls must be between 1 and 5000.")
        sitemap_url = normalize_public_url(url)
        parsed_url = urlsplit(sitemap_url)
        origin = f"{parsed_url.scheme}://{parsed_url.netloc}"
        if self.settings.respect_robots_txt and not self._robots(origin).can_fetch(
            _USER_AGENT, sitemap_url
        ):
            raise ValueError("Sitemap access is disallowed by robots.txt.")
        response = self._request(sitemap_url)
        if response.status_code != 200:
            raise ValueError(f"Sitemap request returned status {response.status_code}.")
        if len(response.content) > self.settings.max_content_bytes:
            raise ValueError("Sitemap exceeded the configured content-size limit.")
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as exc:
            raise ValueError("Sitemap XML is malformed.") from exc
        namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        locations = [
            element.text.strip()
            for element in root.findall(".//sm:loc", namespace)
            if element.text and element.text.strip()
        ]
        safe: list[str] = []
        for location in locations:
            try:
                normalized = normalize_public_url(location)
            except ValueError:
                continue
            if normalized not in safe:
                safe.append(normalized)
            if len(safe) >= max_urls:
                break
        return tuple(safe)

    def crawl(
        self,
        start_urls: tuple[str, ...] | list[str],
        *,
        max_pages: int | None = None,
        progress=None,
        cancelled=None,
    ) -> CrawlResult:
        page_limit = self.settings.max_pages if max_pages is None else max_pages
        if not 1 <= page_limit <= self.settings.max_pages:
            raise ValueError("max_pages must be between 1 and the configured page limit.")
        queue: deque[tuple[str, int]] = deque()
        roots: set[str] = set()
        if len(start_urls) > page_limit:
            raise ValueError("The number of starting URLs cannot exceed the page limit.")
        for raw in start_urls:
            url = normalize_public_url(raw)
            parsed = urlsplit(url)
            root = f"{parsed.scheme}://{parsed.netloc}"
            roots.add(root)
            queue.append((url, 0))
        seen: set[str] = set()
        pages: list[ExtractedPage] = []
        failures: list[CrawlFailure] = []
        while queue and len(pages) < page_limit:
            if cancelled is not None and cancelled():
                break
            url, depth = queue.popleft()
            if url in seen:
                continue
            seen.add(url)
            origin = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}"
            if self.settings.respect_robots_txt and not self._robots(origin).can_fetch(
                _USER_AGENT, url
            ):
                failures.append(CrawlFailure(url, "Blocked by robots.txt."))
                continue
            try:
                page = self.fetch(url)
                pages.append(page)
                if depth < self.settings.max_depth:
                    for link in page.links:
                        parsed_link = urlsplit(link)
                        link_origin = f"{parsed_link.scheme}://{parsed_link.netloc}"
                        if link_origin in roots and link not in seen:
                            queue.append((link, depth + 1))
            except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                failures.append(CrawlFailure(url, str(exc)))
            if progress is not None:
                progress(len(pages) + len(failures), page_limit)
        return CrawlResult(tuple(pages), tuple(failures))
