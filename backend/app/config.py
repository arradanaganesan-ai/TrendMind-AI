"""
Application configuration.

All secrets and tunables are read from environment variables (optionally via a
`.env` file loaded with python-dotenv). Secret values are never logged and
never returned by any API endpoint — only boolean "configured" flags.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

try:
    from dotenv import load_dotenv

    # Load .env from the repository root (two levels above this file) if present.
    _REPO_ROOT = Path(__file__).resolve().parents[2]
    load_dotenv(_REPO_ROOT / ".env")
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")  # backend/.env also accepted
except Exception:  # pragma: no cover - dotenv is optional at runtime
    pass


def _get_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _get_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


@dataclass(frozen=True)
class Settings:
    """Immutable application settings resolved once at startup."""

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    app_version: str = "1.0.0"

    # --- Database ---
    database_path: str = "./data/trendmind.db"

    # --- SerpApi search ---
    serpapi_api_key: str = ""
    serpapi_engine: str = "google"
    search_timeout_seconds: float = 10.0
    max_results_limit: int = 20
    max_query_length: int = 300

    # --- Source extraction (SSRF-protected) ---
    enable_source_extraction: bool = True
    max_extract_pages: int = 3
    extract_timeout_seconds: float = 8.0
    max_page_bytes: int = 1_500_000
    max_extract_chars: int = 12_000

    # --- AI provider ---
    ai_provider: str = "none"  # none | openai_compatible | anthropic
    ai_model: str = ""
    ai_api_key: str = ""
    ai_base_url: str = "https://api.openai.com/v1"
    ai_timeout_seconds: float = 45.0
    ai_max_evidence_chars: int = 24_000

    # --- Rate limiting ---
    research_rate_limit_per_minute: int = 6

    # --- Misc ---
    github_repo_url: str = ""

    # Derived flags -------------------------------------------------------
    @property
    def serpapi_configured(self) -> bool:
        return bool(self.serpapi_api_key.strip())

    @property
    def ai_configured(self) -> bool:
        """True only when a usable AI provider + model + key combination exists."""
        provider = self.ai_provider.strip().lower()
        if provider in {"", "none", "off", "disabled"}:
            return False
        if not self.ai_model.strip():
            return False
        # Local OpenAI-compatible gateways may not need a key; hosted ones do.
        if provider == "anthropic" and not self.ai_api_key.strip():
            return False
        if provider == "openai_compatible":
            # Key optional (local gateways), but a model is required (checked above).
            return True
        return False

    @property
    def demo_mode(self) -> bool:
        """Demo mode is active when live search is unavailable."""
        return not self.serpapi_configured

    @property
    def normalized_ai_provider(self) -> str:
        provider = self.ai_provider.strip().lower()
        if provider in {"", "none", "off", "disabled"}:
            return "none"
        if provider in {"openai", "openai_compatible", "openrouter", "groq", "local"}:
            return "openai_compatible"
        if provider == "anthropic":
            return "anthropic"
        return "none"

    @property
    def effective_search_timeout(self) -> float:
        return self.search_timeout_seconds


def _split_origins(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ("http://localhost:5173", "http://127.0.0.1:5173")
    origins = tuple(o.strip() for o in raw.split(",") if o.strip())
    return origins or ("http://localhost:5173", "http://127.0.0.1:5173")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Resolve settings from the environment (cached; tests can clear the cache)."""
    return Settings(
        host=os.environ.get("HOST", "0.0.0.0"),
        port=_get_int("PORT", 8000, minimum=1, maximum=65535),
        cors_origins=_split_origins(os.environ.get("CORS_ORIGINS")),
        app_version=os.environ.get("APP_VERSION", "1.0.0"),
        database_path=os.environ.get("DATABASE_PATH", "./data/trendmind.db"),
        serpapi_api_key=os.environ.get("SERPAPI_API_KEY", "").strip(),
        serpapi_engine=os.environ.get("SERPAPI_ENGINE", "google").strip() or "google",
        search_timeout_seconds=_get_float(
            "SEARCH_TIMEOUT_SECONDS", 10.0, minimum=1.0, maximum=60.0
        ),
        max_results_limit=_get_int("MAX_RESULTS_LIMIT", 20, minimum=1, maximum=100),
        max_query_length=_get_int("MAX_QUERY_LENGTH", 300, minimum=10, maximum=2000),
        enable_source_extraction=_get_bool("ENABLE_SOURCE_EXTRACTION", True),
        max_extract_pages=_get_int("MAX_EXTRACT_PAGES", 3, minimum=0, maximum=10),
        extract_timeout_seconds=_get_float(
            "EXTRACT_TIMEOUT_SECONDS", 8.0, minimum=1.0, maximum=30.0
        ),
        max_page_bytes=_get_int("MAX_PAGE_BYTES", 1_500_000, minimum=10_000, maximum=10_000_000),
        max_extract_chars=_get_int("MAX_EXTRACT_CHARS", 12_000, minimum=500, maximum=100_000),
        ai_provider=os.environ.get("AI_PROVIDER", "none").strip() or "none",
        ai_model=os.environ.get("AI_MODEL", "").strip(),
        ai_api_key=os.environ.get("AI_API_KEY", "").strip(),
        ai_base_url=os.environ.get("AI_BASE_URL", "https://api.openai.com/v1").strip()
        or "https://api.openai.com/v1",
        ai_timeout_seconds=_get_float("AI_TIMEOUT_SECONDS", 45.0, minimum=5.0, maximum=180.0),
        ai_max_evidence_chars=_get_int(
            "AI_MAX_EVIDENCE_CHARS", 24_000, minimum=2_000, maximum=200_000
        ),
        research_rate_limit_per_minute=_get_int(
            "RESEARCH_RATE_LIMIT_PER_MINUTE", 6, minimum=1, maximum=120
        ),
        github_repo_url=os.environ.get("GITHUB_REPO_URL", "").strip(),
    )


def reset_settings_cache() -> None:
    """Clear the settings cache (used by tests that mutate the environment)."""
    get_settings.cache_clear()


__all__ = ["Settings", "get_settings", "reset_settings_cache"]
