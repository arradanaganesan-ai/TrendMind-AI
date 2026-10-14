"""Unit tests for historical trend tracking (services/trend_tracking.py).

Hand-built in-memory fixtures — no database, no network, no AI provider.
Covers snapshot derivation, date ordering, change detection, the
absence-is-not-contradiction contract, missing/corrupt data, and the bounded
AI summary parsing.
"""

from __future__ import annotations

import pytest

from app.schemas import (
    Finding,
    ReportMethodology,
    ResearchRecord,
    ResearchReport,
    SnapshotTheme,
    SourceRef,
    ThemeCard,
    TimelineSnapshot,
    TrackedTopic,
)
from app.services.trend_tracking import (
    ABSENCE_CAVEAT,
    SINGLE_SNAPSHOT_NOTE,
    _extract_summary_text,
    build_snapshot,
    build_snapshots,
    build_timeline,
    detect_change,
    detect_consecutive_changes,
    match_findings,
    summarize_changes_with_ai,
)


def finding(text: str, source_ids=()) -> Finding:
    return Finding(text=text, sourceIds=list(source_ids), evidenceClass="fact")


def source(sid: str, url: str, domain: str = "example.com") -> SourceRef:
    return SourceRef(
        id=sid, title=f"Title {sid}", url=url, domain=domain, snippet="snippet text"
    )


def record(
    record_id: str,
    query: str,
    findings: list[Finding],
    sources: list[SourceRef] | None = None,
    created_at: str = "2026-01-01T10:00:00+00:00",
    themes: list[ThemeCard] | None = None,
    status: str = "completed",
) -> ResearchRecord:
    report = None
    if status == "completed":
        report = ResearchReport(
            researchQuestion=query,
            executiveSummary="Summary text for the trend test report.",
            keyFindings=findings,
            themes=themes or [],
            sources=sources or [],
            methodology=ReportMethodology(
                searchMode="demo",
                aiMode="basic",
                contentBasis="demo",
                resultCount=len(sources or []),
                extractedPageCount=0,
                snippetOnlyCount=len(sources or []),
                scoringFormula="test formula",
            ),
            searchedAt=created_at,
            generatedAt=created_at,
        )
    return ResearchRecord(
        id=record_id,
        query=query,
        createdAt=created_at,
        status=status,
        mode="demo",
        resultCount=len(sources or []),
        aiMode="basic",
        report=report,
    )


def theme(name: str, strength: int, confidence: str = "moderate") -> ThemeCard:
    return ThemeCard(
        id=f"T{name[:3]}",
        name=name,
        description="observed in tests",
        sourceIds=["S1"],
        mentionCount=2,
        evidenceStrength=strength,
        confidence=confidence,  # type: ignore[arg-type]
    )


def topic() -> TrackedTopic:
    return TrackedTopic(
        id="topic1",
        query="trend query",
        createdAt="2026-01-01T00:00:00+00:00",
        snapshotCount=2,
        firstSnapshotAt="2026-01-01T10:00:00+00:00",
        lastSnapshotAt="2026-01-02T10:00:00+00:00",
    )


# --------------------------------------------------------------------------
# Snapshot derivation & storage
# --------------------------------------------------------------------------

class TestSnapshotDerivation:
    def test_snapshot_carries_real_record_fields(self):
        rec = record(
            "r1",
            "trend query",
            [finding("Serverless databases adoption grows fast", ["S1"])],
            [source("S1", "https://a.example/x"), source("S2", "https://b.example/y", "b.com")],
            created_at="2026-01-01T10:00:00+00:00",
            themes=[theme("serverless", 71, "strong")],
        )
        snap = build_snapshot(rec)
        assert snap is not None
        assert snap.researchId == "r1"
        assert snap.createdAt == "2026-01-01T10:00:00+00:00"
        assert snap.searchedAt == "2026-01-01T10:00:00+00:00"  # real search time
        assert snap.findingCount == 1
        assert snap.sourceCount == 2
        assert snap.domainCount == 2
        assert snap.findings[0].text.startswith("Serverless")
        assert snap.sources[0].url == "https://a.example/x"
        assert snap.themes[0].evidenceStrength == 71

    def test_record_without_report_is_skipped_not_fabricated(self):
        rec = record("r1", "q", [], status="failed")
        assert build_snapshot(rec) is None
        assert build_snapshots([rec]) == []


