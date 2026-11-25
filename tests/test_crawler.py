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
