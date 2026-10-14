"""Historical trend tracking: dated snapshots and consecutive change detection.

Every snapshot is a REAL stored research run matching the tracked query — this
module never invents observations, interpolates missing dates, or backfills a
gap. Changes are computed deterministically between consecutive snapshots:

  * newly observed    — finding in the newer snapshot with no qualifying match
                        in the older one (lexical, same thresholds as the
                        report comparison feature)
  * no longer observed — finding in the older snapshot absent from the newer
                        one. ABSENCE IS NOT CONTRADICTION: a missing finding
                        was simply not seen in that run; it is never described
                        as proven false, retracted, or disproven.
  * source coverage   — shared/added/removed URLs and domains (exact URL match)
  * theme scores      — evidenceStrength deltas ONLY for theme names present in
                        both snapshots; everything else is reported as not
                        comparable instead of being interpolated.

The optional AI summary (`summarize_changes_with_ai`) is invoked by the API
layer only when a provider is configured; any failure falls back to the basic
methodology with an explicit note — the response never claims AI analysis that
did not happen.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime

from ..schemas import (
    FindingRef,
    SnapshotChange,
    SnapshotTheme,
    SourceCoverageDelta,
    SourceRef,
    ThemeScoreChange,
    TimelineSnapshot,
    TrendMethodology,
    TrackedTopic,
    TrendTimeline,
)
from .comparison import (
    SIMILARITY_THRESHOLD,
    content_tokens,
    normalize_text,
    token_similarity,
)

logger = logging.getLogger(__name__)

MAX_URL_DELTAS = 20
MAX_DOMAIN_DELTAS = 20
AI_FINDING_TEXT_CHARS = 180  # bounded evidence sent to the model
AI_SUMMARY_INPUT_CHARS = 4000
AI_SUMMARY_MAX_CHARS = 1600

ABSENCE_CAVEAT = (
    "“No longer observed” means the finding did not reappear in the newer "
    "search — it is NOT evidence that the claim was proven false, retracted, "
    "or disproven. Search results vary between runs; re-run the query and "
    "verify the cited sources before drawing any conclusion."
)

NEWLY_OBSERVED_CAVEAT = (
    "“Newly observed” means the finding appears in this snapshot but not in "
    "the previous one — it may have existed earlier without being surfaced. "
    "Absence from one run is not proof of novelty."
)


# --------------------------------------------------------------------------
# Snapshot construction
# --------------------------------------------------------------------------

def _ref(finding, index: int) -> FindingRef:
    return FindingRef(
        index=index,
        text=finding.text,
        evidenceClass=finding.evidenceClass,
        sourceIds=list(finding.sourceIds),
        caveat=finding.caveat,
    )


def build_snapshot(record) -> TimelineSnapshot | None:
    """Turn one stored research run into a timeline snapshot.

    Returns None when the run carries no usable report (failed/corrupt/legacy
    rows are skipped rather than fabricated). Timestamps come from the record
    itself: `createdAt` (run time) and the report's `searchedAt`.
    """
    report = record.report
    if report is None:
        return None
    searched_at = report.searchedAt or record.createdAt
    themes = [
        SnapshotTheme(
            name=t.name,
            mentionCount=t.mentionCount,
            evidenceStrength=t.evidenceStrength,
            confidence=t.confidence,
        )
        for t in report.themes
    ]
    return TimelineSnapshot(
        researchId=record.id,
        query=record.query,
        createdAt=record.createdAt,
        searchedAt=searched_at,
        mode=record.mode,
        aiMode=record.aiMode,
        resultCount=record.resultCount,
        findingCount=len(report.keyFindings),
        sourceCount=len(report.sources),
        domainCount=len({s.domain for s in report.sources}),
        findings=[_ref(f, i) for i, f in enumerate(report.keyFindings)],
        sources=[SourceRef(**s.model_dump()) for s in report.sources],
        themes=themes,
    )


def build_snapshots(records: list) -> list[TimelineSnapshot]:
    """Snapshots for records already in timeline order; unusable rows dropped.

    Ordering is enforced here (created_at ASC, id tie-break) so the API layer
    can never emit an out-of-order timeline regardless of input.
    """
    snapshots = [s for r in records if (s := build_snapshot(r)) is not None]
    snapshots.sort(key=lambda s: (s.createdAt, s.researchId))
    return snapshots


# --------------------------------------------------------------------------
# Finding matching (deterministic; same thresholds as report comparison)
# --------------------------------------------------------------------------

def match_findings(
    older: list[FindingRef], newer: list[FindingRef]
) -> list[tuple[int, int, float]]:
    """Greedy one-to-one matches (older_index, newer_index, similarity).

    Exact normalized text matches rank first, then content-word Jaccard
    overlap >= SIMILARITY_THRESHOLD. A matched pair means "observed in both"
    — polarity differences are out of scope here (the report comparison
    feature covers conflicts); unmatched items drive new/gone deltas.
    """
    candidates: list[tuple[str, float, int, int]] = []
    for ia, a in enumerate(older):
        norm_a = normalize_text(a.text)
        tokens_a = content_tokens(a.text)
        for ib, b in enumerate(newer):
            if norm_a and norm_a == normalize_text(b.text):
                candidates.append(("exact", 1.0, ia, ib))
                continue
            sim = token_similarity(tokens_a, content_tokens(b.text))
            if sim >= SIMILARITY_THRESHOLD:
                candidates.append(("similar", sim, ia, ib))

    rank = {"exact": 0, "similar": 1}
    candidates.sort(key=lambda c: (rank[c[0]], -c[1], c[2], c[3]))

    matches: list[tuple[int, int, float]] = []
    used_older: set[int] = set()
    used_newer: set[int] = set()
    for _kind, sim, ia, ib in candidates:
        if ia in used_older or ib in used_newer:
            continue
        used_older.add(ia)
        used_newer.add(ib)
        matches.append((ia, ib, round(sim, 3)))
    return matches


# --------------------------------------------------------------------------
# Change detection between consecutive snapshots
# --------------------------------------------------------------------------

def _parse_ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _days_apart(a: str, b: str) -> float:
    ta, tb = _parse_ts(a), _parse_ts(b)
    if ta is None or tb is None:
        return 0.0
    try:
        seconds = abs((tb - ta).total_seconds())
    except TypeError:  # mixed naive/aware timestamps
        return 0.0
    return round(seconds / 86_400, 2)


def _source_coverage(older: TimelineSnapshot, newer: TimelineSnapshot) -> SourceCoverageDelta:
    older_urls = [s.url for s in older.sources]
    newer_urls = [s.url for s in newer.sources]
    set_older, set_newer = set(older_urls), set(newer_urls)
    added = [s.url for s in newer.sources if s.url not in set_older]
    removed = [s.url for s in older.sources if s.url not in set_newer]
    added_domains = sorted({s.domain for s in newer.sources if s.url not in set_older})
    removed_domains = sorted({s.domain for s in older.sources if s.url not in set_newer})
    return SourceCoverageDelta(
        sharedCount=len(set_older & set_newer),
        addedCount=len(added),
        removedCount=len(removed),
        addedUrls=added[:MAX_URL_DELTAS],
        removedUrls=removed[:MAX_URL_DELTAS],
        addedDomains=added_domains[:MAX_DOMAIN_DELTAS],
        removedDomains=removed_domains[:MAX_DOMAIN_DELTAS],
    )


def _theme_key(name: str) -> str:
    return " ".join(normalize_text(name).split())


def _theme_changes(
    older: TimelineSnapshot, newer: TimelineSnapshot
) -> tuple[list[ThemeScoreChange], list[str]]:
    """Score deltas for theme names present in BOTH snapshots, plus the names
    that are not present on both sides (reported as not comparable)."""
    older_map = {_theme_key(t.name): t for t in older.themes}
    newer_map = {_theme_key(t.name): t for t in newer.themes}
    shared_keys = set(older_map) & set(newer_map)

    changes: list[ThemeScoreChange] = []
    for key in sorted(shared_keys):
        o, n = older_map[key], newer_map[key]
        if o.evidenceStrength == n.evidenceStrength:
            continue  # no change to report; not fabricated as a delta
        changes.append(
            ThemeScoreChange(
                theme=n.name,
                olderStrength=o.evidenceStrength,
                newerStrength=n.evidenceStrength,
                delta=n.evidenceStrength - o.evidenceStrength,
                olderConfidence=o.confidence,
                newerConfidence=n.confidence,
            )
        )
    changes.sort(key=lambda c: (-abs(c.delta), c.theme))

    incomparable = sorted(
        {t.name for k, t in older_map.items() if k not in newer_map}
        | {t.name for k, t in newer_map.items() if k not in older_map}
    )
    return changes, incomparable[:40]


def detect_change(older: TimelineSnapshot, newer: TimelineSnapshot) -> SnapshotChange:
    """Deterministic deltas between two consecutive snapshots."""
    matches = match_findings(older.findings, newer.findings)
    matched_older = {ia for ia, _ib, _sim in matches}
    matched_newer = {ib for _ia, ib, _sim in matches}

    newly_observed = [f for i, f in enumerate(newer.findings) if i not in matched_newer]
    no_longer_observed = [f for i, f in enumerate(older.findings) if i not in matched_older]
    theme_changes, incomparable = _theme_changes(older, newer)

    return SnapshotChange(
        fromSnapshot=_ref_snap(older),
        toSnapshot=_ref_snap(newer),
        daysApart=_days_apart(older.searchedAt or older.createdAt, newer.searchedAt or newer.createdAt),
        unchangedCount=len(matches),
        newlyObserved=newly_observed,
        noLongerObserved=no_longer_observed,
        absenceCaveat=ABSENCE_CAVEAT,
        sourceCoverage=_source_coverage(older, newer),
        themeScoreChanges=theme_changes,
        incomparableThemes=incomparable,
    )


def _ref_snap(snapshot: TimelineSnapshot):
    from ..schemas import SnapshotRef

    return SnapshotRef(
        researchId=snapshot.researchId,
        createdAt=snapshot.createdAt,
        searchedAt=snapshot.searchedAt,
    )


def detect_consecutive_changes(snapshots: list[TimelineSnapshot]) -> list[SnapshotChange]:
    """Changes for each consecutive pair in chronological order (n-1 entries)."""
    return [
        detect_change(snapshots[i], snapshots[i + 1])
        for i in range(len(snapshots) - 1)
    ]


# --------------------------------------------------------------------------
# Optional AI summary (always falls back to basic with an explicit note)
# --------------------------------------------------------------------------

def _extract_summary_text(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = (parts[1] if len(parts) > 1 else text).strip()
        # Drop a leading language tag line ("```markdown" → content only).
        lines = text.split("\n", 1)
        if len(lines) == 2 and re.fullmatch(r"[A-Za-z]{1,20}", lines[0].strip()):
            text = lines[1].strip()
    text = text.strip()
    if not text:
        raise ValueError("AI summary is empty")
    # Cosmetic cleanup only: drop stray markdown emphasis/backtick markers the
    # model sometimes emits in plain-text mode. Wording is never rewritten.
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text, flags=re.DOTALL)
    text = text.replace("**", "").replace("`", "").strip()
    if not text:
        raise ValueError("AI summary is empty after cleanup")
    if len(text) > AI_SUMMARY_MAX_CHARS:
        text = text[:AI_SUMMARY_MAX_CHARS].rstrip() + "…"
    return text


async def summarize_changes_with_ai(
    changes: list[SnapshotChange],
    *,
    provider: str,
    model: str,
    api_key: str,
    base_url: str,
    timeout: float,
) -> str:
    """Ask the configured model to summarize the consecutive changes.

    Input is bounded (dates, counts, truncated finding texts) and the response
    is validated as non-empty text. Raises AiError/ValueError on failure so the
    caller can fall back to basic mode honestly.
    """
    from .ai import build_adapter

    def snapshot_line(c: SnapshotChange, pair_index: int) -> str:
        older_label = (c.fromSnapshot.searchedAt or c.fromSnapshot.createdAt)[:10]
        newer_label = (c.toSnapshot.searchedAt or c.toSnapshot.createdAt)[:10]
        deltas = ", ".join(
            f"{t.theme} {t.olderStrength}->{t.newerStrength}" for t in c.themeScoreChanges[:6]
        ) or "none comparable"
        cov = c.sourceCoverage
        lines = [
            f"Interval {pair_index}: {older_label} -> {newer_label}"
            f" ({c.daysApart} days).",
            f"Newly observed: {len(c.newlyObserved)}; no longer observed:"
            f" {len(c.noLongerObserved)}; sources shared {cov.sharedCount},"
            f" added {cov.addedCount}, removed {cov.removedCount}.",
            f"Theme score changes: {deltas}.",
        ]
        for f in c.newlyObserved[:5]:
            lines.append(f"  + {f.text[:AI_FINDING_TEXT_CHARS]}")
        for f in c.noLongerObserved[:5]:
            lines.append(f"  - {f.text[:AI_FINDING_TEXT_CHARS]}")
        return "\n".join(lines)

    block = "\n\n".join(snapshot_line(c, i + 1) for i, c in enumerate(changes))
    block = block[:AI_SUMMARY_INPUT_CHARS]

    system = (
        "You summarize changes between consecutive research snapshots of the "
        "same query. Use ONLY the provided data. Never claim a finding is "
        "false, disproven, or retracted — a finding absent from a newer "
        "snapshot was merely not observed in that run. Phrase everything as "
        "observations from specific search dates."
    )
    user = (
        f"{block}\n\n"
        "Write one short paragraph (max 180 words) summarizing what changed "
        "across these intervals, then one line noting what to re-check. "
        "Respond with plain text only."
    )

    adapter = build_adapter(
        provider=provider, model=model, api_key=api_key, base_url=base_url, timeout=timeout
    )
    completion = await adapter.complete(
        system=system, user=user, json_mode=False, max_tokens=700
    )
    return _extract_summary_text(completion.text)


# --------------------------------------------------------------------------
# Timeline assembly
# --------------------------------------------------------------------------

BASIC_EXPLANATION = [
    "Basic trend analysis: deterministic matching between consecutive dated "
    "snapshots — no AI model was used unless you requested one.",
    "Each snapshot is a real stored research run for this query; dates are the "
    "runs' actual timestamps — no historical data is inferred or backfilled.",
    f"“Newly observed” / “no longer observed” use exact and ≥"
    f"{round(SIMILARITY_THRESHOLD * 100)}% content-word (Jaccard) matching, the "
    "same thresholds as report comparison. Absence from a newer search is not "
    "evidence that a claim is false.",
    "Theme scores are compared only when a theme appears in both snapshots of "
    "an interval; other themes are listed as not comparable rather than "
    "estimated.",
    "Sources are matched by exact URL; domain overlap is informational only.",
]

AI_EXPLANATION = [
    "AI-assisted summary: the configured model wrote the summary from the "
    "deterministic deltas below. All counts, dates, and score changes are "
    "computed from the stored snapshots — they are not model output.",
    "Model summaries can be wrong — verify any claim against the cited sources.",
]

SINGLE_SNAPSHOT_NOTE = (
    "Only one dated snapshot exists for this topic. Change detection and the "
    "history chart appear automatically once another research run with this "
    "query is stored — a single snapshot cannot show a trend over time."
)


def build_timeline(
    topic: TrackedTopic,
    snapshots: list[TimelineSnapshot],
    *,
    ai_summary: str | None = None,
    ai_note: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> TrendTimeline:
    """Assemble the timeline response from ordered snapshots."""
    changes = detect_consecutive_changes(snapshots) if len(snapshots) >= 2 else []
    if ai_summary:
        methodology = TrendMethodology(
            mode="ai", explanation=AI_EXPLANATION, aiNote=ai_note, aiSummary=ai_summary
        )
    else:
        methodology = TrendMethodology(
            mode="basic", explanation=BASIC_EXPLANATION, aiNote=ai_note, aiSummary=None
        )
    return TrendTimeline(
        topic=topic,
        snapshots=snapshots,
        changes=changes,
        methodology=methodology,
        singleSnapshotNote=SINGLE_SNAPSHOT_NOTE if len(snapshots) == 1 else None,
        dateFrom=date_from,
        dateTo=date_to,
    )


def serialize_snapshot_for_ai_check(snapshot: TimelineSnapshot) -> str:  # pragma: no cover
    """Debug helper: compact JSON view of a snapshot (no secrets)."""
    return json.dumps(
        {
            "id": snapshot.researchId,
            "at": snapshot.searchedAt,
            "findings": snapshot.findingCount,
            "sources": snapshot.sourceCount,
        }
    )
