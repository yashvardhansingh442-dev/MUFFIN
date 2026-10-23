
"""Episodic memory: persistent, time-ordered agent events.

SQLite-backed storage for agent experiences. Rollback deletion is supported
for compatibility, but destructive truncation is not an immutable audit log.
"""
from __future__ import annotations

import json
import math
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


def _json_default(value: Any) -> dict[str, str]:
    """Represent unsupported objects without exposing their repr contents."""
    cls = type(value)
    return {
        "_unsupported_type": f"{cls.__module__}.{cls.__qualname__}"
    }


def _validate_identifier(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")


def _validate_limit(limit: int) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise ValueError("limit must be a non-negative integer")


def _escape_like(text: str) -> str:
    """Treat LIKE metacharacters as literal search characters."""
    return (
        text.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


class EpisodicMemory:
    """SQLite event storage, scoped by agent ID."""

    def __init__(self, path: str = ":memory:") -> None:
        if not isinstance(path, str) or not path:
            raise ValueError("path must be a non-empty string")

        if path != ":memory:" and not path.startswith("file:"):
            Path(path).parent.mkdir(parents=True, exist_ok=True)

        # check_same_thread=False is safe here because every connection
        # operation is guarded by this instance's lock.
        self._lock = threading.RLock()
        self._closed = False
        self._db = sqlite3.connect(
            path,
            timeout=5.0,
            check_same_thread=False,
        )

        try:
            with self._lock, self._db:
                self._db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        agent_id TEXT NOT NULL,
                        ts REAL NOT NULL,
                        kind TEXT NOT NULL,
                        data TEXT NOT NULL
                    )
                    """
                )
                self._db.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_agent
                    ON events(agent_id, id)
                    """
                )
        except Exception:
            self._db.close()
            self._closed = True
            raise

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("EpisodicMemory is closed")

    @staticmethod
    def _decode_rows(
        rows: list[tuple[Any, ...]],
    ) -> list[dict[str, Any]]:
        return [
            {
                "id": row[0],
                "ts": row[1],
                "kind": row[2],
                "data": json.loads(row[3]),
            }
            for row in rows
        ]

    def write(
        self,
        agent_id: str,
        kind: str,
        data: dict[str, Any],
    ) -> int:
        """Persist one event and return its database ID."""
        _validate_identifier(agent_id, "agent_id")
        _validate_identifier(kind, "kind")

        if not isinstance(data, dict):
            raise ValueError("data must be a dictionary")

        # Serialize before opening the transaction. Unsupported objects
        # are represented by type, not arbitrary repr output.
        serialized = json.dumps(
            data,
            default=_json_default,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        timestamp = time.time()

        with self._lock:
            self._ensure_open()
            with self._db:
                cursor = self._db.execute(
                    """
                    INSERT INTO events (agent_id, ts, kind, data)
                    VALUES (?, ?, ?, ?)
                    """,
                    (agent_id, timestamp, kind, serialized),
                )
                event_id = cursor.lastrowid

        if event_id is None:
            raise RuntimeError("SQLite did not return an event ID")

        return int(event_id)

    def recent(
        self,
        agent_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Return the most recent events in chronological order."""
        _validate_identifier(agent_id, "agent_id")
        _validate_limit(limit)

        if limit == 0:
            return []

        with self._lock:
            self._ensure_open()
            rows = self._db.execute(
                """
                SELECT id, ts, kind, data
                FROM events
                WHERE agent_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (agent_id, limit),
            ).fetchall()

        return self._decode_rows(list(reversed(rows)))

    def search(
        self,
        agent_id: str,
        text: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search event kinds and serialized data for a literal substring."""
        _validate_identifier(agent_id, "agent_id")
        _validate_limit(limit)

        if not isinstance(text, str):
            raise ValueError("text must be a string")

        if limit == 0:
            return []

        pattern = f"%{_escape_like(text)}%"

        with self._lock:
            self._ensure_open()
            rows = self._db.execute(
                """
                SELECT id, ts, kind, data
                FROM events
                WHERE agent_id = ?
                  AND (
                      kind LIKE ? ESCAPE '\\'
                      OR data LIKE ? ESCAPE '\\'
                  )
                ORDER BY id DESC
                LIMIT ?
                """,
                (agent_id, pattern, pattern, limit),
            ).fetchall()

        return self._decode_rows(rows)

    def count(self, agent_id: str) -> int:
        _validate_identifier(agent_id, "agent_id")

        with self._lock:
            self._ensure_open()
            row = self._db.execute(
                "SELECT COUNT(*) FROM events WHERE agent_id = ?",
                (agent_id,),
            ).fetchone()

        return int(row[0])

    def last_id(self, agent_id: str) -> int:
        """Return the largest event ID currently stored for this agent."""
        _validate_identifier(agent_id, "agent_id")

        with self._lock:
            self._ensure_open()
            row = self._db.execute(
                """
                SELECT COALESCE(MAX(id), 0)
                FROM events
                WHERE agent_id = ?
                """,
                (agent_id,),
            ).fetchone()

        return int(row[0])

    def truncate_after(self, agent_id: str, marker_id: int) -> int:
        """Delete this agent's events after a checkpoint marker.

        This is destructive rollback support, not immutable history.
        """
        _validate_identifier(agent_id, "agent_id")

        if (
            isinstance(marker_id, bool)
            or not isinstance(marker_id, int)
            or marker_id < 0
        ):
            raise ValueError("marker_id must be a non-negative integer")

        with self._lock:
            self._ensure_open()
            with self._db:
                cursor = self._db.execute(
                    """
                    DELETE FROM events
                    WHERE agent_id = ? AND id > ?
                    """,
                    (agent_id, marker_id),
                )
                removed = cursor.rowcount

        return max(0, int(removed))

    def close(self) -> None:
        """Close the database connection. This instance cannot be reused."""
        with self._lock:
            if not self._closed:
                self._db.close()
                self._closed = True

    def __enter__(self) -> EpisodicMemory:
        with self._lock:
            self._ensure_open()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
