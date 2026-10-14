"""Deterministic report comparison.

Compares the stored findings and sources of two research reports with
explainable, conservative text matching:

  * exact    — identical finding text after normalization
  * similar  — content-word (Jaccard) overlap at or above SIMILARITY_THRESHOLD
  * conflict — similar subject with opposing negation/direction cues; ALWAYS
               flagged as insufficient evidence in basic mode (text matching
               cannot confirm a genuine contradiction)
  * unique   — a finding with no qualifying counterpart in the other report

Nothing in this module calls an AI model. The optional AI classification
(`classify_findings_with_ai`) is invoked by the API layer only when a provider
is configured, and any failure falls back to this module with an explicit note
— a comparison is never presented as AI analysis when it was not.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime

from ..schemas import (
    ComparedRun,
    ComparisonMethodology,
    ConflictCandidate,
    Finding,
    FindingPair,
    FindingRef,
    ReportComparison,
    ResearchRecord,
    SourceComparison,
)

logger = logging.getLogger(__name__)

# ---- Tunables (documented in the methodology text sent to clients) ----
SIMILARITY_THRESHOLD = 0.45
CONFLICT_SUBJECT_THRESHOLD = 0.40
MAX_SHARED_URLS = 20
MAX_SHARED_DOMAINS = 20
AI_FINDING_TEXT_CHARS = 300  # bounded evidence sent to the model

NOVELTY_CAVEAT = (
    "A finding that appears in only one run is not proof that it is new. "
    "Search results vary between runs; compare the run dates and re-run the "
    "queries before drawing any conclusion about change over time."
)

_STOPWORDS = frozenset(
    """
    a an the and or but if then else when while of in on at to for from by with
    without into over under about as is are was were be been being it its this
    that these those there here not no nor so than too very can will just do
    does did done have has had having i you he she we they them his her our
    your their our us which who whom what how why all any both each few more
    most other some such only own same s t don should now also may might must
    one two new used use using based
    """.split()
)

# Direction/negation cues used ONLY to flag conflict candidates conservatively.
# Polarity is computed over ALL normalized tokens (not the stopword-filtered
# set) so negation words like "not" survive.
_NEGATION_CUES = frozenset(
    {
        "not", "never", "cannot", "none", "neither", "nor", "without", "lack",
        "lacks", "failed", "fails", "fail", "unlikely", "refuses", "refused",
        "rejected", "banned",
    }
)
_GROWTH_CUES = frozenset(
    {
        "increase", "increases", "increased", "increasing", "grow", "grows",
        "grew", "growing", "growth", "rise", "rises", "rose", "rising",
        "expand", "expands", "expanded", "expanding", "surge", "surges",
        "surged", "surging", "accelerate", "accelerates", "accelerated",
        "accelerating", "adoption", "boost", "boosts", "boosted", "gain",
        "gains", "gained", "strong", "stronger", "record", "outpace",
        "outpaces", "outpaced", "boom", "booming",
    }
)
_DECLINE_CUES = frozenset(
    {
        "decline", "declines", "declined", "declining", "decrease",
        "decreases", "decreased", "decreasing", "drop", "drops", "dropped",
        "dropping", "fall", "falls", "fell", "falling", "shrink", "shrinks",
        "shrinking", "contraction", "slow", "slows", "slowed", "slowing",
        "slowdown", "dip", "dips", "dipped", "stall", "stalls", "stalled",
        "weaker", "weakening",
    }
)


# --------------------------------------------------------------------------
# Text utilities
# --------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """Case/punctuation/whitespace normalization for exact-match detection."""
    lowered = text.lower()
    cleaned = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", cleaned).strip()


def content_tokens(text: str) -> set[str]:
    """Content words used for overlap scoring (lowercased, stopwords removed)."""
    return {
        token
        for token in normalize_text(text).split()
        if token not in _STOPWORDS and len(token) > 1
    }


def all_tokens(text: str) -> set[str]:
    """Every normalized token — polarity cues (e.g. 'not') must survive here."""
    return set(normalize_text(text).split())


def token_similarity(tokens_a: set[str], tokens_b: set[str]) -> float:
    """Jaccard overlap of two content-token sets (0.0 when either is empty)."""
    if not tokens_a or not tokens_b:
        return 0.0
    union = tokens_a | tokens_b
    if not union:
        return 0.0
    return len(tokens_a & tokens_b) / len(union)


def _polarity_conflicts(tokens_a: set[str], tokens_b: set[str]) -> bool:
    """True when the two texts show opposing polarity.

    Conflict candidates (applied only to findings already sharing enough
    content words to be about the same subject) are flagged when either:
      * one side negates a claim and the other does not, or
      * one side uses growth language while the other uses decline language.
    Both conditions are deliberately broad — every candidate is returned as
    insufficient evidence for human review, never as a confirmed conflict.
    """
    neg_a = bool(tokens_a & _NEGATION_CUES)
    neg_b = bool(tokens_b & _NEGATION_CUES)
    opposite_direction = bool(tokens_a & _GROWTH_CUES and tokens_b & _DECLINE_CUES) or bool(
        tokens_a & _DECLINE_CUES and tokens_b & _GROWTH_CUES
    )
    return (neg_a != neg_b) or opposite_direction


# --------------------------------------------------------------------------
# AI-assisted classification (optional; always falls back to basic)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class AiPairJudgement:
    """One model-judged pair. Indices refer to the ordered finding lists."""

    a_index: int
    b_index: int
    relation: str  # "same" | "similar" | "contradictory"
    explanation: str


def _extract_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        cleaned = parts[1] if len(parts) > 1 else cleaned
        if cleaned.lstrip().lower().startswith("json"):
            cleaned = cleaned.lstrip()[4:]
    data = json.loads(cleaned.strip())
    if not isinstance(data, dict):
        raise ValueError("AI response is not a JSON object")
    return data


async def classify_findings_with_ai(
    findings_a: list[Finding],
    findings_b: list[Finding],
    *,
    provider: str,
    model: str,
    api_key: str,
    base_url: str,
    timeout: float,
) -> list[AiPairJudgement]:
    """Ask the configured model to judge finding pairs. Raises AiError on failure.

    The prompt is bounded (each finding truncated) and the response is strictly
    validated; invalid entries are dropped, never guessed at.
    """
    from .ai import build_adapter

    def block(findings: list[Finding], label: str) -> str:
        lines = [f"Report {label} findings:"]
        for i, f in enumerate(findings):
            text = f.text[:AI_FINDING_TEXT_CHARS]
            lines.append(f"[{i}] ({f.evidenceClass}) {text}")
        return "\n".join(lines)

    system = (
        "You compare research findings from two reports about the same topic. "
        "Judge ONLY whether pairs of findings express the same, a similar, or a "
        "contradictory claim. Be conservative: when unsure, omit the pair."
    )
    user = (
        f"{block(findings_a, 'A')}\n\n{block(findings_b, 'B')}\n\n"
        'Respond with ONLY JSON: {"pairs": [{"a": 0, "b": 1, "relation": '
        '"same|similar|contradictory", "explanation": "<max 200 chars>"}]}\n'
        "Rules: each finding may appear in at most one pair; 'same' means the "
        "identical claim, 'similar' an overlapping claim, 'contradictory' an "
        "opposing claim. Omit pairs you are not confident about."
    )

    adapter = build_adapter(
        provider=provider, model=model, api_key=api_key, base_url=base_url, timeout=timeout
    )
    completion = await adapter.complete(
        system=system, user=user, json_mode=False, max_tokens=1500
    )
    payload = _extract_json(completion.text)

    raw_pairs = payload.get("pairs")
    if not isinstance(raw_pairs, list):
        raise ValueError("AI response has no 'pairs' list")

    judgements: list[AiPairJudgement] = []
    used_a: set[int] = set()
    used_b: set[int] = set()
    for item in raw_pairs:
        if not isinstance(item, dict):
            continue
        try:
            a_index = int(item["a"])
            b_index = int(item["b"])
        except (KeyError, TypeError, ValueError):
            continue
        relation = str(item.get("relation", "")).strip().lower()
        if relation not in {"same", "similar", "contradictory"}:
            continue
        if not (0 <= a_index < len(findings_a)) or not (0 <= b_index < len(findings_b)):
            continue
        if a_index in used_a or b_index in used_b:
            continue
        used_a.add(a_index)
        used_b.add(b_index)
        explanation = str(item.get("explanation", "")).strip()[:240]
        judgements.append(
            AiPairJudgement(
                a_index=a_index, b_index=b_index, relation=relation, explanation=explanation
            )
        )
    return judgements


# --------------------------------------------------------------------------
# Core comparison
# --------------------------------------------------------------------------

def _ref(finding: Finding, index: int) -> FindingRef:
    return FindingRef(
        index=index,
        text=finding.text,
        evidenceClass=finding.evidenceClass,
        sourceIds=list(finding.sourceIds),
        caveat=finding.caveat,
    )


def _shared_sources(a: Finding, b: Finding) -> list[str]:
    b_ids = set(b.sourceIds)
    return [sid for sid in a.sourceIds if sid in b_ids]


def _classify_basic(
    findings_a: list[Finding], findings_b: list[Finding]
) -> tuple[list[FindingPair], list[FindingPair], list[ConflictCandidate], list[int], list[int]]:
    """One-to-one greedy matching, most confident pairs first."""
    candidates: list[tuple[str, float, int, int]] = []
    all_a = [all_tokens(f.text) for f in findings_a]
    all_b = [all_tokens(f.text) for f in findings_b]
    for ia, a in enumerate(findings_a):
        tokens_a = content_tokens(a.text)
        norm_a = normalize_text(a.text)
        for ib, b in enumerate(findings_b):
            tokens_b = content_tokens(b.text)
            if norm_a and norm_a == normalize_text(b.text):
                candidates.append(("exact", 1.0, ia, ib))
                continue
            sim = token_similarity(tokens_a, tokens_b)
            if sim >= CONFLICT_SUBJECT_THRESHOLD and _polarity_conflicts(all_a[ia], all_b[ib]):
                candidates.append(("conflict", sim, ia, ib))
            elif sim >= SIMILARITY_THRESHOLD:
                candidates.append(("similar", sim, ia, ib))

    rank = {"exact": 0, "conflict": 1, "similar": 2}
    candidates.sort(key=lambda c: (rank[c[0]], -c[1], c[2], c[3]))

    exact_pairs: list[FindingPair] = []
    similar_pairs: list[FindingPair] = []
    conflicts: list[ConflictCandidate] = []
    used_a: set[int] = set()
    used_b: set[int] = set()

    for kind, sim, ia, ib in candidates:
        if ia in used_a or ib in used_b:
            continue
        used_a.add(ia)
        used_b.add(ib)
        a, b = findings_a[ia], findings_b[ib]
        if kind == "exact":
            exact_pairs.append(
                FindingPair(
                    a=_ref(a, ia),
                    b=_ref(b, ib),
                    similarity=1.0,
                    matchType="exact",
                    sharedSourceIds=_shared_sources(a, b),
                )
            )
        elif kind == "conflict":
            a_t, b_t = all_a[ia], all_b[ib]
            a_neg, b_neg = bool(a_t & _NEGATION_CUES), bool(b_t & _NEGATION_CUES)
            a_dec, b_dec = bool(a_t & _DECLINE_CUES), bool(b_t & _DECLINE_CUES)
            if a_neg and not b_neg:
                direction = "Run A negates the claim while Run B does not"
            elif b_neg and not a_neg:
                direction = "Run B negates the claim while Run A does not"
            elif a_dec and not b_dec:
                direction = "Run A uses decline language while Run B does not"
            elif b_dec and not a_dec:
                direction = "Run B uses decline language while Run A does not"
            else:
                direction = "the two runs use opposing direction cues"
            conflicts.append(
                ConflictCandidate(
                    a=_ref(a, ia),
                    b=_ref(b, ib),
                    similarity=round(sim, 3),
                    status="possible_conflict",
                    explanation=(
                        f"These findings share {round(sim * 100)}% of their content words, but "
                        f"{direction}. Text similarity cannot confirm a genuine contradiction — "
                        "this is flagged as insufficient evidence; review the cited sources."
                    ),
                    insufficientEvidence=True,
                )
            )
        else:
            similar_pairs.append(
                FindingPair(
                    a=_ref(a, ia),
                    b=_ref(b, ib),
                    similarity=round(sim, 3),
                    matchType="similar",
                    sharedSourceIds=_shared_sources(a, b),
                )
            )

    unmatched_a = [i for i in range(len(findings_a)) if i not in used_a]
    unmatched_b = [i for i in range(len(findings_b)) if i not in used_b]
    return exact_pairs, similar_pairs, conflicts, unmatched_a, unmatched_b


def _classify_with_judgements(
    findings_a: list[Finding],
    findings_b: list[Finding],
    judgements: list[AiPairJudgement],
) -> tuple[list[FindingPair], list[FindingPair], list[ConflictCandidate], list[int], list[int]]:
    """Build pairings from validated AI judgements (still one-to-one)."""
    exact_pairs: list[FindingPair] = []
    similar_pairs: list[FindingPair] = []
    conflicts: list[ConflictCandidate] = []
    used_a: set[int] = set()
    used_b: set[int] = set()

    for j in judgements:
        if j.a_index in used_a or j.b_index in used_b:
            continue
        used_a.add(j.a_index)
        used_b.add(j.b_index)
        a, b = findings_a[j.a_index], findings_b[j.b_index]
        sim = round(token_similarity(content_tokens(a.text), content_tokens(b.text)), 3)
        if j.relation == "same":
            exact_pairs.append(
                FindingPair(
                    a=_ref(a, j.a_index),
                    b=_ref(b, j.b_index),
                    similarity=sim,
                    matchType="exact",
                    sharedSourceIds=_shared_sources(a, b),
                )
            )
        elif j.relation == "similar":
            similar_pairs.append(
                FindingPair(
                    a=_ref(a, j.a_index),
                    b=_ref(b, j.b_index),
                    similarity=sim,
                    matchType="similar",
                    sharedSourceIds=_shared_sources(a, b),
                )
            )
        else:  # contradictory
            conflicts.append(
                ConflictCandidate(
                    a=_ref(a, j.a_index),
                    b=_ref(b, j.b_index),
                    similarity=sim,
                    status="ai_reviewed_conflict",
                    explanation=j.explanation
                    or "The model judged these findings contradictory. Verify against the cited sources.",
                    insufficientEvidence=False,
                )
            )

    unmatched_a = [i for i in range(len(findings_a)) if i not in used_a]
    unmatched_b = [i for i in range(len(findings_b)) if i not in used_b]
    return exact_pairs, similar_pairs, conflicts, unmatched_a, unmatched_b


def _parse_ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _temporal_note(a: ComparedRun, b: ComparedRun) -> str | None:
    ta = _parse_ts(a.searchedAt or a.createdAt)
    tb = _parse_ts(b.searchedAt or b.createdAt)
    if ta is None or tb is None:
        return None
    try:
        delta_seconds = abs((tb - ta).total_seconds())
    except TypeError:  # mixed naive/aware timestamps
        return None
    if delta_seconds < 86_400:
        return "Both reports were searched within the same day."
    days = round(delta_seconds / 86_400)
    later = "B" if tb > ta else "A"
    earlier = "A" if later == "B" else "B"
    unit = "day" if days == 1 else "days"
    return f"Run {later} was searched about {days} {unit} after run {earlier}."


def _source_comparison(report_a, report_b) -> SourceComparison:
    urls_a = [s.url for s in report_a.sources]
    urls_b = [s.url for s in report_b.sources]
    set_b = set(urls_b)
    shared_ordered = [u for u in urls_a if u in set_b]
    set_a = set(urls_a)
    shared_set = set(shared_ordered)
    domains = sorted({s.domain for s in report_a.sources} & {s.domain for s in report_b.sources})
    return SourceComparison(
        sharedUrls=shared_ordered[:MAX_SHARED_URLS],
        sharedCount=len(shared_set),
        onlyACount=len(set_a - set_b),
        onlyBCount=len(set_b - set_a),
        sharedDomains=domains[:MAX_SHARED_DOMAINS],
    )


def _run_side(record: ResearchRecord) -> ComparedRun:
    report = record.report
    return ComparedRun(
        id=record.id,
        query=record.query,
        researchQuestion=report.researchQuestion,
        createdAt=record.createdAt,
        searchedAt=report.searchedAt,
        mode=record.mode,
        aiMode=record.aiMode,
        findingCount=len(report.keyFindings),
        sourceCount=len(report.sources),
    )


def compare_records(
    record_a: ResearchRecord,
    record_b: ResearchRecord,
    *,
    ai_judgements: list[AiPairJudgement] | None = None,
    ai_note: str | None = None,
) -> ReportComparison:
    """Compare two stored records. Both must carry a report (validated upstream)."""
    report_a, report_b = record_a.report, record_b.report

    if ai_judgements is not None:
        exact, similar, conflicts, unmatched_a, unmatched_b = _classify_with_judgements(
            report_a.keyFindings, report_b.keyFindings, ai_judgements
        )
        methodology = ComparisonMethodology(
            mode="ai",
            explanation=[
                "AI-assisted comparison: the configured model judged finding pairs from their "
                "text. Overlap percentages and shared-source counts are deterministic, not model output.",
                "Model judgements can be wrong — verify any contradiction against the cited sources.",
                "Sources are matched by exact URL; domain overlap is informational only.",
            ],
            aiNote=ai_note,
        )
    else:
        exact, similar, conflicts, unmatched_a, unmatched_b = _classify_basic(
            report_a.keyFindings, report_b.keyFindings
        )
        methodology = ComparisonMethodology(
            mode="basic",
            explanation=[
                "Basic comparison: deterministic text matching only — no AI model was used for "
                "this comparison.",
                "Exact match: identical finding text after case, punctuation, and whitespace "
                "normalization.",
                f"Similar: at least {round(SIMILARITY_THRESHOLD * 100)}% shared content words "
                "(Jaccard overlap, stopwords removed). This is lexical similarity, not semantic "
                "understanding.",
                f"Possible conflict: at least {round(CONFLICT_SUBJECT_THRESHOLD * 100)}% shared "
                "content words with opposing negation or direction cues. Text matching cannot "
                "confirm a contradiction, so every entry here is flagged as insufficient evidence.",
                "Sources are matched by exact URL; domain overlap is informational only.",
            ],
            aiNote=ai_note,
        )

    run_a = _run_side(record_a)
    run_b = _run_side(record_b)
    return ReportComparison(
        runA=run_a,
        runB=run_b,
        sharedFindings=exact,
        similarFindings=similar,
        conflicts=conflicts,
        uniqueToA=[_ref(report_a.keyFindings[i], i) for i in unmatched_a],
        uniqueToB=[_ref(report_b.keyFindings[i], i) for i in unmatched_b],
        sources=_source_comparison(report_a, report_b),
        methodology=methodology,
        temporalNote=_temporal_note(run_a, run_b),
        noveltyCaveat=NOVELTY_CAVEAT,
    )
