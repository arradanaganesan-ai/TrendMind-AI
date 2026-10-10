"""Repository: typed data access for research records and saved topics.

All queries are parameterized. Records are validated before storage.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

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

    def list(self, limit: int = 20, offset: int = 0) -> tuple[list[ResearchListItem], int]:
        limit = max(1, min(limit, MAX_HISTORY_PAGE))
        offset = max(0, offset)
        rows = self._db.query(
            "SELECT id, query, created_at, search_mode, ai_mode, status, result_count,"
            " error_message FROM research ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        total_row = self._db.query("SELECT COUNT(*) AS c FROM research")
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

    def count(self) -> int:
        rows = self._db.query("SELECT COUNT(*) AS c FROM research")
        return int(rows[0]["c"]) if rows else 0

    def completed_count(self) -> int:
        rows = self._db.query(
            "SELECT COUNT(*) AS c FROM research WHERE status = 'completed'"
        )
        return int(rows[0]["c"]) if rows else 0

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
