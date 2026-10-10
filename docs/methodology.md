# Methodology — TrendMind AI

This document describes exactly how TrendMind AI collects evidence, extracts
content, identifies themes, scores evidence strength, and validates citations —
plus the inherent limitations of snapshot-based analysis.

---

## 1. Search collection

**Service:** `backend/app/services/search_service.py`

1. The incoming query is validated (2–300 characters, whitespace-normalized)
   by the Pydantic schema before anything else runs.
2. Filters (category, region, language, time range, result count) are validated
   against explicit allow-lists. Unsupported values are rejected with `422`.
3. The backend calls SerpApi (`https://serpapi.com/search.json`) with the
   configured engine, applying result limits bounded by
   `MAX_RESULTS_LIMIT` (server-side) — the key never leaves the backend.
4. Each organic result is normalized into a consistent schema:

   | Field            | Rule                                                        |
   |------------------|-------------------------------------------------------------|
   | `position`       | Provider position, or array index as fallback               |
   | `title`          | Required — results without a title are discarded            |
   | `url`            | Required, must be `http(s)` — other schemes discarded       |
   | `snippet`        | Present only if the provider returned one                   |
   | `domain`         | Derived from the URL host (www. stripped)                   |
   | `publishedDate`  | **Only when the provider supplies a date** — never invented |
   | `source`         | **Only when the provider supplies it** — never invented     |

5. Failures map to explicit user-facing messages:
   - missing key → `search_not_configured` (503) with Demo Mode guidance
   - timeout → `search_timeout` (504)
   - provider 429 or "rate limit" error field → `rate_limited` (429)
   - auth rejection → `search_auth_failed` (502, message redacts the body)
   - no results → a completed report whose summary states that no evidence exists

**No retries.** A failed search is not automatically repeated, to avoid
consuming credits or hammering the provider.

**Demo mode.** When `SERPAPI_API_KEY` is unset, the service returns labeled mock
results on reserved `example.com` / `example.org` / `example.net` domains with
`[DEMO]` title prefixes. The run is stamped `mode=demo`, surfaced in the UI with
an amber **Demo data** badge, and never presented as live information.

---

## 2. Source extraction

**Service:** `backend/app/services/extraction_service.py`

Search snippets are often insufficient, so TrendMind may fetch the top
`MAX_EXTRACT_PAGES` pages — but only through a strict SSRF-safe path:

1. **URL validation** (`app/security/ssrf.py`): http/https only; no embedded
   credentials; only standard web ports; localhost / internal name suffixes
   (`.local`, `.internal`, `.lan`, `.corp`, …) rejected.
2. **DNS resolution**: every resolved address is checked — private (10/8,
   172.16/12, 192.168/16), loopback, link-local (169.254/16, including cloud
   metadata endpoints), CGNAT (100.64/10), multicast, reserved, unspecified,
   and IPv6 internal ranges are all blocked.
3. **Redirect control**: redirects are followed manually (max 3 hops) and
   *every destination is re-validated* with the same rules — an attacker cannot
   bounce through a public host to a private one.
4. **Resource limits**: strict timeout (`EXTRACT_TIMEOUT_SECONDS`), hard byte
   cap (`MAX_PAGE_BYTES`), HTML content types only, JavaScript never executed,
   no arbitrary file downloads.
5. **robots.txt** is consulted per host (best effort, cached 15 min);
   disallowed paths are skipped (`status=skipped`).
6. **Readable text extraction** (`html_to_text.py`): scripts, styles, nav,
   header/footer/aside, forms, and SVG are dropped; block-level text is kept
   and truncated at `MAX_EXTRACT_CHARS` with an explicit truncation marker.

Every source records its provenance:

- `extracted` — full page text retrieved and analyzed
- `snippet_only` — fetch attempted, fell back to the search snippet
- `blocked` — blocked by SSRF rules, robots.txt, or access denial (401/403)
- `failed` — timeout, non-HTML, 404, or network error
- `skipped` — extraction disabled or robots-disallowed

The UI renders a badge per source, and reports state how many pages versus
snippets were analyzed. **A snippet-only source is never described as a fully
analyzed page.** If extraction is unavailable entirely, analysis continues and
is explicitly labeled snippet-based (`contentBasis: "snippets"`).

---

## 3. Theme identification

**Service:** `backend/app/services/trends.py`

Themes are computed mechanically from the collected evidence for one run:

1. Text is tokenized (title + content), lowercased, stopword-filtered, and
   lightly normalized (plural → singular) to merge variants.
2. **Bigrams appearing in ≥ 2 sources** and **unigrams appearing in ≥ 3
   sources** become candidate themes; the strongest are kept (max 8), with
   near-duplicate subset phrases suppressed.
3. For each theme the system records: the sources that mention it
   (`sourceIds`), how many (`mentionCount`), and how many distinct domains.
