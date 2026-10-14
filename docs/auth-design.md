# Authentication & Per-User Isolation — Design (Not Implemented)

**Status:** designed only. TrendMind AI v1 is a single-instance workspace:
every user of an instance sees the same history and saved topics. This
document captures the agreed design so a future version can implement it
without re-deciding the architecture. Implementing it was explicitly deferred.

## Goals

1. **Per-user isolation** — history, saved topics, and report access must be
   scoped to the authenticated owner.
2. **Server-side authorization on every private record** — the frontend must
   never be the only gate; each API read/delete checks ownership.
3. **Zero data loss on migration** — existing instance data stays readable.
4. **No behavior change when disabled** — `AUTH_ENABLED=false` (default in v1)
   keeps the current shared-workspace behavior exactly.

## Recommended model: server-side sessions (not JWT)

| Decision | Choice | Rationale |
|---|---|---|
| Credential | Email + password | No third-party dependency; fits single-instance deployments |
| Password hashing | Argon2id (fallback bcrypt) | Memory-hard; current best practice |
| Session | Opaque random token in an **httpOnly, SameSite=Lax, Secure** cookie | Instant revocation via server-side row; no token leakage to JS; no CSRF-prone Authorization header |
| Session store | `sessions` table in the same SQLite DB | Same operational footprint as today |
| Brute-force control | Reuse the existing sliding-window limiter on `/api/auth/login` (e.g. 5/min per client) + exponential backoff per account | The rate limiter already exists and is tested |

JWT was considered and rejected for v1-scale deployments: revocation and
session listing are harder, and the app has no multi-service topology that
would benefit from stateless tokens.

## Proposed schema (additive migration)

```sql
CREATE TABLE IF NOT EXISTS users (
  id            TEXT PRIMARY KEY,          -- hex id, same style as research.id
  email         TEXT NOT NULL UNIQUE,      -- lowercased
  password_hash TEXT NOT NULL,             -- argon2id string
  created_at    TEXT NOT NULL              -- UTC ISO-8601
);

CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,             -- sha256(token); raw token only in cookie
  user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);

-- Additive owner columns; NULL = legacy instance-scoped record.
ALTER TABLE research ADD COLUMN owner_id TEXT REFERENCES users(id);
ALTER TABLE topics    ADD COLUMN owner_id TEXT REFERENCES users(id);
```

**Legacy data:** rows with `owner_id IS NULL` remain visible to every
authenticated user (instance scope) or are claimed by the first registered
admin during a one-time migration — a deployment decision, not a code one.

## Proposed API surface

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/auth/register` | Create account (rate-limited; password policy: min 12 chars) |
| POST | `/api/auth/login` | Start session; sets httpOnly cookie |
| POST | `/api/auth/logout` | Delete session row, clear cookie |
| GET | `/api/auth/me` | Current user (email only; no hashes, no other users) |

Every existing private endpoint (`/api/research*`, `/api/topics*`,
`/api/reports/*`) gains a `get_current_user` dependency that:

1. reads the session cookie,
2. hashes it and looks up a non-expired `sessions` row,
3. injects `user_id`,
4. passes it into the repository layer, which adds `AND owner_id = ?`
   to every SELECT/DELETE (list queries included, so counts and pagination
   stay honest per user).

With `AUTH_ENABLED=false`, the dependency resolves to a synthetic
instance-scoped principal and queries stay unfiltered — behavior identical to
today.

## Security checklist for the implementation PR

- Cookie flags: `HttpOnly`, `SameSite=Lax`, `Secure` (when served over TLS),
  `Path=/`, short expiry (e.g. 14 days) with sliding refresh.
- CSRF: state-changing requests require a custom header (`X-Requested-With`)
  or a double-submit token; SameSite=Lax already blocks cross-site POSTs in
  modern browsers.
- Login/register responses are constant-time-ish and never reveal whether an
  email exists.
- Session tokens are 256-bit random, stored **hashed**; logout and password
  changes revoke all sessions for the user.
- No secrets in logs (existing redaction patterns extended to `password`,
  `token`, `session`).
- Tests: ownership enforcement (user B cannot GET/DELETE user A's record),
  expired-session handling, login rate limiting, `AUTH_ENABLED=false`
  regression parity.

## Explicitly out of scope (for the implementation)

- Email verification, password reset via email, OAuth/SSO, MFA, org/team
  management. These can layer on the same session table later.
