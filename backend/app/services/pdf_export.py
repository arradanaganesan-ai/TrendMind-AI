"""PDF report export (reportlab).

Renders the stored research report to a portable PDF with the same section
structure and honesty labels as the Markdown export. Unicode TTF fonts are
used when available (Arial on Windows, DejaVu on most Linux distros);
otherwise the built-in Helvetica is used and text is safely transliterated
to Latin-1 so arbitrary web content can never crash the exporter.
"""

from __future__ import annotations

import logging
import os
from xml.sax.saxutils import escape

from ..schemas import ReportComparison, ResearchReport

logger = logging.getLogger(__name__)

# Candidate Unicode TTFs (family, bold), first match wins.
_FONT_CANDIDATES = [
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/TTF/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
]

_EVIDENCE_LABELS = {
    "fact": "Retrieved information",
    "interpretation": "AI interpretation",
    "hypothesis": "Hypothesis — needs verification",
}


def _font_setup() -> tuple[str, str, bool]:
    """Register a Unicode TTF when present.

    Returns (regular_name, bold_name, unicode_ok).
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for regular, bold in _FONT_CANDIDATES:
        if os.path.exists(regular) and os.path.exists(bold):
            try:
                pdfmetrics.registerFont(TTFont("TrendSans", regular))
                pdfmetrics.registerFont(TTFont("TrendSans-Bold", bold))
                return "TrendSans", "TrendSans-Bold", True
            except Exception:  # noqa: BLE001 - fall through to Helvetica
                logger.debug("Could not register TTF fonts", exc_info=True)
    return "Helvetica", "Helvetica-Bold", False


def _text(value: str, unicode_ok: bool) -> str:
    """Escape for reportlab Paragraph and transliterate when using Helvetica."""
    if not unicode_ok:
        value = value.encode("latin-1", "replace").decode("latin-1")
    return escape(value)


def report_to_pdf(report: ResearchReport) -> bytes:
    """Render a research report as PDF bytes. Raises RuntimeError if the
    PDF backend is unavailable (reported to the client as 503)."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (  # type: ignore[import-not-found]
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("PDF backend is not available") from exc

    regular, bold, unicode_ok = _font_setup()
    from io import BytesIO

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        title=report.researchQuestion,
        author="TrendMind AI",
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )

    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "TmTitle", parent=base["Title"], fontName=bold, fontSize=17,
            leading=21, alignment=TA_CENTER, spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "TmH2", parent=base["Heading2"], fontName=bold, fontSize=12.5,
            leading=16, spaceBefore=12, spaceAfter=4, textColor=colors.HexColor("#4c1d95"),
        ),
        "body": ParagraphStyle(
            "TmBody", parent=base["BodyText"], fontName=regular, fontSize=9.5,
            leading=13.5, spaceAfter=4,
        ),
        "meta": ParagraphStyle(
            "TmMeta", parent=base["BodyText"], fontName=regular, fontSize=8.5,
            leading=12, textColor=colors.HexColor("#475569"),
        ),
        "small": ParagraphStyle(
            "TmSmall", parent=base["BodyText"], fontName=regular, fontSize=8,
            leading=11, textColor=colors.HexColor("#64748b"), spaceAfter=3,
        ),
        "bullet": ParagraphStyle(
            "TmBullet", parent=base["BodyText"], fontName=regular, fontSize=9.5,
            leading=13.5, leftIndent=10, bulletIndent=2, spaceAfter=3,
        ),
    }

    def p(text: str, style: str = "body") -> Paragraph:
        return Paragraph(_text(text, unicode_ok), styles[style])

    def cite(ids: list[str]) -> str:
        return f" [{', '.join(ids)}]" if ids else ""

    def bullet(text: str, label: str | None = None) -> Paragraph:
        prefix = f"<b>[{_text(label, unicode_ok)}]</b> " if label else ""
        return Paragraph(
            f"• {prefix}{_text(text, unicode_ok)}", styles["bullet"]
        )

    m = report.methodology
    story: list = []

    story.append(p(report.researchQuestion, "title"))
    mode_line = (
        f"Searched: {report.searchedAt}  ·  Generated: {report.generatedAt}  ·  "
        f"Mode: {'DEMO DATA' if m.searchMode == 'demo' else 'live search'}  ·  "
        f"Analysis: {'AI-generated' if m.aiMode == 'llm' else 'basic (non-AI)'}  ·  "
        f"Sources: {m.resultCount}"
    )
    story.append(p(mode_line, "meta"))
    if m.searchMode == "demo":
        story.append(
            p(
                "DEMO DATA — sources are labeled mock entries on reserved example "
                "domains, not live web information.",
                "small",
            )
        )
    story.append(Spacer(1, 4 * mm))

    def section(title: str) -> None:
        story.append(p(title, "h2"))

    section("1. Executive summary")
    story.append(p(report.executiveSummary))

    section("2. Key findings")
    if report.keyFindings:
        for f in report.keyFindings:
            story.append(bullet(f.text + cite(f.sourceIds), _EVIDENCE_LABELS[f.evidenceClass]))
            if f.caveat:
                story.append(p(f"Caveat: {f.caveat}", "small"))
    else:
        story.append(p("Available sources do not provide enough evidence to support findings.", "small"))

    section("3. Important themes")
    if report.themes:
        for t in report.themes:
            story.append(
                bullet(
                    f"{t.name} ({t.confidence}, strength {t.evidenceStrength}/100, "
                    f"{t.mentionCount} source(s)) — {t.description}{cite(t.sourceIds)}"
                )
            )
            if t.limitations:
                story.append(p(f"Limitation: {t.limitations}", "small"))
    else:
        story.append(p("No recurring themes were identified.", "small"))

    section("4. Evidence and source comparisons")
    if report.evidenceComparison:
        for c in report.evidenceComparison:
            story.append(p(c.aspect, "body"))
            for claim in c.claims:
                story.append(bullet(claim.claim + cite(claim.sourceIds)))
            if c.note:
                story.append(p(c.note, "small"))
    else:
        story.append(p("Not enough overlapping claims were found across sources.", "small"))

    section("5. Conflicting claims")
    if report.conflictingClaims:
        for c in report.conflictingClaims:
            story.append(p(c.topic))
            for pos in c.positions:
                story.append(bullet(pos.position + cite(pos.sourceIds)))
            if c.note:
                story.append(p(c.note, "small"))
    else:
        story.append(p("No direct contradictions were detected among the collected sources.", "small"))

    for title, items in (
        ("6. Emerging developments", report.emergingDevelopments),
        ("7. Opportunities", report.opportunities),
    ):
        section(title)
        if items:
            for f in items:
                story.append(bullet(f.text + cite(f.sourceIds)))
        else:
            story.append(
                p(
                    "The collected evidence does not establish clear items for this section.",
                    "small",
                )
            )

    section("8. Risks and limitations")
    for r in report.risksAndLimitations:
        story.append(bullet(r))

    section("9. Recommended follow-up questions")
    for q in report.followUpQuestions:
        story.append(bullet(q))

    section("10. Sources and references")
    for s in report.sources:
        status = s.extractionStatus.replace("_", " ")
        line = (
            f'<b>{_text(s.id, unicode_ok)}</b> · '
            f'<link href="{escape(s.url)}" color="#4c1d95">{_text(s.title, unicode_ok)}</link> · '
            f'{_text(s.domain, unicode_ok)} · {_text(status, unicode_ok)}'
        )
        if s.publishedDate:
            line += f" · published {_text(s.publishedDate, unicode_ok)}"
        story.append(Paragraph(line, styles["bullet"]))
        if s.extractionNote:
            story.append(p(f"{s.id}: {s.extractionNote}", "small"))

    cov = report.coverage
    section("11. Evidence coverage")
    data = [
        ["Supported by sources", "Conflicting", "Insufficient"],
        [str(cov.supported), str(cov.conflicting), str(cov.insufficient)],
    ]
    table = Table(data, colWidths=[55 * mm, 40 * mm, 40 * mm])
    table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, 0), bold, 8.5),
                ("FONT", (0, 1), (-1, 1), regular, 9.5),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#475569")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(table)

    section("12. Research methodology")
    story.append(p(f"Search mode: {m.searchMode}"))
    story.append(
        p(
            f"Analysis: {m.aiMode}"
            + ("" if m.aiMode == "llm" else " (deterministic, non-AI)")
        )
    )
    story.append(p(f"Content basis: {m.contentBasis}"))
    story.append(
        p(
            f"Full pages retrieved: {m.extractedPageCount} · "
            f"snippets only: {m.snippetOnlyCount}"
        )
    )
    story.append(p(f"Scoring formula: {m.scoringFormula}", "small"))
    for n in m.notes:
        story.append(p(f"Note: {n}", "small"))

    story.append(Spacer(1, 6 * mm))
    story.append(p("Generated by TrendMind AI — The Web Intelligence Engine.", "small"))

    def _footer(canvas, doc_):  # noqa: ANN001 - reportlab callback
        canvas.saveState()
        canvas.setFont(regular, 7.5)
        canvas.setFillColor(colors.HexColor("#94a3b8"))
        canvas.drawCentredString(
            A4[0] / 2, 10 * mm, f"TrendMind AI · page {doc_.page}"
        )
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


