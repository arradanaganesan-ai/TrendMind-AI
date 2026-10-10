# Architecture — TrendMind AI

## Overview

TrendMind AI is a two-service application: a React SPA frontend and a FastAPI
backend that owns all secrets, external calls, analysis, and persistence.

```mermaid
flowchart TD
    subgraph Browser["Browser (React + TS + Vite + Tailwind)"]
        L["Landing page"]
        W["Workspace / Dashboard / Report pages"]
        C["Typed API layer (src/services/api.ts)"]
    end

    subgraph Backend["FastAPI backend (Python)"]
        API["API routes (app/api/routes.py)"]
        RL["Rate limiter"]
        PIPE["Research pipeline (app/services/analysis_pipeline.py)"]
        SERP["SerpApi search service"]
        EXT["Source extraction (SSRF-protected)"]
        AI["AI adapters: openai_compatible / anthropic"]
        BASIC["Deterministic basic analysis"]
        TRENDS["Trend discovery + scoring"]
        CITE["Citation validation"]
        EXP["Markdown / JSON export"]
        SEC["security: ssrf, ratelimit, sanitize"]
    end

    DB[("SQLite (research + saved_topic)")]
    SERPAPI[("SerpApi")]:::ext
    WEB[("Public web pages")]:::ext
    LLM[("AI provider")]:::ext

    L --> C
    W --> C
    C -->|"VITE_API_BASE_URL"| API
    API --> RL --> PIPE
    PIPE --> SERP --> SERPAPI
    PIPE --> EXT --> WEB
    PIPE --> AI --> LLM
    PIPE --> BASIC
    PIPE --> TRENDS
    PIPE --> CITE
    PIPE --> DB
    API --> EXP
    SEC -.-> API
    EXP --> C

    classDef ext fill:#1a2242,stroke:#8b6cff,color:#dde3f2
```

## Research pipeline sequence

```mermaid
sequenceDiagram
    participant U as User
    participant F as Frontend
    participant A as API routes
    participant S as Search service
    participant E as Extraction
    participant X as AI adapter / Basic
    participant V as Citation validation
    participant D as SQLite

    U->>F: Enter topic + filters
    F->>A: POST /api/research
    A->>A: Validate input, check rate limit, create pending record
    A->>S: Query (SerpApi live OR demo data)
    S-->>A: Normalized results
    A->>E: Extract top N pages (SSRF-validated, best effort)
    E-->>A: Page text or fallback status
    A->>X: Bounded evidence package
    X-->>A: Structured report (or fallback to basic mode)
    A->>V: Verify every citation against collected sources
    V-->>A: Cleaned report
    A->>D: Store record + report
    A-->>F: ResearchRecord
    F->>F: Render report, charts, citations
```

## Layers

| Layer | Location | Responsibility |
|---|---|---|
| UI | `frontend/src/pages`, `components` | Presentation only; no direct `fetch` |
| API client | `frontend/src/services/api.ts` | Typed HTTP, timeouts, error mapping |
| Types | `frontend/src/types/api.ts` | Mirrors backend Pydantic schemas |
| Routes | `backend/app/api/routes.py` | Validation, rate limiting, error envelope |
| Pipeline | `backend/app/services/analysis_pipeline.py` | Orchestrates search → extraction → analysis → validation |
| Search | `backend/app/services/search_service.py` | SerpApi integration + normalization |
| Extraction | `backend/app/services/extraction_service.py` | SSRF-safe fetching + HTML → text |
| AI | `backend/app/services/ai/` | Provider adapters + prompts |
| Analysis | `basic_analysis.py`, `trends.py`, `citations.py` | Fallback mode, themes/scoring, citation checks |
| Persistence | `backend/app/database/` | SQLite, parameterized queries, repositories |
| Security | `backend/app/security/` | SSRF validation, rate limiting, secret redaction |

## Key design decisions

1. **Search and analysis are separate services.** The AI step never performs
   searches; it only consumes the bounded evidence package. This keeps external
   calls predictable, testable, and cheap.
2. **Fail open to evidence, closed to fabrication.** If AI analysis fails, the
   run falls back to deterministic basic mode with search results preserved. If
   search fails, the run fails with a clear message — nothing is invented.
3. **One repair attempt, then fallback.** Structured output is validated;
   at most one repair call is made. No retry loops against paid APIs.
4. **Citations are data, not text.** Source IDs are validated against collected
   sources before storage; the frontend can only link to what exists.
5. **Secrets stay server-side.** The frontend reads only boolean configuration
   flags from `/api/config/status`; no `VITE_` variable ever holds a secret.
6. **Demo mode is structurally visible.** Mock data uses reserved domains,
   `[DEMO]` titles, and a distinct badge — it cannot be mistaken for live data.

## Data model (SQLite)

```mermaid
erDiagram
    RESEARCH {
        text id PK
        text query
        text created_at
        text search_mode "live | demo"
        text ai_mode "llm | basic"
        text status "pending | completed | failed"
        int result_count
        text filters_json
        text results_json
        text report_json
        text error_message
    }
    SAVED_TOPIC {
        text id PK
        text topic "UNIQUE"
        text created_at
    }
```

Schema is created idempotently at startup (`CREATE TABLE IF NOT EXISTS`) —
documented initialization strategy with no external migration tool required.

## Error contract

All error responses share one shape:

```json
{ "error": { "code": "rate_limited", "message": "…user-facing…", "details": {} } }
```

Codes are stable strings (`validation_error`, `search_not_configured`,
`rate_limited`, `not_found`, `payload_too_large`, `internal_error`, …).
Stack traces and secrets never reach the client; full tracebacks go to
server-side logs only.

## Trust boundaries

- **Untrusted:** search results, webpage content, AI output, user queries.
  All are validated/sanitized before use.
- **Trusted:** environment configuration, application code, database contents
  written by the backend itself.
- **No code execution:** neither model output nor scraped content is ever
  executed; extraction uses a parser, not a browser.
