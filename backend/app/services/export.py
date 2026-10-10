"""Report export — Markdown and JSON with safe filenames and escaped content."""

from __future__ import annotations

import json
import re

from ..schemas import ResearchReport, SearchResult

_SAFE_CHARS = re.compile(r"[^a-z0-9\s-]")


def safe_filename(query: str, extension: str) -> str:
    """Build a filesystem-safe download filename from user input."""
    cleaned = _SAFE_CHARS.sub("", query.lower().strip())
    cleaned = re.sub(r"\s+", "-", cleaned).strip("-")[:60] or "research"
    ext = extension.lstrip(".")
    if ext not in {"md", "json"}:
        ext = "txt"
    return f"trendmind-report-{cleaned}.{ext}"


def _md_escape(text: str) -> str:
    """Escape user/content text for Markdown display."""
    return (
        text.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _cite_links(report: ResearchReport) -> dict[str, str]:
    return {s.id: s.url for s in report.sources}


def report_to_markdown(report: ResearchReport, results: list[SearchResult] | None = None) -> str:
    """Render a full research report as portable Markdown."""
    urls = _cite_links(report)
    m = report.methodology

    def cite(ids: list[str]) -> str:
        parts = []
        for sid in ids:
            url = urls.get(sid)
            if url:
                parts.append(f"[{sid}]({url})")
            else:
                parts.append(f"{sid}?")
        return " ".join(parts)

    lines: list[str] = []
    lines.append(f"# {_md_escape(report.researchQuestion)}")
    lines.append("")
    lines.append(
        f"> **Search performed:** {report.searchedAt} · "
        f"**Report generated:** {report.generatedAt}"
    )
    lines.append(
        f"> **Mode:** {'Demo data' if m.searchMode == 'demo' else 'Live search'} · "
        f"**Analysis:** {'AI-generated' if m.aiMode == 'llm' else 'Basic (non-AI)'} · "
        f"**Content basis:** {m.contentBasis}"
    )
    lines.append("")
    lines.append("> ⚠️ **Demo data** — sources are labeled mock entries on reserved example "
                 "domains, not live web information."
                 if m.searchMode == "demo" else
                 "")
    lines.append("")

    lines.append("## 1. Executive summary")
    lines.append("")
    lines.append(_md_escape(report.executiveSummary))
    lines.append("")

    lines.append("## 2. Key findings")
    lines.append("")
    if report.keyFindings:
        for f in report.keyFindings:
            label = {"fact": "Retrieved information", "interpretation": "AI interpretation",
                     "hypothesis": "Hypothesis — needs verification"}[f.evidenceClass]
            lines.append(f"- **[{label}]** {_md_escape(f.text)} {cite(f.sourceIds)}")
            if f.caveat:
                lines.append(f"  - _{_md_escape(f.caveat)}_")
    else:
        lines.append("_Available sources do not provide enough evidence to support findings._")
    lines.append("")

    lines.append("## 3. Important themes")
    lines.append("")
    if report.themes:
        for t in report.themes:
            lines.append(
                f"- **{_md_escape(t.name)}** ({t.confidence}, strength {t.evidenceStrength}/100, "
                f"{t.mentionCount} source(s)) — {_md_escape(t.description)} {cite(t.sourceIds)}"
            )
            if t.limitations:
                lines.append(f"  - _Limitation: {_md_escape(t.limitations)}_")
    else:
        lines.append("_No recurring themes were identified._")
    lines.append("")

    lines.append("## 4. Evidence and source comparisons")
    lines.append("")
    if report.evidenceComparison:
        for c in report.evidenceComparison:
            lines.append(f"### {_md_escape(c.aspect)}")
            for claim in c.claims:
                lines.append(f"- {_md_escape(claim.claim)} {cite(claim.sourceIds)}")
            if c.note:
                lines.append(f"- _{_md_escape(c.note)}_")
            lines.append("")
    else:
        lines.append("_Not enough overlapping claims were found across sources._")
        lines.append("")

    lines.append("## 5. Conflicting claims")
    lines.append("")
    if report.conflictingClaims:
        for c in report.conflictingClaims:
            lines.append(f"**{_md_escape(c.topic)}**")
            for p in c.positions:
                lines.append(f"- {_md_escape(p.position)} {cite(p.sourceIds)}")
            if c.note:
                lines.append(f"- _{_md_escape(c.note)}_")
            lines.append("")
    else:
        lines.append("_No direct contradictions were detected among the collected sources._")
        lines.append("")

    lines.append("## 6. Emerging developments")
    lines.append("")
    if report.emergingDevelopments:
        for f in report.emergingDevelopments:
            lines.append(f"- {_md_escape(f.text)} {cite(f.sourceIds)}")
    else:
        lines.append("_The collected evidence does not establish clear emerging developments._")
    lines.append("")

    lines.append("## 7. Opportunities")
    lines.append("")
    if report.opportunities:
        for f in report.opportunities:
            lines.append(f"- {_md_escape(f.text)} {cite(f.sourceIds)}")
    else:
        lines.append("_No well-supported opportunities were identified._")
    lines.append("")

    lines.append("## 8. Risks and limitations")
    lines.append("")
    for r in report.risksAndLimitations:
        lines.append(f"- {_md_escape(r)}")
    lines.append("")

    lines.append("## 9. Recommended follow-up questions")
    lines.append("")
    for q in report.followUpQuestions:
        lines.append(f"- {_md_escape(q)}")
    lines.append("")

    lines.append("## 10. Sources and references")
    lines.append("")
    for s in report.sources:
        pub = f" — published {s.publishedDate}" if s.publishedDate else ""
        basis = "full page" if s.extracted else "search snippet"
        lines.append(
            f"- **{s.id}** · [{_md_escape(s.title)}]({s.url}) · {_md_escape(s.domain)} · "
            f"{basis}{pub}"
        )
    lines.append("")

    lines.append("## 11. Evidence coverage")
    lines.append("")
    cov = report.coverage
    lines.append(
        f"- Supported by sources: **{cov.supported}** · "
        f"Conflicting: **{cov.conflicting}** · "
        f"Insufficient: **{cov.insufficient}**"
    )
    lines.append("")

    lines.append("## 12. Research methodology")
    lines.append("")
    lines.append(f"- Search mode: **{m.searchMode}**")
    lines.append(f"- Analysis: **{m.aiMode}**" + ("" if m.aiMode == "llm" else " (deterministic, non-AI)"))
    lines.append(f"- Content basis: **{m.contentBasis}**")
    lines.append(f"- Results collected: **{m.resultCount}**")
    lines.append(f"- Full pages retrieved: **{m.extractedPageCount}** · "
                 f"snippets only: **{m.snippetOnlyCount}**")
    lines.append(f"- Scoring formula: `{_md_escape(m.scoringFormula)}`")
    if m.notes:
        lines.append("- Notes:")
        for n in m.notes:
            lines.append(f"  - {_md_escape(n)}")
    lines.append("")
    lines.append("---")
    lines.append("_Generated by TrendMind AI — The Web Intelligence Engine._")
    lines.append("")

    return "\n".join(line for line in lines if line is not None)


def report_to_json(report: ResearchReport) -> str:
    """Serialize the report as stable, pretty-printed JSON."""
    return json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False)
