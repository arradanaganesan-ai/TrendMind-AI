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
for var in ("SERPAPI_API_KEY", "AI_API_KEY", "AI_MODEL", "AI_PROVIDER"):
    os.environ.pop(var, None)
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
