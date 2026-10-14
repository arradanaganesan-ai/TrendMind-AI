"""Health, config status, and validation tests."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


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


class TestWorkspaceStats:
    def test_stats_shape(self, client):
        r = client.get("/api/stats")
        assert r.status_code == 200
        body = r.json()
        for key in (
            "researchTotal",
            "researchCompleted",
            "researchFailed",
            "reportsTotal",
            "savedTopics",
            "last7DaysResearch",
            "last7DaysCompleted",
        ):
            assert key in body
            assert isinstance(body[key], int)
            assert body[key] >= 0

    def test_stats_reflect_real_database_rows(self, client):
        # Empty database: all counters zero.
        before = client.get("/api/stats").json()
        assert before["researchTotal"] == 0

        # One demo research run + one saved topic must be counted exactly.
        assert client.post("/api/research", json={"query": "stats probe"}).status_code == 201
        assert client.post("/api/topics", json={"topic": "stats topic"}).status_code == 201

        after = client.get("/api/stats").json()
        assert after["researchTotal"] == 1
        assert after["researchCompleted"] == 1
        assert after["reportsTotal"] == 1
        assert after["last7DaysResearch"] == 1
        assert after["last7DaysCompleted"] == 1
        assert after["savedTopics"] == 1

    def test_stats_never_leak_secrets(self, client):
        body = str(client.get("/api/stats").json()).lower()
        for forbidden in ("api_key", "apikey", "secret", "bearer"):
            assert forbidden not in body


class TestResearchStream:
    """SSE progress endpoint: honest stage events, then one result event."""

    def _collect(self, client, payload):
        events = []
        with client.stream("POST", "/api/research/stream", json=payload) as r:
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/event-stream")
            current_event = None
            for line in r.iter_lines():
                if line.startswith("event: "):
                    current_event = line[len("event: "):].strip()
                elif line.startswith("data: ") and current_event:
                    import json as _json

                    events.append((current_event, _json.loads(line[len("data: "):])))
        return events

    def test_stream_emits_stages_then_result(self, client):
        events = self._collect(client, {"query": "stream probe"})
        kinds = [k for k, _ in events]
        stages = [d["stage"] for k, d in events if k == "stage"]

        # Honest pipeline order; "extracting" is absent because demo mode
        # never attempts page extraction (documented behavior).
        assert stages == ["searching", "analyzing", "validating"]
        assert kinds[-1] == "result"

        record = events[-1][1]
        assert record["status"] == "completed"
        assert record["query"] == "stream probe"
        assert record["report"] is not None
        assert record["id"]

    def test_stream_result_is_persisted(self, client):
        events = self._collect(client, {"query": "persisted stream run"})
        rid = events[-1][1]["id"]
        fetched = client.get(f"/api/research/{rid}")
        assert fetched.status_code == 200
        assert fetched.json()["query"] == "persisted stream run"

    def test_stream_rejects_invalid_query(self, client):
        r = client.post("/api/research/stream", json={"query": "x"})
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "validation_error"


class TestResearchDateFilters:
    """GET /api/research date_from/date_to filtering (4D)."""

    @staticmethod
    def _seed(client, n=2):
        for i in range(n):
            r = client.post("/api/research", json={"query": f"date filter seed {i}"})
            assert r.status_code == 201

    @staticmethod
    def _day(offset_days: int) -> str:
        return (date.today() + timedelta(days=offset_days)).isoformat()

    def test_filters_by_date_from(self, client):
        self._seed(client)
        today = self._day(0)
        r = client.get(f"/api/research?date_from={today}")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2

        # A future lower bound excludes everything.
        r2 = client.get(f"/api/research?date_from={self._day(10)}")
        assert r2.status_code == 200
        assert r2.json()["total"] == 0
        assert r2.json()["items"] == []

    def test_filters_by_date_to_exclusive_of_future(self, client):
        self._seed(client, 1)
        # Yesterday is before the seeded record's creation date.
        r = client.get(f"/api/research?date_to={self._day(-1)}")
        assert r.status_code == 200
        assert r.json()["total"] == 0

        # Today includes it.
        r2 = client.get(f"/api/research?date_to={self._day(0)}")
        assert r2.status_code == 200
        assert r2.json()["total"] == 1

    def test_rejects_malformed_date(self, client):
        r = client.get("/api/research?date_from=not-a-date")
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "validation_error"
        assert "YYYY-MM-DD" in r.json()["error"]["message"]

    def test_rejects_inverted_range(self, client):
        r = client.get(f"/api/research?date_from={self._day(5)}&date_to={self._day(1)}")
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "validation_error"


class TestPdfExport:
    """GET /api/reports/{id}/pdf (4A - backend PDF export)."""

    def test_pdf_export_returns_pdf_bytes(self, client):
        created = client.post("/api/research", json={"query": "pdf export probe"})
        assert created.status_code == 201
        rid = created.json()["id"]

        r = client.get(f"/api/reports/{rid}/pdf")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content[:5] == b"%PDF-"
        assert ".pdf" in r.headers.get("content-disposition", "")
        # Sanity: a real document is more than a header.
        assert len(r.content) > 1000

    def test_pdf_export_unknown_id_404(self, client):
        r = client.get("/api/reports/does-not-exist/pdf")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "not_found"

    def test_pdf_filename_extension(self):
        from app.services.export import safe_filename

        assert safe_filename("Some Query", "pdf").endswith(".pdf")


class TestActivityEndpoint:
    """GET /api/stats/activity (4E - real historical activity series)."""

    def test_activity_series_is_zero_filled_from_real_rows(self, client):
        for i in range(2):
            r = client.post("/api/research", json={"query": f"activity seed {i}"})
            assert r.status_code == 201

        r = client.get("/api/stats/activity?days=7")
        assert r.status_code == 200
        body = r.json()
        assert body["days"] == 7
        pts = body["points"]
        assert len(pts) == 7
        # Dates ascend and end today (UTC).
        dates = [p["date"] for p in pts]
        assert dates == sorted(dates)
        today = datetime.now(timezone.utc).date().isoformat()
        assert dates[-1] == today
        # Today reflects the two seeded runs; earlier days are explicit zeros.
        assert pts[-1]["count"] == 2
        assert pts[-1]["completed"] == 2
        for p in pts[:-1]:
            assert p["count"] == 0
            assert p["completed"] == 0

    def test_activity_rejects_out_of_range_days(self, client):
        assert client.get("/api/stats/activity?days=0").status_code == 422
        assert client.get("/api/stats/activity?days=999").status_code == 422


class TestCompareApi:
    """GET /api/compare and its exports (comparison feature)."""

    @staticmethod
    def _seed_two(client) -> tuple[str, str]:
        ids = []
        for i in range(2):
            r = client.post("/api/research", json={"query": f"comparison seed {i}"})
            assert r.status_code == 201
            ids.append(r.json()["id"])
        return ids[0], ids[1]

    def test_compare_basic_success(self, client):
        a, b = self._seed_two(client)
        r = client.get(f"/api/compare?a={a}&b={b}")
        assert r.status_code == 200
        body = r.json()
        assert body["runA"]["id"] == a
        assert body["runB"]["id"] == b
        assert body["methodology"]["mode"] == "basic"
        assert any("no AI model was used" in line for line in body["methodology"]["explanation"])
        assert body["noveltyCaveat"]
        for key in ("sharedFindings", "similarFindings", "conflicts", "uniqueToA", "uniqueToB"):
            assert isinstance(body[key], list)
        assert body["sources"]["sharedCount"] >= 0

    def test_compare_is_symmetric_enough(self, client):
        a, b = self._seed_two(client)
        forward = client.get(f"/api/compare?a={a}&b={b}").json()
        backward = client.get(f"/api/compare?a={b}&b={a}").json()
        assert backward["runA"]["id"] == b  # sides follow the parameters
        total_f = len(forward["uniqueToA"]) + len(forward["uniqueToB"])
        total_b = len(backward["uniqueToA"]) + len(backward["uniqueToB"])
        assert total_f == total_b

    def test_compare_unknown_id_404(self, client):
        a, _ = self._seed_two(client)
        r = client.get(f"/api/compare?a={a}&b=does-not-exist")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "not_found"
        assert r.json()["error"]["details"] == {"side": "b"}

    def test_compare_same_id_422(self, client):
        a, _ = self._seed_two(client)
        r = client.get(f"/api/compare?a={a}&b={a}")
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "validation_error"

    def test_compare_missing_param_422(self, client):
        a, _ = self._seed_two(client)
        r = client.get(f"/api/compare?a={a}")
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "validation_error"

    def test_compare_malformed_id_422(self, client):
        r = client.get("/api/compare?a=../../etc&b=other")
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "validation_error"

    def test_compare_invalid_mode_422(self, client):
        a, b = self._seed_two(client)
        r = client.get(f"/api/compare?a={a}&b={b}&mode=psychic")
        assert r.status_code == 422
        assert "basic" in r.json()["error"]["message"]

    def test_compare_record_without_report_409(self, client, monkeypatch):
        from app.database.repository import ResearchRepository

        a, b = self._seed_two(client)
        real_get = ResearchRepository.get

        def get_with_reportless_b(self, research_id):
            rec = real_get(self, research_id)
            if rec is not None and research_id == b:
                return rec.model_copy(update={"report": None})
            return rec

        monkeypatch.setattr(ResearchRepository, "get", get_with_reportless_b)
        r = client.get(f"/api/compare?a={a}&b={b}")
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "no_report"
        assert r.json()["error"]["details"] == {"side": "b"}

    def test_mode_auto_without_provider_falls_back_with_note(self, client):
        a, b = self._seed_two(client)
        r = client.get(f"/api/compare?a={a}&b={b}&mode=auto")
        assert r.status_code == 200
        body = r.json()
        assert body["methodology"]["mode"] == "basic"
        assert "no AI provider is configured" in body["methodology"]["aiNote"]

    def test_mode_auto_ai_error_falls_back_with_note(self, client, monkeypatch):
        from app.services.ai import AiUnavailableError

        async def boom(*args, **kwargs):
            raise AiUnavailableError("provider down", code="ai_unavailable")

        import app.api.routes as routes_mod

        monkeypatch.setattr(routes_mod, "classify_findings_with_ai", boom)
        monkeypatch.setattr("app.config.Settings.ai_configured", property(lambda self: True))

        a, b = self._seed_two(client)
        r = client.get(f"/api/compare?a={a}&b={b}&mode=auto")
        assert r.status_code == 200
        body = r.json()
        assert body["methodology"]["mode"] == "basic"
        assert "no AI analysis was performed" in body["methodology"]["aiNote"]

    def test_mode_auto_ai_success_uses_judgements(self, client, monkeypatch):
        from app.services.comparison import AiPairJudgement

        async def fake_classify(findings_a, findings_b, **kwargs):
            return [
                AiPairJudgement(
                    a_index=0,
                    b_index=0,
                    relation="same",
                    explanation="identical claim",
                )
            ]

        import app.api.routes as routes_mod

        monkeypatch.setattr(routes_mod, "classify_findings_with_ai", fake_classify)
        monkeypatch.setattr("app.config.Settings.ai_configured", property(lambda self: True))

        a, b = self._seed_two(client)
        r = client.get(f"/api/compare?a={a}&b={b}&mode=auto")
        assert r.status_code == 200
        body = r.json()
        assert body["methodology"]["mode"] == "ai"
        assert len(body["sharedFindings"]) == 1
        assert body["sharedFindings"][0]["a"]["index"] == 0

    def test_markdown_export(self, client):
        a, b = self._seed_two(client)
        r = client.get(f"/api/compare/markdown?a={a}&b={b}")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/markdown")
        assert ".md" in r.headers.get("content-disposition", "")
        text = r.text
        assert "# Research Report Comparison" in text
        assert "Basic comparison" in text
        assert "comparison seed 0" in text
        assert "comparison seed 1" in text
        assert "not proof that it is new" in text

    def test_json_export(self, client):
        import json as jsonlib

        a, b = self._seed_two(client)
        r = client.get(f"/api/compare/json?a={a}&b={b}")
        assert r.status_code == 200
        assert ".json" in r.headers.get("content-disposition", "")
        body = jsonlib.loads(r.text)
        assert body["runA"]["id"] == a
        assert body["methodology"]["mode"] == "basic"

    def test_pdf_export(self, client):
        a, b = self._seed_two(client)
        r = client.get(f"/api/compare/pdf?a={a}&b={b}")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content[:5] == b"%PDF-"
        assert ".pdf" in r.headers.get("content-disposition", "")
        assert len(r.content) > 1000

    def test_exports_propagate_lookup_errors(self, client):
        for path in ("markdown", "json", "pdf"):
            r = client.get(f"/api/compare/{path}?a=missing-one&b=missing-two")
            assert r.status_code == 404
            assert r.json()["error"]["code"] == "not_found"

    def test_comparison_filename_helper(self):
        from app.services.export import comparison_filename

        name = comparison_filename("Serverless Trends", "AI in Healthcare", "md")
        assert name == "trendmind-compare-serverless-trends-vs-ai-in-healthcare.md"
        assert comparison_filename("???", "!!!", "pdf").endswith(".pdf")