# --------------------------------------------------------------------------
# Date ordering
# --------------------------------------------------------------------------

class TestDateOrdering:
    def test_snapshots_are_sorted_oldest_first(self):
        records = [
            record("c", "q", [], created_at="2026-01-03T00:00:00+00:00"),
            record("a", "q", [], created_at="2026-01-01T00:00:00+00:00"),
            record("b", "q", [], created_at="2026-01-02T00:00:00+00:00"),
        ]
        snaps = build_snapshots(records)
        assert [s.researchId for s in snaps] == ["a", "b", "c"]

    def test_equal_timestamps_tie_break_by_id(self):
        records = [
            record("zzz", "q", [], created_at="2026-01-01T00:00:00+00:00"),
            record("aaa", "q", [], created_at="2026-01-01T00:00:00+00:00"),
        ]
        snaps = build_snapshots(records)
        assert [s.researchId for s in snaps] == ["aaa", "zzz"]

    def test_changes_follow_chronological_snapshot_order(self):
        older = record("old", "q", [finding("same claim held steady")],
                       created_at="2026-01-01T00:00:00+00:00")
        newer = record("new", "q", [finding("same claim held steady")],
                       created_at="2026-01-02T00:00:00+00:00")
        snaps = build_snapshots([newer, older])  # deliberately shuffled
        changes = detect_consecutive_changes(snaps)
        assert len(changes) == 1
        assert changes[0].fromSnapshot.researchId == "old"
        assert changes[0].toSnapshot.researchId == "new"


# --------------------------------------------------------------------------
# Finding matching & change detection
# --------------------------------------------------------------------------

class TestMatchFindings:
    def test_exact_and_similar_match_but_weak_overlap_does_not(self):
        older = [
            Finding(index=0, text="Serverless database adoption accelerates in 2026"),
            Finding(index=1, text="Quantum computing remains theoretical for most firms"),
        ]
        newer = [
            Finding(index=0, text="serverless database adoption accelerates in 2026!"),
            Finding(index=1, text="Totally unrelated gardening statistics worldwide"),
        ]
        matches = match_findings(older, newer)
        assert (0, 0, 1.0) in [(a, b, s) for a, b, s in matches]
        matched_pairs = {(a, b) for a, b, _ in matches}
        assert (0, 0) in matched_pairs
        assert (0, 1) not in matched_pairs and (1, 1) not in matched_pairs

    def test_matches_are_one_to_one(self):
        dup = [Finding(index=0, text="identical claim text here")]
        newer = [
            Finding(index=0, text="identical claim text here"),
            Finding(index=1, text="identical claim text here"),
        ]
        matches = match_findings(dup, newer)
        assert len(matches) == 1


