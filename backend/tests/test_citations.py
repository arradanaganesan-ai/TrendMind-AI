"""Citation validation tests — no citation may point at an uncollected source."""

from __future__ import annotations

from app.schemas import (
    ClaimGroup,
    ConflictItem,
    ConflictPosition,
    EvidenceComparison,
    Finding,
    ReportMethodology,
    ResearchReport,
    SourceRef,
    ThemeCard,
)
from app.services.citations import validate_report_citations


def make_report() -> ResearchReport:
    sources = [
        SourceRef(
            id="S1",
            title="One",
            url="https://example.com/1",
            domain="example.com",
            snippet="s1",
        ),
        SourceRef(
            id="S2",
            title="Two",
            url="https://example.org/2",
            domain="example.org",
            snippet="s2",
        ),
    ]
    return ResearchReport(
        researchQuestion="q",
        executiveSummary="summary",
        keyFindings=[
            Finding(text="valid claim", sourceIds=["S1", "S2"], evidenceClass="fact"),
            Finding(text="bogus citation", sourceIds=["S99"], evidenceClass="fact"),
            Finding(text="mixed citation", sourceIds=["S1", "GHOST"], evidenceClass="fact"),
        ],
        themes=[
            ThemeCard(
                id="T1",
                name="Theme A",
                description="d",
                sourceIds=["S1", "S404"],
                mentionCount=2,
                evidenceStrength=50,
                confidence="moderate",
            ),
            ThemeCard(
                id="T2",
                name="Theme B",
                description="d",
                sourceIds=["GHOST"],
                mentionCount=1,
                evidenceStrength=30,
                confidence="emerging",
            ),
        ],
        evidenceComparison=[
            EvidenceComparison(
                aspect="aspect",
                claims=[
                    ClaimGroup(sourceIds=["S1"], claim="claim"),
                    ClaimGroup(sourceIds=["FAKE"], claim="ghost claim"),
                ],
            ),
            EvidenceComparison(
                aspect="all-ghost",
                claims=[ClaimGroup(sourceIds=["FAKE2"], claim="x")],
            ),
        ],
        conflictingClaims=[
            ConflictItem(
                topic="conflict ok",
                positions=[
                    ConflictPosition(sourceIds=["S1"], position="p1"),
                    ConflictPosition(sourceIds=["S2"], position="p2"),
                ],
            ),
            ConflictItem(
                topic="conflict weak",
                positions=[
                    ConflictPosition(sourceIds=["S1"], position="p1"),
                    ConflictPosition(sourceIds=["GHOST"], position="p2"),
                ],
            ),
        ],
        sources=sources,
        methodology=ReportMethodology(
            searchMode="demo",
            aiMode="basic",
            contentBasis="demo",
            resultCount=2,
            extractedPageCount=0,
            snippetOnlyCount=2,
            scoringFormula="x",
        ),
        searchedAt="t",
        generatedAt="t",
    )


class TestCitationValidation:
    def test_invalid_citations_removed(self):
        result = validate_report_citations(make_report())
        valid = {"S1", "S2"}
        for f in result.report.keyFindings:
            assert set(f.sourceIds) <= valid
        for t in result.report.themes:
            assert set(t.sourceIds) <= valid
        for c in result.report.evidenceComparison:
            for claim in c.claims:
                assert set(claim.sourceIds) <= valid

    def test_finding_losing_all_citations_reclassified(self):
        result = validate_report_citations(make_report())
        bogus = next(f for f in result.report.keyFindings if f.text == "bogus citation")
        assert bogus.sourceIds == []
        assert bogus.evidenceClass == "interpretation"  # no longer grounded as fact
        assert bogus.caveat  # caveat explains why

    def test_theme_with_no_valid_sources_dropped(self):
        result = validate_report_citations(make_report())
        names = [t.name for t in result.report.themes]
        assert "Theme B" not in names  # only had a ghost citation
        assert "Theme A" in names  # still has S1

    def test_mention_count_matches_valid_sources(self):
        result = validate_report_citations(make_report())
        for t in result.report.themes:
            assert t.mentionCount == len(t.sourceIds)

    def test_comparison_needing_valid_claims(self):
        result = validate_report_citations(make_report())
        aspects = [c.aspect for c in result.report.evidenceComparison]
        assert "aspect" in aspects
        assert "all-ghost" not in aspects  # all citations were invalid

    def test_weak_conflict_dropped_keeps_strong(self):
        result = validate_report_citations(make_report())
        topics = [c.topic for c in result.report.conflictingClaims]
        assert "conflict ok" in topics
        assert "conflict weak" not in topics  # only one cited position survived
        for c in result.report.conflictingClaims:
            assert len(c.positions) >= 2

    def test_removed_count_reported(self):
        result = validate_report_citations(make_report())
        assert result.removed_citations > 0
        assert result.warnings

    def test_coverage_recomputed_after_cleanup(self):
        result = validate_report_citations(make_report())
        assert result.report.coverage.conflicting == len(result.report.conflictingClaims)

    def test_valid_report_untouched(self):
        report = make_report()
        report.keyFindings = [Finding(text="ok", sourceIds=["S1"], evidenceClass="fact")]
        report.themes = [
            ThemeCard(
                id="T1",
                name="A",
                description="d",
                sourceIds=["S1", "S2"],
                mentionCount=2,
                evidenceStrength=60,
                confidence="moderate",
            )
        ]
        report.evidenceComparison = []
        report.conflictingClaims = []
        result = validate_report_citations(report)
        assert result.removed_citations == 0
        assert result.report.keyFindings[0].sourceIds == ["S1"]
        assert result.report.coverage.supported == 1
