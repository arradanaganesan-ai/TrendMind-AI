# TrendMind AI — The Web Intelligence Engine

**Search the web. Discover patterns. Understand what matters.**

TrendMind AI is an AI-powered web research and trend intelligence platform.
Enter a topic, question, technology, industry, or emerging trend — the platform
retrieves web search results, organizes evidence, identifies recurring themes,
compares source claims, and presents a structured intelligence report with
validated citations.

---

When evidence is insufficient, reports say so explicitly.

## Implementation checklist

All phases completed and verified — see [Running tests](#running-tests) for the
current results.

- [x] **Phase 1 — Foundation:** structure, dependencies, design system, landing page + dashboard shell, frontend builds
- [x] **Phase 2 — UI:** navigation + mobile drawer, search form with filters, result/theme cards, loading/error/empty states, labeled demo data, responsive layouts, 4 component tests
- [x] **Phase 3 — Backend:** FastAPI, env config, SQLite persistence, validated routes, health/config endpoints, tests run (**126 passed**)
- [x] **Phase 4 — SerpApi:** search service, tolerant normalization, full error handling (missing key/timeout/rate limit/empty/API errors), mocked tests, demo mode
- [x] **Phase 5 — Analysis:** openai_compatible + anthropic adapters, bounded evidence package, strict schema, citation verification with exactly one repair attempt, basic-mode fallback, malformed-output tests
- [x] **Phase 6 — Trends:** theme discovery, documented scoring formula, evidence coverage, Recharts on real data, snapshot labeling
- [x] **Phase 7 — History & reports:** history with pagination/deletion, saved topics, 12-section report page, Markdown/JSON export, persistence verified
- [x] **Phase 8 — Security & QA:** validation/error handling, SSRF test suite, secret-handling review, backend **126 passed**, frontend tsc + eslint + vitest **4/4** + build all pass
- [x] **Phase 9 — Docs & deployment:** README, methodology/architecture/deployment docs, Vercel config, local-run checklist, honest limitations

### Upgrade session (2026 — current state)

- [x] **Phase 2 — Premium UI/UX:** CSS-variable design tokens, **light + dark theme** with persisted toggle, redesigned landing/dashboard/report surfaces, AppShell focus-trap drawer, micro-interactions, `animate-fadeUp`, print stylesheet
- [x] **Phase 3 — Research workflow honesty:** SSE progress streaming (`/api/research/stream`) with real pipeline stages, query validation, per-source **extraction-status badges** (`blocked` / `failed` / `skipped` + user-safe notes), **uncited-finding flags**, evidence-class labeling (retrieved / interpretation / hypothesis)
- [x] **Phase 4 — Features:** PDF export (reportlab) + Print button + print CSS · report **comparison** (`/compare`) · **Evidence Explorer** (sources ↔ claims both directions) · History **date filters** (server-side) · real **activity-over-time** chart from existing DB rows · auth **deferred** (design in [`docs/auth-design.md`](docs/auth-design.md))
- [x] **Phase 5 — Quality:** dead-code cleanup, duplicated dashboard metrics fixed, backend **142 passed** (3× consecutive), frontend tsc + eslint + vitest **5/5** + build all pass, browser-verified in both themes
- [x] **Phase 6 — Historical trend tracking:** tracked topics, dated snapshots derived from real stored runs, consecutive-snapshot change detection with an explicit absence caveat, history chart, optional bounded AI summary with transparent basic-mode fallback (`/trends`)
- [x] **Phase 7 — Release-readiness audit:** navigation verified (Compare added to the sidebar; header titles for `/compare` + `/trends`), dashboard now surfaces **real tracked-topic status + latest detected changes** (independent failure isolation), loading/empty/error/responsive/theme/focus states audited, DB init verified additive for existing data, secrets audit clean, README brought up to date — backend **237 passed**, frontend tsc + eslint + vitest **28/28** + build all pass

## Problem statement

Web research today is fragmented: results are scattered across tabs, snippets
lack context, sources contradict each other without resolution, and AI tools
frequently invent statistics or citations. Analysts, students, and engineers
need a way to move from a raw query to a *structured, evidence-linked* report —
one that is honest about what is known, what is interpreted, and what remains
unverified.

## Proposed solution

TrendMind AI runs a transparent research pipeline:

1. **Collect** normalized search results (SerpApi) — or clearly labeled demo
   data when no key is configured.
2. **Extract** readable content from publicly accessible pages through an
   SSRF-protected fetcher — falling back to snippets when pages are blocked.
3. **Analyze** a bounded evidence package with a configurable AI provider — or
   a deterministic, clearly labeled basic mode when no AI is configured.
4. **Validate** every citation against the sources actually collected, then
   **store** and render the report with charts computed from real data.

---

## Main features

- **Landing page** with hero research input, example topics, capabilities,
  product preview, methodology, and footer links.
- **Light + dark theme** — CSS-variable design tokens, persisted toggle
  (system preference honored, no flash of wrong theme).
- **Live progress** — the research workspace streams honest pipeline stages
  (searching → extracting → analyzing → validating) from the backend over
  SSE; each stage appears only when it actually runs.
- **Intelligence dashboard** — recent research, saved topics, **tracked-topic
  status with the latest detected trend changes** (real snapshot counts and
  change intervals from this instance's database, never invented), real
  activity counts, and a 30-day **activity-over-time** chart (zero-filled from
  real rows).
- **Research workspace** — validated query + filters (category, region,
  language, time range, result count), loading/error/empty states.
- **SerpApi live search** from the backend only; key never reaches the browser.
- **Demo mode** with mock data on reserved `example.com` domains, `[DEMO]`
  titles, and an amber badge — never mistaken for live information.
- **SSRF-protected source extraction** (DNS checks, redirect re-validation,
  timeouts, size caps, robots.txt, HTML-only, no JS execution).
- **AI analysis** with strict structured output, prompt-injection defenses,
  and **exactly one** repair attempt before falling back.
- **Deterministic basic analysis** fallback — labeled as non-AI everywhere.
- **Trend discovery** — themes, recurring terms, conflicts, and gaps with a
  documented 0–100 evidence-strength formula.
- **Intelligence reports** — 13 sections from research question to
  methodology, with clickable citations that can only point at collected
  sources; findings without a supporting source are flagged, not hidden.
- **Evidence Explorer** — every collected source shows the exact claims it
  supports; every claim links back to its sources; retrieval state
  (`extracted` / `blocked` / `failed` / `skipped`) and user-safe notes are
  shown per source.
- **Report comparison** — pick any two stored runs (`/compare`) for a
  side-by-side of metrics, shared sources (exact-URL overlap), and theme
  overlap, all computed from the records themselves.
- **Historical trend tracking** (`/trends`) — track any research query and
  follow it across **dated snapshots derived from real stored runs** (no
  fabricated history): a history chart once ≥2 snapshots exist, deterministic
  change detection between consecutive snapshots (newly observed / no longer
  observed / source-coverage and theme-strength deltas), date filters,
  snapshot details with source links, an explicit caveat that **absence from
  a newer search is not proof a finding is false**, and an optional one-call
  AI summary that falls back to a clearly labeled basic analysis.
- **Interactive analytics** — theme distribution, source distribution, evidence
  coverage (Recharts; real data only; accessible descriptions; empty states).
- **Research history** with pagination, deletion, and **date filters**
  (presets + custom range, applied server-side); **saved topics** with
  add/remove.
- **Report export** — server-rendered **PDF** (reportlab), **Print** (with a
  print-optimized stylesheet that forces light output), Markdown, and JSON —
  all with safe filenames and escaped content.
- **Settings** — search defaults, theme preference, configuration status
  (booleans only, no secrets), privacy explanation.
- **Accessible UI** — semantic HTML, visible focus states, keyboard navigation,
  Escape-closing dialogs/drawers, `prefers-reduced-motion` support, responsive
  from mobile to desktop.

---

## Architecture overview

```mermaid
flowchart TD
    subgraph FE["Frontend — React + TypeScript + Vite + Tailwind"]
        P["Pages: Landing, Dashboard, Research, Report, History, Compare, Trends, Topics, Settings, About"]
        API["Typed API layer (src/services/api.ts)"]
    end
    subgraph BE["Backend — FastAPI"]
        R["Routes + validation + rate limiting"]
        PIPE["Research pipeline"]
        S["SerpApi service"]
        X["SSRF-safe extraction"]
        A["AI adapters (openai_compatible / anthropic)"]
        B["Basic analysis fallback"]
        T["Trend discovery + scoring"]
        V["Citation validation"]
    end
    DB[("SQLite")]
    EXT[("SerpApi · Web pages · AI provider")]:::ext

    P --> API --> R --> PIPE
    PIPE --> S & X & A & B --> T --> V --> DB
    R --> EXT
    classDef ext fill:#1a2242,stroke:#8b6cff,color:#dde3f2
```

Detailed diagrams: [`docs/architecture.md`](docs/architecture.md).

## Technology stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite 6, Tailwind CSS 3, React Router 6, Recharts, Lucide icons |
| Frontend QA | tsc, ESLint (flat config), Vitest + Testing Library |
| Backend | Python 3.13, FastAPI, Pydantic 2, httpx, uvicorn |
| Persistence | SQLite (parameterized queries, idempotent schema) |
| Search | SerpApi Search API (backend-only) |
| AI | OpenAI-compatible chat completions + Anthropic Messages (optional) |
| Testing | pytest, pytest-asyncio, httpx MockTransport (no live credits) |

## Project structure

```
TrendMind-AI/
├── README.md
├── .gitignore                  # .env, secrets, build output ignored
├── .env.example                # placeholders only
├── docs/
│   ├── architecture.md
│   ├── auth-design.md           # deferred auth: full design, not implemented
│   ├── methodology.md
│   └── deployment.md
├── frontend/
│   ├── package.json / vite.config.ts / tsconfig*.json
│   ├── tailwind.config.js      # design tokens
│   ├── eslint.config.js
│   ├── vercel.json             # SPA rewrite
│   ├── .env.example            # VITE_ vars (no secrets, ever)
│   └── src/
│       ├── main.tsx / App.tsx
│       ├── components/  (layout, ui, search, results, report, charts)
│       │   └── ui/ThemeProvider.tsx   # light/dark tokens, persisted
│       ├── pages/       (Landing, Dashboard, NewResearch, ReportPage,
│       │                 History, Compare, Trends, SavedTopics, Settings, About)
│       ├── hooks/       (useToast, useConfigStatus)
│       ├── services/    (api.ts — the only fetch layer, incl. SSE parsing)
│       ├── types/       (api.ts — mirrors backend schemas)
│       ├── styles/      (index.css — design system)
│       └── test/        (Vitest component tests, mocked API)
└── backend/
    ├── requirements.txt
    ├── app/
    │   ├── main.py             # app factory, CORS, error handlers, logging
    │   ├── config.py           # env-based settings (no secrets logged)
    │   ├── api/routes.py       # all endpoints
    │   ├── schemas/            # Pydantic contract
    │   ├── services/
    │   │   ├── search_service.py      # SerpApi
    │   │   ├── demo_data.py           # labeled mock results
    │   │   ├── extraction_service.py  # SSRF-protected fetch
    │   │   ├── html_to_text.py        # stdlib HTML → text
    │   │   ├── analysis_pipeline.py   # orchestration
    │   │   ├── basic_analysis.py      # deterministic fallback
    │   │   ├── trends.py              # themes + scoring formula
    │   │   ├── comparison.py          # run-vs-run comparison
    │   │   ├── trend_tracking.py      # dated snapshots + change detection
    │   │   ├── citations.py           # citation validation
    │   │   ├── export.py              # Markdown / JSON
    │   │   ├── pdf_export.py              # server-rendered PDF (reportlab)
    │   │   └── ai/                    # adapters + prompts
    │   ├── database/           # db.py, repository.py
    │   └── security/           # ssrf.py, ratelimit.py, sanitize.py
    └── tests/                  # 237 tests, all externals mocked
```

---

## Prerequisites

- **Node.js 20+** and npm (verified on Node 24)
- **Python 3.11+** and pip (verified on 3.13)
- Optional: SerpApi key (live search), AI provider key (LLM analysis)

## Local installation

### 1. Backend

```bash
cd backend
pip install -r requirements.txt
```

### 2. Frontend

```bash
cd frontend
npm install
```

### 3. Environment

```bash
cp .env.example .env          # backend secrets (git-ignored)
cp frontend/.env.example frontend/.env.local   # VITE_ vars (no secrets)
```

## Frontend setup

```bash
cd frontend
npm run dev          # http://localhost:5173
```

Scripts: `npm run dev` · `npm run build` · `npm run typecheck` ·
`npm run lint` · `npm test`.

## Backend setup

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

- API docs: `http://localhost:8000/api/docs`
- Health: `GET /api/health`
- Config status: `GET /api/config/status`

---

## Environment variables

### Backend (`.env` at repo root — **never commit**)

| Variable | Default | Purpose |
|---|---|---|
| `HOST` / `PORT` | `0.0.0.0` / `8000` | Server bind |
| `CORS_ORIGINS` | `http://localhost:5173,…` | Comma-separated allowed origins |
| `DATABASE_PATH` | `./data/trendmind.db` | SQLite file location |
| `SERPAPI_API_KEY` | *(empty)* | **Live search.** Empty ⇒ Demo Mode |
| `SERPAPI_ENGINE` | `google` | SerpApi engine |
| `SEARCH_TIMEOUT_SECONDS` | `10` | Search request timeout |
| `MAX_RESULTS_LIMIT` | `20` | Server-side result cap |
| `MAX_QUERY_LENGTH` | `300` | Query character cap |
| `ENABLE_SOURCE_EXTRACTION` | `true` | Page fetching (SSRF-protected) |
| `MAX_EXTRACT_PAGES` | `3` | Pages fetched per run |
| `EXTRACT_TIMEOUT_SECONDS` | `8` | Per-page timeout |
| `MAX_PAGE_BYTES` | `1500000` | Response size cap |
| `MAX_EXTRACT_CHARS` | `12000` | Extracted text cap per page |
| `AI_PROVIDER` | `none` | `none` \| `openai_compatible` \| `anthropic` |
| `AI_MODEL` | *(empty)* | Model name (required for AI mode) |
| `AI_API_KEY` | *(empty)* | Provider key (never exposed) |
| `AI_BASE_URL` | OpenAI v1 | Any OpenAI-compatible endpoint |
| `AI_TIMEOUT_SECONDS` | `45` | AI request timeout |
| `AI_MAX_EVIDENCE_CHARS` | `24000` | Evidence package cap |
| `RESEARCH_RATE_LIMIT_PER_MINUTE` | `6` | Per-client limit on `POST /api/research` |
| `GITHUB_REPO_URL` | *(empty)* | Footer/About repository link |

### Frontend (`frontend/.env.local` — **no secrets, ever**)

| Variable | Purpose |
|---|---|
| `VITE_API_BASE_URL` | Backend base URL (e.g. `http://localhost:8000`) |
| `VITE_APP_VERSION` | Displayed application version |
| `VITE_GITHUB_REPO_URL` | Optional footer/About link |

> Anything prefixed `VITE_` is embedded in the browser bundle. Server secrets
> (SerpApi, AI keys) **must never** be placed there.

## SerpApi setup

1. Create a key at [serpapi.com](https://serpapi.com) (free tier available).
2. Add `SERPAPI_API_KEY=your_key` to `.env`.
3. Restart the backend. `/api/config/status` now reports
   `"serpapiConfigured": true` and `"searchMode": "live"`.
4. Leave it empty to stay in **Demo Mode** (no credits consumed).

## AI provider setup

**OpenAI-compatible** (OpenAI, OpenRouter, Groq, local gateways):

```bash
AI_PROVIDER=openai_compatible
AI_MODEL=gpt-4o-mini
AI_API_KEY=sk-...
AI_BASE_URL=https://api.openai.com/v1
```

**Anthropic:**

```bash
AI_PROVIDER=anthropic
AI_MODEL=claude-sonnet-4-5
AI_API_KEY=sk-ant-...
```

**No AI (default):** `AI_PROVIDER=none` — reports are produced by the
deterministic basic analysis and labeled **Basic analysis** in the UI. The app
remains fully functional.

## Demo mode

Demo mode activates automatically when `SERPAPI_API_KEY` is unset (or can be
forced by leaving it empty). Characteristics:

- Results use reserved `example.com/.org/.net` domains with `[DEMO]` titles.
- The API stamps `mode: "demo"`; the UI shows an amber **Demo data** badge.
- The full pipeline (themes, charts, report, export) runs on mock data —
  ideal for development and demos without consuming credits.

---

## Running tests

### Backend (externals mocked — no live API calls)

```bash
cd backend
python -m pytest tests/ -q
```

**Result: 237 passed** covering: health/config endpoints, input validation,
missing SerpApi key, search normalization (valid/malformed/empty), API error
mapping (timeout, 429, auth, unreadable), citation validation, trend analysis
and scoring, database persistence (incl. date-filtered listing and the
zero-filled activity series), report generation/export (Markdown, JSON, PDF),
extraction-status propagation to `SourceRef`, SSE stream endpoints, SSRF URL
validation, source-extraction restrictions, HTML extraction, AI malformed-output
handling (one repair attempt then fallback), prompt-injection containment,
rate limiting, run-vs-run comparison, and **historical trend tracking**
(snapshot storage from real runs, chronological ordering, change detection,
absence caveats, AI-summary fallback, trends API validation).

### Frontend

```bash
cd frontend
npm run typecheck     # tsc — passed
npm run lint          # eslint — passed
npm test              # vitest — 28 passed (API mocked)
npm run build         # production build — passed
```

---

## API reference

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Liveness + version |
| GET | `/api/config/status` | Feature flags (booleans only, no secrets) |
| POST | `/api/research` | Run a research query (rate-limited) |
| POST | `/api/research/stream` | Same, as SSE: honest progress stages + final record |
| GET | `/api/research?limit&offset&date_from&date_to` | History list with pagination and optional UTC date filters (YYYY-MM-DD) |
| GET | `/api/research/{id}` | Full record + report |
| DELETE | `/api/research/{id}` | Delete a record |
| GET | `/api/stats` | Real workspace counters (this instance only) |
| GET | `/api/stats/activity?days` | Daily run counts, zero-filled (1–365 days) |
| GET | `/api/topics` | Saved topics |
| POST | `/api/topics` | Save a topic |
| DELETE | `/api/topics/{id}` | Remove a topic |
| GET | `/api/reports/{id}/markdown` | Markdown export (attachment) |
| GET | `/api/reports/{id}/json` | JSON export (attachment) |
| GET | `/api/reports/{id}/pdf` | PDF export (attachment, reportlab) |
| GET | `/api/compare?a&b&mode` | Side-by-side comparison of two stored runs |
| GET | `/api/compare/markdown?a&b` | Comparison as Markdown (attachment) |
| GET | `/api/compare/json?a&b` | Comparison as JSON (attachment) |
| GET | `/api/compare/pdf?a&b` | Comparison as PDF (attachment) |
| GET | `/api/trends` | Tracked topics with real snapshot counts |
| GET | `/api/trends/candidates` | Queries with completed runs (for the tracking picker) |
| POST | `/api/trends` | Start tracking a query (422 unless ≥1 completed run exists) |
| GET | `/api/trends/{id}?dateFrom&dateTo&mode` | Dated snapshots + consecutive change detection (`mode`: `basic` \| `auto`) |
| DELETE | `/api/trends/{id}` | Stop tracking a topic |

Errors always return:
`{"error": {"code": "...", "message": "user-facing text", "details": {...}}}`

---

## Troubleshooting

| Symptom | Cause & fix |
|---|---|
| "Live search is not configured yet…" | Set `SERPAPI_API_KEY` in `.env` and restart, or stay in Demo Mode. |
| Frontend "Could not reach the TrendMind backend" | Backend not running or wrong `VITE_API_BASE_URL`. Start uvicorn; check `/api/health`. |
| CORS error in browser console | `CORS_ORIGINS` must include your exact frontend origin (no trailing slash). |
| "Search capacity has temporarily been reached" | SerpApi quota/rate limit or the app's own limit. Wait, or raise `RESEARCH_RATE_LIMIT_PER_MINUTE`. |
| Report says "Basic analysis" though AI key set | `AI_MODEL` missing, or `AI_PROVIDER` unrecognized. Check `/api/config/status` → `aiConfigured`. |
| Empty results | Query too narrow. Broaden it or change filters — the app reports this explicitly. |
| "This source could not be accessed…" | Page blocked/timeout; the report correctly uses the search snippet and says so. |
| Tables empty after redeploy | SQLite on ephemeral storage — use a persistent `DATABASE_PATH` (see deployment docs). |
| `npm run build` fails on type check | Run `npm run typecheck` to see errors; ensure `npm install` completed. |

## Deployment

See [`docs/deployment.md`](docs/deployment.md) for Vercel (frontend) + a Python
host (backend), including SPA rewrites, environment configuration, SQLite
persistence, and a post-deploy verification checklist.

**Deployment is not claimed to be live** — no deployment has been performed
from this environment. Follow the checklist in the doc to deploy and verify.

## Security notes

- **Secrets:** environment-only; `.env` is git-ignored; `.env.example` has
  placeholders; logs redact `api_key/token/secret/password` patterns; errors
  never include stack traces or credentials.
- **SSRF:** http(s)-only, credential-URL rejection, localhost/internal-suffix
  blocking, DNS resolution with private/loopback/link-local/CGNAT/IPv6-internal
  checks, per-hop redirect re-validation (max 3), port allow-list, byte caps,
  timeouts, HTML content types only, **no JavaScript execution**, robots.txt
  respected, no paywall/auth bypass.
- **Prompt injection:** retrieved content is delimited and declared untrusted;
  instructions inside it are ignored; no tools/code execution exist in the
  analysis step; AI-generated URLs are never fetched without full SSRF checks.
- **Input validation:** Pydantic schemas with allow-listed filter values,
  length caps, and a 64 KB request-size limit.
- **Rate limiting:** sliding-window limiter on `POST /api/research`.
- **CORS:** explicit origin allow-list (never `*` by default), no credentials.
- **Output escaping:** Markdown exports escape HTML/`|`; the frontend renders
  text as text (no `dangerouslySetInnerHTML` anywhere).
- **Dependency hygiene:** small, stable dependency set (no scraping frameworks,
  no headless browsers).

## Limitations

- **No authentication.** History and saved topics are shared across the
  instance and are **not private per user**. A complete design (sessions,
  per-record authorization, additive migration) is documented in
  [`docs/auth-design.md`](docs/auth-design.md) — deliberately not implemented
  in v1.
- **Snapshot analysis.** One search cannot establish trends over time; findings
  are phrased as themes observed in the collected results. The activity chart
  tracks *research runs* from real database rows — it is not a web-trend time
  series.
- **Demo domains.** Demo links point to reserved `example.*` pages by design.
- **AI-dependent sections.** Opportunities/developments are sparse in basic
  mode (deliberately — it does not fabricate interpretation).
- **Rate limiter is per-process/in-memory** — multi-worker deployments multiply
  the effective limit.
- **Some sites block extraction** (JS-rendered, bot-protected, paywalled);
  these degrade to snippet analysis and are labeled as such per source.
- **Report comparison matches sources by exact URL** — the same article on two
  different URLs counts as two sources.
- **PDF rendering uses system fonts when available** (Arial/DejaVu); exotic
  scripts may transliterate to Latin-1 on systems without Unicode TTFs.

## Future improvements

- Implement the designed authentication layer
  ([`docs/auth-design.md`](docs/auth-design.md)) with server-side
  authorization on every private record.
- Scheduled snapshot collection for genuine web-trend time series (the current
  activity chart covers research-run history only).
- User-managed extraction allow/deny lists and per-domain concurrency limits.
- Richer keyboard shortcuts in the research workspace.
- External database adapter (Postgres) behind the repository layer.
- Per-source reliability scoring — only with a transparent, documented formula
  (consistent with the existing evidence-strength methodology).

## Recording a demo

1. `cp .env.example .env` — leave `SERPAPI_API_KEY` empty (Demo Mode) or add a
   real key for live search.
2. Start backend: `cd backend && uvicorn app.main:app --reload --port 8000`.
3. Start frontend: `cd frontend && npm run dev`.
4. Open `http://localhost:5173` and record:
   - Landing page → hero input → example topic chip → research runs.
   - Demo badge visible; results cards with links; **Open full report**.
   - Report sections, citations, theme cards, three charts.
   - Export Markdown / JSON.
   - History pagination + delete; saved topics add/remove; Settings status.
   - Mobile layout via dev-tools responsive mode (drawer navigation).
5. Optional: show `npm test` and `python -m pytest tests/ -q` output to
   demonstrate mocked, credit-free tests.

---

## License

All rights reserved © 2026 TrendMind AI.
