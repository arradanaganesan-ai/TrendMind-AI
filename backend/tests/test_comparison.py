"""Unit tests for the deterministic comparison core (services/comparison.py).

All fixtures are hand-built in memory — no database, no network, no AI.
"""

from __future__ import annotations

import pytest

from app.schemas import (
    Finding,
    ReportMethodology,
    ResearchRecord,
    ResearchReport,
    SourceRef,
)
from app.services.comparison import (
    AiPairJudgement,
    NOVELTY_CAVEAT,
    classify_findings_with_ai,
    compare_records,
    content_tokens,
    normalize_text,
    token_similarity,
)


def finding(text: str, source_ids=(), evidence_class="fact") -> Finding:
    return Finding(text=text, sourceIds=list(source_ids), evidenceClass=evidence_class)


def source(sid: str, url: str, domain: str = "example.com") -> SourceRef:
    return SourceRef(
        id=sid,
        title=f"Title {sid}",
        url=url,
        domain=domain,
        snippet="snippet text for tests",
    )


def record(
    record_id: str,
    query: str,
    findings: list[Finding],
    sources: list[SourceRef] | None = None,
    searched_at: str = "2026-01-01T10:00:00+00:00",
) -> ResearchRecord:
    report = ResearchReport(
        researchQuestion=query,
        executiveSummary="Summary text for the test report.",
        keyFindings=findings,
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
        searchedAt=searched_at,
        generatedAt=searched_at,
    )
    return ResearchRecord(
        id=record_id,
        query=query,
        createdAt=searched_at,
        status="completed",
        mode="demo",
        resultCount=len(sources or []),
        aiMode="basic",
        report=report,
    )


# --------------------------------------------------------------------------
# Text utilities
# --------------------------------------------------------------------------

class TestTextUtilities:
    def test_normalize_ignores_case_punctuation_whitespace(self):
        assert normalize_text("AI,  Adoption — Surges!") == "ai adoption surges"

    def test_content_tokens_drop_stopwords_and_single_chars(self):
        tokens = content_tokens("The adoption of AI is growing rapidly in the market")
        assert "adoption" in tokens
        assert "growing" in tokens
        assert "the" not in tokens
        assert "is" not in tokens

    def test_similarity_identical_sets_is_one(self):
        t = content_tokens("serverless database growth")
        assert token_similarity(t, t) == 1.0

    def test_similarity_empty_set_is_zero(self):
        assert token_similarity(set(), content_tokens("anything here")) == 0.0


# --------------------------------------------------------------------------
# Classification: exact / similar / conflict / unique
# --------------------------------------------------------------------------

