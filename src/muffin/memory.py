"""Episodic memory: an append-only, time-ordered record of what happened."""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Any


class EpisodicMemory:
    def __init__(self, path: str = ":memory:") -> None:
        self._db = sqlite3.connect(path)
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS events (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   agent_id TEXT NOT NULL,
                   ts REAL NOT NULL,
                   kind TEXT NOT NULL,
                   data TEXT NOT NULL)"""
        )
        self._db.execute("CREATE INDEX IF NOT EXISTS idx_agent ON events(agent_id, id)")
        self._db.commit()

    def write(self, agent_id: str, kind: str, data: dict[str, Any]) -> int:
        cur = self._db.execute(
            "INSERT INTO events (agent_id, ts, kind, data) VALUES (?, ?, ?, ?)",
            (agent_id, time.time(), kind, json.dumps(data, default=repr)),
        )
        self._db.commit()
        return int(cur.lastrowid)

    def recent(self, agent_id: str, limit: int = 10) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT id, ts, kind, data FROM events WHERE agent_id=? ORDER BY id DESC LIMIT ?",
            (agent_id, limit),
        ).fetchall()
        return [{"id": r[0], "ts": r[1], "kind": r[2], "data": json.loads(r[3])} for r in reversed(rows)]

    def search(self, agent_id: str, text: str, limit: int = 10) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT id, ts, kind, data FROM events WHERE agent_id=? AND (kind LIKE ? OR data LIKE ?) "
            "ORDER BY id DESC LIMIT ?",
            (agent_id, f"%{text}%", f"%{text}%", limit),
        ).fetchall()
        return [{"id": r[0], "ts": r[1], "kind": r[2], "data": json.loads(r[3])} for r in rows]

    def count(self, agent_id: str) -> int:
        return int(self._db.execute("SELECT COUNT(*) FROM events WHERE agent_id=?", (agent_id,)).fetchone()[0])

    def last_id(self, agent_id: str) -> int:
        row = self._db.execute("SELECT COALESCE(MAX(id), 0) FROM events WHERE agent_id=?", (agent_id,)).fetchone()
        return int(row[0])

    def truncate_after(self, agent_id: str, marker_id: int) -> int:
        """Remove events newer than marker_id (used by rollback). Returns rows removed."""
        cur = self._db.execute("DELETE FROM events WHERE agent_id=? AND id>?", (agent_id, marker_id))
        self._db.commit()
        return cur.rowcount
