"""Shared pytest fixtures.

All external services are mocked — the standard test suite never consumes
live SerpApi credits or calls any AI provider.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Make `app` importable when running pytest from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Force a clean, secret-free environment BEFORE app modules are imported.
#
# app.config runs load_dotenv() at import time, and dotenv only skips variables
# that are already PRESENT in the environment. Merely popping the keys would
# therefore let backend/.env re-inject the real credentials on first import —
# which silently turned API tests into live SerpApi searches (network-bound,
# credit-consuming, and intermittently failing). Explicit empty values keep the
# secrets out and pin the suite to deterministic demo mode.
os.environ["SERPAPI_API_KEY"] = ""
os.environ["AI_API_KEY"] = ""
os.environ["AI_MODEL"] = ""
os.environ["AI_PROVIDER"] = "none"
os.environ["ENABLE_SOURCE_EXTRACTION"] = "false"  # no network in tests
os.environ["DATABASE_PATH"] = ":memory:"
os.environ["RESEARCH_RATE_LIMIT_PER_MINUTE"] = "100"


@pytest.fixture()
def settings():
    from app.config import get_settings, reset_settings_cache

    reset_settings_cache()
    s = get_settings()
    yield s
    reset_settings_cache()


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Give every test a fresh rate limiter.

    routes._research_limiter is module-level, so without this its token
    buckets accumulate checks across tests (and across randomized orderings),
    which can intermittently 429 an unrelated test once the session-wide
    total passes the per-minute limit.
    """
    from app.api import routes

    routes._research_limiter = None
    yield
    routes._research_limiter = None


@pytest.fixture()
def client():
    """Fresh app client with an in-memory database."""
    from app.config import reset_settings_cache
    from app.database import reset_db_for_tests

    reset_settings_cache()
    reset_db_for_tests()
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c
    reset_db_for_tests()
    reset_settings_cache()


@pytest.fixture()
def make_settings():
    """Build an ad-hoc Settings object with overrides (for unit tests)."""
    from app.config import Settings

    def _make(**overrides):
        base = dict(
            serpapi_api_key="",
            enable_source_extraction=False,
            database_path=":memory:",
            ai_provider="none",
            research_rate_limit_per_minute=100,
        )
        base.update(overrides)
        return Settings(**base)

    return _make
