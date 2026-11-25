# Phase 4: Crawler and Extraction

## Objective

Fetch permitted public pages from approved Phase 3 source candidates, extract readable text, and retain provenance without executing page scripts or bypassing site restrictions.

## Initial implementation boundary

- HTTP/HTTPS only; candidate URLs are normalized again immediately before each request.
- Resolve hostnames and reject any destination with a non-global IP address.
- Redirects are handled manually, with URL and DNS validation repeated at each hop; maximum five redirects.
- Disable environment proxy inheritance, use a clear application user agent, and do not send credentials or cookies.
- Respect robots.txt by default. A robots.txt retrieval failure is treated conservatively as disallow.
- Limit page count, depth, retries, request timeout, content bytes, and per-host request rate.
- Extract title, readable text, links, and a SHA-256 content hash. Scripts and non-content elements are ignored.
- Parse XML sitemap URL entries with bounded result counts.
- Restrict link following to the exact origins explicitly supplied as crawl roots.
- No JavaScript execution, login, CAPTCHA handling, paywall bypass, or access-control circumvention.

## Current service API

`CrawlSettings` provides validated safety bounds.
`WebCrawler.fetch(url)` fetches and extracts one page.
`WebCrawler.parse_sitemap(url)` parses a sitemap.
`WebCrawler.crawl(start_urls)` performs a bounded same-origin crawl and returns pages plus per-URL failures.

The service accepts an injected HTTPX client and DNS resolver for deterministic tests. The application UI and persistent extracted-content repository are subsequent Phase 4 integration steps.

## Important security note

DNS is checked immediately before each outbound request and again after redirects. This is a defence against ordinary private-network and redirect attacks. The default HTTPX transport performs its own hostname resolution when opening the connection, so this implementation does not claim resistance to a malicious DNS-rebinding race. Production hardening must pin the validated address at connection time or use a transport that connects only to the validated public IP while preserving TLS hostname verification.

## Validation

Run on Windows PowerShell:

```powershell
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\python.exe -m pytest
```
