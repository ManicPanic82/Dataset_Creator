# Phase 4: Crawler and Extraction

## Objective

Fetch permitted public pages from approved Phase 3 source candidates, extract readable text, and retain provenance without executing page scripts or bypassing site restrictions.

## Initial implementation boundary

- HTTP/HTTPS only; candidate URLs are normalized again immediately before each request.
- Resolve hostnames and reject any destination with a non-global IP address.
- Redirects are handled manually, with URL and DNS validation repeated at each hop; maximum five redirects.
- Disable environment proxy inheritance, use a clear application user agent, and do not send credentials or cookies.
- Respect robots.txt by default. A missing robots.txt (HTTP 404) permits crawling; server errors and network failures fail closed and disallow crawling.
- Limit page count, depth, retries, request timeout, streamed response bytes, and per-host request rate. A bounded worker pool runs up to the configured concurrency (1–4) across different hosts. Requests to the same host are serialized through a shared per-host lock so the configured delay cannot be bypassed by parallel workers.
- Extract title, readable text, links, and a SHA-256 content hash. Scripts and non-content elements are ignored.
- Parse XML sitemap URL entries with bounded result counts and expose sitemap import in Sources.
- Restrict link following to the exact origins explicitly supplied as crawl roots.
- No JavaScript execution, login, CAPTCHA handling, paywall bypass, or access-control circumvention.

## Current service API

`CrawlSettings` provides validated safety bounds.
`WebCrawler.fetch(url)` fetches and extracts one page.
`WebCrawler.parse_sitemap(url)` parses a sitemap.
`WebCrawler.crawl(start_urls)` performs a bounded same-origin crawl and returns pages plus per-URL failures. The worker pool reserves page slots before dispatch, caps in-flight work at `max_concurrent_requests`, and stops scheduling when cancelled. Same-host requests share a lock and rate-limit clock; robots.txt is fetched once per origin even when several workers start together.

The Sources page is integrated with the existing project-scoped candidate list. A user must accept a candidate in Research before fetching it. Fetching runs in the background, checks robots.txt, and saves extracted snapshots and provenance in SQLite. The page displays title, final URL, and text previews. Same-origin links are followed within the configured page/depth bounds. Users can also import URLs from a public XML sitemap, with each URL added as a reviewable candidate. The content repository is isolated from the existing research-plan tables.

## Important security note

DNS is checked immediately before each outbound request and again after redirects. This blocks ordinary private-network and redirect attacks. The default HTTPX transport performs its own hostname resolution when opening the connection, so this implementation does not claim resistance to a malicious DNS-rebinding race. Production hardening must pin the validated address at connection time or use a transport that connects only to the validated public IP while preserving TLS hostname verification. Do not treat this first Phase 4 implementation as a hardened public crawler until that transport-level protection is implemented and reviewed.

## Validation

Run on Windows PowerShell:

```powershell
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\python.exe -m pytest
```
