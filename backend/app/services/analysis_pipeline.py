"""Analysis pipeline — orchestrates the full research run.

Steps:
  1. Collect normalized search results (live or demo).
  2. Extract source content where safely available (SSRF-protected).
  3. Prepare a bounded evidence package.
  4. Generate structured analysis (configured AI provider, or deterministic basic mode).
  5. Validate structure (Pydantic) and semantics (citations), with at most ONE
     controlled repair attempt when the model output is structurally invalid.
  6. Verify citations against collected sources; drop invalid ones.
  7. Return a complete ResearchReport.

Search and analysis remain separate services — the analysis step never performs
its own searches.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from ..config import Settings
from ..schemas import (
    ConflictItem,
    EvidenceComparison,
    Finding,
    ReportMethodology,
    ResearchReport,
    SearchResult,
    SourceRef,
    ThemeCard,
)
from .ai import AiError, AiUnavailableError, build_adapter
from .ai.prompts import SYSTEM_PROMPT, build_user_prompt
from .basic_analysis import build_basic_report
from .citations import validate_report_citations
from .demo_data import demo_search
from .extraction_service import extract_pages
from .search_service import SearchError, SerpApiSearchService
from .trends import FORMULA_TEXT, SourceDoc, compute_coverage, identify_themes

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_note(reason: str) -> str | None:
    """Bound a user-facing extraction note (why a page was not retrieved).

    Collapses whitespace and truncates so notes stay short and safe for the UI;
    returns None when there is nothing meaningful to show.
    """
    cleaned = " ".join(str(reason).split())
    return cleaned[:160] if cleaned else None


def _domain_of(url: str) -> str:
    from urllib.parse import urlparse

    try:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


class ResearchPipeline:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def run(
        self,
        query: str,
        *,
        filters: dict[str, Any] | None = None,
        search_client: Any = None,
        on_stage: Any = None,
    ) -> tuple[list[SearchResult], ResearchReport | None, str, str | None]:
        """Execute the pipeline.

        Returns (results, report, mode, error_message).
        On AI failure the report still returns in basic mode (graceful fallback).

        `on_stage` is an optional async callback invoked with honest progress
        stages: "searching" -> "extracting" -> "analyzing" -> "validating".
        It is best-effort: a failing callback never fails the research run.
        """
        settings = self._settings
        filters = filters or {}
        num_results = int(filters.get("numResults") or 10)
        num_results = max(1, min(num_results, settings.max_results_limit))

        async def stage(name: str) -> None:
            if on_stage is None:
                return
            try:
                await on_stage(name)
            except Exception:  # noqa: BLE001 - progress must never break research
                logger.debug("Stage callback failed for %s", name, exc_info=True)

        # ---- Step 1: collect search results (live or demo) ----
        await stage("searching")
        searched_at = _now()
        if settings.serpapi_configured:
            mode = "live"
            service = SerpApiSearchService(
                settings.serpapi_api_key,
                engine=settings.serpapi_engine,
                timeout=settings.search_timeout_seconds,
            )
            response = await service.search(
                query,
                num_results=num_results,
                category=str(filters.get("category") or "general"),
                region=str(filters.get("region") or "us"),
                language=str(filters.get("language") or "en"),
                time_range=str(filters.get("timeRange") or "any"),
                client=search_client,
            )
            results = response.results
            searched_at = response.searched_at or searched_at
        else:
            mode = "demo"
            results = demo_search(query, num_results)

        if not results:
            report = self._empty_report(query, mode, searched_at)
            return results, report, mode, None

        # ---- Step 2: source extraction (SSRF-protected, best effort) ----
        extracted_count = 0
        content_by_url: dict[str, tuple[str, str, bool]] = {}
        # url -> (text, title, extracted_ok)
        # Real outcome for every ATTEMPTED page, including blocked/failed ones,
        # so the UI can show honest per-source retrieval states.
        extraction_outcome_by_url: dict[str, tuple[str, str | None]] = {}

        if settings.enable_source_extraction and mode == "live":
            await stage("extracting")
            targets = [r.url for r in results[: settings.max_extract_pages]]
            try:
                extraction_results = await extract_pages(
                    targets,
                    max_pages=settings.max_extract_pages,
                    timeout_seconds=settings.extract_timeout_seconds,
                    max_bytes=settings.max_page_bytes,
                    max_chars=settings.max_extract_chars,
                )
                for ex in extraction_results:
                    extraction_outcome_by_url[ex.url] = (ex.status, _sanitize_note(ex.reason))
                    if ex.status == "extracted":
                        content_by_url[ex.url] = (ex.text, ex.title, True)
                        extracted_count += 1
            except Exception:  # Extraction must never fail the research run.
                logger.info("Source extraction unavailable; continuing with snippets only.")

        # Build SourceRefs + SourceDocs
        sources_ref: list[SourceRef] = []
        source_docs: list[SourceDoc] = []
        for i, r in enumerate(results, start=1):
            sid = f"S{i}"
            has_page = r.url in content_by_url
            if has_page:
                text, _title, _ = content_by_url[r.url]
                status, note = "extracted", None
            else:
                attempted = extraction_outcome_by_url.get(r.url)
                if attempted is not None:
                    # Extraction was attempted: surface the REAL outcome
                    # (blocked / failed / skipped) plus a user-safe note.
                    status, note = attempted
                elif settings.enable_source_extraction and mode == "live":
                    # Attempted? No — this URL was beyond the extraction cap.
                    status, note = "snippet_only", None
                else:
                    status, note = ("skipped" if mode == "demo" else "snippet_only"), None

            snippet_or_content = content_by_url.get(r.url, (r.snippet, "", False))[0]
            sources_ref.append(
                SourceRef(
                    id=sid,
                    title=r.title,
                    url=r.url,
                    domain=r.domain,
                    snippet=r.snippet,
                    publishedDate=r.publishedDate,
                    extracted=has_page,
                    extractionStatus=status,  # type: ignore[arg-type]
                    extractionNote=note,
                )
            )
            source_docs.append(
                SourceDoc(
                    source_id=sid,
                    domain=r.domain,
                    title=r.title,
                    content=snippet_or_content or r.snippet,
                    extracted=has_page,
                    url=r.url,
                )
            )

        snippet_only_count = len(results) - extracted_count
        content_basis = (
            "demo"
            if mode == "demo"
            else "extracted"
            if extracted_count == len(results) and results
            else "mixed"
            if extracted_count > 0
            else "snippets"
        )

        # ---- Step 3: bounded evidence package ----
        computed_themes = identify_themes(source_docs)
        mode_notes = self._mode_notes(mode, extracted_count, len(results))

        # ---- Step 4: analysis (AI if configured, else deterministic basic) ----
        await stage("analyzing")
        ai_mode = "basic"
        report: ResearchReport | None = None

        if settings.ai_configured:
            try:
                report = await self._analyze_with_ai(
                    query=query,
                    source_docs=source_docs,
                    computed_themes=computed_themes,
                    mode_notes=mode_notes,
                    content_basis=content_basis,
                    searched_at=searched_at,
                )
                ai_mode = "llm"
            except (AiUnavailableError, AiError, ValidationError) as exc:
                # Graceful fallback: preserve collected results, label basic mode.
                logger.warning("AI analysis fell back to basic mode: %s", exc.code)
                report = None

        if report is None:
            report = build_basic_report(
                query=query,
                sources=source_docs,
                searched_at=searched_at,
                generated_at=_now(),
                mode=mode,
                content_basis=content_basis,
                result_count=len(results),
                extracted_count=extracted_count,
                snippet_only_count=snippet_only_count,
            )
            ai_mode = "basic"
            # Ensure computed themes are present even in basic mode.
            if not report.themes:
                report.themes = computed_themes
            report.coverage = compute_coverage(report.keyFindings, len(report.conflictingClaims))

        # ---- Steps 5-6: attach sources, methodology, validate citations ----
        await stage("validating")
        report.sources = sources_ref
        report.searchedAt = searched_at
        report.generatedAt = _now()
        report.methodology = ReportMethodology(
            searchMode=mode,  # type: ignore[arg-type]
            aiMode=ai_mode,  # type: ignore[arg-type]
            contentBasis=content_basis,  # type: ignore[arg-type]
            resultCount=len(results),
            extractedPageCount=extracted_count,
            snippetOnlyCount=snippet_only_count,
            scoringFormula=FORMULA_TEXT,
            notes=self._methodology_notes(mode, ai_mode, extracted_count, len(results)),
        )
        if not report.researchQuestion:
            report.researchQuestion = query

        validation = validate_report_citations(report)
        if validation.warnings:
            report.risksAndLimitations = _dedupe(
                list(report.risksAndLimitations) + validation.warnings
            )

        return results, validation.report, mode, None

    # ------------------------------------------------------------------
    def _mode_notes(self, mode: str, extracted_count: int, total: int) -> list[str]:
        notes = []
        if mode == "demo":
            notes.append(
                "DEMO MODE: all sources are labeled mock entries on reserved example domains. "
                "Do not treat them as real web information."
            )
        if extracted_count == 0:
            notes.append(
                "No full pages were retrieved — analysis is limited to search snippets."
            )
        else:
            notes.append(
                f"{extracted_count} of {total} sources have full page text; the rest are snippets."
            )
        return notes

    def _methodology_notes(
        self, mode: str, ai_mode: str, extracted_count: int, total: int
    ) -> list[str]:
        notes: list[str] = []
        if mode == "demo":
            notes.append(
                "Demo mode: results are clearly labeled mock data from reserved example domains, "
                "not live web information."
            )
        else:
            notes.append("Live search results retrieved via the configured search provider.")
        if ai_mode == "llm":
            notes.append(
                "Structured analysis generated by the configured AI model, then validated "
                "against collected sources; invalid citations were removed."
            )
        else:
            notes.append(
                "No AI model configured — deterministic keyword-based analysis "
                "(not an LLM-generated answer)."
            )
        if extracted_count:
            notes.append(
                f"Full page content retrieved for {extracted_count} source(s); "
                "remaining sources analyzed from search snippets only."
            )
        else:
            notes.append("No pages were retrieved; analysis is snippet-based.")
        notes.append(
            "Snapshot of a single search — no historical comparison or global trend volume "
            "is claimed."
        )
        notes.append(
            "Retrieved webpage content is treated as untrusted data; instructions inside it "
            "are ignored."
        )
        return notes

    def _empty_report(self, query: str, mode: str, searched_at: str) -> ResearchReport:
        return ResearchReport(
            researchQuestion=query,
            executiveSummary=(
                "No relevant results were returned for this query. "
                "Try a broader query or change your search filters."
            ),
            keyFindings=[],
            themes=[],
            evidenceComparison=[],
            conflictingClaims=[],
            emergingDevelopments=[],
            opportunities=[],
            risksAndLimitations=[
                "The search returned no results, so no evidence-based conclusions are possible."
            ],
            followUpQuestions=[],
            sources=[],
            coverage=compute_coverage([], 0),
            methodology=ReportMethodology(
                searchMode=mode,  # type: ignore[arg-type]
                aiMode="basic",
                contentBasis="demo" if mode == "demo" else "snippets",
                resultCount=0,
                extractedPageCount=0,
                snippetOnlyCount=0,
                scoringFormula=FORMULA_TEXT,
                notes=["Search returned no results."],
            ),
            searchedAt=searched_at,
            generatedAt=_now(),
        )

    # ------------------------------------------------------------------
    async def _analyze_with_ai(
        self,
        *,
        query: str,
        source_docs: list[SourceDoc],
        computed_themes: list[ThemeCard],
        mode_notes: list[str],
        content_basis: str,
        searched_at: str,
    ) -> ResearchReport:
        settings = self._settings
        adapter = build_adapter(
            provider=settings.normalized_ai_provider,
            model=settings.ai_model,
            api_key=settings.ai_api_key,
            base_url=settings.ai_base_url,
            timeout=settings.ai_timeout_seconds,
        )

        evidence_sources = [
            {
                "id": d.source_id,
                "title": d.title,
                "url": d.url,
                "domain": d.domain,
                "publishedDate": None,
                "extracted": d.extracted,
                "content": d.content[:4000],
            }
            for d in source_docs
        ]

        user_prompt = build_user_prompt(
            query=query,
            evidence_sources=evidence_sources,
            computed_themes=[
                {
                    "name": t.name,
                    "sourceIds": t.sourceIds,
                    "mentionCount": t.mentionCount,
                    "evidenceStrength": t.evidenceStrength,
                }
                for t in computed_themes
            ],
            scoring_formula=FORMULA_TEXT,
            mode_notes=mode_notes,
            max_chars=settings.ai_max_evidence_chars,
        )

        completion = await adapter.complete(
            system=SYSTEM_PROMPT, user=user_prompt, json_mode=False, max_tokens=3500
        )

        # Attempt 1: parse + schema-validate. On ANY failure, make exactly ONE
        # controlled repair attempt; if that also fails, raise AiUnavailableError
        # so the pipeline falls back to deterministic basic mode (never loops).
        try:
            payload = _parse_json_response(completion.text)
            ai_themes = [ThemeCard.model_validate(t) for t in payload.get("themes", [])]
            ai_findings = [Finding.model_validate(f) for f in payload.get("keyFindings", [])]
        except (ValueError, ValidationError):
            payload = await self._repair(adapter, user_prompt, completion.text)
            try:
                ai_themes = [ThemeCard.model_validate(t) for t in payload.get("themes", [])]
                ai_findings = [Finding.model_validate(f) for f in payload.get("keyFindings", [])]
            except (ValueError, ValidationError) as exc:
                raise AiUnavailableError(
                    "AI analysis produced invalid output. Your collected search results are preserved.",
                    code="ai_invalid_output",
                ) from exc

        # Validate the remaining sections; drop malformed ones instead of failing the run.
        evidence_comparison = _validate_list(payload.get("evidenceComparison", []), EvidenceComparison)
        conflicts = _validate_list(payload.get("conflictingClaims", []), ConflictItem)
        developments = _validate_list(payload.get("emergingDevelopments", []), Finding)
        opportunities = _validate_list(payload.get("opportunities", []), Finding)

        # Merge computed themes when the model returned none (keeps charts alive).
        themes = ai_themes or computed_themes

        report = ResearchReport(
            researchQuestion=str(payload.get("researchQuestion") or query),
            executiveSummary=str(
                payload.get("executiveSummary")
                or "The model did not return an executive summary for this evidence package."
            )[:4000],
            keyFindings=ai_findings,
            themes=themes,
            evidenceComparison=evidence_comparison,
            conflictingClaims=conflicts,
            emergingDevelopments=developments,
            opportunities=opportunities,
            risksAndLimitations=[str(r) for r in payload.get("risksAndLimitations", [])],
            followUpQuestions=[str(q) for q in payload.get("followUpQuestions", [])],
            sources=[],
            coverage=compute_coverage(ai_findings, len(conflicts)),
            methodology=ReportMethodology(
                searchMode="live",
                aiMode="llm",
                contentBasis=content_basis,  # type: ignore[arg-type]
                resultCount=len(source_docs),
                extractedPageCount=sum(1 for d in source_docs if d.extracted),
                snippetOnlyCount=sum(1 for d in source_docs if not d.extracted),
                scoringFormula=FORMULA_TEXT,
                notes=[],
            ),
            searchedAt=searched_at,
            generatedAt=_now(),
        )
        return report

    async def _repair(self, adapter, user_prompt: str, bad_output: str) -> dict:
        """Single controlled repair attempt — never loops."""
        repair_prompt = (
            f"{user_prompt}\n\n"
            "Your previous response was not valid JSON matching the schema.\n"
            "Previous response (truncated):\n"
            f"{bad_output[:3000]}\n\n"
            "Return ONLY the corrected JSON object. No markdown fences."
        )
        try:
            completion = await adapter.complete(
                system=SYSTEM_PROMPT, user=repair_prompt, json_mode=False, max_tokens=3500
            )
            return _parse_json_response(completion.text)
        except (ValueError, AiError) as exc:
            raise AiUnavailableError(
                "AI analysis produced invalid output. Your collected search results are preserved.",
                code="ai_invalid_output",
            ) from exc


def _validate_list(items: Any, model) -> list:
    """Validate a list of model objects; skip malformed entries safely."""
    validated = []
    for item in items if isinstance(items, list) else []:
        try:
            validated.append(model.model_validate(item))
        except ValidationError:
            continue
    return validated


def _parse_json_response(text: str) -> dict:
    """Parse model JSON, tolerating ```json fences. Raises ValueError if invalid."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    # Fall back to the outermost braces if there is surrounding prose.
    if not cleaned.startswith("{"):
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end > start:
            cleaned = cleaned[start : end + 1]
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("Model response was not a JSON object.")
    return data


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip()
        if key and key not in seen:
            seen.add(key)
            out.append(item)
    return out


__all__ = ["ResearchPipeline", "SearchError"]