# --------------------------------------------------------------------------
# Comparison PDF (same font machinery as report_to_pdf)
# --------------------------------------------------------------------------

def comparison_to_pdf(comparison: ReportComparison) -> bytes:
    """Render a report comparison as PDF bytes (same 503-on-missing contract)."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (  # type: ignore[import-not-found]
            Paragraph,
            SimpleDocTemplate,
            Spacer,
        )
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("PDF backend is not available") from exc

    regular, bold, unicode_ok = _font_setup()
    from io import BytesIO

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        title="Research Report Comparison",
        author="TrendMind AI",
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )

    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "TmCmpTitle", parent=base["Title"], fontName=bold, fontSize=17,
            leading=21, alignment=TA_CENTER, spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "TmCmpH2", parent=base["Heading2"], fontName=bold, fontSize=12.5,
            leading=16, spaceBefore=12, spaceAfter=4, textColor=colors.HexColor("#4c1d95"),
        ),
        "body": ParagraphStyle(
            "TmCmpBody", parent=base["BodyText"], fontName=regular, fontSize=9.5,
            leading=13.5, spaceAfter=4,
        ),
        "meta": ParagraphStyle(
            "TmCmpMeta", parent=base["BodyText"], fontName=regular, fontSize=8.5,
            leading=12, textColor=colors.HexColor("#475569"),
        ),
        "small": ParagraphStyle(
            "TmCmpSmall", parent=base["BodyText"], fontName=regular, fontSize=8,
            leading=11, textColor=colors.HexColor("#64748b"), spaceAfter=3,
        ),
        "bullet": ParagraphStyle(
            "TmCmpBullet", parent=base["BodyText"], fontName=regular, fontSize=9.5,
            leading=13.5, leftIndent=10, bulletIndent=2, spaceAfter=3,
        ),
    }

    def p(text: str, style: str = "body") -> Paragraph:
        return Paragraph(_text(text, unicode_ok), styles[style])

    def bullet(text: str) -> Paragraph:
        return Paragraph(f"• {_text(text, unicode_ok)}", styles["bullet"])

    story: list = []
    story.append(p("Research Report Comparison", "title"))

    cmp = comparison
    for label, run in (("A", cmp.runA), ("B", cmp.runB)):
        story.append(
            p(
                f"Run {label}: {_text(run.query, unicode_ok)} — searched {run.searchedAt} · "
                f"{run.findingCount} findings · {run.sourceCount} sources · "
                f"{'DEMO DATA' if run.mode == 'demo' else 'live search'} · "
                f"{'AI' if run.aiMode == 'llm' else 'basic'} analysis",
                "meta",
            )
        )
    if cmp.temporalNote:
        story.append(p(cmp.temporalNote, "small"))
    story.append(Spacer(1, 4 * mm))

    def section(title: str) -> None:
        story.append(p(title, "h2"))

    section("How this comparison was computed")
    mode_line = (
        "AI-assisted comparison (the configured model judged finding pairs)."
        if cmp.methodology.mode == "ai"
        else "Basic comparison — deterministic text matching only; no AI model was used."
    )
    story.append(p(mode_line, "body"))
    if cmp.methodology.aiNote:
        story.append(p(f"Note: {cmp.methodology.aiNote}", "small"))
    for line in cmp.methodology.explanation:
        story.append(bullet(line))

    def pair_block(pairs, title: str, empty_note: str) -> None:
        section(title)
        if not pairs:
            story.append(p(empty_note, "small"))
            return
        for pair in pairs:
            pct = round(pair.similarity * 100)
            story.append(
                bullet(
                    f"Run A#{pair.a.index + 1} <-> Run B#{pair.b.index + 1} "
                    f"({pair.matchType}, {pct}% token overlap)"
                )
            )
            story.append(p(f"A: {pair.a.text}", "small"))
            story.append(p(f"B: {pair.b.text}", "small"))
            if pair.sharedSourceIds:
                story.append(p(f"Shared sources: {', '.join(pair.sharedSourceIds)}", "small"))

    pair_block(
        cmp.sharedFindings,
        "1. Shared findings (exact matches)",
        "No identical findings in both runs.",
    )
    pair_block(
        cmp.similarFindings,
        "2. Similar findings",
        "No sufficiently similar finding pairs were found.",
    )

    section("3. Potential conflicts")
    if cmp.conflicts:
        for c in cmp.conflicts:
            flag = (
                "INSUFFICIENT EVIDENCE — text matching cannot confirm this contradiction."
                if c.insufficientEvidence
                else "Judged contradictory by the model — verify against the cited sources."
            )
            story.append(
                bullet(f"Run A#{c.a.index + 1} <-> Run B#{c.b.index + 1} ({c.status})")
            )
            story.append(p(f"A: {c.a.text}", "small"))
            story.append(p(f"B: {c.b.text}", "small"))
            story.append(p(f"Explanation: {c.explanation}", "small"))
            story.append(p(f"Flag: {flag}", "small"))
    else:
        story.append(
            p("No potential conflicts were identified between the two runs.", "small")
        )

    section("4. Findings unique to one run")
    if cmp.uniqueToA:
        story.append(p(f"Only in Run A ({len(cmp.uniqueToA)}):", "body"))
        for ref in cmp.uniqueToA:
            story.append(bullet(ref.text))
    if cmp.uniqueToB:
        story.append(p(f"Only in Run B ({len(cmp.uniqueToB)}):", "body"))
        for ref in cmp.uniqueToB:
            story.append(bullet(ref.text))
    if not cmp.uniqueToA and not cmp.uniqueToB:
        story.append(p("Every finding has a counterpart in the other run.", "small"))
    story.append(p(f"Caveat: {cmp.noveltyCaveat}", "small"))

    section("5. Source overlap")
    src = cmp.sources
    story.append(
        p(
            f"Shared URLs: {src.sharedCount} · only in A: {src.onlyACount} · "
            f"only in B: {src.onlyBCount}"
        )
    )
    for url in src.sharedUrls:
        story.append(bullet(url))
    if src.sharedCount > len(src.sharedUrls):
        story.append(
            p(f"(+{src.sharedCount - len(src.sharedUrls)} more shared URLs)", "small")
        )
    if src.sharedDomains:
        story.append(p(f"Shared domains: {', '.join(src.sharedDomains)}", "small"))

    story.append(Spacer(1, 6 * mm))
    story.append(p("Generated by TrendMind AI — The Web Intelligence Engine.", "small"))

    def _footer(canvas, doc_):  # noqa: ANN001 - reportlab callback
        canvas.saveState()
        canvas.setFont(regular, 7.5)
        canvas.setFillColor(colors.HexColor("#94a3b8"))
        canvas.drawCentredString(
            A4[0] / 2, 10 * mm, f"TrendMind AI comparison · page {doc_.page}"
        )
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
