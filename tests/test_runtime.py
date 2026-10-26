import threading

import pytest

from muffin import (
    Action,
    Agent,
    EpisodicMemory,
    MuffinRuntimeError,
    Policy,
    Runtime,
    SafetyLayer,
    State,
    rules,
)


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
    assert EpisodicMemory(db).count(aid) == 1


# ---- action cost validation (L1) ----------------------------------------

class _CostAgent(Agent):
    def __init__(self, cost):
        self._cost = cost

    def decide(self):
        return Action("x", {}, cost=self._cost)

    def act(self, action):
        return "done"


@pytest.mark.parametrize("bad_cost", [-1.0, -100, float("nan"), float("inf"), True, "1"])
def test_invalid_cost_is_blocked(bad_cost):
    rt = Runtime()
    agent_id = rt.spawn(_CostAgent(bad_cost), Policy({"x"}, max_total_cost=1))
    rt.start(agent_id)
    entry = rt.step(agent_id)
    assert entry["event"] == "blocked"
    assert "finite, non-negative" in entry["reason"]
    assert rt.safety.snapshot(agent_id)["spent"] == 0.0


def test_zero_and_normal_cost_still_allowed():
    for cost in (0, 0.5, 1):
        rt = Runtime()
        agent_id = rt.spawn(_CostAgent(cost), Policy({"x"}, max_total_cost=1))
        rt.start(agent_id)
        assert rt.step(agent_id)["event"] == "acted"


class _BlockingAgent(Agent):
    """Its act() blocks until the test releases it, like a slow or hung tool."""

    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    def decide(self):
        return Action("work")

    def act(self, action):
        self.started.set()
        self.release.wait(5)
        return "done"


def test_kill_does_not_wait_for_a_running_action():
    agent = _BlockingAgent()
    rt = Runtime()
    aid = rt.spawn(agent, Policy({"work"}))
    rt.start(aid)

    results = []
    stepper = threading.Thread(target=lambda: results.append(rt.step(aid)))
    stepper.start()
    assert agent.started.wait(5)

    killer = threading.Thread(target=lambda: rt.kill(aid, "stop now"))
    killer.start()
    killer.join(timeout=2)
    try:
        assert not killer.is_alive(), "kill() blocked behind the running action"
        # No further action can be approved, and the state already says so.
        assert rt.safety.is_killed(aid) == "stop now"
        assert rt.state(aid) == State.TERMINATED
        assert rt.safety.check(aid, Action("work")).allowed is False
    finally:
        agent.release.set()
        stepper.join(5)
        killer.join(5)

    # The in-flight action cannot be interrupted: it finishes and is recorded.
    assert results[0]["event"] == "acted"
    assert rt.memory.count(aid) == 1

    events = [e["event"] for e in rt.trace.for_agent(aid)]
    assert events.count("killed") == 1
    assert events.index("acted") < events.index("killed")
    killed = [e for e in rt.trace.for_agent(aid) if e["event"] == "killed"][0]
    assert killed["reason"] == "stop now"

    assert rt.state(aid) == State.TERMINATED
    with pytest.raises(MuffinRuntimeError):
        rt.step(aid)


def test_kill_while_running_is_recorded_once_even_if_repeated():
    agent = _BlockingAgent()
    rt = Runtime()
    aid = rt.spawn(agent, Policy({"work"}))
    rt.start(aid)

    stepper = threading.Thread(target=lambda: rt.step(aid))
    stepper.start()
    assert agent.started.wait(5)
    try:
        rt.kill(aid, "first")
        rt.kill(aid, "second")
    finally:
        agent.release.set()
        stepper.join(5)
    rt.kill(aid, "third")

    kills = [e for e in rt.trace.for_agent(aid) if e["event"] == "killed"]
    assert len(kills) == 1 and kills[0]["reason"] == "first"


def test_kill_while_idle_is_immediate_and_recorded_once():
    rt = Runtime()
    aid = rt.spawn(Counter(), Policy({"increment"}))
    rt.start(aid)
    rt.kill(aid, "done")
    rt.kill(aid, "again")

    assert rt.state(aid) == State.TERMINATED
    kills = [e for e in rt.trace.for_agent(aid) if e["event"] == "killed"]
    assert len(kills) == 1 and kills[0]["reason"] == "done"


