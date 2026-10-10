"""API routes.

Error responses use a consistent shape:
    {"error": {"code": "...", "message": "...", "details": ...}}
Stack traces and secrets are never exposed to clients.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from ..config import Settings, get_settings
from ..database import ResearchRepository, TopicRepository, get_db
from ..schemas import (
    ConfigStatus,
    HealthResponse,
    ResearchListResponse,
    ResearchRecord,
    ResearchRequest,
    SavedTopic,
    TopicCreate,
    TopicListResponse,
)
from ..security.ratelimit import RateLimiter
from ..services.analysis_pipeline import ResearchPipeline
from ..services.export import report_to_json, report_to_markdown, safe_filename
from ..services.search_service import SearchError

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
        research_repo.save_completed(
            research_id,
            status="failed",
            ai_mode="basic",
            result_count=0,
            results=[],
            report=None,
            error_message=exc.message,
        )
        return error_response(exc.status, exc.code, exc.message)
    except Exception:
        logger.exception("Research pipeline failed")
        research_repo.save_completed(
            research_id,
            status="failed",
            ai_mode="basic",
            result_count=0,
            results=[],
            report=None,
            error_message="The research run failed unexpectedly.",
        )
        return error_response(
            500, "internal_error", "The research run failed unexpectedly. Please try again."
        )

    ai_mode = report.methodology.aiMode if report else "basic"
    status = "completed" if report is not None else "failed"
    error_message = None if report is not None else "Analysis could not be produced."

    if report is None:
        # Search succeeded but analysis failed entirely: preserve results.
        research_repo.save_completed(
            research_id,
            status="failed",
            ai_mode="basic",
            result_count=len(results),
            results=results,
            report=None,
            error_message="AI analysis is currently unavailable. Your collected search results are preserved.",
        )
        return error_response(
            503,
            "ai_unavailable",
            "AI analysis is currently unavailable. Your collected search results are preserved.",
        )

    research_repo.save_completed(
        research_id,
        status=status,
        ai_mode=ai_mode,
        result_count=len(results),
        results=results,
        report=report,
        error_message=error_message,
    )

    record = research_repo.get(research_id)
    if record is None:  # pragma: no cover - defensive
        return error_response(500, "internal_error", "The record could not be stored.")
    return record


@router.get("/api/research", response_model=ResearchListResponse, tags=["research"])
async def list_research(
    settings: Annotated[Settings, Depends(get_settings_dep)],
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
):
    research_repo, _ = _repos(settings)
    items, total = research_repo.list(limit=limit, offset=offset)
    return ResearchListResponse(items=items, total=total)


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

@router.get("/api/reports/{research_id}/markdown", tags=["reports"])
async def export_markdown(research_id: str, settings: Annotated[Settings, Depends(get_settings_dep)]):
    research_repo, _ = _repos(settings)
    record = research_repo.get(research_id)
    if record is None:
        return error_response(404, "not_found", "The requested research record was not found.")
    if record.report is None:
        return error_response(
            409, "no_report", "This record has no stored report to export."
        )
    md = report_to_markdown(record.report, record.results)
    filename = safe_filename(record.query, "md")
    return PlainTextResponse(
        md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/reports/{research_id}/json", tags=["reports"])
async def export_json(research_id: str, settings: Annotated[Settings, Depends(get_settings_dep)]):
    research_repo, _ = _repos(settings)
    record = research_repo.get(research_id)
    if record is None:
        return error_response(404, "not_found", "The requested research record was not found.")
    if record.report is None:
        return error_response(
            409, "no_report", "This record has no stored report to export."
        )
    body = report_to_json(record.report)
    filename = safe_filename(record.query, "json")
    return PlainTextResponse(
        body,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
