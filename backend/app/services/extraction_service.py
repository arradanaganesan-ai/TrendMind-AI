"""Source extraction service — fetches publicly accessible pages safely.

Security posture (all enforced, not optional):
- http/https only; credentials-in-URL rejected.
- localhost, private, loopback, link-local, CGNAT, and internal names blocked.
- DNS resolved and checked for EVERY address before connecting.
- Every redirect hop re-validated with the same rules (max 3 hops).
- Strict timeout, response-size limit, HTML content types only.
- JavaScript is never executed; no arbitrary file downloads.
- robots.txt is consulted (best effort) and disallowed paths are skipped.
- Never bypasses authentication or paywalls; failures degrade to snippet-only.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx

from ..security.ssrf import SsrfError, validate_public_url
from .html_to_text import html_to_text

logger = logging.getLogger(__name__)

MAX_REDIRECTS = 3
USER_AGENT = "TrendMindAI-Bot/1.0 (+research; respects robots.txt)"
ALLOWED_CONTENT_TYPES = ("text/html", "application/xhtml+xml")

# Per-host robots cache: (decision, monotonic_expiry)
_ROBOTS_CACHE: dict[str, tuple[bool, float]] = {}
_ROBOTS_TTL = 900.0


@dataclass
class ExtractionResult:
    url: str
    status: str  # extracted | blocked | failed | skipped
    title: str = ""
    text: str = ""
    final_url: str = ""
    reason: str = ""


async def _robots_allows(client: httpx.AsyncClient, scheme: str, host: str, path: str) -> bool:
    """Best-effort robots.txt check for the default user agent."""
    import time

    cache_key = f"{scheme}://{host}"
    cached = _ROBOTS_CACHE.get(cache_key)
    if cached and cached[1] > time.monotonic():
        return cached[0]

    allowed = True
    try:
        resp = await client.get(
            f"{cache_key}/robots.txt",
            headers={"User-Agent": USER_AGENT},
            follow_redirects=False,
        )
        if resp.status_code == 200:
            allowed = _evaluate_robots(resp.text, path)
        # 404/410 → no rules → allowed; 5xx → be conservative but not blocking.
    except Exception:
        allowed = True  # If robots cannot be fetched, do not block, but never retry-loop.

    _ROBOTS_CACHE[cache_key] = (allowed, time.monotonic() + _ROBOTS_TTL)
    return allowed


def _evaluate_robots(text: str, path: str) -> bool:
    """Evaluate Disallow rules for User-agent: * groups (subset of the spec)."""
    applies = False
    disallows: list[str] = []
    allows: list[str] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, _, value = line.partition(":")
        field = field.strip().lower()
        value = value.strip()
        if field == "user-agent":
            applies = value == "*"
        elif field == "disallow" and applies:
            if value:
                disallows.append(value)
            else:
                disallows.append("")  # explicit "allow all" marker in this group
        elif field == "allow" and applies and value:
            allow_patterns = allows
            allow_patterns.append(value)

    for pattern in allows:
        if path.startswith(pattern):
            return True
    for pattern in disallows:
        if pattern == "":
            continue
        if path.startswith(pattern):
            return False
    return True


async def extract_page(
    url: str,
    *,
    timeout_seconds: float = 8.0,
    max_bytes: int = 1_500_000,
    max_chars: int = 12_000,
    client: httpx.AsyncClient | None = None,
) -> ExtractionResult:
    """Fetch and extract one URL. Returns a result object; never raises for
    unreachable/blocked pages (the pipeline degrades to snippet-only)."""
    try:
        validated = validate_public_url(url)
    except SsrfError as exc:
        return ExtractionResult(url=url, status="blocked", reason=exc.code)

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            max_redirects=0,
        )

    try:
        # --- robots.txt (best effort, per host) ---
        scheme = "https" if validated.url.startswith("https") else "http"
        path = "/"
        try:
            from urllib.parse import urlparse

            path = urlparse(validated.url).path or "/"
        except Exception:
            path = "/"

        if not await _robots_allows(client, scheme, validated.host, path):
            return ExtractionResult(url=url, status="skipped", reason="robots_disallowed")

        # --- manual redirect handling with per-hop validation ---
        current = validated.url
        for _hop in range(MAX_REDIRECTS + 1):
            try:
                response = await client.get(
                    current,
                    headers={
                        "User-Agent": USER_AGENT,
                        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
                    },
                    follow_redirects=False,
                )
            except httpx.TimeoutException:
                return ExtractionResult(url=url, status="failed", reason="timeout")
            except httpx.HTTPError:
                return ExtractionResult(url=url, status="failed", reason="network_error")

            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    return ExtractionResult(url=url, status="failed", reason="bad_redirect")
                # Resolve relative redirects, then re-validate the destination.
                from urllib.parse import urljoin

                next_url = urljoin(current, location)
                try:
                    validated_next = validate_public_url(next_url)
                except SsrfError as exc:
                    return ExtractionResult(url=url, status="blocked", reason=f"redirect_{exc.code}")
                current = validated_next.url
                continue

            if response.status_code == 404 or response.status_code == 410:
                return ExtractionResult(url=url, status="failed", reason="not_found")
            if response.status_code in (401, 403):
                return ExtractionResult(url=url, status="blocked", reason="access_denied")
            if response.status_code >= 400:
                return ExtractionResult(url=url, status="failed", reason=f"http_{response.status_code}")

            content_type = response.headers.get("content-type", "").lower()
            if not any(ct in content_type for ct in ALLOWED_CONTENT_TYPES):
                return ExtractionResult(url=url, status="skipped", reason="not_html")

            # --- read with a hard byte cap ---
            body = b""
            async for chunk in response.aiter_bytes():
                body += chunk
                if len(body) > max_bytes:
                    body = body[:max_bytes]
                    break

            html = body.decode("utf-8", errors="replace")
            text, title = html_to_text(html, max_chars=max_chars)
            if not text.strip():
                return ExtractionResult(url=url, status="failed", reason="no_text")

            return ExtractionResult(
                url=url,
                status="extracted",
                title=title or url,
                text=text,
                final_url=str(response.url),
            )

        return ExtractionResult(url=url, status="failed", reason="too_many_redirects")
    finally:
        if owns_client:
            await client.aclose()


async def extract_pages(
    urls: list[str],
    *,
    max_pages: int,
    timeout_seconds: float,
    max_bytes: int,
    max_chars: int,
) -> list[ExtractionResult]:
    """Extract up to `max_pages` pages concurrently with bounded parallelism."""
    targets = urls[: max(0, max_pages)]
    if not targets:
        return []
    results = await asyncio.gather(
        *(
            extract_page(
                u,
                timeout_seconds=timeout_seconds,
                max_bytes=max_bytes,
                max_chars=max_chars,
            )
            for u in targets
        ),
        return_exceptions=True,
    )
    out: list[ExtractionResult] = []
    for url, res in zip(targets, results):
        if isinstance(res, ExtractionResult):
            out.append(res)
        elif isinstance(res, BaseException):
            logger.info("Extraction failed for a URL (safe fallback to snippet): %s", type(res).__name__)
            out.append(ExtractionResult(url=url, status="failed", reason="unexpected_error"))
        else:  # pragma: no cover - defensive
            out.append(ExtractionResult(url=url, status="failed", reason="unexpected"))
    return out


def clear_robots_cache() -> None:
    _ROBOTS_CACHE.clear()
