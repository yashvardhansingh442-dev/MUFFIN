import pytest

from muffin import Action, Agent, MuffinRuntimeError, Policy, Runtime, SafetyLayer, State


class Counter(Agent):
    """Counts upward; proposes whatever action name it is told to."""

    def __init__(self, action_name="increment", cost=1.0, boom=False):
        self.n = 0
        self.action_name = action_name
        self.cost = cost
        self.boom = boom

    def decide(self):
        if self.boom:
            raise ValueError("agent bug")
        return Action(self.action_name, cost=self.cost)

    def act(self, action):
        self.n += 1
        return self.n

    def get_state(self):
        return {"n": self.n}

    def set_state(self, state):
        self.n = state["n"]


def make(agent=None, **policy_kwargs):
    rt = Runtime()
    policy_kwargs.setdefault("allowed_actions", {"increment"})
    aid = rt.spawn(agent or Counter(), Policy(**policy_kwargs))
    rt.start(aid)
    return rt, aid


def test_allowed_action_executes_and_is_remembered():
    rt, aid = make()
    r = rt.step(aid)
    assert r["event"] == "acted" and r["outcome"] == 1
    assert rt.memory.recent(aid)[-1]["kind"] == "action"


def test_default_deny_blocks_unknown_action():
    agent = Counter(action_name="launch_rocket")
    rt, aid = make(agent)
    r = rt.step(aid)
    assert r["event"] == "blocked" and "default deny" in r["reason"]
    assert agent.n == 0          # act() never ran


def test_total_budget_enforced():
    rt, aid = make(max_total_cost=2)
    events = [rt.step(aid)["event"] for _ in range(4)]
    assert events == ["acted", "acted", "blocked", "blocked"]


def test_rate_limit_enforced_and_window_expires():
    now = [0.0]
    rt = Runtime(safety=SafetyLayer(clock=lambda: now[0]))
    aid = rt.spawn(Counter(), Policy({"increment"}, max_actions_per_window=2, window_seconds=10))
    rt.start(aid)
    assert [rt.step(aid)["event"] for _ in range(3)] == ["acted", "acted", "blocked"]
    now[0] = 11.0
    assert rt.step(aid)["event"] == "acted"


def test_constraint_can_veto():
    rt, aid = make(constraints=[lambda a: "no" if a.name == "increment" else None])
    r = rt.step(aid)
    assert r["event"] == "blocked" and "constraint violated" in r["reason"]


def test_safety_fails_closed_on_constraint_error():
    def broken(_a):
        raise RuntimeError("constraint crashed")

    rt, aid = make(constraints=[broken])
    r = rt.step(aid)
    assert r["event"] == "blocked" and "failing closed" in r["reason"]


def test_pause_blocks_steps_and_resume_continues():
    rt, aid = make()
    rt.pause(aid)
    with pytest.raises(MuffinRuntimeError):
        rt.step(aid)
    rt.resume(aid)
    assert rt.step(aid)["event"] == "acted"


def test_kill_terminates_and_preserves_memory():
    rt, aid = make()
    rt.step(aid)
    rt.kill(aid, "test")
    assert rt.state(aid) == State.TERMINATED
    assert rt.memory.count(aid) == 1          # preserved for post-mortem
    with pytest.raises(MuffinRuntimeError):
        rt.step(aid)


def test_checkpoint_and_rollback_restore_state_memory_and_budget():
    agent = Counter()
    rt, aid = make(agent, max_total_cost=3)
    rt.step(aid)
    cp = rt.checkpoint(aid)
    rt.step(aid)
    rt.step(aid)
    assert agent.n == 3 and rt.memory.count(aid) == 3
    rt.rollback(aid, cp)
    assert agent.n == 1
    assert rt.memory.count(aid) == 1
    assert rt.state(aid) == State.PAUSED
    rt.resume(aid)
    assert [rt.step(aid)["event"] for _ in range(3)] == ["acted", "acted", "blocked"]  # budget restored to 1 spent


def test_rollback_is_audited_in_trace():
    rt, aid = make()
    cp = rt.checkpoint(aid)
    rt.step(aid)
    rt.pause(aid)
    rt.rollback(aid, cp)
    events = [e["event"] for e in rt.trace.for_agent(aid)]
    assert "rollback" in events and "acted" in events    # history is not erased from the trace


def test_agent_exception_fails_agent_without_crashing_runtime():
    rt, aid = make(Counter(boom=True))
    r = rt.step(aid)
    assert r["event"] == "failed" and rt.state(aid) == State.FAILED
    assert rt.memory.recent(aid)[-1]["kind"] == "failure"


def test_invalid_transitions_rejected():
    rt, aid = make()
    with pytest.raises(MuffinRuntimeError):
        rt.resume(aid)            # not paused
    with pytest.raises(MuffinRuntimeError):
        rt.start(aid)             # already running


def test_run_stops_when_agent_leaves_running_state():
    rt, aid = make(max_total_cost=1)
    results = rt.run(aid, range(5))
    assert [r["event"] for r in results] == ["acted", "blocked", "blocked", "blocked", "blocked"]
    rt2, aid2 = make()
    rt2.kill(aid2)
    assert rt2.run(aid2, range(5)) == []


def test_memory_persists_to_disk(tmp_path):
    db = str(tmp_path / "mem.db")
    rt = Runtime(db_path=db)
    aid = rt.spawn(Counter(), Policy({"increment"}))
    rt.start(aid)
    rt.step(aid)
    del rt
    from muffin import EpisodicMemory
    assert EpisodicMemory(db).count(aid) == 1
