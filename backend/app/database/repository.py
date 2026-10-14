"""Repository: typed data access for research records and saved topics.

All queries are parameterized. Records are validated before storage.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone

from ..database.db import Database
from ..schemas import (
    ResearchListItem,
    ResearchRecord,
    ResearchReport,
    SavedTopic,
    SearchResult,
)

MAX_HISTORY_PAGE = 50


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


class ResearchRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    # -- Research ---------------------------------------------------------

    def create_pending(self, query: str, mode: str, filters: dict | None) -> str:
        rid = _new_id()
        self._db.execute(
            "INSERT INTO research (id, query, created_at, search_mode, ai_mode, status,"
            " result_count, filters_json, results_json, report_json, error_message)"
            " VALUES (?, ?, ?, ?, ?, 'pending', 0, ?, '[]', NULL, NULL)",
            (
                rid,
                query,
                _now(),
                mode,
                "basic",
                json.dumps(filters) if filters else None,
            ),
        )
        return rid

    def save_completed(
        self,
        research_id: str,
        *,
        status: str,
        ai_mode: str,
        result_count: int,
        results: list[SearchResult],
        report: ResearchReport | None,
        error_message: str | None,
    ) -> None:
        self._db.execute(
            "UPDATE research SET status = ?, ai_mode = ?, result_count = ?, results_json = ?,"
            " report_json = ?, error_message = ? WHERE id = ?",
            (
                status,
                ai_mode,
                result_count,
                json.dumps([r.model_dump(exclude_none=True) for r in results]),
                json.dumps(report.model_dump(mode="json")) if report else None,
                error_message,
                research_id,
            ),
        )

    def get(self, research_id: str) -> ResearchRecord | None:
        rows = self._db.query("SELECT * FROM research WHERE id = ?", (research_id,))
        if not rows:
            return None
        return self._to_record(rows[0])

    def list(
        self,
        limit: int = 20,
        offset: int = 0,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> tuple[list[ResearchListItem], int]:
        """List research runs newest-first, optionally bounded by dates.

        `date_from` / `date_to` are YYYY-MM-DD strings (inclusive, compared in
        UTC) against `created_at`. Both the page query and the total count use
        the same WHERE clause so pagination stays consistent under filters.
        """
        limit = max(1, min(limit, MAX_HISTORY_PAGE))
        offset = max(0, offset)
        where = ""
        params: list = []
        if date_from:
            where += " AND date(created_at) >= date(?)"
            params.append(date_from)
        if date_to:
            where += " AND date(created_at) <= date(?)"
            params.append(date_to)
        rows = self._db.query(
            "SELECT id, query, created_at, search_mode, ai_mode, status, result_count,"
            f" error_message FROM research WHERE 1=1{where}"
            " ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        )
        total_row = self._db.query(
            f"SELECT COUNT(*) AS c FROM research WHERE 1=1{where}",
            tuple(params),
        )
        total = int(total_row[0]["c"]) if total_row else 0
        items = [
            ResearchListItem(
                id=r["id"],
                query=r["query"],
                createdAt=r["created_at"],
                status=r["status"],
                mode=r["search_mode"],
                resultCount=r["result_count"],
                aiMode=r["ai_mode"],
                errorMessage=r["error_message"],
            )
            for r in rows
        ]
        return items, total

    def delete(self, research_id: str) -> bool:
        before = self._db.query("SELECT id FROM research WHERE id = ?", (research_id,))
        if not before:
            return False
        self._db.execute("DELETE FROM research WHERE id = ?", (research_id,))
        return True

    def stats(self, since_iso: str | None = None) -> dict:
        """Aggregate counters computed by the database.

        Every number returned here is a real COUNT over this instance's
        `research` table — nothing is estimated or client-side derived.
        `since_iso` (UTC ISO-8601) optionally restricts the *_since counters.
        """
        def _count(sql: str, params: tuple = ()) -> int:
            rows = self._db.query(sql, params)
            return int(rows[0]["c"]) if rows else 0

        base = {
            "research_total": _count("SELECT COUNT(*) AS c FROM research"),
            "research_completed": _count(
                "SELECT COUNT(*) AS c FROM research WHERE status = 'completed'"
            ),
            "research_failed": _count(
                "SELECT COUNT(*) AS c FROM research WHERE status = 'failed'"
            ),
            "reports_total": _count(
                "SELECT COUNT(*) AS c FROM research"
                " WHERE status = 'completed' AND report_json IS NOT NULL"
            ),
        }
        if since_iso:
            params = (since_iso,)
            base["research_since"] = _count(
                "SELECT COUNT(*) AS c FROM research WHERE created_at >= ?", params
            )
            base["research_completed_since"] = _count(
                "SELECT COUNT(*) AS c FROM research"
                " WHERE status = 'completed' AND created_at >= ?",
                params,
            )
        return base

    def activity(self, days: int = 30) -> list[dict]:
        """Daily research-run counts for the last `days` days (UTC), inclusive.

        Built entirely from existing `research` rows: one entry per calendar
        day with real COUNTs; days without runs are explicitly zero (so the
        chart never invents data or hides gaps).
        """
        days = max(1, min(days, 365))
        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=days - 1)
        rows = self._db.query(
            "SELECT date(created_at) AS d, COUNT(*) AS c,"
            " SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS done"
            " FROM research WHERE date(created_at) >= ?"
            " GROUP BY date(created_at)",
            (start.isoformat(),),
        )
        by_day = {r["d"]: (int(r["c"]), int(r["done"] or 0)) for r in rows}
        out: list[dict] = []
        for i in range(days):
            d = (start + timedelta(days=i)).isoformat()
            count, completed = by_day.get(d, (0, 0))
            out.append({"date": d, "count": count, "completed": completed})
        return out

    # -- Helpers ----------------------------------------------------------

    def _to_record(self, row) -> ResearchRecord:
        try:
            results_raw = json.loads(row["results_json"] or "[]")
            results = [SearchResult(**r) for r in results_raw]
        except (json.JSONDecodeError, TypeError):
            results = []

        report = None
        if row["report_json"]:
            try:
                report = ResearchReport.model_validate(json.loads(row["report_json"]))
            except Exception:
                report = None  # Corrupt/legacy payload: degrade instead of failing.

        filters = None
        if row["filters_json"]:
            try:
                from ..schemas import ResearchFilters

                filters = ResearchFilters.model_validate(json.loads(row["filters_json"]))
            except Exception:
                filters = None

        return ResearchRecord(
            id=row["id"],
            query=row["query"],
            createdAt=row["created_at"],
            status=row["status"],
            mode=row["search_mode"],
            resultCount=row["result_count"],
            aiMode=row["ai_mode"],
            errorMessage=row["error_message"],
            filters=filters,
            results=results,
            report=report,
        )


class TopicRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def count(self) -> int:
        rows = self._db.query("SELECT COUNT(*) AS c FROM saved_topic")
        return int(rows[0]["c"]) if rows else 0

    def list(self) -> list[SavedTopic]:
        rows = self._db.query(
            "SELECT id, topic, created_at FROM saved_topic ORDER BY created_at DESC"
        )
        return [
            SavedTopic(id=r["id"], topic=r["topic"], createdAt=r["created_at"]) for r in rows
        ]

    def create(self, topic: str) -> SavedTopic:
        existing = self._db.query(
            "SELECT id, topic, created_at FROM saved_topic WHERE topic = ?", (topic,)
        )
        if existing:
            r = existing[0]
            return SavedTopic(id=r["id"], topic=r["topic"], createdAt=r["created_at"])
        tid = _new_id()
        created = _now()
        self._db.execute(
            "INSERT INTO saved_topic (id, topic, created_at) VALUES (?, ?, ?)",
            (tid, topic, created),
        )
        return SavedTopic(id=tid, topic=topic, createdAt=created)

    def delete(self, topic_id: str) -> bool:
        rows = self._db.query("SELECT id FROM saved_topic WHERE id = ?", (topic_id,))
        if not rows:
            return False
        self._db.execute("DELETE FROM saved_topic WHERE id = ?", (topic_id,))
        return True


class TrendRepository:
    """Tracked topics for historical trend tracking.

    A tracked topic stores ONLY the query string — snapshots are derived from
    the existing `research` rows that match it (real, dated results; nothing is
    copied or fabricated here). Created strictly for completed runs so a topic
    always has at least one real snapshot.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    def get(self, topic_id: str) -> dict | None:
        rows = self._db.query(
            "SELECT id, query, created_at FROM tracked_topic WHERE id = ?", (topic_id,)
        )
        if not rows:
            return None
        r = rows[0]
        return {"id": r["id"], "query": r["query"], "createdAt": r["created_at"]}

    def find_by_query(self, query: str) -> dict | None:
        rows = self._db.query(
            "SELECT id, query, created_at FROM tracked_topic WHERE query = ?", (query,)
        )
        if not rows:
            return None
        r = rows[0]
        return {"id": r["id"], "query": r["query"], "createdAt": r["created_at"]}

    def create(self, query: str) -> dict:
        """Create (or return the existing) tracked topic for an exact query."""
        existing = self.find_by_query(query)
        if existing:
            return existing
        tid = _new_id()
        created = _now()
        self._db.execute(
            "INSERT INTO tracked_topic (id, query, created_at) VALUES (?, ?, ?)",
            (tid, query, created),
        )
        return {"id": tid, "query": query, "createdAt": created}

    def delete(self, topic_id: str) -> bool:
        rows = self._db.query("SELECT id FROM tracked_topic WHERE id = ?", (topic_id,))
        if not rows:
            return False
        self._db.execute("DELETE FROM tracked_topic WHERE id = ?", (topic_id,))
        return True

    def list_with_snapshots(self) -> list[dict]:
        """Every tracked topic with REAL snapshot counts over `research`.

        Counts include only completed runs carrying a stored report — the same
        rows the timeline endpoint serves — so the list can never advertise a
        snapshot the timeline would not show.
        """
        rows = self._db.query(
            "SELECT id, query, created_at FROM tracked_topic ORDER BY created_at DESC"
        )
        out: list[dict] = []
        for r in rows:
            stats = self.snapshot_stats(r["query"])
            out.append(
                {
                    "id": r["id"],
                    "query": r["query"],
                    "createdAt": r["created_at"],
                    **stats,
                }
            )
        return out

    def snapshot_ids_for_query(
        self,
        query: str,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[str]:
        """Completed run ids matching `query`, oldest-first (timeline order).

        `date_from`/`date_to` are inclusive YYYY-MM-DD bounds on `created_at`
        (UTC), mirroring the history filters. Ordering uses created_at ASC with
        id as a deterministic tie-break so equal timestamps never shuffle.
        """
        where = " WHERE query = ? AND status = 'completed' AND report_json IS NOT NULL"
        params: list = [query]
        if date_from:
            where += " AND date(created_at) >= date(?)"
            params.append(date_from)
        if date_to:
            where += " AND date(created_at) <= date(?)"
            params.append(date_to)
        rows = self._db.query(
            f"SELECT id FROM research{where} ORDER BY created_at ASC, id ASC",
            tuple(params),
        )
        return [r["id"] for r in rows]

    def query_candidates(self) -> list[dict]:
        """Distinct queries of completed runs, for the 'track a topic' picker."""
        rows = self._db.query(
            "SELECT query, COUNT(*) AS n, MIN(created_at) AS first, MAX(created_at) AS last"
            " FROM research WHERE status = 'completed' AND report_json IS NOT NULL"
            " GROUP BY query ORDER BY n DESC, query ASC"
        )
        return [
            {
                "query": r["query"],
                "runCount": int(r["n"]),
                "firstRunAt": r["first"],
                "lastRunAt": r["last"],
            }
            for r in rows
        ]

    def snapshot_stats(self, query: str) -> dict:
        rows = self._db.query(
            "SELECT COUNT(*) AS c, MIN(created_at) AS first, MAX(created_at) AS last"
            " FROM research"
            " WHERE query = ? AND status = 'completed' AND report_json IS NOT NULL",
            (query,),
        )
        c = int(rows[0]["c"]) if rows else 0
        return {
            "snapshotCount": c,
            "firstSnapshotAt": rows[0]["first"] if c else None,
            "lastSnapshotAt": rows[0]["last"] if c else None,
        }