class TestChangeDetection:
    def test_detects_new_gone_and_unchanged_with_absence_caveat(self):
        older_snap = build_snapshot(
            record(
                "old",
                "q",
                [
                    finding("Serverless databases gain enterprise adoption"),
                    finding("Edge computing latency improvements continue"),
                    finding("Legacy migration costs stay high"),
                ],
                [source("S1", "https://a.example/1"), source("S2", "https://b.example/2", "b.com")],
                created_at="2026-01-01T00:00:00+00:00",
            )
        )
        newer_snap = build_snapshot(
            record(
                "new",
                "q",
                [
                    finding("Serverless databases gain enterprise adoption"),
                    finding("AI chip shortages slow datacenter expansion"),
                ],
                [source("S1", "https://a.example/1"), source("S3", "https://c.example/3", "c.com")],
                created_at="2026-01-02T00:00:00+00:00",
            )
        )
        change = detect_change(older_snap, newer_snap)

        assert change.unchangedCount == 1
        assert [f.text for f in change.newlyObserved] == [
            "AI chip shortages slow datacenter expansion"
        ]
        gone = [f.text for f in change.noLongerObserved]
        assert "Legacy migration costs stay high" in gone
        assert "Edge computing latency improvements continue" in gone

        # Absence is NEVER presented as contradiction/proof of falseness.
        assert change.absenceCaveat == ABSENCE_CAVEAT
        assert "NOT evidence" in change.absenceCaveat
        assert "proven false" in change.absenceCaveat
        assert "false" not in " ".join(f.text for f in change.noLongerObserved).lower()

        cov = change.sourceCoverage
        assert cov.sharedCount == 1
        assert cov.addedCount == 1 and cov.addedUrls == ["https://c.example/3"]
        assert cov.removedCount == 1 and cov.removedUrls == ["https://b.example/2"]
        assert cov.addedDomains == ["c.com"]
        assert cov.removedDomains == ["b.com"]

    def test_theme_score_changes_only_for_shared_theme_names(self):
        older_snap = build_snapshot(
            record(
                "old",
                "q",
                [finding("a claim")],
                themes=[theme("serverless database", 60), theme("old only theme", 40)],
                created_at="2026-01-01T00:00:00+00:00",
            )
        )
        newer_snap = build_snapshot(
            record(
                "new",
                "q",
                [finding("a claim")],
                themes=[theme("Serverless Database", 75, "strong"), theme("brand new theme", 50)],
                created_at="2026-01-02T00:00:00+00:00",
            )
        )
        change = detect_change(older_snap, newer_snap)

        assert len(change.themeScoreChanges) == 1
        delta = change.themeScoreChanges[0]
        assert delta.theme == "Serverless Database"  # name matches case-insensitively
        assert (delta.olderStrength, delta.newerStrength, delta.delta) == (60, 75, 15)
        assert delta.olderConfidence == "moderate" and delta.newerConfidence == "strong"

        assert set(change.incomparableThemes) == {"old only theme", "brand new theme"}

    def test_equal_theme_scores_produce_no_delta(self):
        older_snap = build_snapshot(
            record("old", "q", [finding("x")], themes=[theme("steady theme", 55)],
                   created_at="2026-01-01T00:00:00+00:00")
        )
        newer_snap = build_snapshot(
            record("new", "q", [finding("x")], themes=[theme("steady theme", 55)],
                   created_at="2026-01-02T00:00:00+00:00")
        )
        change = detect_change(older_snap, newer_snap)
        assert change.themeScoreChanges == []

    def test_days_apart_is_computed_from_real_timestamps(self):
        older_snap = build_snapshot(
            record("old", "q", [finding("x")], created_at="2026-01-01T00:00:00+00:00")
        )
        newer_snap = build_snapshot(
            record("new", "q", [finding("x")], created_at="2026-01-03T12:00:00+00:00")
        )
        change = detect_change(older_snap, newer_snap)
        assert change.daysApart == pytest.approx(2.5)


# --------------------------------------------------------------------------
# Missing data / single snapshot
# --------------------------------------------------------------------------

class TestMissingData:
    def test_no_snapshots_yields_empty_timeline_without_single_note(self):
        timeline = build_timeline(topic(), [])
        assert timeline.snapshots == []
        assert timeline.changes == []
        assert timeline.singleSnapshotNote is None

    def test_single_snapshot_has_note_and_no_changes(self):
        snap = build_snapshot(record("solo", "q", [finding("only one run")]))
        timeline = build_timeline(topic(), [snap])
        assert len(timeline.snapshots) == 1
        assert timeline.changes == []
        assert timeline.singleSnapshotNote == SINGLE_SNAPSHOT_NOTE
        assert "cannot show a trend" in timeline.singleSnapshotNote

    def test_two_snapshots_have_one_change_and_no_single_note(self):
        snaps = build_snapshots(
            [
                record("a", "q", [finding("claim")], created_at="2026-01-01T00:00:00+00:00"),
                record("b", "q", [finding("claim")], created_at="2026-01-02T00:00:00+00:00"),
            ]
        )
        timeline = build_timeline(topic(), snaps)
        assert len(timeline.changes) == 1
        assert timeline.singleSnapshotNote is None


# --------------------------------------------------------------------------
# Methodology & honest labeling
# --------------------------------------------------------------------------

class TestMethodology:
    def test_basic_mode_explanation_states_limits(self):
        timeline = build_timeline(topic(), [])
        assert timeline.methodology.mode == "basic"
        assert timeline.methodology.aiSummary is None
        joined = " ".join(timeline.methodology.explanation)
        assert "no AI model was used" in joined
        assert "not evidence that a claim is false" in joined
        assert "real stored research run" in joined

    def test_ai_summary_sets_mode_and_keeps_deterministic_claims(self):
        timeline = build_timeline(topic(), [], ai_summary="Overall, findings held steady.")
        assert timeline.methodology.mode == "ai"
        assert timeline.methodology.aiSummary == "Overall, findings held steady."
        joined = " ".join(timeline.methodology.explanation)
        assert "not model output" in joined

    def test_ai_note_keeps_basic_mode_when_fallback(self):
        timeline = build_timeline(topic(), [], ai_note="model unavailable")
        assert timeline.methodology.mode == "basic"
        assert timeline.methodology.aiNote == "model unavailable"
        assert timeline.methodology.aiSummary is None


