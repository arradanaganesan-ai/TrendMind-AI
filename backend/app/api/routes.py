"""API routes.

Error responses use a consistent shape:
    {"error": {"code": "...", "message": "...", "details": ...}}
Stack traces and secrets are never exposed to clients.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse

from ..config import Settings, get_settings
from ..database import ResearchRepository, TopicRepository, TrendRepository, get_db
from ..schemas import (
    ActivityResponse,
    ConfigStatus,
    HealthResponse,
    ReportComparison,
    ResearchListResponse,
    ResearchRecord,
    ResearchRequest,
    SavedTopic,
    TopicCreate,
    TopicListResponse,
    TrackedTopic,
    TrackedTopicCreate,
    TrackedTopicListResponse,
    TrendCandidate,
    TrendCandidateListResponse,
    TrendTimeline,
    WorkspaceStats,
)
from ..security.ratelimit import RateLimiter
from ..services.ai import AiError
from ..services.analysis_pipeline import ResearchPipeline
from ..services.comparison import classify_findings_with_ai, compare_records
from ..services.export import (
    comparison_filename,
    comparison_to_json,
    comparison_to_markdown,
    report_to_json,
    report_to_markdown,
    safe_filename,
)
from ..services.pdf_export import comparison_to_pdf, report_to_pdf
from ..services.search_service import SearchError
from ..services.trend_tracking import (
    build_snapshots,
    build_timeline,
    detect_consecutive_changes,
    summarize_changes_with_ai,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def error_response(status: int, code: str, message: str, details=None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details}},
    )


def get_settings_dep() -> Settings:
    return get_settings()


def _repos(settings: Settings):
    db = get_db(settings.database_path)
    return ResearchRepository(db), TopicRepository(db)


# Process-wide limiter for the expensive research endpoint.
_research_limiter: RateLimiter | None = None


def _limiter(settings: Settings) -> RateLimiter:
    global _research_limiter
    if _research_limiter is None or _research_limiter.limit != settings.research_rate_limit_per_minute:
        _research_limiter = RateLimiter(settings.research_rate_limit_per_minute, 60.0)
    return _research_limiter


def _client_key(request: Request) -> str:
    # Prefer the direct client address; do not trust forwarded headers blindly.
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _normalize_filters(payload: ResearchRequest, settings: Settings) -> dict | None:
    """Clamp/validate request filters to what the backend actually supports."""
    filters = payload.filters.model_dump() if payload.filters else None
    if filters and filters.get("numResults"):
        filters["numResults"] = max(1, min(int(filters["numResults"]), settings.max_results_limit))
    if filters is None:
        filters = {"numResults": min(10, settings.max_results_limit)}
    return filters


def _store_failed_run(research_repo: ResearchRepository, research_id: str, error_message: str) -> None:
    research_repo.save_completed(
        research_id,
        status="failed",
        ai_mode="basic",
        result_count=0,
        results=[],
        report=None,
        error_message=error_message,
    )


def _store_completed_run(
    research_repo: ResearchRepository,
    research_id: str,
    results,
    report,
) -> ResearchRecord | None:
    ai_mode = report.methodology.aiMode if report else "basic"
    status = "completed" if report is not None else "failed"
    research_repo.save_completed(
        research_id,
        status=status,
        ai_mode=ai_mode,
        result_count=len(results),
        results=results,
        report=report,
        error_message=None
        if report is not None
        else "AI analysis is currently unavailable. Your collected search results are preserved.",
    )
    return research_repo.get(research_id)


# --------------------------------------------------------------------------
# Health & config
# --------------------------------------------------------------------------

@router.get("/api/health", response_model=HealthResponse, tags=["system"])
async def health(settings: Annotated[Settings, Depends(get_settings_dep)]) -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="trendmind-ai",
        version=settings.app_version,
        time=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/api/config/status", response_model=ConfigStatus, tags=["system"])
async def config_status(settings: Annotated[Settings, Depends(get_settings_dep)]) -> ConfigStatus:
    """Configuration status. Secret values are NEVER included — booleans only."""
    return ConfigStatus(
        version=settings.app_version,
        searchMode="demo" if settings.demo_mode else "live",
        serpapiConfigured=settings.serpapi_configured,
        aiProvider=settings.normalized_ai_provider,
        aiConfigured=settings.ai_configured,
        sourceExtractionEnabled=settings.enable_source_extraction,
        demoMode=settings.demo_mode,
        maxResultsLimit=settings.max_results_limit,
        githubRepoUrl=settings.github_repo_url or None,
    )


# --------------------------------------------------------------------------
# Research
# --------------------------------------------------------------------------

@router.post("/api/research", response_model=ResearchRecord, tags=["research"], status_code=201)
async def create_research(
    request: Request,
    payload: ResearchRequest,
    settings: Annotated[Settings, Depends(get_settings_dep)],
):
    """Run a research query: search -> extraction -> analysis -> validation -> store."""
    allowed, retry_after = _limiter(settings).check(_client_key(request))
    if not allowed:
        return error_response(
            429,
            "rate_limited",
            "Search capacity has temporarily been reached. Please wait before trying again.",
            {"retryAfterSeconds": retry_after},
        )

    filters = payload.filters.model_dump() if payload.filters else None
    if filters and filters.get("numResults"):
        filters["numResults"] = max(1, min(int(filters["numResults"]), settings.max_results_limit))

    research_repo, _ = _repos(settings)

    # Respect the configured result cap even without filters.
    if filters is None:
        filters = {"numResults": min(10, settings.max_results_limit)}

    mode = "demo" if settings.demo_mode else "live"
    research_id = research_repo.create_pending(payload.query, mode, filters)

    try:
        pipeline = ResearchPipeline(settings)
        results, report, effective_mode, error_msg = await pipeline.run(
            payload.query, filters=filters
        )
    except SearchError as exc:
        # Configured-but-failing live search: store the failure, surface a safe message.
        _store_failed_run(research_repo, research_id, exc.message)
        return error_response(exc.status, exc.code, exc.message)
    except Exception:
        logger.exception("Research pipeline failed")
        _store_failed_run(research_repo, research_id, "The research run failed unexpectedly.")
        return error_response(
            500, "internal_error", "The research run failed unexpectedly. Please try again."
        )

    record = _store_completed_run(research_repo, research_id, results, report)
    if record is None:  # pragma: no cover - defensive
        return error_response(500, "internal_error", "The record could not be stored.")
    if record.status == "failed":
        return error_response(
            503,
            "ai_unavailable",
            "AI analysis is currently unavailable. Your collected search results are preserved.",
        )
    return record


@router.post("/api/research/stream", tags=["research"], status_code=200)
async def create_research_stream(
    request: Request,
    payload: ResearchRequest,
    settings: Annotated[Settings, Depends(get_settings_dep)],
):
    """Run a research query with honest Server-Sent Events progress.

    Emits `stage` events (searching -> extracting -> analyzing -> validating)
    as the pipeline actually reaches each step, then a single `result` event
    carrying the stored ResearchRecord, or an `error` event with a safe message.
    Stage events are progress signals emitted at real step boundaries.
    """
    import asyncio
    import json as _json

    allowed, retry_after = _limiter(settings).check(_client_key(request))
    if not allowed:
        return error_response(
            429,
            "rate_limited",
            "Search capacity has temporarily been reached. Please wait before trying again.",
            {"retryAfterSeconds": retry_after},
        )

    filters = _normalize_filters(payload, settings)
    research_repo, _ = _repos(settings)
    mode = "demo" if settings.demo_mode else "live"
    research_id = research_repo.create_pending(payload.query, mode, filters)

    def sse(event: str, data) -> str:
        return f"event: {event}\ndata: {_json.dumps(data)}\n\n"

    async def event_stream():
        queue: asyncio.Queue = asyncio.Queue()

        async def on_stage(name: str) -> None:
            await queue.put(("stage", {"stage": name}))

        async def run() -> None:
            try:
                pipeline = ResearchPipeline(settings)
                results, report, _mode, _err = await pipeline.run(
                    payload.query, filters=filters, on_stage=on_stage
                )
                await queue.put(("done", (results, report)))
            except SearchError as exc:
                await queue.put(("search_error", {"code": exc.code, "message": exc.message}))
            except Exception:
                logger.exception("Research pipeline failed")
                await queue.put(
                    (
                        "internal_error",
                        {
                            "code": "internal_error",
                            "message": "The research run failed unexpectedly. Please try again.",
                        },
                    )
                )

        task = asyncio.create_task(run())
        try:
            while True:
                kind, data = await queue.get()
                if kind == "stage":
                    yield sse("stage", data)
                elif kind == "search_error":
                    _store_failed_run(research_repo, research_id, data["message"])
                    yield sse("error", data)
                    break
                elif kind == "internal_error":
                    _store_failed_run(
                        research_repo, research_id, "The research run failed unexpectedly."
                    )
                    yield sse("error", data)
                    break
                else:  # done — persist exactly like the non-streaming endpoint
                    results, report = data
                    record = _store_completed_run(research_repo, research_id, results, report)
                    if record is None:  # pragma: no cover - defensive
                        yield sse(
                            "error",
                            {"code": "internal_error", "message": "The record could not be stored."},
                        )
                    elif record.status == "failed":
                        yield sse(
                            "error",
                            {
                                "code": "ai_unavailable",
                                "message": "AI analysis is currently unavailable. Your collected search results are preserved.",
                            },
                        )
                    else:
                        yield sse("result", record.model_dump(mode="json"))
                    break
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/research", response_model=ResearchListResponse, tags=["research"])
async def list_research(
    settings: Annotated[Settings, Depends(get_settings_dep)],
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    date_from: str | None = Query(
        default=None, description="Include runs on/after this date (YYYY-MM-DD, UTC)."
    ),
    date_to: str | None = Query(
        default=None, description="Include runs on/before this date (YYYY-MM-DD, UTC)."
    ),
):
    for label, value in (("date_from", date_from), ("date_to", date_to)):
        if value is None:
            continue
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return error_response(
                422,
                "validation_error",
                f"{label} must be a date in YYYY-MM-DD format.",
            )
    if date_from and date_to and date_from > date_to:
        return error_response(
            422,
            "validation_error",
            "date_from must be on or before date_to.",
        )
    research_repo, _ = _repos(settings)
    items, total = research_repo.list(
        limit=limit, offset=offset, date_from=date_from, date_to=date_to
    )
    return ResearchListResponse(items=items, total=total)


@router.get("/api/stats", response_model=WorkspaceStats, tags=["research"])
async def workspace_stats(settings: Annotated[Settings, Depends(get_settings_dep)]):
    """Real workspace counters computed by the database (this instance only)."""
    research_repo, topic_repo = _repos(settings)
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    raw = research_repo.stats(since_iso=since)
    return WorkspaceStats(
        researchTotal=raw["research_total"],
        researchCompleted=raw["research_completed"],
        researchFailed=raw["research_failed"],
        reportsTotal=raw["reports_total"],
        savedTopics=topic_repo.count(),
        last7DaysResearch=raw.get("research_since", 0),
        last7DaysCompleted=raw.get("research_completed_since", 0),
    )


@router.get("/api/stats/activity", response_model=ActivityResponse, tags=["research"])
async def workspace_activity(
    settings: Annotated[Settings, Depends(get_settings_dep)],
    days: int = Query(default=30, ge=1, le=365),
):
    """Daily research activity for the last N days, from existing rows only.

    Zero-filled so gaps in activity are shown honestly instead of skipped.
    """
    research_repo, _ = _repos(settings)
    return ActivityResponse(days=days, points=research_repo.activity(days))


@router.get("/api/research/{research_id}", response_model=ResearchRecord, tags=["research"])
async def get_research(research_id: str, settings: Annotated[Settings, Depends(get_settings_dep)]):
    research_repo, _ = _repos(settings)
    record = research_repo.get(research_id)
    if record is None:
        return error_response(404, "not_found", "The requested research record was not found.")
    return record


@router.delete("/api/research/{research_id}", tags=["research"], status_code=204)
async def delete_research(research_id: str, settings: Annotated[Settings, Depends(get_settings_dep)]):
    research_repo, _ = _repos(settings)
    if not research_repo.delete(research_id):
        return error_response(404, "not_found", "The requested research record was not found.")
    return JSONResponse(status_code=204, content=None)


# --------------------------------------------------------------------------
# Topics
# --------------------------------------------------------------------------

@router.get("/api/topics", response_model=TopicListResponse, tags=["topics"])
async def list_topics(settings: Annotated[Settings, Depends(get_settings_dep)]):
    _, topic_repo = _repos(settings)
    return TopicListResponse(items=topic_repo.list())


@router.post("/api/topics", response_model=SavedTopic, tags=["topics"], status_code=201)
async def create_topic(payload: TopicCreate, settings: Annotated[Settings, Depends(get_settings_dep)]):
    _, topic_repo = _repos(settings)
    try:
        return topic_repo.create(payload.topic)
    except Exception:
        logger.exception("Topic insert failed")
        return error_response(500, "internal_error", "The topic could not be saved.")


@router.delete("/api/topics/{topic_id}", tags=["topics"], status_code=204)
async def delete_topic(topic_id: str, settings: Annotated[Settings, Depends(get_settings_dep)]):
    _, topic_repo = _repos(settings)
    if not topic_repo.delete(topic_id):
        return error_response(404, "not_found", "The requested topic was not found.")
    return JSONResponse(status_code=204, content=None)


# --------------------------------------------------------------------------
# Report exports
# --------------------------------------------------------------------------

async def _lookup_report(research_id: str, settings: Settings):
    """Resolve a stored report or an error_response (404 / 409)."""
    research_repo, _ = _repos(settings)
    record = research_repo.get(research_id)
    if record is None:
        return None, error_response(404, "not_found", "The requested research record was not found.")
    if record.report is None:
        return None, error_response(
            409, "no_report", "This record has no stored report to export."
        )
    return record, None


@router.get("/api/reports/{research_id}/markdown", tags=["reports"])
async def export_markdown(research_id: str, settings: Annotated[Settings, Depends(get_settings_dep)]):
    record, err = await _lookup_report(research_id, settings)
    if err is not None:
        return err
    md = report_to_markdown(record.report)
    filename = safe_filename(record.query, "md")
    return PlainTextResponse(
        md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/reports/{research_id}/json", tags=["reports"])
async def export_json(research_id: str, settings: Annotated[Settings, Depends(get_settings_dep)]):
    record, err = await _lookup_report(research_id, settings)
    if err is not None:
        return err
    body = report_to_json(record.report)
    filename = safe_filename(record.query, "json")
    return PlainTextResponse(
        body,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/reports/{research_id}/pdf", tags=["reports"])
async def export_pdf(research_id: str, settings: Annotated[Settings, Depends(get_settings_dep)]):
    """Server-rendered PDF of a stored report (reportlab, dependency-light)."""
    record, err = await _lookup_report(research_id, settings)
    if err is not None:
        return err
    try:
        pdf_bytes = report_to_pdf(record.report)
    except RuntimeError:
        return error_response(
            503,
            "pdf_unavailable",
            "PDF export is not available on this server. Use Markdown export or Print instead.",
        )
    filename = safe_filename(record.query, "pdf")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --------------------------------------------------------------------------
# Report comparison
# --------------------------------------------------------------------------

_COMPARE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_COMPARE_MODES = {"basic", "auto"}


async def _lookup_comparison(a: str | None, b: str | None, settings: Settings):
    """Validate comparison parameters and resolve both records.

    Returns ((record_a, record_b), None) on success or (None, error_response)
    with the standard envelope for 422 (invalid parameters), 404 (unknown id)
    or 409 (record has no stored report).
    """
    for side, value in (("A", a), ("B", b)):
        if not value or not value.strip():
            return None, error_response(
                422, "validation_error", f"Both research runs are required (missing run {side})."
            )
        if not _COMPARE_ID_PATTERN.match(value.strip()):
            return None, error_response(
                422,
                "validation_error",
                f"Research run {side} has an invalid identifier format.",
            )
    if a.strip() == b.strip():
        return None, error_response(
            422, "validation_error", "Choose two different research runs to compare."
        )

    research_repo, _ = _repos(settings)
    record_a = research_repo.get(a.strip())
    if record_a is None:
        return None, error_response(
            404, "not_found", "Research run A was not found.", details={"side": "a"}
        )
    record_b = research_repo.get(b.strip())
    if record_b is None:
        return None, error_response(
            404, "not_found", "Research run B was not found.", details={"side": "b"}
        )
    for side, record in (("a", record_a), ("b", record_b)):
        if record.report is None:
            return None, error_response(
                409,
                "no_report",
                f"Research run {side.upper()} has no stored report to compare.",
                details={"side": side},
            )
    return (record_a, record_b), None


@router.get("/api/compare", response_model=ReportComparison, tags=["comparison"])
async def compare_reports(
    settings: Annotated[Settings, Depends(get_settings_dep)],
    a: str | None = None,
    b: str | None = None,
    mode: str = "basic",
):
    """Compare the stored findings/sources of two research runs.

    mode=basic (default) is deterministic text matching. mode=auto attempts ONE
    bounded AI classification only when a provider is configured; any failure
    falls back to the basic comparison with an explicit note — the response
    never claims AI analysis that did not happen.
    """
    if mode not in _COMPARE_MODES:
        return error_response(
            422, "validation_error", "mode must be 'basic' or 'auto'."
        )
    records, err = await _lookup_comparison(a, b, settings)
    if err is not None:
        return err
    record_a, record_b = records

    ai_judgements = None
    ai_note = None
    if mode == "auto":
        if not settings.ai_configured:
            ai_note = (
                "AI comparison was requested, but no AI provider is configured. The basic "
                "deterministic comparison was computed instead — no AI analysis was performed."
            )
        elif not record_a.report.keyFindings or not record_b.report.keyFindings:
            ai_note = (
                "One of the reports has no findings to classify, so the basic deterministic "
                "comparison was computed instead."
            )
        else:
            try:
                ai_judgements = await classify_findings_with_ai(
                    record_a.report.keyFindings,
                    record_b.report.keyFindings,
                    provider=settings.normalized_ai_provider,
                    model=settings.ai_model,
                    api_key=settings.ai_api_key,
                    base_url=settings.ai_base_url,
                    timeout=min(settings.ai_timeout_seconds, 30.0),
                )
            except (AiError, ValueError) as exc:
                logger.warning("AI comparison fell back to basic mode: %s", exc)
                ai_note = (
                    "AI comparison was requested, but the model was unavailable or returned "
                    "invalid output. The basic deterministic comparison was computed instead — "
                    "no AI analysis was performed."
                )

    return compare_records(record_a, record_b, ai_judgements=ai_judgements, ai_note=ai_note)


@router.get("/api/compare/markdown", tags=["comparison"])
async def export_comparison_markdown(
    settings: Annotated[Settings, Depends(get_settings_dep)],
    a: str | None = None,
    b: str | None = None,
):
    """Portable Markdown export of a comparison (always deterministic basic mode)."""
    records, err = await _lookup_comparison(a, b, settings)
    if err is not None:
        return err
    record_a, record_b = records
    md = comparison_to_markdown(compare_records(record_a, record_b))
    filename = comparison_filename(record_a.query, record_b.query, "md")
    return PlainTextResponse(
        md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/compare/json", tags=["comparison"])
async def export_comparison_json(
    settings: Annotated[Settings, Depends(get_settings_dep)],
    a: str | None = None,
    b: str | None = None,
):
    """JSON export of a comparison (always deterministic basic mode)."""
    records, err = await _lookup_comparison(a, b, settings)
    if err is not None:
        return err
    record_a, record_b = records
    body = comparison_to_json(compare_records(record_a, record_b))
    filename = comparison_filename(record_a.query, record_b.query, "json")
    return PlainTextResponse(
        body,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/compare/pdf", tags=["comparison"])
async def export_comparison_pdf(
    settings: Annotated[Settings, Depends(get_settings_dep)],
    a: str | None = None,
    b: str | None = None,
):
    """Server-rendered PDF of a comparison (reportlab; 503 when unavailable)."""
    records, err = await _lookup_comparison(a, b, settings)
    if err is not None:
        return err
    record_a, record_b = records
    try:
        pdf_bytes = comparison_to_pdf(compare_records(record_a, record_b))
    except RuntimeError:
        return error_response(
            503,
            "pdf_unavailable",
            "PDF export is not available on this server. Use Markdown export or Print instead.",
        )
    filename = comparison_filename(record_a.query, record_b.query, "pdf")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --------------------------------------------------------------------------
# Historical trend tracking (dated snapshots over real research runs)
# --------------------------------------------------------------------------

_TREND_MODES = {"basic", "auto"}
_DATE_PARAM_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _trend_repo(settings: Settings) -> TrendRepository:
    return TrendRepository(get_db(settings.database_path))


def _validate_date_window(date_from: str | None, date_to: str | None) -> JSONResponse | None:
    """Validate inclusive YYYY-MM-DD bounds; returns an error response or None."""
    for label, value in (("dateFrom", date_from), ("dateTo", date_to)):
        if value is None:
            continue
        if not _DATE_PARAM_PATTERN.match(value):
            return error_response(
                422, "validation_error", f"{label} must be a YYYY-MM-DD date."
            )
        try:
            date.fromisoformat(value)
        except ValueError:
            return error_response(
                422, "validation_error", f"{label} is not a real calendar date."
            )
    if date_from and date_to and date_from > date_to:
        return error_response(
            422, "validation_error", "dateFrom must not be after dateTo."
        )
    return None


def _tracked_topic_with_stats(repo: TrendRepository, topic_row: dict) -> TrackedTopic:
    # Dict merge (not double **kwargs) so rows that already carry stats — e.g.
    # from list_with_snapshots — never collide with freshly computed ones.
    merged = {**topic_row, **repo.snapshot_stats(topic_row["query"])}
    return TrackedTopic(**merged)


# NOTE: declared BEFORE /api/trends/{topic_id} so "candidates" is not swallowed
# by the path parameter.
@router.get("/api/trends", response_model=TrackedTopicListResponse, tags=["trends"])
async def list_tracked_topics(
    settings: Annotated[Settings, Depends(get_settings_dep)],
):
    """Every tracked topic with REAL snapshot counts over stored runs."""
    repo = _trend_repo(settings)
    items = [_tracked_topic_with_stats(repo, row) for row in repo.list_with_snapshots()]
    return TrackedTopicListResponse(items=items)


@router.get("/api/trends/candidates", response_model=TrendCandidateListResponse, tags=["trends"])
async def list_trend_candidates(
    settings: Annotated[Settings, Depends(get_settings_dep)],
):
    """Distinct queries of completed runs — real options for 'track a topic'."""
    items = [TrendCandidate(**row) for row in _trend_repo(settings).query_candidates()]
    return TrendCandidateListResponse(items=items)


@router.post(
    "/api/trends", response_model=TrackedTopic, tags=["trends"], status_code=201
)
async def create_tracked_topic(
    payload: TrackedTopicCreate,
    settings: Annotated[Settings, Depends(get_settings_dep)],
):
    """Start tracking an existing research query (idempotent per query).

    422 when no completed run with this query exists: tracking requires real
    dated results, so no empty or synthetic topics are ever created.
    """
    repo = _trend_repo(settings)
    if not repo.snapshot_ids_for_query(payload.query):
        return error_response(
            422,
            "validation_error",
            "No completed research runs found for this query yet — run the "
            "research first, then track it for history.",
            details={"query": payload.query},
        )
    topic = repo.create(payload.query)
    return _tracked_topic_with_stats(repo, topic)


@router.get("/api/trends/{topic_id}", response_model=TrendTimeline, tags=["trends"])
async def get_trend_timeline(
    topic_id: str,
    settings: Annotated[Settings, Depends(get_settings_dep)],
    dateFrom: str | None = None,
    dateTo: str | None = None,
    mode: str = "basic",
):
    """Dated snapshots (oldest-first) + deterministic consecutive changes.

    mode=basic (default) is deterministic. mode=auto attempts ONE bounded AI
    summary only when a provider is configured and >= 2 snapshots exist; any
    failure falls back to basic with an explicit note — the response never
    claims AI analysis that did not happen.
    """
    if mode not in _TREND_MODES:
        return error_response(422, "validation_error", "mode must be 'basic' or 'auto'.")
    err = _validate_date_window(dateFrom, dateTo)
    if err is not None:
        return err

    repo = _trend_repo(settings)
    topic_row = repo.get(topic_id)
    if topic_row is None:
        return error_response(404, "not_found", "Tracked topic not found.")

    research_repo, _ = _repos(settings)
    run_ids = repo.snapshot_ids_for_query(
        topic_row["query"], date_from=dateFrom, date_to=dateTo
    )
    records = [r for rid in run_ids if (r := research_repo.get(rid)) is not None]
    snapshots = build_snapshots(records)
    topic = _tracked_topic_with_stats(repo, topic_row)

    ai_summary: str | None = None
    ai_note: str | None = None
    if mode == "auto":
        if not settings.ai_configured:
            ai_note = (
                "AI summary was requested, but no AI provider is configured. The basic "
                "deterministic change analysis is shown instead — no AI analysis was performed."
            )
        elif len(snapshots) < 2:
            ai_note = (
                "Fewer than two dated snapshots are in range, so there are no changes to "
                "summarize — no AI analysis was performed."
            )
        else:
            try:
                ai_summary = await summarize_changes_with_ai(
                    detect_consecutive_changes(snapshots),
                    provider=settings.normalized_ai_provider,
                    model=settings.ai_model,
                    api_key=settings.ai_api_key,
                    base_url=settings.ai_base_url,
                    timeout=min(settings.ai_timeout_seconds, 30.0),
                )
            except (AiError, ValueError) as exc:
                logger.warning("AI trend summary fell back to basic mode: %s", exc)
                ai_note = (
                    "AI summary was requested, but the model was unavailable or returned "
                    "invalid output. The basic deterministic change analysis is shown instead "
                    "— no AI analysis was performed."
                )

    return build_timeline(
        topic,
        snapshots,
        ai_summary=ai_summary,
        ai_note=ai_note,
        date_from=dateFrom,
        date_to=dateTo,
    )


@router.delete("/api/trends/{topic_id}", tags=["trends"], status_code=204)
async def delete_tracked_topic(
    topic_id: str,
    settings: Annotated[Settings, Depends(get_settings_dep)],
):
    """Stop tracking a topic. Stored research runs are never deleted here."""
    if not _trend_repo(settings).delete(topic_id):
        return error_response(404, "not_found", "Tracked topic not found.")
    return Response(status_code=204)
