import json

from pathlib import Path

import pytest

from muffin.trace import TraceLog


def test_record_returns_unique_ids():
    log = TraceLog()

    first = log.record("agent-1", "started")
    second = log.record("agent-1", "finished")

    assert first["decision_id"] != second["decision_id"]
    assert len(first["decision_id"]) == 32


def test_records_are_written_as_jsonl(tmp_path):
    path = tmp_path / "logs" / "trace.jsonl"
    log = TraceLog(str(path))

    log.record("agent-1", "action", tool="search")
    log.record("agent-1", "result", success=True)

    lines = path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 2
    assert json.loads(lines[0])["event"] == "action"
    assert json.loads(lines[1])["event"] == "result"


@pytest.mark.parametrize("field", ["decision_id", "ts"])
def test_reserved_fields_cannot_be_overridden(field):
    log = TraceLog()

    with pytest.raises(ValueError):
        log.record("agent-1", "action", **{field: "x"})


@pytest.mark.parametrize("field", ["agent_id", "event"])
def test_positional_fields_cannot_be_passed_as_extra_fields(field):
    log = TraceLog()

    # Python itself rejects the duplicate before the reserved-field check runs.
    with pytest.raises(TypeError):
        log.record("agent-1", "action", **{field: "x"})


def test_returned_record_cannot_mutate_internal_record():
    log = TraceLog()

    record = log.record(
        "agent-1",
        "action",
        details={"tool": "search"},
    )
    record["details"]["tool"] = "malicious"

    assert log.for_agent("agent-1")[0]["details"]["tool"] == "search"


def test_invalid_json_number_is_rejected():
    log = TraceLog()

    with pytest.raises(ValueError):
        log.record("agent-1", "action", cost=float("nan"))

    assert log.for_agent("agent-1") == []


def test_failed_write_does_not_add_memory_entry(tmp_path, monkeypatch):
    path = tmp_path / "trace.jsonl"
    log = TraceLog(str(path))

    def fail_open(*args, **kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr(Path, "open", fail_open)

    with pytest.raises(OSError):
        log.record("agent-1", "action")

    assert log.for_agent("agent-1") == []


def test_unknown_objects_do_not_use_repr():
    class Secret:
        def __repr__(self):
            return "password=super-secret"

    log = TraceLog()
    record = log.record("agent-1", "action", data=Secret())

    serialized = json.dumps(record)

    assert "super-secret" not in serialized
    assert record["data"]["_unsupported_type"].endswith(".Secret")


def test_invalid_agent_and_event_are_rejected():
    log = TraceLog()

    with pytest.raises(ValueError):
        log.record("", "action")

    with pytest.raises(ValueError):
        log.record("agent-1", "")


@pytest.mark.parametrize("agent_id, event", [
    ("   ", "action"),
    ("agent-1", "   "),
    (5, "action"),
    ("agent-1", None),
])
def test_blank_or_non_string_agent_and_event_are_rejected(agent_id, event):
    log = TraceLog()

    with pytest.raises(ValueError):
        log.record(agent_id, event)

    assert log.entries == []


def test_records_are_timestamped_in_order():
    log = TraceLog()

    first = log.record("agent-1", "started")
    second = log.record("agent-1", "finished")

    assert 0 < first["ts"] <= second["ts"]


def test_for_agent_returns_only_that_agents_detached_records():
    log = TraceLog()
    log.record("agent-1", "action", details={"tool": "search"})
    log.record("agent-2", "action")

    records = log.for_agent("agent-1")
    records[0]["details"]["tool"] = "malicious"

    assert [r["event"] for r in records] == ["action"]
    assert log.for_agent("agent-1")[0]["details"]["tool"] == "search"


def test_non_ascii_text_stays_readable_in_the_file(tmp_path):
    path = tmp_path / "trace.jsonl"
    log = TraceLog(str(path))

    log.record("agent-1", "note", text="café")

    assert "café" in path.read_text(encoding="utf-8")
