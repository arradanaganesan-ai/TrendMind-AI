# Deployment — TrendMind AI

Frontend and backend are deployed **separately** — they do not share an
environment. Never commit API keys.

---

## 1. Backend (Python / ASGI)

Any host that runs a long-lived Python process with a writable disk works:
a VPS, Render, Railway, Fly.io, Hugging Face Spaces (Docker), or a container
platform.

### Requirements
- Python 3.11+ (verified on 3.13)
- Writable disk for SQLite (see persistence notes below)

### Steps

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Configure secrets via environment (NEVER commit these)
export SERPAPI_API_KEY=...          # live search; leave empty for Demo Mode
export AI_PROVIDER=openai_compatible # or anthropic / none
export AI_MODEL=gpt-4o-mini
export AI_API_KEY=...
export CORS_ORIGINS=https://your-frontend.vercel.app
export DATABASE_PATH=/data/trendmind.db

uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

- **ASGI server:** `uvicorn` (production; `--workers 1` recommended — see
  rate limiter notes).
- **Health check:** `GET /api/health` → `{"status":"ok",…}`.
- **CORS:** set `CORS_ORIGINS` to your exact frontend origin(s). The default
  only allows `http://localhost:5173`.
- **Docs:** `GET /api/docs` (Swagger UI). Disable by running behind a proxy
  that blocks it if your policy requires.

### Environment variables
All backend variables are documented in `.env.example` at the repository root
and in the README. The server reads `.env` from the repo root or `backend/.env`.

---

## 2. Frontend (Vite → static SPA)

### Build

```bash
cd frontend
npm install
echo "VITE_API_BASE_URL=https://api.yourdomain.com" > .env.local
npm run build        # outputs frontend/dist
```

`VITE_API_BASE_URL` must be set at **build time** — there is no hardcoded
localhost fallback for production builds beyond the dev default.

### Vercel

1. Import the repo, set **Root Directory** to `frontend`.
2. Framework preset: **Vite** (auto-detected).
   - Build command: `npm run build`
   - Output directory: `dist`
3. Add env var `VITE_API_BASE_URL=https://your-backend-domain` (Production and
   Preview).
4. **SPA rewrite** (required so deep links like `/report/abc` resolve):
   add `vercel.json` in `frontend/`:

   ```json
   { "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }] }
   ```

5. Deploy. Verify a deep link (`/about`) loads the SPA and `/api/health`
   from the frontend origin (CORS must allow it).

### Netlify equivalent
Build `npm run build`, publish `frontend/dist`, and add
`/*  /index.html   200` to `_redirects`.

---

## 3. Database persistence (SQLite)

SQLite is a single file chosen for zero-ops persistence. **Important:**

- On hosts with **ephemeral filesystems** (serverless functions, some free
  tiers), the database file is **lost on every redeploy/restart** unless you:
  - mount a **persistent disk** and point `DATABASE_PATH` at it, **or**
  - migrate to an external database (Porter, Turso, managed Postgres) by
    replacing `app/database/db.py` — the repository layer isolates all SQL.
- Recommended: any host with a persistent volume (`DATABASE_PATH=/data/trendmind.db`).
- WAL mode is enabled; keep `--workers 1` because the rate limiter is
  in-process (multi-worker deployments need a shared store — see Limitations).

---

## 4. Verifying a deployment

Run these after deploying; do not consider a deployment successful without them:

```bash
# Backend
curl https://api.yourdomain.com/api/health
curl https://api.yourdomain.com/api/config/status   # confirms key flags

# Frontend
open https://your-frontend.vercel.app/              # landing renders
# From the UI: run a research query, open the report, export Markdown.

# CORS sanity: the frontend network tab must show 200s, not CORS errors.
```

**Demo-mode check:** with `SERPAPI_API_KEY` unset, `/api/config/status` returns
`"demoMode": true` and the UI must show the amber **Demo data** badge.

---

## 5. Security checklist for deployment

- [ ] `.env` is **not** committed (`.gitignore` covers it) and exists only on
      the server / host secret manager.
- [ ] `SERPAPI_API_KEY` and `AI_API_KEY` are set as environment secrets, never
      in frontend env vars, never in the repo.
- [ ] `CORS_ORIGINS` lists only your real frontend origin(s) — no `*`.
- [ ] HTTPS enforced at the proxy/CDN.
- [ ] `/api/docs` blocked if not needed publicly.
- [ ] `DATABASE_PATH` points to a persistent, non-public location with
      restricted permissions.
- [ ] Rate limit (`RESEARCH_RATE_LIMIT_PER_MINUTE`) set to a sane value.
- [ ] Backend logs checked to confirm no keys appear (log redaction is built in,
      but verify).

---

## 6. Honest limitations of this deployment target

- Research history is **not private per user** — no authentication exists in
  v1; anyone with URL access shares one history.
- The rate limiter is **per-process, in-memory** — with multiple workers or
  replicas the effective limit multiplies.
- SQLite single-file writes serialize under heavy concurrency; fine for a
  portfolio/hackathon load, not for many concurrent users.
- Source extraction makes outbound HTTP requests from your server — expect some
  sites to block your IP or require JS rendering (these degrade to snippets).

See `README.md` → *Limitations* for the full list, and `docs/methodology.md`
for analysis constraints.
