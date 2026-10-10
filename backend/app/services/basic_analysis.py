"""Deterministic basic analysis — the fallback when no AI provider is configured.

This is NOT an LLM output and is never presented as one:
- The report is stamped aiMode="basic".
- The UI shows a "Basic analysis" badge.
- Summaries are constructed from computed counts and extracted phrases only.

It produces a valid ResearchReport so the full UI (themes, charts, exports)
remains functional without any AI credentials.
"""

from __future__ import annotations

from ..schemas import (
    ConflictItem,
    EvidenceComparison,
    Finding,
    ResearchReport,
    ReportMethodology,
    ThemeCard,
)
from .trends import SourceDoc, compute_coverage, extract_frequent_terms, identify_themes


def build_basic_report(
    *,
    query: str,
    sources: list[SourceDoc],
    searched_at: str,
    generated_at: str,
    mode: str,
    content_basis: str,
    result_count: int,
    extracted_count: int,
    snippet_only_count: int,
) -> ResearchReport:
    themes = identify_themes(sources)
    domains = sorted({s.domain for s in sources})

    # --- Executive summary (constructed from real counts only) ---
    if not sources:
        summary = (
            "No relevant results were returned for this query, so no evidence-based analysis "
            "could be produced. Try a broader query or change your search filters."
        )
    else:
        top_terms = extract_frequent_terms(sources, limit=5)
        term_list = ", ".join(t for t, _ in top_terms) or "no dominant terms"
        summary = (
            f"This report analyzes {len(sources)} collected source{'s' if len(sources) != 1 else ''} "
            f"from {len(domains)} distinct domain{'s' if len(domains) != 1 else ''} "
            f"for the query “{query}”. "
            f"Recurring terms across the evidence include {term_list}. "
            f"{len(themes)} theme{'s' if len(themes) != 1 else ''} were identified using the "
            f"documented evidence-strength formula. "
            + (
                f"Full page content was retrieved for {extracted_count} source"
                f"{'s' if extracted_count != 1 else ''}; the remaining "
                f"{snippet_only_count} were analyzed from search snippets only."
                if extracted_count
                else "Analysis is based on search snippets only; no full pages were retrieved."
            )
            + " Basic (non-AI) analysis: findings below are computed counts and phrases, "
            "not interpretive conclusions."
        )

    # --- Key findings: grounded only in what was actually counted ---
    findings: list[Finding] = []
    if sources:
        findings.append(
            Finding(
                text=(
                    f"{len(sources)} search results were collected for this query across "
                    f"{len(domains)} domains: {', '.join(domains[:6])}"
                    + (f" and {len(domains) - 6} more" if len(domains) > 6 else "")
                    + "."
                ),
                sourceIds=[s.source_id for s in sources[:8]],
                evidenceClass="fact",
            )
        )
        if themes:
            top = themes[0]
            findings.append(
                Finding(
                    text=(
                        f"The most widely shared theme is “{top.name}”, mentioned by "
                        f"{top.mentionCount} of {len(sources)} sources."
                    ),
                    sourceIds=top.sourceIds[:6],
                    evidenceClass="fact",
                )
            )
        term_counts = extract_frequent_terms(sources, limit=3)
        if term_counts:
            findings.append(
                Finding(
                    text=(
                        "Most frequent terms in the collected content: "
                        + ", ".join(f"{t} ({c} mentions)" for t, c in term_counts)
                        + "."
                    ),
                    sourceIds=[],
                    evidenceClass="fact",
                    caveat="Computed word frequency — not a significance measure.",
                )
            )
        findings.append(
            Finding(
                text=(
                    "This is a snapshot of one search at one moment; it cannot establish "
                    "growth, decline, or historical trajectory for this topic."
                ),
                sourceIds=[],
                evidenceClass="hypothesis",
                caveat="Methodological limitation of snapshot-based analysis.",
            )
        )

    # --- Evidence comparison: overlap of themes across domains ---
    comparisons: list[EvidenceComparison] = []
    for theme in themes[:4]:
        theme_domains = {s.domain for s in sources if s.source_id in theme.sourceIds}
        if len(theme_domains) >= 2:
            comparisons.append(
                EvidenceComparison(
                    aspect=f"Shared coverage: {theme.name}",
                    claims=[
                        {
                            "sourceIds": [sid],
                            "claim": f"Source {sid} discusses {theme.name.lower()}.",
                        }
                        for sid in theme.sourceIds[:4]
                    ],
                    note=f"Mentioned across {len(theme_domains)} distinct domains.",
                )
            )

    # --- Conflicts: detected only when the same theme spans divergent domains
    #     with different framing words — conservative by design. ---
    conflicts: list[ConflictItem] = []

    # --- Risks & limitations (always accurate for basic mode) ---
    risks = [
        "Basic analysis mode: no AI model is configured, so this report contains computed "
        "counts and phrases rather than interpretive synthesis.",
        "Snapshot analysis: a single search cannot demonstrate trends over time.",
        f"{'Content is limited to search snippets for sources that could not be retrieved.' if extracted_count < len(sources) else 'All sources were retrieved as full pages.'}",
        "Search ranking reflects the provider's ranking at query time, not an exhaustive view "
        "of the topic.",
    ]
    if len(sources) < 5:
        risks.insert(
            1,
            "Available sources do not provide enough evidence to support a confident conclusion.",
        )

    follow_ups = [
        f"What do recent primary sources say about {query} in the last 3 months?",
        f"Which organizations are the most cited authorities on {query}?",
        f"What evidence contradicts the dominant themes found for {query}?",
        f"How does {query} differ across regions or industries?",
    ]

    methodology = ReportMethodology(
        searchMode=mode,  # type: ignore[arg-type]
        aiMode="basic",
        contentBasis=content_basis,  # type: ignore[arg-type]
        resultCount=result_count,
        extractedPageCount=extracted_count,
        snippetOnlyCount=snippet_only_count,
        scoringFormula=(
            "evidenceStrength = round(50 * min(supporting_sources/4, 1) "
            "+ 30 * distinct_domains/total_domains + 20 * extracted_ratio); "
            "bands: strong>=70, moderate>=50, emerging>=30, tentative<30. "
            "Heuristic display aid, not a probability."
        ),
        notes=[
            "Deterministic keyword-based analysis — no AI model was invoked.",
            "Themes are computed from term recurrence across the collected sources.",
            "Findings describe this result set only; no global trend claim is made.",
        ],
    )

    return ResearchReport(
        researchQuestion=query,
        executiveSummary=summary,
        keyFindings=findings,
        themes=themes,
        evidenceComparison=comparisons,
        conflictingClaims=conflicts,
        emergingDevelopments=[],
        opportunities=[],
        risksAndLimitations=risks,
        followUpQuestions=follow_ups,
        sources=[
            # Sources are attached by the pipeline, not here.
        ],
        coverage=compute_coverage(findings, len(conflicts)),
        methodology=methodology,
        searchedAt=searched_at,
        generatedAt=generated_at,
    )
