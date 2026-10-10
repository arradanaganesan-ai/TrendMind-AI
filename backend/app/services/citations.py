"""Citation validation — every cited source must exist in collected evidence.

Defense in depth:
1. Model output is validated by Pydantic schemas (structure).
2. This module validates semantics: citation IDs must resolve to real sources,
   claim lists must be non-empty, theme strengths must match the formula.
3. Invalid citations are REMOVED (not silently linked); findings left without
   evidence are re-classified as interpretation or dropped when inappropriate.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..schemas import (
    ConflictItem,
    EvidenceComparison,
    Finding,
    ResearchReport,
    ThemeCard,
)


@dataclass
class ValidationResult:
    report: ResearchReport
    removed_citations: int = 0
    repaired: bool = False
    warnings: list[str] = field(default_factory=list)


def _clean_finding(f: Finding, valid_ids: set[str]) -> tuple[Finding, int]:
    removed = 0
    kept: list[str] = []
    for sid in f.sourceIds:
        if sid in valid_ids and sid not in kept:
            kept.append(sid)
        else:
            removed += 1
    f.sourceIds = kept
    # A factual claim that lost all citations is no longer grounded as a fact.
    if f.evidenceClass == "fact" and not kept:
        f.evidenceClass = "interpretation"
        f.caveat = (f.caveat + " " if f.caveat else "") + "No supporting source remained after citation validation."
    return f, removed


def validate_report_citations(report: ResearchReport) -> ValidationResult:
    """Drop citations that do not resolve; normalize coverage."""
    valid_ids = {s.id for s in report.sources}
    removed = 0
    warnings: list[str] = []

    cleaned_findings: list[Finding] = []
    for f in report.keyFindings:
        f2, n = _clean_finding(f, valid_ids)
        removed += n
        if f2.text.strip():
            cleaned_findings.append(f2)
    report.keyFindings = cleaned_findings

    for bucket in (report.emergingDevelopments, report.opportunities):
        cleaned: list[Finding] = []
        for f in bucket:
            f2, n = _clean_finding(f, valid_ids)
            removed += n
            if f2.text.strip():
                cleaned.append(f2)
        bucket[:] = cleaned

    # Themes: keep only valid source ids; recompute mention counts to match.
    cleaned_themes: list[ThemeCard] = []
    for t in report.themes:
        before = len(t.sourceIds)
        t.sourceIds = [s for s in t.sourceIds if s in valid_ids]
        removed += max(0, before - len(t.sourceIds))
        if not t.sourceIds:
            continue  # A theme with zero valid sources is not reportable.
        t.mentionCount = len(t.sourceIds)
        cleaned_themes.append(t)
    report.themes = cleaned_themes

    # Comparisons: drop claims whose citations are all invalid.
    comparisons: list[EvidenceComparison] = []
    for c in report.evidenceComparison:
        kept_claims = []
        for claim in c.claims:
            valid = [s for s in claim.sourceIds if s in valid_ids]
            removed += len(claim.sourceIds) - len(valid)
            if valid and claim.claim.strip():
                claim.sourceIds = valid
                kept_claims.append(claim)
        if kept_claims:
            c.claims = kept_claims
            comparisons.append(c)
    report.evidenceComparison = comparisons

    # Conflicts: need >= 2 positions with citations to be meaningful.
    conflicts: list[ConflictItem] = []
    for c in report.conflictingClaims:
        kept_positions = []
        for p in c.positions:
            valid = [s for s in p.sourceIds if s in valid_ids]
            removed += len(p.sourceIds) - len(valid)
            if valid and p.position.strip():
                p.sourceIds = valid
                kept_positions.append(p)
        if len(kept_positions) >= 2:
            c.positions = kept_positions
            conflicts.append(c)
        elif kept_positions:
            warnings.append(f"Conflict '{c.topic}' dropped: fewer than two cited positions remained.")
    report.conflictingClaims = conflicts

    # Recompute coverage consistently with the cleaned content.
    from .trends import compute_coverage

    report.coverage = compute_coverage(report.keyFindings, len(report.conflictingClaims))

    if removed:
        warnings.append(f"{removed} citation reference(s) were removed because they did not match collected sources.")

    return ValidationResult(report=report, removed_citations=removed, warnings=warnings)
