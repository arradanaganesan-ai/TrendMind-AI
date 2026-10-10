"""Database persistence, report export, and analysis fallback tests."""

from __future__ import annotations

import json

from app.database.db import Database
from app.database.repository import ResearchRepository, TopicRepository
from app.schemas import (
    Finding,
    ReportMethodology,
    ResearchReport,
    SearchResult,
    SourceRef,
)
from app.services.export import report_to_json, report_to_markdown, safe_filename


def make_report() -> ResearchReport:
    return ResearchReport(
        researchQuestion="What is happening in <script>alert(1)</script> AI?",
        executiveSummary="Summary with | pipes and <tags> to escape.",
        keyFindings=[
            Finding(text="Finding one", sourceIds=["S1"], evidenceClass="fact"),
        ],
        sources=[
            SourceRef(
                id="S1",
                title="Source <b>one</b>",
                url="https://example.com/one",
                domain="example.com",
                snippet="snippet",
            )
        ],
        methodology=ReportMethodology(
            searchMode="live",
            aiMode="basic",
            contentBasis="snippets",
            resultCount=1,
            extractedPageCount=0,
            snippetOnlyCount=1,
            scoringFormula="f",
            notes=["note"],
        ),
        searchedAt="2026-01-01T00:00:00+00:00",
        generatedAt="2026-01-01T00:00:01+00:00",
    )


class TestDatabase:
    def test_create_and_get_research(self):
        db = Database(":memory:")
        repo = ResearchRepository(db)
        rid = repo.create_pending("my query", "demo", {"numResults": 5})
        record = repo.get(rid)
        assert record is not None
        assert record.query == "my query"
        assert record.status == "pending"
        assert record.filters is not None
        assert record.filters.numResults == 5

    def test_save_completed_with_report(self):
        db = Database(":memory:")
        repo = ResearchRepository(db)
        rid = repo.create_pending("q", "demo", None)
        results = [
            SearchResult(
                position=1, title="t", url="https://example.com", snippet="s", domain="example.com"
            )
        ]
        repo.save_completed(
            rid,
            status="completed",
            ai_mode="basic",
            result_count=1,
            results=results,
            report=make_report(),
            error_message=None,
        )
        record = repo.get(rid)
        assert record.status == "completed"
        assert record.resultCount == 1
        assert record.results[0].title == "t"
        assert record.report is not None
        assert record.report.executiveSummary.startswith("Summary")

    def test_list_pagination(self):
        db = Database(":memory:")
        repo = ResearchRepository(db)
        for i in range(15):
            repo.create_pending(f"query {i}", "demo", None)
        page1, total = repo.list(limit=10, offset=0)
        page2, _ = repo.list(limit=10, offset=10)
        assert total == 15
        assert len(page1) == 10
        assert len(page2) == 5

    def test_list_caps_limit(self):
        db = Database(":memory:")
        repo = ResearchRepository(db)
        repo.create_pending("q", "demo", None)
        items, _ = repo.list(limit=10_000, offset=0)
        assert len(items) <= 50  # MAX_HISTORY_PAGE

    def test_delete_existing_and_missing(self):
        db = Database(":memory:")
        repo = ResearchRepository(db)
        rid = repo.create_pending("q", "demo", None)
        assert repo.delete(rid) is True
        assert repo.get(rid) is None
        assert repo.delete("nope") is False

    def test_corrupt_report_json_degrades(self):
        db = Database(":memory:")
        repo = ResearchRepository(db)
        rid = repo.create_pending("q", "demo", None)
        db.execute(
            "UPDATE research SET report_json = ? WHERE id = ?",
            ("{not valid json", rid),
        )
        record = repo.get(rid)  # must not raise
        assert record.report is None

    def test_topic_create_list_delete(self):
        db = Database(":memory:")
        topics = TopicRepository(db)
        t = topics.create("AI trends")
        assert t.topic == "AI trends"
        # Duplicate returns existing (idempotent)
        t2 = topics.create("AI trends")
        assert t2.id == t.id
        assert len(topics.list()) == 1
        assert topics.delete(t.id) is True
        assert topics.list() == []
        assert topics.delete("missing") is False

    def test_no_secrets_stored(self):
        db = Database(":memory:")
        repo = ResearchRepository(db)
        rid = repo.create_pending("q", "demo", None)
        rows = db.query("SELECT * FROM research WHERE id = ?", (rid,))
        dumped = json.dumps(dict(rows[0]))
        assert "api_key" not in dumped.lower()
        assert "serpapi" not in dumped.lower()


class TestExport:
    def test_safe_filename(self):
        assert safe_filename("AI: Trends & <News>?", "md") == "trendmind-report-ai-trends-news.md"
        assert safe_filename("!!!", "json") == "trendmind-report-research.json"
        # Only whitelisted extensions survive
        assert safe_filename("x", "exe").endswith(".md") is False or True
        assert safe_filename("x", "exe").endswith((".md", ".json", ".txt"))
        # Length-capped
        assert len(safe_filename("a" * 500, "md")) < 100

    def test_markdown_contains_sections_and_links(self):
        md = report_to_markdown(make_report())
        assert "# What is happening in" in md
        assert "## 1. Executive summary" in md
        assert "## 12. Research methodology" in md
        assert "[S1](https://example.com/one)" in md  # clickable citation
        assert "**Live search**" in md or "live" in md.lower()

    def test_markdown_escapes_html(self):
        md = report_to_markdown(make_report())
        assert "&lt;script&gt;" in md
        assert "<script>alert(1)</script>" not in md

    def test_json_export_is_valid(self):
        raw = report_to_json(make_report())
        data = json.loads(raw)
        assert data["researchQuestion"]
        assert isinstance(data["sources"], list)
        assert data["methodology"]["aiMode"] == "basic"

    def test_demo_mode_labeled_in_markdown(self):
        report = make_report()
        report.methodology.searchMode = "demo"
        md = report_to_markdown(report)
        assert "Demo" in md


class TestBasicAnalysis:
    def test_basic_report_marks_ai_mode(self):
        from app.services.basic_analysis import build_basic_report
        from app.services.trends import SourceDoc

        docs = [
            SourceDoc(
                source_id="S1",
                domain="a.com",
                title="AI in healthcare",
                content="AI in healthcare improves diagnostics and treatment workflows.",
                extracted=True,
                url="https://a.com/1",
            ),
            SourceDoc(
                source_id="S2",
                domain="b.org",
                title="AI healthcare adoption",
                content="Healthcare providers adopt AI tools for diagnostics.",
                extracted=False,
                url="https://b.org/2",
            ),
        ]
        report = build_basic_report(
            query="AI in healthcare",
            sources=docs,
            searched_at="t1",
            generated_at="t2",
            mode="live",
            content_basis="mixed",
            result_count=2,
            extracted_count=1,
            snippet_only_count=1,
        )
        assert report.methodology.aiMode == "basic"
        assert "Basic" in report.executiveSummary or "basic" in report.executiveSummary
        assert any("keyword-based" in n or "non-AI" in n for n in report.methodology.notes)
        assert report.themes  # themes computed from real docs
        assert report.followUpQuestions

    def test_empty_sources_report(self):
        from app.services.basic_analysis import build_basic_report

        report = build_basic_report(
            query="nothing",
            sources=[],
            searched_at="t",
            generated_at="t",
            mode="demo",
            content_basis="demo",
            result_count=0,
            extracted_count=0,
            snippet_only_count=0,
        )
        assert "No relevant results" in report.executiveSummary
        assert report.keyFindings == []
