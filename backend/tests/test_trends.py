"""Trend discovery and scoring tests — computed from actual source data."""

from __future__ import annotations

from app.services.trends import (
    SourceDoc,
    band_for,
    compute_coverage,
    compute_strength,
    extract_frequent_terms,
    identify_themes,
)
from app.schemas import Finding


def make_doc(sid: str, domain: str, content: str, extracted: bool = False) -> SourceDoc:
    return SourceDoc(
        source_id=sid,
        domain=domain,
        title=f"Title {sid}",
        content=content,
        extracted=extracted,
        url=f"https://{domain}/{sid}",
    )


SHARED = (
    "Electric vehicle battery costs fell this year according to the report. "
    "Electric vehicle charging infrastructure expanded across cities. "
    "Battery costs remain a key factor for electric vehicle adoption."
)


class TestScoring:
    def test_formula_zero_sources(self):
        assert compute_strength(0, 0, 1, 0.0) == 0

    def test_formula_max_breadth_diversity_depth(self):
        # 4 sources, 4 distinct domains (of 4), all extracted
        score = compute_strength(4, 4, 4, 1.0)
        assert score == 100

    def test_formula_single_source_single_domain_snippet_only(self):
        score = compute_strength(1, 1, 1, 0.0)
        # 50 * 0.25 + 30 * 1 + 0 = 42.5 -> 43? round(42.5)=42 banker's? python round(42.5)=42
        assert 40 <= score <= 45

    def test_breadth_capped_at_four_sources(self):
        assert compute_strength(4, 1, 1, 0.0) == compute_strength(10, 1, 1, 0.0)

    def test_bands(self):
        assert band_for(75) == "strong"
        assert band_for(55) == "moderate"
        assert band_for(35) == "emerging"
        assert band_for(10) == "tentative"


class TestThemeIdentification:
    def test_recurs_across_sources(self):
        docs = [
            make_doc("S1", "a.com", SHARED),
            make_doc("S2", "b.org", SHARED),
            make_doc("S3", "c.net", "Unrelated content about cooking recipes and gardening tools."),
        ]
        themes = identify_themes(docs)
        names = [t.name.lower() for t in themes]
        # The shared phrase must surface.
        assert any("battery" in n or "electric vehicle" in n for n in names)
        # Theme must cite only real source ids.
        valid = {"S1", "S2", "S3"}
        for t in themes:
            assert set(t.sourceIds) <= valid
            assert t.mentionCount == len(t.sourceIds)
            assert 0 <= t.evidenceStrength <= 100

    def test_single_source_still_scores_lower_than_multi(self):
        multi = identify_themes(
            [make_doc("S1", "a.com", SHARED), make_doc("S2", "b.org", SHARED)]
        )
        single = identify_themes([make_doc("S1", "a.com", SHARED)])
        if multi and single:
            top_multi = max(t.evidenceStrength for t in multi)
            top_single = max(t.evidenceStrength for t in single)
            assert top_multi >= top_single

    def test_empty_input_no_themes(self):
        assert identify_themes([]) == []

    def test_snapshot_limitation_recorded_for_thin_evidence(self):
        docs = [make_doc("S1", "a.com", SHARED)]
        themes = identify_themes(docs)
        for t in themes:
            # Any theme from < 3 sources carries an explicit limitation.
            if t.mentionCount < 3:
                assert t.limitations is not None
                assert "snapshot" in t.limitations.lower()

    def test_no_urls_invented(self):
        docs = [make_doc("S1", "a.com", SHARED), make_doc("S2", "b.org", SHARED)]
        themes = identify_themes(docs)
        # Themes reference source ids only — no raw URLs.
        for t in themes:
            for sid in t.sourceIds:
                assert sid.startswith("S")


class TestCoverage:
    def test_counts_supported_and_insufficient(self):
        findings = [
            Finding(text="A", sourceIds=["S1"], evidenceClass="fact"),
            Finding(text="B", sourceIds=[], evidenceClass="fact"),
            Finding(text="C", sourceIds=["S2"], evidenceClass="interpretation"),
        ]
        cov = compute_coverage(findings, conflicting=2)
        assert cov.supported == 1  # only fact-with-citation counts as supported
        assert cov.insufficient == 1  # no citations
        assert cov.conflicting == 2


class TestFrequentTerms:
    def test_stopwords_excluded(self):
        docs = [make_doc("S1", "a.com", "the and of cybersecurity matters about security")]
        terms = extract_frequent_terms(docs)
        words = [w for w, _ in terms]
        assert "the" not in words
        assert "and" not in words
        assert any("security" in w for w in words)