4. A theme with no valid supporting source is removed; a theme supported by
   fewer than 3 sources carries an explicit limitation string.

Recurring **contradictions** are detected by comparing claims across sources:
positions that cite different sources for opposing statements are surfaced in
the *Conflicting claims* section (AI mode) and dropped automatically if fewer
than two cited positions survive validation.

**Missing information** and **follow-up questions** are generated from evidence
gaps: snippet-only coverage, low source counts, and absent dates each produce
explicit limitation notes; follow-up questions are phrased to target those gaps.

---

## 4. Evidence-strength scoring

Each theme receives a 0–100 score:

```
evidenceStrength = round(
    50 * min(supporting_sources / 4, 1)      # breadth (capped at 4 sources)
  + 30 * distinct_domains / total_domains     # diversity across publishers
  + 20 * extracted_ratio                      # full-page vs snippet-only support
)
```

Bands: `strong ≥ 70`, `moderate ≥ 50`, `emerging ≥ 30`, `tentative < 30`.

Properties, by construction:

- **Breadth** dominates: a theme seen across 4 sources reaches full breadth
  credit; a single-source observation can never outscore a widely supported one.
- **Diversity** rewards independent publishers over repeated syndication.
- **Depth** prefers sources whose full text was retrieved over snippet-only
  mentions.

> **This is a heuristic display aid, not a scientific probability.** It measures
> only what is inside *this* result set. The formula appears verbatim in every
> report's methodology section and in `backend/app/services/trends.py`.

**Evidence coverage** counts how claims are grounded:

- `supported` — factual findings that carry at least one valid citation
- `conflicting` — conflicts with ≥ 2 opposing cited positions
- `insufficient` — findings with no supporting citation

---

## 5. Citation validation

**Service:** `backend/app/services/citations.py`

Citations are enforced *after* analysis and *before* storage:

1. Pydantic validates the report structure (types, lengths, enum values).
2. Every `sourceId` in findings, themes, comparisons, conflicts, developments,
   and opportunities must exist in the run's collected sources.
   - Unknown IDs are **removed** (counted and reported in report warnings).
   - A factual finding that loses all citations is **reclassified** as
     `interpretation` with a caveat explaining why.
   - Themes with zero valid sources are **dropped**; `mentionCount` is
     recomputed from surviving IDs.
   - Comparisons/conflicts with no cited positions are dropped (conflicts need
     ≥ 2 opposing cited positions).
3. Coverage is recomputed from the cleaned content.

**AI output repair policy:** at most **one** controlled repair attempt is made
when the model returns structurally invalid JSON/schema. If the repair fails,
the run falls back to deterministic basic mode with search results preserved —
the model is never called in a loop.

The report UI only renders citation markers that resolve to real sources;
unresolvable markers display as unresolved text, never as links.

---

## 6. Prompt-injection defenses

Retrieved webpages and search snippets are **untrusted input**:

- Content is embedded inside clearly delimited `UNTRUSTED RETRIEVED CONTENT
  BEGINS/ENDS` markers and declared to be data, not instructions.
- The system prompt explicitly instructs the model to ignore instructions found
  inside retrieved content (including "ignore previous instructions" style
  payloads) and to never reveal system prompts or credentials.
- Retrieved content cannot trigger tools or privileged actions — the analysis
  step has no tool access, no code execution, and no outbound calls beyond the
  configured model endpoint.
- AI-generated URLs are never fetched directly; extraction only runs on URLs
  that came from the search provider, and those still pass full SSRF validation.

---

## 7. Limitations of snapshot-based analysis

TrendMind analyzes **one search at one moment**. This imposes hard limits:

1. **No time-series claims.** Growth, decline, acceleration, and seasonality
   require repeated snapshots; a single snapshot cannot demonstrate them.
   TrendMind therefore says "themes observed in the collected results" and never
   "X is rising".
2. **Search results ≠ the web.** Results reflect the provider's index and
   ranking for your query, region, and language — not an exhaustive census.
3. **Ranking bias.** Higher-ranked sources dominate the evidence package;
   long-tail perspectives may be absent entirely.
4. **No significance testing.** Mention counts and scores describe the sample,
   not a population; small samples (n < 5) are flagged as limited evidence.
5. **Publication dates are often missing.** When the provider omits them,
   TrendMind shows no date rather than inferring one — so the timeline chart
   only renders when real timestamps exist.
6. **Extraction coverage varies.** Blocked, paywalled, or non-HTML pages reduce
   analysis to snippets, which contain far less context than full articles.
7. **Snapshot conflict ≠ falsehood.** Detected contradictions may reflect
   differing definitions, timeframes, or scopes rather than factual error.
8. **Local history.** Research history lives in a single-instance SQLite file —
   it is not per-user private and may be lost on ephemeral hosting storage.

When historical snapshots are ever added, the measurement method must be
documented and the comparison made explicit — TrendMind never manufactures
historical data.
