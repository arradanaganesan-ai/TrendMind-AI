"""SerpApi search service (backend-only integration).

Reads SERPAPI_API_KEY from the environment; the key is never exposed to the
frontend, logs, or error messages. Handles timeouts, API errors, rate limits,
and empty results with a consistent response schema.

Docs: https://serpapi.com/search-api
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

from ..schemas import SearchResult
from ..security.sanitize import safe_external_title

logger = logging.getLogger(__name__)

SERPAPI_ENDPOINT = "https://serpapi.com/search.json"

# qdr: relative time operator understood by SerpApi's `tbs` parameter.
_TIME_RANGE_MAP = {
    "day": "qdr:d",
    "week": "qdr:w",
    "month": "qdr:m",
    "year": "qdr:y",
}


class SearchError(Exception):
    """Raised when a search cannot be completed."""

    def __init__(self, message: str, *, code: str, status: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


@dataclass
class SearchResponse:
    results: list[SearchResult] = field(default_factory=list)
    mode: str = "live"
    raw_count: int = 0
    searched_at: str = ""


def _domain_of(url: str) -> str:
    try:
        host = urlparse(url).hostname or ""
        return host.lower().removeprefix("www.")
    except ValueError:
        return ""


def normalize_organic_results(raw_items: list[dict[str, Any]]) -> list[SearchResult]:
    """Normalize SerpApi organic results into the internal schema.

    Field availability varies per result — missing fields stay None/empty and
    are never fabricated (especially publication dates and source metadata).
    """
    normalized: list[SearchResult] = []
    for index, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            continue
        url = str(item.get("link") or "").strip()
        title = safe_external_title(str(item.get("title") or ""), 300)
        if not url or not title:
            continue  # A result without a URL or title is unusable.
        if not url.startswith(("http://", "https://")):
            continue

        snippet = safe_external_title(str(item.get("snippet") or ""), 700)
        published = item.get("date")  # SerpApi provides `date` only when known.
        source = item.get("source")

        normalized.append(
            SearchResult(
                position=int(item.get("position") or index),
                title=title,
                url=url,
                snippet=snippet,
                domain=_domain_of(url),
                publishedDate=safe_external_title(str(published), 60) if published else None,
                source=safe_external_title(str(source), 80) if source else None,
            )
        )
    return normalized


def build_params(
    query: str,
    *,
    engine: str,
    num_results: int,
    category: str,
    region: str,
    language: str,
    time_range: str,
    api_key: str,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "engine": engine,
        "q": query,
        "api_key": api_key,
        "num": min(num_results, 100),
        "hl": language,
        "gl": region,
    }
    if category and category != "general":
        params["category"] = category
    if time_range in _TIME_RANGE_MAP:
        params["tbs"] = _TIME_RANGE_MAP[time_range]
    return params


class SerpApiSearchService:
    """Thin, testable wrapper around the SerpApi HTTP API."""

    def __init__(self, api_key: str, *, engine: str = "google", timeout: float = 10.0) -> None:
        self._api_key = api_key
        self._engine = engine or "google"
        self._timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    async def search(
        self,
        query: str,
        *,
        num_results: int = 10,
        category: str = "general",
        region: str = "us",
        language: str = "en",
        time_range: str = "any",
        client: httpx.AsyncClient | None = None,
    ) -> SearchResponse:
        """Run a search. `client` allows tests to inject a mock transport."""
        if not self.configured:
            raise SearchError(
                "Live search is not configured yet. Add SERPAPI_API_KEY to your backend "
                "environment or switch to Demo Mode.",
                code="search_not_configured",
                status=503,
            )

        params = build_params(
            query,
            engine=self._engine,
            num_results=num_results,
            category=category,
            region=region,
            language=language,
            time_range=time_range,
            api_key=self._api_key,
        )

        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(timeout=httpx.Timeout(self._timeout))

        try:
            response = await client.get(SERPAPI_ENDPOINT, params=params)
        except httpx.TimeoutException as exc:
            raise SearchError(
                "The search provider did not respond in time. Please try again.",
                code="search_timeout",
                status=504,
            ) from exc
        except httpx.HTTPError:
            raise SearchError(
                "The search provider could not be reached. Please try again.",
                code="search_unreachable",
                status=502,
            ) from exc
        finally:
            if owns_client:
                await client.aclose()

        if response.status_code == 429:
            raise SearchError(
                "Search capacity has temporarily been reached. Please wait before trying again.",
                code="rate_limited",
                status=429,
            )
        if response.status_code in (401, 403):
            # Never echo the provider's response body — it can contain the key.
            logger.warning("SerpApi rejected the configured credentials (status %s)", response.status_code)
            raise SearchError(
                "The configured search credentials were rejected. Check SERPAPI_API_KEY.",
                code="search_auth_failed",
                status=502,
            )
        if response.status_code >= 500:
            raise SearchError(
                "The search provider is currently unavailable. Please try again later.",
                code="search_provider_error",
                status=502,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise SearchError(
                "The search provider returned an unreadable response.",
                code="search_bad_response",
                status=502,
            ) from exc

        # SerpApi signals application errors with an `error` field.
        api_error = payload.get("error")
        if isinstance(api_error, str):
            lowered = api_error.lower()
            if "invalid api key" in lowered or "unauthorized" in lowered:
                raise SearchError(
                    "The configured search credentials were rejected. Check SERPAPI_API_KEY.",
                    code="search_auth_failed",
                    status=502,
                )
            if "rate limit" in lowered or "too many" in lowered:
                raise SearchError(
                    "Search capacity has temporarily been reached. Please wait before trying again.",
                    code="rate_limited",
                    status=429,
                )
            logger.warning("SerpApi error response (message redacted): length=%d", len(api_error))
            raise SearchError(
                "The search request failed at the provider. Please try again.",
                code="search_provider_error",
                status=502,
            )

        organic = payload.get("organic_results")
        if not isinstance(organic, list):
            organic = []

        results = normalize_organic_results(organic)[: max(1, num_results)]

        from datetime import datetime, timezone

        return SearchResponse(
            results=results,
            mode="live",
            raw_count=len(results),
            searched_at=datetime.now(timezone.utc).isoformat(),
        )
