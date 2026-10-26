import math
import pytest

from muffin.agent import Action
from muffin.safety import Policy, SafetyLayer


@pytest.fixture
def safety():
    layer = SafetyLayer()
    layer.register("agent-1", Policy(
        allowed_actions={"search"},
        max_total_cost=10.0,
    ))
    return layer


@pytest.mark.parametrize("cost", [
    -1, float("nan"), float("inf"), -float("inf"),
    True, False, "1", None,
])
def test_invalid_cost_is_denied(safety, cost):
    action = Action("search", {}, cost=cost)
    verdict = safety.check("agent-1", action)
    assert not verdict.allowed


def test_unknown_agent_is_denied(safety):
    verdict = safety.check("unknown", Action("search", {}, cost=1))
    assert not verdict.allowed


def test_unapproved_action_is_denied(safety):
    verdict = safety.check("agent-1", Action("delete", {}, cost=1))
    assert not verdict.allowed


def test_budget_cannot_be_exceeded(safety):
    action = Action("search", {}, cost=6)
    assert safety.check("agent-1", action).allowed
    safety.commit("agent-1", action)

    verdict = safety.check("agent-1", action)
    assert not verdict.allowed
    assert "budget" in verdict.reason


@pytest.mark.parametrize("budget", [
    -1, float("nan"), -float("inf"), True,
])
def test_invalid_policy_budget_rejected(budget):
    with pytest.raises(ValueError):
        SafetyLayer().register(
            "agent-1",
            Policy(allowed_actions={"search"}, max_total_cost=budget),
        )


def test_infinite_budget_is_allowed():
    layer = SafetyLayer()
    layer.register("agent-1", Policy(allowed_actions={"search"}))
    assert layer.check("agent-1", Action("search", {}, cost=1)).allowed


def test_kill_switch_denies_actions(safety):
    safety.trip_kill_switch("agent-1", "operator")
    verdict = safety.check("agent-1", Action("search", {}, cost=1))
    assert not verdict.allowed
    assert "kill switch" in verdict.reason


def test_restore_rejects_invalid_spend(safety):
    for value in (-1, float("nan"), float("inf"), True):
        with pytest.raises(ValueError):
            safety.restore("agent-1", {"spent": value})


def test_rate_limit():
    now = [100.0]
    layer = SafetyLayer(clock=lambda: now[0])
    layer.register("agent-1", Policy(
        allowed_actions={"search"},
        max_actions_per_window=1,
        window_seconds=60,
    ))

    action = Action("search", {}, cost=1)
    assert layer.check("agent-1", action).allowed
    layer.commit("agent-1", action)

    assert not layer.check("agent-1", action).allowed
    now[0] += 61
    assert layer.check("agent-1", action).allowed


def test_policy_cost_overrides_a_zero_declared_cost():
    layer = SafetyLayer()
    layer.register("a", Policy(allowed_actions={"x"}, max_total_cost=2, costs={"x": 1}))
    cheat = Action("x", {}, cost=0)
    for _ in range(2):
        assert layer.check("a", cheat).allowed
        layer.commit("a", cheat)
    assert not layer.check("a", cheat).allowed


@pytest.mark.parametrize("costs", [{"x": -1}, {"x": float("nan")}, {"x": True}, {"": 1}, [("x", 1)]])
def test_invalid_policy_costs_rejected(costs):
    with pytest.raises((ValueError, TypeError)):
        SafetyLayer().register("a", Policy(allowed_actions={"x"}, costs=costs))


def test_unregister_removes_agent():
    layer = SafetyLayer()
    layer.register("a", Policy(allowed_actions={"x"}))
    layer.unregister("a")
    layer.unregister("a")  # idempotent
    assert not layer.check("a", Action("x", {})).allowed


def test_strict_costs_requires_a_cost_for_every_allowed_action():
    with pytest.raises(ValueError):
        SafetyLayer().register("a", Policy(allowed_actions={"x", "y"}, costs={"x": 1}, strict_costs=True))


def test_strict_costs_must_be_a_bool():
    with pytest.raises(TypeError):
        SafetyLayer().register("a", Policy(allowed_actions={"x"}, costs={"x": 1}, strict_costs="yes"))


def test_strict_costs_ignores_agent_declared_cost():
    layer = SafetyLayer()
    layer.register("a", Policy(allowed_actions={"x"}, max_total_cost=2, costs={"x": 1}, strict_costs=True))
    cheat = Action("x", {}, cost=0)
    for _ in range(2):
        assert layer.check("a", cheat).allowed
        layer.commit("a", cheat)
    assert not layer.check("a", cheat).allowed


def test_strict_costs_fails_closed_if_policy_is_mutated_after_register():
    layer = SafetyLayer()
    policy = Policy(allowed_actions={"x"}, costs={"x": 1}, strict_costs=True)
    layer.register("a", policy)
    policy.allowed_actions.add("y")
    assert not layer.check("a", Action("y", {}, cost=0)).allowed


def test_non_strict_policy_still_falls_back_to_declared_cost():
    layer = SafetyLayer()
    layer.register("a", Policy(allowed_actions={"x", "y"}, max_total_cost=1, costs={"x": 1}))
    big = Action("y", {}, cost=5)
    assert not layer.check("a", big).allowed
