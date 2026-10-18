"""Decision traces: the audit record that makes behavior explainable."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any


class TraceLog:
    def __init__(self, path: str | None = None) -> None:
        self._path = Path(path) if path else None
        self.entries: list[dict[str, Any]] = []
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, agent_id: str, event: str, **fields: Any) -> dict[str, Any]:
        entry = {"decision_id": uuid.uuid4().hex[:12], "agent_id": agent_id, "ts": time.time(), "event": event, **fields}
        self.entries.append(entry)
        if self._path:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, default=repr) + "\n")
        return entry

    def for_agent(self, agent_id: str) -> list[dict[str, Any]]:
        return [e for e in self.entries if e["agent_id"] == agent_id]