# --------------------------------------------------------------------------
# AI summary parsing (bounded, validated)
# --------------------------------------------------------------------------

class TestAiSummaryParsing:
    def test_plain_text_returned(self):
        assert _extract_summary_text("  Findings held steady across dates. ") == (
            "Findings held steady across dates."
        )

    def test_code_fenced_text_stripped(self):
        assert _extract_summary_text("```markdown\nSummary line\n```") == "Summary line"

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            _extract_summary_text("   ")

    def test_overlong_summary_truncated(self):
        out = _extract_summary_text("x" * 5000)
        assert len(out) <= 1601
        assert out.endswith("…")

    def test_markdown_markers_are_stripped_cosmetically(self):
        out = _extract_summary_text("Draft Re-check Line:**\nWhat to re-check: **scores** stay `steady`.")
        assert "**" not in out
        assert "`" not in out
        assert out == "Draft Re-check Line:\nWhat to re-check: scores stay steady."

    def test_cleanup_that_empties_output_raises(self):
        with pytest.raises(ValueError):
            _extract_summary_text("**`**")


class TestAiSummaryCall:
    class _Stub:
        def __init__(self, text):
            self._text = text

        async def complete(self, **kwargs):
            class _C:
                text = self._text

            return _C()

    @pytest.mark.asyncio
    async def test_success_returns_validated_text(self, monkeypatch):
        import app.services.ai as ai_mod

        def fake_build(**kwargs):  # build_adapter is a sync factory
            return self._Stub("Snapshots show stable coverage across dates.")

        monkeypatch.setattr(ai_mod, "build_adapter", fake_build)
        snaps = build_snapshots(
            [
                record("a", "q", [finding("claim one")], created_at="2026-01-01T00:00:00+00:00"),
                record("b", "q", [finding("claim one"), finding("claim two")],
                       created_at="2026-01-02T00:00:00+00:00"),
            ]
        )
        changes = detect_consecutive_changes(snaps)
        text = await summarize_changes_with_ai(
            changes,
            provider="openai_compatible",
            model="m",
            api_key="k",
            base_url="https://example.invalid",
            timeout=5.0,
        )
        assert text == "Snapshots show stable coverage across dates."

    @pytest.mark.asyncio
    async def test_empty_model_output_raises_value_error(self, monkeypatch):
        import app.services.ai as ai_mod

        def fake_build(**kwargs):  # build_adapter is a sync factory
            return self._Stub("   ")

        monkeypatch.setattr(ai_mod, "build_adapter", fake_build)
        snaps = build_snapshots(
            [
                record("a", "q", [finding("claim")], created_at="2026-01-01T00:00:00+00:00"),
                record("b", "q", [finding("claim")], created_at="2026-01-02T00:00:00+00:00"),
            ]
        )
        with pytest.raises(ValueError):
            await summarize_changes_with_ai(
                detect_consecutive_changes(snaps),
                provider="openai_compatible",
                model="m",
                api_key="k",
                base_url="https://example.invalid",
                timeout=5.0,
            )


# --------------------------------------------------------------------------
# Snapshot schema sanity
# --------------------------------------------------------------------------

class TestSnapshotSchema:
    def test_snapshot_theme_model_bounds_strength(self):
        with pytest.raises(Exception):
            SnapshotTheme(name="x", evidenceStrength=150)
        ok = SnapshotTheme(name="x", evidenceStrength=100)
        assert ok.evidenceStrength == 100

    def test_timeline_snapshot_requires_real_id(self):
        with pytest.raises(Exception):
            TimelineSnapshot(
                query="q",
                createdAt="t",
                searchedAt="t",
                mode="demo",
                aiMode="basic",
                resultCount=1,
                findingCount=0,
                sourceCount=0,
                domainCount=0,
            )  # missing researchId
