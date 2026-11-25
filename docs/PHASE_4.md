# Phase 4: Crawler and Extraction

## Objective

Fetch permitted public pages from approved Phase 3 source candidates, extract readable text, and retain provenance without executing page scripts or bypassing site restrictions.

## Initial implementation boundary

- HTTP/HTTPS only; candidate URLs are normalized again immediately before each request.
- Resolve hostnames and reject any destination with a non-global IP address.
- Redirects are handled manually, with URL and DNS validation repeated at each hop; maximum five redirects.
- Disable environment proxy inheritance, use a clear application user agent, and do not send credentials or cookies.
- Respect robots.txt by default. A robots.txt retrieval failure is treated conservatively as disallow.
- Limit page count, depth, retries, request timeout, streamed response bytes, and per-host request rate. Requests are currently sequential; the concurrency setting is a validated upper-bound configuration for the later worker-pool implementation.
- Extract title, readable text, links, and a SHA-256 content hash. Scripts and non-content elements are ignored.
- Parse XML sitemap URL entries with bounded result counts.
- Restrict link following to the exact origins explicitly supplied as crawl roots.
- No JavaScript execution, login, CAPTCHA handling, paywall bypass, or access-control circumvention.

## Current service API

`CrawlSettings` provides validated safety bounds.
`WebCrawler.fetch(url)` fetches and extracts one page.
`WebCrawler.parse_sitemap(url)` parses a sitemap.
`WebCrawler.crawl(start_urls)` performs a bounded same-origin crawl and returns pages plus per-URL failures.

The Sources page is integrated with the existing project-scoped candidate list. A user must accept a candidate in Research before fetching it. Fetching runs in the background, checks robots.txt, and saves the extracted snapshot and provenance in SQLite. The page displays the extracted title, final URL, and text preview. The content repository is isolated from the existing research-plan tables.

## Important security note

DNS is checked immediately before each outbound request and again after redirects. This blocks ordinary private-network and redirect attacks. The default HTTPX transport performs its own hostname resolution when opening the connection, so this implementation does not claim resistance to a malicious DNS-rebinding race. Production hardening must pin the validated address at connection time or use a transport that connects only to the validated public IP while preserving TLS hostname verification. Do not treat this first Phase 4 implementation as a hardened public crawler until that transport-level protection is implemented and reviewed.

## Validation

Run on Windows PowerShell:

```powershell
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\python.exe -m pytest
```