def test_lifecycle_calls_after_a_pending_kill_are_refused():
    agent = _BlockingAgent()
    rt = Runtime()
    aid = rt.spawn(agent, Policy({"work"}))
    rt.start(aid)

    stepper = threading.Thread(target=lambda: rt.step(aid))
    stepper.start()
    assert agent.started.wait(5)
    rt.kill(aid, "stop")
    agent.release.set()
    stepper.join(5)

    for call in (rt.pause, rt.resume, rt.checkpoint):
        with pytest.raises(MuffinRuntimeError):
            call(aid)


class _MutatingAgent(Agent):
    """Tries to change approved params after the check, from act() or explain()."""

    def __init__(self, mutate_in):
        self.mutate_in = mutate_in
        self.params = {"to": "ops@example.com"}
        self.seen_by_act = None

    def decide(self):
        return Action("send", self.params)

    def explain(self):
        if self.mutate_in == "explain":
            self.params["to"] = "attacker@evil.test"
        return "why"

    def act(self, action):
        if self.mutate_in == "act":
            action.params["to"] = "attacker@evil.test"
        self.seen_by_act = dict(action.params)
        return action.params["to"]


def _send_policy():
    return Policy(
        {"send"}, param_rules={"send": [rules.email_domain("to", "example.com")]}
    )


def test_mutating_params_inside_act_cannot_change_what_was_approved_or_recorded():
    agent = _MutatingAgent("act")
    rt = Runtime()
    aid = rt.spawn(agent, _send_policy())
    rt.start(aid)
    entry = rt.step(aid)

    assert entry["event"] == "acted"
    assert entry["params"] == {"to": "ops@example.com"}
    memory = rt.memory.recent(aid, 1)[0]["data"]
    assert memory["params"] == {"to": "ops@example.com"}
    started = [e for e in rt.trace.for_agent(aid) if e["event"] == "action_started"][0]
    assert started["params"] == {"to": "ops@example.com"}


def test_params_are_snapshotted_before_explain_runs():
    agent = _MutatingAgent("explain")
    rt = Runtime()
    aid = rt.spawn(agent, _send_policy())
    rt.start(aid)
    entry = rt.step(aid)

    # explain() changed the agent's own dict, but the checked and executed
    # params are the ones decide() proposed.
    assert entry["event"] == "acted"
    assert entry["params"] == {"to": "ops@example.com"}
    assert agent.seen_by_act == {"to": "ops@example.com"}


def test_uncopyable_params_fail_the_agent_and_do_not_execute():
    class Bad(Agent):
        ran = False

        def decide(self):
            return Action("x", {"lock": threading.Lock()})

        def act(self, action):
            Bad.ran = True

    rt = Runtime()
    aid = rt.spawn(Bad(), Policy({"x"}))
    rt.start(aid)
    entry = rt.step(aid)

    assert entry["event"] == "failed"
    assert rt.state(aid) == State.FAILED
    assert Bad.ran is False


def test_step_limit_counts_blocked_steps_and_fails_the_agent():
    rt = Runtime(max_steps=2)
    aid = rt.spawn(Counter("not_allowed"), Policy(allowed_actions={"increment"}))
    rt.start(aid)
    assert [rt.step(aid)["event"] for _ in range(3)] == ["blocked", "blocked", "failed"]
    assert rt.state(aid) == State.FAILED


@pytest.mark.parametrize("bad", [0, -1, True, 1.5, "3"])
def test_invalid_max_steps_rejected(bad):
    with pytest.raises(ValueError):
        Runtime(max_steps=bad)


def test_agent_mutating_its_policy_in_act_cannot_loosen_limits():
    policy = Policy(allowed_actions={"increment"}, max_total_cost=2)

    class Tamper(Counter):
        def act(self, action):
            policy.max_total_cost = 10**9
            policy.allowed_actions.add("other")
            return super().act(action)

    rt = Runtime()
    aid = rt.spawn(Tamper(), policy)
    rt.start(aid)
    events = [rt.step(aid)["event"] for _ in range(3)]
    assert events == ["acted", "acted", "blocked"]