class TestBasicClassification:
    def test_exact_match_after_normalization(self):
        a = record("a", "q", [finding("Serverless adoption grows rapidly")])
        b = record("b", "q", [finding("serverless adoption grows  rapidly!")])
        cmp = compare_records(a, b)
        assert len(cmp.sharedFindings) == 1
        assert cmp.sharedFindings[0].matchType == "exact"
        assert cmp.sharedFindings[0].similarity == 1.0
        assert cmp.similarFindings == []
        assert cmp.uniqueToA == [] and cmp.uniqueToB == []

    def test_similar_findings_matched_by_overlap(self):
        a = record("a", "q", [finding("Serverless database adoption grows rapidly in enterprise")])
        b = record("b", "q", [finding("Serverless database adoption grows steadily in enterprise")])
        cmp = compare_records(a, b)
        assert len(cmp.similarFindings) == 1
        pair = cmp.similarFindings[0]
        assert pair.matchType == "similar"
        assert pair.similarity >= 0.45
        assert pair.a.index == 0 and pair.b.index == 0
        assert cmp.sharedFindings == []

    def test_opposite_polarity_flagged_as_insufficient_conflict(self):
        a = record("a", "q", [finding("Serverless adoption grows rapidly among enterprises")])
        b = record("b", "q", [finding("Serverless adoption declines rapidly among enterprises")])
        cmp = compare_records(a, b)
        assert len(cmp.conflicts) == 1
        conflict = cmp.conflicts[0]
        assert conflict.status == "possible_conflict"
        assert conflict.insufficientEvidence is True
        assert "insufficient evidence" in conflict.explanation
        # A conflict pair is not double-counted as similar/unique.
        assert cmp.similarFindings == []
        assert cmp.uniqueToA == [] and cmp.uniqueToB == []

    def test_negation_vs_growth_flagged(self):
        a = record("a", "q", [finding("Enterprises do not adopt serverless databases")])
        b = record("b", "q", [finding("Enterprises adopt serverless databases rapidly")])
        cmp = compare_records(a, b)
        assert len(cmp.conflicts) == 1
        assert cmp.conflicts[0].status == "possible_conflict"

    def test_unrelated_findings_are_unique(self):
        a = record("a", "q", [finding("Quantum computing benchmarks improved this quarter")])
        b = record("b", "q", [finding("Coffee prices rose in regional markets")])
        cmp = compare_records(a, b)
        assert cmp.sharedFindings == [] and cmp.similarFindings == [] and cmp.conflicts == []
        assert [r.index for r in cmp.uniqueToA] == [0]
        assert [r.index for r in cmp.uniqueToB] == [0]

    def test_matching_is_one_to_one(self):
        # One A finding should match at most one B finding (the best pair).
        a = record(
            "a",
            "q",
            [finding("Serverless database adoption grows rapidly in enterprise environments")],
        )
        b = record(
            "b",
            "q",
            [
                finding("Serverless database adoption grows rapidly in enterprise markets"),
                finding("Serverless database adoption grows rapidly in enterprise settings"),
            ],
        )
        cmp = compare_records(a, b)
        paired_b = [p.b.index for p in cmp.sharedFindings + cmp.similarFindings]
        assert len(paired_b) == len(set(paired_b)) == 1

    def test_shared_sources_listed_on_pairs(self):
        a = record("a", "q", [finding("Serverless adoption grows rapidly", source_ids=["S1"])])
        b = record(
            "b",
            "q",
            [finding("Serverless adoption grows rapidly", source_ids=["S1", "S2"])],
        )
        cmp = compare_records(a, b)
        assert cmp.sharedFindings[0].sharedSourceIds == ["S1"]

    def test_both_empty_findings_compare_cleanly(self):
        cmp = compare_records(record("a", "q", []), record("b", "q", []))
        assert cmp.sharedFindings == [] and cmp.similarFindings == [] and cmp.conflicts == []
        assert cmp.uniqueToA == [] and cmp.uniqueToB == []
        assert cmp.methodology.mode == "basic"

    def test_one_side_empty_means_all_unique(self):
        a = record("a", "q", [finding("First claim"), finding("Second claim")])
        cmp = compare_records(a, record("b", "q", []))
        assert len(cmp.uniqueToA) == 2
        assert cmp.uniqueToB == []

    def test_novelty_caveat_always_present(self):
        cmp = compare_records(record("a", "q", []), record("b", "q", []))
        assert cmp.noveltyCaveat == NOVELTY_CAVEAT


# --------------------------------------------------------------------------
# Sources & temporal note
# --------------------------------------------------------------------------

class TestSourcesAndTemporal:
    def test_source_overlap_by_exact_url(self):
        a = record(
            "a",
            "q",
            [],
            sources=[
                source("S1", "https://example.com/shared"),
                source("S2", "https://example.com/only-a"),
            ],
        )
        b = record(
            "b",
            "q",
            [],
            sources=[
                source("S1", "https://example.com/shared"),
                source("S3", "https://example.com/only-b"),
            ],
        )
        cmp = compare_records(a, b)
        assert cmp.sources.sharedCount == 1
        assert cmp.sources.sharedUrls == ["https://example.com/shared"]
        assert cmp.sources.onlyACount == 1
        assert cmp.sources.onlyBCount == 1
        assert "example.com" in cmp.sources.sharedDomains

    def test_shared_urls_bounded(self):
        a_urls = [source(f"S{i}", f"https://example.com/p/{i}") for i in range(30)]
        b_urls = [source(f"S{i}", f"https://example.com/p/{i}") for i in range(30)]
        cmp = compare_records(record("a", "q", [], sources=a_urls), record("b", "q", [], sources=b_urls))
        assert cmp.sources.sharedCount == 30
        assert len(cmp.sources.sharedUrls) == 20  # bounded for transport

    def test_temporal_note_reports_later_run(self):
        a = record("a", "q", [], searched_at="2026-01-01T10:00:00+00:00")
        b = record("b", "q", [], searched_at="2026-01-04T10:00:00+00:00")
        cmp = compare_records(a, b)
        assert "Run B" in cmp.temporalNote
        assert "3 days" in cmp.temporalNote

    def test_temporal_note_same_day(self):
        a = record("a", "q", [], searched_at="2026-01-01T10:00:00+00:00")
        b = record("b", "q", [], searched_at="2026-01-01T22:00:00+00:00")
        cmp = compare_records(a, b)
        assert "same day" in cmp.temporalNote

    def test_temporal_note_none_on_unparseable_dates(self):
        a = record("a", "q", [], searched_at="not-a-date")
        b = record("b", "q", [], searched_at="2026-01-04T10:00:00+00:00")
        assert compare_records(a, b).temporalNote is None


