import json

import pytest

from muffin.memory import EpisodicMemory


def test_write_and_recent_preserve_order():
    memory = EpisodicMemory()

    first_id = memory.write("agent-1", "observation", {"value": 1})
    second_id = memory.write("agent-1", "action", {"value": 2})

    events = memory.recent("agent-1")

    assert [event["id"] for event in events] == [first_id, second_id]
    assert [event["kind"] for event in events] == [
        "observation",
        "action",
    ]


def test_agents_have_separate_memories():
    memory = EpisodicMemory()

    memory.write("agent-1", "note", {"secret": "alpha"})
    memory.write("agent-2", "note", {"secret": "beta"})

    assert memory.count("agent-1") == 1
    assert memory.count("agent-2") == 1
    assert memory.recent("agent-1")[0]["data"]["secret"] == "alpha"


def test_search_treats_percent_as_literal():
    memory = EpisodicMemory()

    memory.write("agent-1", "note", {"text": "100% complete"})
    memory.write("agent-1", "note", {"text": "100 items complete"})

    results = memory.search("agent-1", "%")

    assert len(results) == 1
    assert results[0]["data"]["text"] == "100% complete"


def test_search_treats_underscore_as_literal():
    memory = EpisodicMemory()

    memory.write("agent-1", "note", {"text": "hello_world"})
    memory.write("agent-1", "note", {"text": "helloXworld"})

    results = memory.search("agent-1", "_")

    assert len(results) == 1
    assert results[0]["data"]["text"] == "hello_world"


def test_rollback_deletes_only_target_agents_future_events():
    memory = EpisodicMemory()

    marker = memory.write("agent-1", "checkpoint", {"step": 1})
    memory.write("agent-2", "note", {"step": 2})
    memory.write("agent-1", "action", {"step": 3})

    removed = memory.truncate_after("agent-1", marker)

    assert removed == 1
    assert memory.count("agent-1") == 1
    assert memory.count("agent-2") == 1


def test_invalid_json_values_are_rejected():
    memory = EpisodicMemory()

    with pytest.raises(ValueError):
        memory.write("agent-1", "note", {"value": float("nan")})

    assert memory.count("agent-1") == 0


def test_invalid_inputs_are_rejected():
    memory = EpisodicMemory()

    with pytest.raises(ValueError):
        memory.write("", "note", {})

    with pytest.raises(ValueError):
        memory.recent("agent-1", limit=-1)

    with pytest.raises(ValueError):
        memory.truncate_after("agent-1", -1)


def test_unknown_objects_do_not_leak_repr():
    class Secret:
        def __repr__(self):
            return "password=super-secret"

    memory = EpisodicMemory()
    memory.write("agent-1", "note", {"value": Secret()})

    data = memory.recent("agent-1")[0]["data"]
    assert "super-secret" not in json.dumps(data)
    assert data["value"]["_unsupported_type"].endswith(".Secret")


def test_close_prevents_further_operations():
    memory = EpisodicMemory()
    memory.close()

    with pytest.raises(RuntimeError):
        memory.count("agent-1")


def test_file_database_persists_events(tmp_path):
    path = str(tmp_path / "memory.sqlite3")

    with EpisodicMemory(path) as memory:
        memory.write("agent-1", "note", {"value": 42})

    with EpisodicMemory(path) as memory:
        assert memory.recent("agent-1")[0]["data"]["value"] == 42


def test_recent_and_search_never_cross_agents():
    memory = EpisodicMemory()
    memory.write("agent-1", "note", {"secret": "alpha"})
    memory.write("agent-2", "note", {"secret": "beta"})

    assert [e["data"]["secret"] for e in memory.recent("agent-2")] == ["beta"]
    assert memory.search("agent-2", "alpha") == []
    assert len(memory.search("agent-1", "alpha")) == 1


def test_limits_are_respected_and_search_is_newest_first():
    memory = EpisodicMemory()
    for n in (1, 2, 3):
        memory.write("agent-1", "note", {"n": n})

    assert [e["data"]["n"] for e in memory.recent("agent-1", limit=2)] == [2, 3]
    # "note" appears only in the kind, so this also proves search matches on kind
    assert [e["data"]["n"] for e in memory.search("agent-1", "note", limit=2)] == [3, 2]


def test_last_id_is_per_agent_and_zero_when_empty():
    memory = EpisodicMemory()
    first = memory.write("agent-1", "note", {})
    other = memory.write("agent-2", "note", {})

    assert memory.last_id("agent-1") == first
    assert memory.last_id("agent-2") == other
    assert memory.last_id("nobody") == 0


@pytest.mark.parametrize("bad", [True, -1, 1.5])
def test_bad_limits_and_markers_are_rejected(bad):
    memory = EpisodicMemory()

    with pytest.raises(ValueError):
        memory.recent("agent-1", limit=bad)

    with pytest.raises(ValueError):
        memory.truncate_after("agent-1", bad)


def test_wrong_argument_types_are_rejected():
    memory = EpisodicMemory()

    with pytest.raises(ValueError):
        memory.write("agent-1", "note", [1, 2])

    with pytest.raises(ValueError):
        memory.search("agent-1", 5)


def test_search_treats_backslash_as_literal():
    memory = EpisodicMemory()
    memory.write("agent-1", "note", {"text": "C:\\temp"})
    memory.write("agent-1", "note", {"text": "100%"})

    results = memory.search("agent-1", "\\")

    assert [e["data"]["text"] for e in results] == ["C:\\temp"]


def test_events_are_timestamped_in_order():
    memory = EpisodicMemory()
    memory.write("agent-1", "note", {})
    memory.write("agent-1", "note", {})

    first, second = memory.recent("agent-1")

    assert 0 < first["ts"] <= second["ts"]


def test_file_database_creates_missing_folders(tmp_path):
    path = tmp_path / "a" / "b" / "memory.sqlite3"

    with EpisodicMemory(str(path)) as memory:
        memory.write("agent-1", "note", {})

    assert path.exists()
