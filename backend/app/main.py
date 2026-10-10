"""FastAPI application entry point.

Run:  uvicorn app.main:app --reload --port 8000   (from backend/)
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api.routes import error_response, router
from .config import get_settings
from .database import get_db
from .security.sanitize import redact_secrets

# ---------------------------------------------------------------------------
# Logging — structured, secret-free.
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
# Ensure accidental secrets in log messages are redacted.
class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg)
        return True


for _handler in logging.root.handlers:
    _handler.addFilter(RedactingFilter())

logger = logging.getLogger("trendmind")

# Maximum accepted request body (bytes) — rejects oversized payloads early.
MAX_REQUEST_BYTES = 64 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    # Initialize the database (idempotent schema creation).
    get_db(settings.database_path)
    logger.info(
        "TrendMind AI starting | version=%s | search_mode=%s | ai_configured=%s",
        settings.app_version,
        "demo" if settings.demo_mode else "live",
        settings.ai_configured,
    )
    if not settings.serpapi_configured:
        logger.warning(
            "SERPAPI_API_KEY not set — running in DEMO MODE with clearly labeled mock data."
        )
    if not settings.ai_configured:
        logger.warning(
            "AI provider not configured — using deterministic basic analysis (labeled as such)."
        )
    yield
    logger.info("TrendMind AI shutting down.")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="TrendMind AI — The Web Intelligence Engine",
        description=(
            "Web research and trend intelligence API. "
            "Search results, retrieved content, AI analysis, and hypotheses are kept distinct."
        ),
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    # --- CORS (configurable, restrictive by default) ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
        max_age=600,
    )

    # --- Request size guard (cheap body-length check) ---
    @app.middleware("http")
    async def limit_body_size(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH"}:
            length = request.headers.get("content-length")
            if length:
                try:
                    if int(length) > MAX_REQUEST_BYTES:
                        return error_response(
                            413, "payload_too_large", "Request body is too large."
                        )
                except ValueError:
                    return error_response(400, "bad_request", "Invalid Content-Length header.")
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        # Access log without query strings (they may contain user queries — logged at DEBUG only).
        logger.debug(
            "%s %s -> %s (%.0f ms)", request.method, request.url.path, response.status_code, elapsed_ms
        )
        return response

    # --- Consistent error responses; no tracebacks to clients ---
    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        details = []
        for err in exc.errors()[:5]:
            loc = ".".join(str(p) for p in err.get("loc", []) if p != "body")
            details.append({"field": loc or "body", "message": err.get("msg", "invalid value")})
        first = details[0] if details else {"field": "body", "message": "invalid value"}
        return error_response(
            422,
            "validation_error",
            f"{first['field']}: {first['message']}",
            {"fields": details},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(request: Request, exc: StarletteHTTPException):
        code = "not_found" if exc.status_code == 404 else "http_error"
        message = {
            404: "The requested resource was not found.",
            405: "Method not allowed.",
        }.get(exc.status_code, "The request could not be completed.")
        return error_response(exc.status_code, code, message)

    @app.exception_handler(Exception)
    async def generic_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return error_response(
            500, "internal_error", "An unexpected error occurred. Please try again."
        )

    app.include_router(router)
    return app


app = create_app()
