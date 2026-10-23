
"""Decision traces: structured records of agent behavior.

TraceLog provides append-only JSONL output and an in-memory view.
It is useful for debugging and auditing, but is not a tamper-proof
or multi-process transactional audit system.
"""
from __future__ import annotations

import json
import math
import threading
import time
import uuid
from pathlib import Path
from typing import Any


def _json_default(value: Any) -> Any:
    """Serialize unsupported objects without exposing their repr contents."""
    value_type = type(value)
    return {
        "_unsupported_type": (
            f"{value_type.__module__}.{value_type.__qualname__}"
        )
    }


def _serialize_entry(entry: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Produce strict JSON and a detached, JSON-compatible record."""
    line = json.dumps(
        entry,
        default=_json_default,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )

    # Normalize values such as custom objects and detach nested structures.
    normalized = json.loads(line)
    return line, normalized


class TraceLog:
    """Record structured agent events in memory and optionally to JSONL."""

    _RESERVED_FIELDS = frozenset(
        {"decision_id", "agent_id", "ts", "event"}
    )

    def __init__(self, path: str | None = None) -> None:
        self._path = Path(path) if path is not None else None
        self.entries: list[dict[str, Any]] = []
        self._lock = threading.RLock()

        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        agent_id: str,
        event: str,
        **fields: Any,
    ) -> dict[str, Any]:
        """Record an event, persisting it before updating memory."""
        if not isinstance(agent_id, str) or not agent_id.strip():
            raise ValueError("agent_id must be a non-empty string")

        if not isinstance(event, str) or not event.strip():
            raise ValueError("event must be a non-empty string")

        collisions = self._RESERVED_FIELDS.intersection(fields)
        if collisions:
            names = ", ".join(sorted(collisions))
            raise ValueError(f"Reserved trace field(s): {names}")

        entry = {
            "decision_id": uuid.uuid4().hex,
            "agent_id": agent_id,
            "ts": time.time(),
            "event": event,
            **fields,
        }

        line, normalized = _serialize_entry(entry)

        with self._lock:
            if self._path is not None:
                # Open in append mode for each record so file handles are
                # not retained for the lifetime of the TraceLog instance.
                with self._path.open("a", encoding="utf-8", newline="\n") as fh:
                    fh.write(line + "\n")
                    fh.flush()

            # Only publish the in-memory record after a successful write.
            self.entries.append(normalized)

            # Return a detached record so callers cannot mutate our copy.
            return json.loads(json.dumps(normalized, allow_nan=False))

    def for_agent(self, agent_id: str) -> list[dict[str, Any]]:
        """Return detached records belonging to one agent."""
        with self._lock:
            return [
                json.loads(json.dumps(entry, allow_nan=False))
                for entry in self.entries
                if entry["agent_id"] == agent_id
            ]
