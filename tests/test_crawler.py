from __future__ import annotations

import httpx
import pytest

from dataset_forge.services.crawler import (
    CrawlSettings,
    WebCrawler,
    extract_html,
)


def public_resolver(_host, _port, **_kwargs):
    return [(None, None, None, None, ("93.184.216.34", 0))]


def test_extract_html_ignores_script_and_navigation_content():
    title, text, links = extract_html(
        "<html><head><title>Python guide</title></head><body>"
        "<nav>Navigation noise</nav><main><h1>Functions</h1>"
        "<p>Use def to define a function.</p><script>secret()</script>"
        '<a href="/tutorial">Tutorial</a></main></body></html>',
        "https://docs.example.org/intro",
    )
    assert title == "Python guide"
    assert "Functions" in text
    assert "Use def to define a function." in text
    assert "Navigation noise" not in text
    assert "secret()" not in text
    assert links == ("https://docs.example.org/tutorial",)


def test_crawl_settings_enforce_safe_bounds():
    with pytest.raises(ValueError, match="max_pages"):
        CrawlSettings(max_pages=1000)
    with pytest.raises(ValueError, match="max_concurrent_requests"):
        CrawlSettings(max_concurrent_requests=10)


def test_fetch_rejects_non_public_dns_before_request():
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, text="unused"))
    client = httpx.Client(transport=transport)
    crawler = WebCrawler(client=client, resolver=lambda *_args, **_kwargs: [
        (None, None, None, None, ("127.0.0.1", 0))
    ])
    try:
        with pytest.raises(ValueError, match="non-public"):
            crawler.fetch("https://example.org/")
    finally:
        crawler.close()
        client.close()


def test_fetch_extracts_html_and_hashes_content():
    def handler(request):
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="<title>Guide</title><main><p>Useful content.</p></main>",
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    crawler = WebCrawler(client=client, resolver=public_resolver)
    try:
        page = crawler.fetch("https://example.org/guide")
    finally:
        crawler.close()
        client.close()
    assert page.title == "Guide"
    assert "Useful content." in page.text
    assert len(page.content_hash) == 64


def test_fetch_rejects_non_html_content():
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(
            200, headers={"content-type": "application/pdf"}, content=b"pdf", request=request
        )
    ))
    crawler = WebCrawler(client=client, resolver=public_resolver)
    try:
        with pytest.raises(ValueError, match="Unsupported content type"):
            crawler.fetch("https://example.org/file")
    finally:
        crawler.close()
        client.close()



def test_fetch_enforces_content_limit_while_streaming():
    payload = b"x" * 2048
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=payload,
            request=request,
        )
    ))
    crawler = WebCrawler(
        CrawlSettings(max_content_bytes=1024, delay_seconds=0),
        client=client,
        resolver=public_resolver,
    )
    try:
        with pytest.raises(ValueError, match="content-size limit"):
            crawler.fetch("https://example.org/large")
    finally:
        crawler.close()
        client.close()


def test_redirect_to_private_destination_is_rejected():
    def handler(request):
        return httpx.Response(
            302,
            headers={"location": "http://127.0.0.1/admin"},
            request=request,
        )

    def resolver(host, _port, **_kwargs):
        address = "127.0.0.1" if host == "127.0.0.1" else "93.184.216.34"
        return [(None, None, None, None, (address, 0))]

    client = httpx.Client(transport=httpx.MockTransport(handler))
    crawler = WebCrawler(client=client, resolver=resolver)
    try:
        with pytest.raises(ValueError, match="non-public"):
            crawler.fetch("https://example.org/redirect")
    finally:
        crawler.close()
        client.close()


def test_parse_sitemap_returns_only_safe_http_urls():
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        '<url><loc>https://example.org/one</loc></url>'
        '<url><loc>http://127.0.0.1/private</loc></url>'
        '<url><loc>https://example.org/two</loc></url>'
        '</urlset>'
    )
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "application/xml"},
            text=xml,
            request=request,
        )
    ))
    crawler = WebCrawler(client=client, resolver=public_resolver)
    try:
        urls = crawler.parse_sitemap("https://example.org/sitemap.xml")
    finally:
        crawler.close()
        client.close()
    assert urls == ("https://example.org/one", "https://example.org/two")
