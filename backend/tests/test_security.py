"""SSRF protection and source-extraction restriction tests.

Uses IP literals to avoid real DNS/network calls in the standard suite.
"""

from __future__ import annotations

import pytest

from app.security.ssrf import SsrfError, validate_public_url


class TestUrlValidation:
    # --- blocked schemes ---
    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "ftp://example.com/x",
            "javascript:alert(1)",
            "data:text/html,<script>x</script>",
            "gopher://example.com",
            "ws://example.com",
        ],
    )
    def test_non_http_schemes_blocked(self, url):
        with pytest.raises(SsrfError) as exc:
            validate_public_url(url)
        assert exc.value.code == "scheme_blocked"

    # --- localhost / private / loopback / link-local ---
    @pytest.mark.parametrize(
        "url",
        [
            "http://localhost/admin",
            "http://localhost:8080/",
            "https://LOCALHOST/",
            "http://127.0.0.1/",
            "http://127.0.0.1:9200/_cat/indices",
            "http://10.0.0.5/internal",
            "http://192.168.1.1/router",
            "http://172.16.0.1/",
            "http://169.254.169.254/latest/meta-data/",  # cloud metadata endpoint
            "http://[::1]/",
            "http://[fc00::1]/",
            "http://0.0.0.0/",
            "http://100.64.0.1/",  # CGNAT
        ],
    )
    def test_private_and_internal_addresses_blocked(self, url):
        with pytest.raises(SsrfError):
            validate_public_url(url)

    # --- internal hostname patterns ---
    @pytest.mark.parametrize(
        "url",
        [
            "http://intranet/",
            "http://db.internal/",
            "http://service.local/",
            "http://nas.lan/",
            "http://router.home/",
            "http://files.corp/",
            "http://wiki.intranet/",
        ],
    )
    def test_internal_hostnames_blocked_before_dns(self, url):
        with pytest.raises(SsrfError):
            validate_public_url(url)

    # --- credentials in URL ---
    def test_embedded_credentials_blocked(self):
        with pytest.raises(SsrfError) as exc:
            validate_public_url("http://user:pass@example.com/")
        assert exc.value.code == "credentials_blocked"

    # --- ports ---
    @pytest.mark.parametrize("url", ["http://93.184.216.34:22/", "http://93.184.216.34:6379/"])
    def test_non_web_ports_blocked(self, url):
        with pytest.raises(SsrfError) as exc:
            validate_public_url(url)
        assert exc.value.code == "port_blocked"

    # --- accepted public URLs (IP literal, no DNS needed) ---
    @pytest.mark.parametrize(
        "url",
        [
            "https://93.184.216.34/page",
            "http://93.184.216.34:8080/page",
        ],
    )
    def test_public_urls_allowed(self, url):
        result = validate_public_url(url)
        assert result.url == url
        assert result.addresses

    def test_http_and_https_only_allowed(self):
        assert validate_public_url("http://93.184.216.34/").url.startswith("http://")
        assert validate_public_url("https://93.184.216.34/").url.startswith("https://")

    # --- garbage inputs ---
    @pytest.mark.parametrize("url", ["", "not a url", "http://", "x" * 3000])
    def test_invalid_urls_blocked(self, url):
        with pytest.raises(SsrfError):
            validate_public_url(url)


class TestExtractionRestrictions:
    @pytest.mark.asyncio
    async def test_extraction_blocks_private_urls_without_fetch(self):
        """extract_page must refuse private targets before any I/O."""
        from app.services.extraction_service import extract_page

        result = await extract_page("http://169.254.169.254/latest/meta-data/")
        assert result.status == "blocked"
        assert result.text == ""

    @pytest.mark.asyncio
    async def test_extraction_blocks_scheme(self):
        from app.services.extraction_service import extract_page

        result = await extract_page("file:///etc/passwd")
        assert result.status == "blocked"

    @pytest.mark.asyncio
    async def test_extraction_blocks_localhost(self):
        from app.services.extraction_service import extract_page

        result = await extract_page("http://localhost:3000/secret")
        assert result.status == "blocked"

    @pytest.mark.asyncio
    async def test_extract_pages_bounded_by_max_pages(self, monkeypatch):
        """No more than max_pages URLs are attempted."""
        from app.services import extraction_service

        called: list[str] = []

        async def fake_extract(url, **kwargs):
            called.append(url)
            return extraction_service.ExtractionResult(url=url, status="failed", reason="test")

        monkeypatch.setattr(extraction_service, "extract_page", fake_extract)
        urls = [f"https://93.184.216.34/{i}" for i in range(10)]
        results = await extraction_service.extract_pages(
            urls, max_pages=3, timeout_seconds=1, max_bytes=1000, max_chars=1000
        )
        assert len(called) == 3
        assert len(results) == 3


class TestHtmlToText:
    def test_scripts_and_styles_removed(self):
        from app.services.html_to_text import html_to_text

        html = """
        <html><head><title>My Page</title>
        <style>body { color: red; }</style>
        <script>alert('xss')</script></head>
        <body><nav>Menu</nav><article><h1>Heading</h1><p>Real content here.</p></article>
        <script>trackPageview()</script></body></html>
        """
        text, title = html_to_text(html)
        assert title == "My Page"
        assert "Real content here." in text
        assert "alert" not in text
        assert "trackPageview" not in text
        assert "color: red" not in text
        assert "Menu" not in text  # nav chrome removed

    def test_size_limit_enforced(self):
        from app.services.html_to_text import html_to_text

        html = "<html><body>" + "".join(f"<p>Paragraph {i} with words.</p>" for i in range(500)) + "</body></html>"
        text, _ = html_to_text(html, max_chars=500)
        assert len(text) <= 600  # limit + truncation marker
        assert "truncated" in text.lower()

    def test_malformed_html_does_not_crash(self):
        from app.services.html_to_text import html_to_text

        text, _ = html_to_text("<p>Unclosed <div>Structure <span>still parses")
        assert isinstance(text, str)
