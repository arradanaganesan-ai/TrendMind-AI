"""API tests for historical trend tracking (/api/trends).

Seeded through the real research endpoint (demo mode, no network) so every
snapshot reflects an actual stored run. Covers storage, ordering, date
filters, validation envelopes, the single-snapshot path, deletion, and the
optional AI summary fallback contract.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.trend_tracking import ABSENCE_CAVEAT, SINGLE_SNAPSHOT_NOTE

TODAY = datetime.now(timezone.utc).date().isoformat()


def _seed(client, query: str, n: int = 1) -> list[str]:
    ids = []
    for _ in range(n):
        r = client.post("/api/research", json={"query": query})
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    return ids


class TestTopicCreation:
    def test_candidates_list_reflects_real_runs(self, client):
        _seed(client, "candidate query one", 2)
        _seed(client, "candidate query two", 1)
        body = client.get("/api/trends/candidates").json()
        by_query = {c["query"]: c for c in body["items"]}
        assert by_query["candidate query one"]["runCount"] == 2
        assert by_query["candidate query two"]["runCount"] == 1
        assert by_query["candidate query one"]["firstRunAt"]

    def test_create_requires_existing_completed_runs(self, client):
        r = client.post("/api/trends", json={"query": "never researched before"})
        assert r.status_code == 422
        err = r.json()["error"]
        assert err["code"] == "validation_error"
        assert "No completed research runs" in err["message"]
        assert client.get("/api/trends").json()["items"] == []

    def test_create_is_idempotent_per_query(self, client):
        _seed(client, "tracked twice", 2)
        first = client.post("/api/trends", json={"query": "tracked twice"})
        second = client.post("/api/trends", json={"query": "tracked twice"})
        assert first.status_code == 201 and second.status_code == 201
        assert first.json()["id"] == second.json()["id"]
        assert first.json()["snapshotCount"] == 2

    def test_create_normalizes_whitespace_query(self, client):
        _seed(client, "spaced query")
        r = client.post("/api/trends", json={"query": "  spaced   query  "})
        assert r.status_code == 201
        assert r.json()["query"] == "spaced query"

    @pytest.mark.parametrize(
        "payload",
        [
            {"query": ""},
            {"query": "   "},
            {"query": "a"},
            {"query": "x" * 400},
            {},
        ],
    )
    def test_create_rejects_invalid_queries_with_envelope(self, client, payload):
        r = client.post("/api/trends", json=payload)
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "validation_error"

    def test_list_includes_topic_with_real_counts(self, client):
        _seed(client, "listed topic", 3)
        client.post("/api/trends", json={"query": "listed topic"})
        items = client.get("/api/trends").json()["items"]
        topic = next(t for t in items if t["query"] == "listed topic")
        assert topic["snapshotCount"] == 3
        assert topic["firstSnapshotAt"] <= topic["lastSnapshotAt"]


class TestTimeline:
    def test_returns_snapshots_oldest_first_with_consecutive_changes(self, client):
        _seed(client, "timeline topic", 3)
        tid = client.post("/api/trends", json={"query": "timeline topic"}).json()["id"]
        body = client.get(f"/api/trends/{tid}").json()

        stamps = [s["createdAt"] for s in body["snapshots"]]
        assert stamps == sorted(stamps), "snapshots must be date-ordered"
        assert len(body["snapshots"]) == 3
        assert len(body["changes"]) == 2  # consecutive pairs only
        assert body["singleSnapshotNote"] is None

        # Every change carries real endpoints and the absence-not-false caveat.
        first_change = body["changes"][0]
        assert first_change["fromSnapshot"]["researchId"] == body["snapshots"][0]["researchId"]
        assert first_change["toSnapshot"]["researchId"] == body["snapshots"][1]["researchId"]
        assert first_change["absenceCaveat"] == ABSENCE_CAVEAT
        assert first_change["daysApart"] >= 0
        assert first_change["sourceCoverage"]["sharedCount"] >= 0

        # Snapshot details expose findings/sources for the UI.
        snap = body["snapshots"][0]
        assert snap["findingCount"] == len(snap["findings"])
        assert snap["sourceCount"] == len(snap["sources"])
        assert body["methodology"]["mode"] == "basic"
        assert body["methodology"]["aiSummary"] is None

    def test_single_snapshot_has_note_and_no_changes(self, client):
        _seed(client, "solo snapshot topic", 1)
        tid = client.post("/api/trends", json={"query": "solo snapshot topic"}).json()["id"]
        body = client.get(f"/api/trends/{tid}").json()
        assert len(body["snapshots"]) == 1
        assert body["changes"] == []
        assert body["singleSnapshotNote"] == SINGLE_SNAPSHOT_NOTE

    def test_date_filters_are_inclusive(self, client):
        _seed(client, "date filtered topic", 2)
        tid = client.post("/api/trends", json={"query": "date filtered topic"}).json()["id"]

        included = client.get(
            f"/api/trends/{tid}?dateFrom={TODAY}&dateTo={TODAY}"
        ).json()
        assert len(included["snapshots"]) == 2
        assert included["dateFrom"] == TODAY and included["dateTo"] == TODAY

        empty = client.get(f"/api/trends/{tid}?dateFrom=1999-01-01&dateTo=1999-01-02").json()
        assert empty["snapshots"] == []
        assert empty["changes"] == []
        assert empty["singleSnapshotNote"] is None

    @pytest.mark.parametrize(
        "query",
        [
            "dateFrom=not-a-date",
            "dateFrom=2026-13-45",
            "dateFrom=2026-10-11&dateTo=2026-10-10",
            "mode=weird",
        ],
    )
    def test_invalid_timeline_parameters_rejected(self, client, query):
        _seed(client, "validation topic", 1)
        tid = client.post("/api/trends", json={"query": "validation topic"}).json()["id"]
        r = client.get(f"/api/trends/{tid}?{query}")
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "validation_error"

    def test_unknown_topic_is_404(self, client):
        assert client.get("/api/trends/definitely-missing").status_code == 404

    def test_failed_runs_are_never_snapshots(self, client, monkeypatch):
        from app.services.analysis_pipeline import ResearchPipeline

        async def failing_run(self, query, filters=None):
            return [], None, "demo", "search failed"

        monkeypatch.setattr(ResearchPipeline, "run", failing_run)
        r = client.post("/api/research", json={"query": "failed then ok topic"})
        assert r.status_code == 503
        monkeypatch.undo()

        _seed(client, "failed then ok topic", 1)
        tid = client.post("/api/trends", json={"query": "failed then ok topic"}).json()["id"]
        topic = client.get("/api/trends").json()["items"]
        topic = next(t for t in topic if t["query"] == "failed then ok topic")
        assert topic["snapshotCount"] == 1

        body = client.get(f"/api/trends/{tid}").json()
        assert len(body["snapshots"]) == 1
        assert body["singleSnapshotNote"] == SINGLE_SNAPSHOT_NOTE


class TestAiMode:
    def test_auto_without_provider_falls_back_with_note(self, client):
        _seed(client, "auto no provider topic", 2)
        tid = client.post("/api/trends", json={"query": "auto no provider topic"}).json()["id"]
        body = client.get(f"/api/trends/{tid}?mode=auto").json()
        assert body["methodology"]["mode"] == "basic"
        assert "no AI provider is configured" in body["methodology"]["aiNote"]
        assert body["methodology"]["aiSummary"] is None
        # Deterministic changes are still fully present in fallback mode.
        assert len(body["changes"]) == 1

    def test_auto_success_sets_ai_mode(self, client, monkeypatch):
        import app.api.routes as routes_mod

        _seed(client, "auto success topic", 2)
        tid = client.post("/api/trends", json={"query": "auto success topic"}).json()["id"]

        async def fake_summary(changes, **kwargs):
            return "Coverage held steady; two findings newly observed."

        monkeypatch.setattr(
            "app.config.Settings.ai_configured", property(lambda self: True)
        )
        monkeypatch.setattr(routes_mod, "summarize_changes_with_ai", fake_summary)

        body = client.get(f"/api/trends/{tid}?mode=auto").json()
        assert body["methodology"]["mode"] == "ai"
        assert body["methodology"]["aiSummary"] == (
            "Coverage held steady; two findings newly observed."
        )
        assert body["methodology"]["aiNote"] is None
        # Deterministic sections are still computed alongside the summary.
        assert len(body["changes"]) == 1
        assert "not model output" in " ".join(body["methodology"]["explanation"])

    def test_auto_model_failure_falls_back_with_note(self, client, monkeypatch):
        import app.api.routes as routes_mod

        _seed(client, "auto failure topic", 2)
        tid = client.post("/api/trends", json={"query": "auto failure topic"}).json()["id"]

        async def broken_summary(changes, **kwargs):
            raise ValueError("model returned junk")

        monkeypatch.setattr(
            "app.config.Settings.ai_configured", property(lambda self: True)
        )
        monkeypatch.setattr(routes_mod, "summarize_changes_with_ai", broken_summary)

        body = client.get(f"/api/trends/{tid}?mode=auto").json()
        assert body["methodology"]["mode"] == "basic"
        assert "no AI analysis was performed" in body["methodology"]["aiNote"]
        assert body["methodology"]["aiSummary"] is None
        assert len(body["changes"]) == 1

    def test_auto_single_snapshot_skips_ai_with_note(self, client, monkeypatch):
        _seed(client, "auto solo topic", 1)
        tid = client.post("/api/trends", json={"query": "auto solo topic"}).json()["id"]
        monkeypatch.setattr(
            "app.config.Settings.ai_configured", property(lambda self: True)
        )
        body = client.get(f"/api/trends/{tid}?mode=auto").json()
        assert body["methodology"]["mode"] == "basic"
        assert "Fewer than two" in body["methodology"]["aiNote"]


class TestDeletion:
    def test_delete_topic_does_not_touch_runs_or_saved_topics(self, client):
        _seed(client, "deletable topic", 2)
        client.post("/api/topics", json={"topic": "saved keeper"})
        tid = client.post("/api/trends", json={"query": "deletable topic"}).json()["id"]

        assert client.delete(f"/api/trends/{tid}").status_code == 204
        assert client.get(f"/api/trends/{tid}").status_code == 404
        assert client.delete(f"/api/trends/{tid}").status_code == 404
        assert not any(t["id"] == tid for t in client.get("/api/trends").json()["items"])

        # Stored research and saved topics are untouched.
        runs = client.get("/api/research").json()
        assert any(r["query"] == "deletable topic" for r in runs["items"])
        saved = client.get("/api/topics").json()["items"]
        assert any(t["topic"] == "saved keeper" for t in saved)