# --------------------------------------------------------------------------
# AI judgements (merged classification) & AI input validation
# --------------------------------------------------------------------------

class TestAiJudgements:
    def test_judgements_replace_basic_pairing(self):
        a = record("a", "q", [finding("Quantum benchmarks improved"), finding("Serverless adoption grows")])
        b = record("b", "q", [finding("Serverless adoption expands"), finding("Coffee prices rose")])
        judgements = [AiPairJudgement(1, 0, "contradictory", "Model says opposing claims.")]
        cmp = compare_records(a, b, ai_judgements=judgements)
        assert cmp.methodology.mode == "ai"
        assert len(cmp.conflicts) == 1
        assert cmp.conflicts[0].status == "ai_reviewed_conflict"
        assert cmp.conflicts[0].insufficientEvidence is False
        # Unjudged findings stay unique.
        assert [r.index for r in cmp.uniqueToA] == [0]
        assert [r.index for r in cmp.uniqueToB] == [1]

    def test_same_relation_becomes_exact_pair(self):
        a = record("a", "q", [finding("Adoption grows")])
        b = record("b", "q", [finding("Adoption expands")])
        cmp = compare_records(
            a, b, ai_judgements=[AiPairJudgement(0, 0, "same", "identical claim")]
        )
        assert len(cmp.sharedFindings) == 1
        assert cmp.sharedFindings[0].similarity <= 1.0

    def test_duplicate_judgement_indices_dropped(self):
        a = record("a", "q", [finding("Claim one"), finding("Claim two")])
        b = record("b", "q", [finding("Claim one again"), finding("Claim two again")])
        judgements = [
            AiPairJudgement(0, 0, "same", ""),
            AiPairJudgement(1, 0, "similar", ""),  # b already used
        ]
        cmp = compare_records(a, b, ai_judgements=judgements)
        assert len(cmp.sharedFindings) == 1
        assert len(cmp.similarFindings) == 0

    def test_ai_note_and_novelty_caveat_surface(self):
        a = record("a", "q", [])
        b = record("b", "q", [])
        cmp = compare_records(a, b, ai_judgements=[], ai_note="Model unavailable; fell back.")
        assert cmp.methodology.aiNote == "Model unavailable; fell back."
        assert cmp.noveltyCaveat == NOVELTY_CAVEAT


class TestAiInputValidation:
    @staticmethod
    def _run(findings_a, findings_b, response_text, monkeypatch):
        """Drive classify_findings_with_ai with a stubbed adapter."""
        import asyncio

        from app.services.ai import AiCompletion

        class StubAdapter:
            async def complete(self, **kwargs):
                return AiCompletion(text=response_text, model="test", provider="stub")

        # classify_findings_with_ai imports build_adapter from .ai at call time.
        import app.services.ai as ai_mod

        monkeypatch.setattr(ai_mod, "build_adapter", lambda **kwargs: StubAdapter())
        return asyncio.run(
            classify_findings_with_ai(
                findings_a,
                findings_b,
                provider="openai",
                model="test",
                api_key="k",
                base_url="http://localhost",
                timeout=5.0,
            )
        )

    def test_valid_response_parses(self, monkeypatch):
        fa = [finding("Claim A")]
        fb = [finding("Claim B")]
        text = '{"pairs": [{"a": 0, "b": 0, "relation": "similar", "explanation": "overlap"}]}'
        judgements = self._run(fa, fb, text, monkeypatch)
        assert judgements == [AiPairJudgement(0, 0, "similar", "overlap")]

    def test_code_fenced_response_parses(self, monkeypatch):
        text = '```json\n{"pairs": [{"a": 0, "b": 0, "relation": "same", "explanation": "x"}]}\n```'
        judgements = self._run([finding("A")], [finding("B")], text, monkeypatch)
        assert judgements[0].relation == "same"

    def test_out_of_range_and_invalid_relation_dropped(self, monkeypatch):
        text = (
            '{"pairs": ['
            '{"a": 5, "b": 0, "relation": "same", "explanation": "bad index"},'
            '{"a": 0, "b": 0, "relation": "maybe", "explanation": "bad relation"},'
            '{"a": 0, "b": 1, "relation": "same", "explanation": "out of range b"}'
            "]}"
        )
        judgements = self._run([finding("A")], [finding("B")], text, monkeypatch)
        assert judgements == []

    def test_non_json_response_raises(self, monkeypatch):
        with pytest.raises(ValueError):
            self._run([finding("A")], [finding("B")], "not json at all", monkeypatch)

    def test_pairs_missing_raises(self, monkeypatch):
        with pytest.raises(ValueError):
            self._run([finding("A")], [finding("B")], '{"result": []}', monkeypatch)
