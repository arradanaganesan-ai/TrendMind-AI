"""Health, config status, and validation tests."""

from __future__ import annotations


class TestHealth:
    def test_health_ok(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["service"] == "trendmind-ai"
        assert "time" in body

    def test_config_status_shape(self, client):
        r = client.get("/api/config/status")
        assert r.status_code == 200
        body = r.json()
        # Required keys per the frontend contract
        for key in (
            "version",
            "searchMode",
            "serpapiConfigured",
            "aiProvider",
            "aiConfigured",
            "sourceExtractionEnabled",
            "demoMode",
            "maxResultsLimit",
        ):
            assert key in body

    def test_config_status_never_leaks_secrets(self, client):
        body = client.get("/api/config/status").json()
        serialized = str(body).lower()
        for forbidden in ("api_key", "apikey", "secret", "bearer", "authorization"):
            assert forbidden not in serialized

    def test_404_uses_error_schema(self, client):
        r = client.get("/api/research/does-not-exist")
        assert r.status_code == 404
        body = r.json()
        assert body["error"]["code"] == "not_found"
        assert "message" in body["error"]
        assert "Traceback" not in str(body)


class TestValidation:
    def test_query_too_short_rejected(self, client):
        r = client.post("/api/research", json={"query": "a"})
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "validation_error"

    def test_query_empty_rejected(self, client):
        r = client.post("/api/research", json={"query": "   "})
        assert r.status_code == 422

    def test_query_too_long_rejected(self, client):
        r = client.post("/api/research", json={"query": "x" * 400})
        assert r.status_code == 422

    def test_unknown_filter_value_rejected(self, client):
        r = client.post(
            "/api/research",
            json={"query": "test topic", "filters": {"region": "atlantis"}},
        )
        assert r.status_code == 422

    def test_invalid_num_results_rejected(self, client):
        r = client.post(
            "/api/research",
            json={"query": "test topic", "filters": {"numResults": 999}},
        )
        assert r.status_code == 422

    def test_valid_query_normalizes_whitespace(self, client):
        r = client.post("/api/research", json={"query": "  ai   trends  "})
        assert r.status_code == 201
        assert r.json()["query"] == "ai trends"

    def test_missing_body_rejected(self, client):
        r = client.post("/api/research", json={})
        assert r.status_code == 422

    def test_topic_validation(self, client):
        assert client.post("/api/topics", json={"topic": ""}).status_code == 422
        assert client.post("/api/topics", json={"topic": "ok topic"}).status_code == 201

    def test_oversized_payload_rejected(self, client):
        big = {"query": "valid topic", "filters": {"category": "general"}, "padding": "x" * 100_000}
        r = client.post("/api/research", json=big)
        assert r.status_code == 413
