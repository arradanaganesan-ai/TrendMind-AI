"""Search service tests — SerpApi responses are mocked via httpx.MockTransport.

No live API calls are made; no search credits are consumed.
"""

from __future__ import annotations

import httpx
import pytest

from app.services.search_service import (
    SearchError,
    SerpApiSearchService,
    build_params,
    normalize_organic_results,
)

# A realistic SerpApi organic_results payload (shape per official docs).
SERP_SAMPLE = {
    "search_metadata": {"id": "test", "status": "Success"},
    "organic_results": [
        {
            "position": 1,
            "title": "Zero trust adoption accelerates",
            "link": "https://www.example.com/zero-trust",
            "snippet": "Enterprises report rising zero trust deployment.",
            "date": "Jan 5, 2026",
            "source": "Example News",
        },
        {
            "position": 2,
            "title": "AI security tooling roundup",
            "link": "https://example.org/ai-security",
            "snippet": "A survey of AI-assisted security products.",
        },
        # Malformed entries must be skipped, not crash.
        {"position": 3, "title": "No link here", "snippet": "orphan"},
        {"position": 4, "link": "ftp://not-supported/file", "title": "Bad scheme"},
        "not-a-dict",
        {
            "position": 5,
            "title": "Valid but javascript scheme",
            "link": "javascript:alert(1)",
            "snippet": "x",
        },
    ],
}


@pytest.mark.asyncio
async def test_normalize_parses_valid_results():
    results = normalize_organic_results(SERP_SAMPLE["organic_results"])
    assert len(results) == 2  # 4 malformed entries skipped (no link, bad scheme, non-dict)
    first = results[0]
    assert first.title == "Zero trust adoption accelerates"
    assert first.url == "https://www.example.com/zero-trust"
    assert first.domain == "example.com"
    assert first.publishedDate == "Jan 5, 2026"
    assert first.source == "Example News"
    assert first.position == 1
    # Missing fields stay missing — never fabricated.
    assert results[1].publishedDate is None
    assert results[1].source is None


@pytest.mark.asyncio
async def test_normalize_rejects_bad_schemes():
    results = normalize_organic_results(SERP_SAMPLE["organic_results"])
    urls = [r.url for r in results]
    assert all(u.startswith(("http://", "https://")) for u in urls)
    assert not any(u.startswith("ftp:") for u in urls)
    assert not any(u.startswith("javascript:") for u in urls)


@pytest.mark.asyncio
async def test_search_with_mocked_transport():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=SERP_SAMPLE))
    async with httpx.AsyncClient(transport=transport) as client:
        service = SerpApiSearchService("fake-key")
        resp = await service.search("zero trust", num_results=5, client=client)
    assert resp.mode == "live"
    assert len(resp.results) == 2  # malformed entries in the fixture are skipped
    assert resp.results[0].title.startswith("Zero trust")
    assert resp.searched_at


@pytest.mark.asyncio
async def test_search_empty_results():
    payload = {"organic_results": []}
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=payload))
    async with httpx.AsyncClient(transport=transport) as client:
        service = SerpApiSearchService("fake-key")
        resp = await service.search("nothing here", client=client)
    assert resp.results == []


@pytest.mark.asyncio
async def test_search_missing_organic_results_key():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={}))
    async with httpx.AsyncClient(transport=transport) as client:
        service = SerpApiSearchService("fake-key")
        resp = await service.search("no key", client=client)
    assert resp.results == []


@pytest.mark.asyncio
async def test_rate_limit_maps_to_user_message():
    transport = httpx.MockTransport(lambda req: httpx.Response(429, json={}))
    async with httpx.AsyncClient(transport=transport) as client:
        service = SerpApiSearchService("fake-key")
        with pytest.raises(SearchError) as exc:
            await service.search("topic", client=client)
    assert exc.value.code == "rate_limited"
    assert exc.value.status == 429
    assert "temporarily" in exc.value.message.lower()


@pytest.mark.asyncio
async def test_auth_error_does_not_leak_key():
    transport = httpx.MockTransport(lambda req: httpx.Response(401, json={"error": "denied"}))
    async with httpx.AsyncClient(transport=transport) as client:
        service = SerpApiSearchService("super-secret-key-12345")
        with pytest.raises(SearchError) as exc:
            await service.search("topic", client=client)
    assert "super-secret-key" not in exc.value.message


@pytest.mark.asyncio
async def test_provider_error_field_handled():
    payload = {"error": "Your account has run out of searches."}
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=payload))
    async with httpx.AsyncClient(transport=transport) as client:
        service = SerpApiSearchService("fake-key")
        with pytest.raises(SearchError):
            await service.search("topic", client=client)


@pytest.mark.asyncio
async def test_unreadable_response_handled():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, text="<html>oops</html>"))
    async with httpx.AsyncClient(transport=transport) as client:
        service = SerpApiSearchService("fake-key")
        with pytest.raises(SearchError) as exc:
            await service.search("topic", client=client)
    assert exc.value.code == "search_bad_response"


@pytest.mark.asyncio
async def test_missing_key_raises_configured_message():
    service = SerpApiSearchService("")  # not configured
    with pytest.raises(SearchError) as exc:
        await service.search("topic")
    assert exc.value.code == "search_not_configured"
    assert "SERPAPI_API_KEY" in exc.value.message
    assert "Demo Mode" in exc.value.message


@pytest.mark.asyncio
async def test_timeout_maps_to_user_message():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = SerpApiSearchService("fake-key")
        with pytest.raises(SearchError) as exc:
            await service.search("topic", client=client)
    assert exc.value.code == "search_timeout"


def test_build_params_applies_filters():
    params = build_params(
        "ai trends",
        engine="google",
        num_results=8,
        category="news",
        region="in",
        language="hi",
        time_range="month",
        api_key="k",
    )
    assert params["q"] == "ai trends"
    assert params["num"] == 8
    assert params["category"] == "news"
    assert params["gl"] == "in"
    assert params["hl"] == "hi"
    assert params["tbs"] == "qdr:m"
    # API key present in params (sent to provider) but never logged/returned.
    assert params["api_key"] == "k"


def test_build_params_general_category_omitted():
    params = build_params(
        "x",
        engine="google",
        num_results=5,
        category="general",
        region="us",
        language="en",
        time_range="any",
        api_key="k",
    )
    assert "category" not in params
    assert "tbs" not in params


def test_result_count_capped_by_limit():
    service = SerpApiSearchService("key")
    params = build_params(
        "q",
        engine="google",
        num_results=1000,  # absurd value
        category="general",
        region="us",
        language="en",
        time_range="any",
        api_key="k",
    )
    assert params["num"] <= 100
    assert service.configured is True
